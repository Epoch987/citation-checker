# app.py

from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
import requests
from werkzeug.exceptions import HTTPException
from collections import OrderedDict
import logging

# 初始化Flask应用
app = Flask(__name__)
CORS(app)  # 启用跨域支持

# 配置日志记录
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# API配置
# ##################################################################
# ▼▼▼ 请在此处输入您的 Scopus API Key ▼▼▼
API_KEY = "75f3b08325f4a8511053a6f3cc2ac2d5"
# ▲▲▲ 请在此处输入您的 Scopus API Key ▲▲▲
# ##################################################################
BASE_URL = "https://api.elsevier.com"

# 核心外语期刊列表
FOREIGN_LANGUAGE_JOURNALS = [
    "Modern Language Journal", "Applied Linguistics", "Language Learning", "TESOL Quarterly",
    "Foreign Language Annals", "Language Teaching Research", "System", "Journal of Second Language Writing"
]

# 自定义异常类
class ApiException(Exception):
    def __init__(self, message, status_code=400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code

# 错误处理
@app.errorhandler(ApiException)
def handle_api_exception(error):
    return jsonify({"success": False, "error": error.message}), error.status_code

@app.errorhandler(Exception)
def handle_generic_exception(error):
    if isinstance(error, HTTPException):
        return error
    logging.error(f"发生未捕获的异常: {error}", exc_info=True)
    return jsonify({"success": False, "error": f"服务器发生内部错误: {str(error)}"}), 500

# Scopus API 请求函数
def make_scopus_request(endpoint, params=None):
    if params is None:
        params = {}
    
    headers = {
        'Accept': 'application/json',
        'X-ELS-APIKey': API_KEY
    }
    
    url = f"{BASE_URL}/{endpoint.lstrip('/')}"
    
    logging.info(f"向 Scopus 发送请求: URL={url}, Params={params}")
    
    try:
        response = requests.get(url, params=params, headers=headers, timeout=40)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.HTTPError as e:
        status_code = e.response.status_code
        try:
            error_details = e.response.json().get('service-error', {}).get('status', {})
            error_text = error_details.get('statusText', f"The requestor is not authorized to access the requested view or fields of the resource.")
        except:
            error_text = e.response.text
        message = f"Scopus API 返回错误 (代码: {status_code})。详情: {error_text}"
        logging.error(f"Scopus API HTTP 错误 ({status_code}): {error_text}")
        raise ApiException(message, status_code)
    except requests.exceptions.RequestException as e:
        logging.error(f"无法连接到 Scopus API: {e}")
        raise ApiException("无法连接到 Scopus API。请检查网络连接。", 503)

# 处理搜索结果
def process_search_results(results):
    articles = []
    if not results:
        return []
        
    for doc in results:
        authors_list = doc.get('author', [])
        author_names = ', '.join([author.get('authname', 'N/A') for author in authors_list])
        
        eid = doc.get('eid')
        if not eid:
            scopus_id = doc.get('dc:identifier', '').replace('SCOPUS_ID:', '')
            if scopus_id.isdigit():
                 eid = f'2-s2.0-{scopus_id}'
        
        # 关键修复：如果找不到有效的EID，则跳过此条目
        if not eid:
            logging.warning(f"无法为文章 '{doc.get('dc:title', 'N/A')}' 找到有效EID，已跳过。")
            continue

        articles.append({
            "eid": eid,
            "doi": doc.get('prism:doi'),
            "title": doc.get('dc:title'),
            "publicationName": doc.get('prism:publicationName'),
            "coverDate": doc.get('prism:coverDate'),
            "url": next((link['@href'] for link in doc.get('link', []) if link.get('@ref') == 'scopus'), '#'),
            "authors": author_names
        })
    
    return articles

# 页面路由
@app.route('/')
def index():
    return render_template('index.html')

# API 端点 - 查教授引用
@app.route('/api/find-author', methods=['POST'])
def find_author_endpoint():
    data = request.get_json()
    last_name, first_name, affiliation = data.get('lastName', '').strip(), data.get('firstName', '').strip(), data.get('affiliation', '').strip()
    
    if not last_name:
        raise ApiException("姓氏为必填项。")
    
    author_name_query = f'"{last_name}, {first_name}"' if first_name else f'"{last_name}"'
    query = f'AUTHOR-NAME({author_name_query})'
    
    if affiliation:
        query += f' AND AFFIL("{affiliation}")'
    
    response_json = make_scopus_request("content/search/scopus", {'query': query, 'count': 10, 'view': 'STANDARD'})
    
    authors = OrderedDict()
    entries = response_json.get('search-results', {}).get('entry', [])
    
    if not entries:
        raise ApiException(f"找不到与作者 '{last_name}, {first_name}' 相关的任何文章。")
    
    for article in entries:
        current_affiliation = article.get('affiliation', [{}])[0].get('affilname', 'N/A')
        for author in article.get('author', []):
            auid = author.get('authid')
            if auid and auid not in authors and last_name.lower() in author.get('authname', '').lower():
                authors[auid] = {
                    "eid": auid,
                    "name": author.get('authname'),
                    "affiliation": current_affiliation,
                }
    
    return jsonify({"success": True, "authors": list(authors.values())[:10]})

@app.route('/api/analyze-professor-citations', methods=['POST'])
def analyze_professor_citations_endpoint():
    data = request.get_json()
    author_id, start_year, end_year, target_journal = data.get('author_id'), data.get('start_year'), data.get('end_year'), data.get('target_journal', '').strip()
    
    if not all([author_id, start_year, end_year, target_journal]):
        raise ApiException("缺少必要参数。")
    
    query = (
        f'AU-ID({author_id}) '
        f'AND PUBYEAR > {int(start_year) - 1} '
        f'AND PUBYEAR < {int(end_year) + 1} '
        f'AND REFSRCTITLE("{target_journal}")'
    )
    
    response_json = make_scopus_request("content/search/scopus", {'query': query, 'count': 20, 'view': 'STANDARD'})
    articles = process_search_results(response_json.get('search-results', {}).get('entry', []))
    
    return jsonify({"success": True, "count": len(articles), "articles": articles})

# API 端点 - 查期刊互引
@app.route('/api/search-journal-citations', methods=['POST'])
def search_journal_citations_endpoint():
    data = request.get_json()
    source_journals_str, target_journal, start_year, end_year = data.get('source_journals', '').strip(), data.get('target_journal', '').strip(), data.get('start_year'), data.get('end_year')
    
    if not all([source_journals_str, target_journal, start_year, end_year]):
        raise ApiException("所有字段均为必填项。")
    
    source_query = " OR ".join([f'SRCTITLE("{j.strip()}")' for j in source_journals_str.split(',') if j.strip()])
    query = f'({source_query}) AND (REFSRCTITLE("{target_journal}")) AND PUBYEAR > {int(start_year) - 1} AND PUBYEAR < {int(end_year) + 1}'
    
    all_articles = []
    start_index = 0
    page_size = 25
    max_results = 500

    while len(all_articles) < max_results:
        params = {'query': query, 'count': page_size, 'start': start_index, 'view': 'STANDARD'}
        response_json = make_scopus_request("content/search/scopus", params)
        results = response_json.get('search-results', {})
        entries = results.get('entry', [])
        if not entries: break
        
        all_articles.extend(process_search_results(entries))
        
        total_results = int(results.get('opensearch:totalResults', 0))
        start_index += len(entries)
        if start_index >= total_results or len(entries) < page_size: break

    logging.info(f"期刊互引查询完成，共获取 {len(all_articles)} 条结果。")
    return jsonify({"success": True, "count": len(all_articles), "articles": all_articles})

# API 端点 - 查文章被引
@app.route('/api/find-article', methods=['POST'])
def find_article_endpoint():
    data = request.get_json()
    identifier = data.get('identifier', '').strip()
    
    if not identifier:
        raise ApiException("请输入文章标题、DOI或EID。")
    
    # 关键修复：对于标题搜索，使用花括号 {} 来避免特殊字符问题
    if '10.' in identifier and '/' in identifier:
        query = f'DOI("{identifier}")'
    elif identifier.startswith('2-s2.0-'):
        query = f'EID("{identifier}")'
    else:
        # 使用 f-string 的双花括号来转义，最终生成 TITLE({identifier})
        query = f'TITLE({{{identifier}}})'
    
    response_json = make_scopus_request("content/search/scopus", {'query': query, 'count': 10, 'view': 'STANDARD'})
    articles = process_search_results(response_json.get('search-results', {}).get('entry', []))
    
    return jsonify({"success": True, "articles": articles})

@app.route('/api/search-cited-by', methods=['POST'])
def search_cited_by_endpoint():
    data = request.get_json()
    eid, start_year, end_year = data.get('eid'), data.get('start_year'), data.get('end_year')
    
    # 关键修复：增加严格的EID验证，防止无效EID进入查询
    if not eid or not isinstance(eid, str) or not eid.startswith('2-s2.0-'):
        raise ApiException(f"提供的EID '{eid}' 无效或缺失。请重新查找并选择文章。")
    
    query_citing = f'REF(EID({eid})) AND PUBYEAR > {int(start_year) - 1} AND PUBYEAR < {int(end_year) + 1}'

    all_citing_articles = []
    start_index = 0
    page_size = 25
    max_results = 500

    while len(all_citing_articles) < max_results:
        params = {'query': query_citing, 'count': page_size, 'start': start_index, 'view': 'STANDARD'}
        citing_data = make_scopus_request("content/search/scopus", params)
        results = citing_data.get('search-results', {})
        entries = results.get('entry', [])
        if not entries: break

        all_citing_articles.extend(process_search_results(entries))
        
        total_results = int(results.get('opensearch:totalResults', 0))
        start_index += len(entries)
        if start_index >= total_results or len(entries) < page_size: break

    logging.info(f"被引文献查询完成，共获取 {len(all_citing_articles)} 条。")

    filtered_citations = [
        article for article in all_citing_articles
        if article.get('publicationName') in FOREIGN_LANGUAGE_JOURNALS
    ]
    
    return jsonify({
        "success": True,
        "total_citations": {"count": len(all_citing_articles), "articles": all_citing_articles},
        "filtered_citations": {"count": len(filtered_citations), "articles": filtered_citations}
    })

if __name__ == '__main__':
    app.run(debug=True, port=5000)
