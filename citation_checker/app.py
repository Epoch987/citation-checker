# app.py (V14 - Scopus最终版：引入智能作者甄别 + 恢复所有功能)

from flask import Flask, render_template, request, jsonify
import requests
import time

app = Flask(__name__)

# --- 全局配置 ---
SCOPUS_API_KEY = "75f3b08325f4a8511053a6f3cc2ac2d5"
BASE_API_URL = "https://api.elsevier.com/content"

# --- 统一的API请求函数 ---
def make_scopus_request(endpoint, query_params=None):
    if query_params is None: query_params = {}
    query_params['apiKey'] = SCOPUS_API_KEY
    headers = {'Accept': 'application/json'}
    url = f"{BASE_API_URL}/{endpoint.lstrip('/')}"
    print(f"向Scopus发送请求: URL={url}, Params={query_params}")
    try:
        response = requests.get(url, params=query_params, headers=headers)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.HTTPError as e:
        error_details = e.response.text
        raise Exception(f"API请求返回错误: {e}. 服务器详情: {error_details}")
    except requests.exceptions.RequestException as e:
        raise Exception(f"网络或请求配置错误: {e}")

# --- 核心逻辑区 ---

def find_author_scopus(author_name):
    """(新)分步查询-1: 查找并智能甄别作者"""
    try:
        query_author_paper = f'AUTHOR-NAME("{author_name}")'
        author_paper_data = make_scopus_request("search/scopus", {'query': query_author_paper, 'count': 25})
        
        author_paper_entries = author_paper_data.get('search-results', {}).get('entry', [])
        if not author_paper_entries:
            return {"success": False, "error": f"在Scopus中找不到与 '{author_name}' 相关的任何文章"}

        candidates = {}
        for paper_entry in author_paper_entries:
            authors_list = paper_entry.get('author', [])
            affiliation_name = paper_entry.get('affiliation', [{}])[0].get('affilname', 'N/A') if paper_entry.get('affiliation') else 'N/A'
            for auth in authors_list:
                auth_id = auth.get('authid')
                if auth_id and auth_id not in candidates:
                    candidates[auth_id] = {"id": auth_id, "name": auth.get('authname'), "affiliation": affiliation_name}
        
        if not candidates:
            return {"success": False, "error": "找到了相关文章，但无法从中提取任何带有唯一ID的作者信息。"}
        
        candidate_list = list(candidates.values())
        
        # 智能判断：如果只有一个候选人，直接返回该作者信息
        if len(candidate_list) == 1:
            author_id = candidate_list[0]['id']
            # 为了获取更全的信息，我们再用ID查一次
            author_profile_data = make_scopus_request(f"author/author_id/{author_id}")
            profile = author_profile_data.get('author-retrieval-response', [{}])[0].get('coredata', {})
            return {"success": True, "author": { "id": author_id, "display_name": profile.get('preferred-name', {}).get('surname', '') + ', ' + profile.get('preferred-name', {}).get('given-name', ''), "document_count": profile.get('document-count', 'N/A'), "cited_by_count": profile.get('cited-by-count', 'N/A')}}
        else:
            # 如果有多个候选人，返回列表让用户选择
            return {"success": True, "candidates": candidate_list}

    except Exception as e:
        return {"success": False, "error": str(e)}

def get_author_works_scopus(author_id, start_year, end_year):
    """分步查询-2: 获取指定作者的文章"""
    try:
        query_works = f'AU-ID({author_id}) AND PUBYEAR > {int(start_year) - 1} AND PUBYEAR < {int(end_year) + 1}'
        works_data = make_scopus_request("search/scopus", {'query': query_works, 'field': 'dc:identifier,dc:title,prism:doi'})
        articles = works_data.get('search-results', {}).get('entry', [])
        return {"success": True, "articles": articles}
    except Exception as e:
        return {"success": False, "error": str(e)}

def analyze_citations_scopus(scopus_ids, target_journal_name):
    """分步查询-3: 分析引用"""
    try:
        citing_articles = []
        for scopus_id_full in scopus_ids:
            scopus_id = scopus_id_full.split(':')[-1]
            time.sleep(0.2)
            try:
                abstract_data = make_scopus_request(f"abstract/scopus_id/{scopus_id}", {'view': 'FULL'})
                article_title = abstract_data.get('full-text-retrieval-response', {}).get('coredata', {}).get('dc:title', 'N/A')
                references = abstract_data.get('full-text-retrieval-response', {}).get('references', {}).get('reference', [])
                if not references: continue
                for ref in references:
                    if ref.get('sourcetitle', '') and target_journal_name.lower() in ref.get('sourcetitle', '').lower():
                        citing_articles.append({"title": article_title, "url": f"https://www.scopus.com/record/display.uri?eid=2-s2.0-{scopus_id}"})
                        break
            except Exception as e: print(f"获取文章 {scopus_id} 的参考文献失败: {e}")
        return {"success": True, "count": len(citing_articles), "articles": citing_articles}
    except Exception as e:
        return {"success": False, "error": str(e)}

def search_journal_citations_scopus(source_journal_name, target_journal_name, start_year, end_year):
    """“查期刊引用”的逻辑"""
    try:
        query_works = f'SRCTITLE("{source_journal_name}") AND PUBYEAR > {int(start_year) - 1} AND PUBYEAR < {int(end_year) + 1}'
        works_data = make_scopus_request("search/scopus", {'query': query_works, 'field': 'dc:identifier'})
        work_ids = [w['dc:identifier'] for w in works_data.get('search-results', {}).get('entry', [])]
        if not work_ids: return {"success": True, "count": 0, "articles": []}
        return analyze_citations_scopus(work_ids, target_journal_name)
    except Exception as e:
        return {"success": False, "error": str(e)}

def search_cited_by_scopus(identifier, start_year, end_year):
    """“查文章被引”的逻辑"""
    try:
        query_work = f'DOI("{identifier}")' if (identifier.startswith('10.') and '/' in identifier) else f'TITLE("{identifier}")'
        work_data = make_scopus_request("search/scopus", {'query': query_work, 'field': 'dc:identifier'})
        if 'search-results' not in work_data or not work_data['search-results'].get('entry'):
            return {"success": False, "error": f"找不到文章: '{identifier}'"}
        original_scopus_id = work_data['search-results']['entry'][0]['dc:identifier'].split(':')[-1]
        query_citing = f'REF({original_scopus_id}) AND PUBYEAR > {int(start_year) - 1} AND PUBYEAR < {int(end_year) + 1}'
        citing_data = make_scopus_request("search/scopus", {'query': query_citing, 'field': 'dc:title,dc:identifier'})
        results = citing_data.get('search-results', {}).get('entry', [])
        articles = [{"title": r.get('dc:title', 'N/A'), "url": f"https://www.scopus.com/record/display.uri?eid=2-s2.0-{r['dc:identifier'].split(':')[-1]}"} for r in results]
        return {"success": True, "count": len(articles), "articles": articles}
    except Exception as e:
        return {"success": False, "error": str(e)}

# --- Flask 路由区 ---
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/find-author')
def find_author_endpoint():
    author_name = request.args.get('author', '').strip()
    if not author_name: return jsonify({"success": False, "error": "作者姓名不能为空。"}), 400
    return jsonify(find_author_scopus(author_name))

@app.route('/api/get-works')
def get_works_endpoint():
    author_id = request.args.get('author_id', '').strip()
    start_year = request.args.get('start_year'); end_year = request.args.get('end_year')
    if not all([author_id, start_year, end_year]): return jsonify({"success": False, "error": "缺少必要参数。"}), 400
    return jsonify(get_author_works_scopus(author_id, start_year, end_year))

@app.route('/api/analyze-citations', methods=['POST'])
def analyze_citations_endpoint():
    data = request.get_json()
    work_ids = data.get('work_ids', []); target_journal = data.get('target_journal', '').strip()
    if not all([work_ids, target_journal]): return jsonify({"success": False, "error": "缺少必要参数。"}), 400
    return jsonify(analyze_citations_scopus(work_ids, target_journal))

@app.route('/search/journal')
def search_journal_endpoint():
    source_journal = request.args.get('source_journal', '').strip(); target_journal = request.args.get('target_journal', '').strip()
    start_year = request.args.get('start_year'); end_year = request.args.get('end_year')
    if not all([source_journal, target_journal, start_year, end_year]): return jsonify({"success": False, "error": "所有字段均为必填项。"}), 400
    return jsonify(search_journal_citations_scopus(source_journal, target_journal, start_year, end_year))

@app.route('/search/cited-by')
def search_cited_by_endpoint():
    identifier = request.args.get('identifier', '').strip()
    start_year = request.args.get('start_year'); end_year = request.args.get('end_year')
    if not all([identifier, start_year, end_year]): return jsonify({"success": False, "error": "所有字段均为必填项。"}), 400
    return jsonify(search_cited_by_scopus(identifier, start_year, end_year))

if __name__ == '__main__':
    app.run(debug=True)