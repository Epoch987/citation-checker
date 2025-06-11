# --- START OF FILE app.py (FULL REPLACEMENT WITH AUTH SYSTEM) ---

from flask import Flask, render_template, request, jsonify, session, redirect, url_for, flash
from flask_cors import CORS
import requests
from werkzeug.exceptions import HTTPException
import logging
import re
import os
import json

app = Flask(__name__)
# 警告：在生产环境中请务必使用更复杂且保密的密钥！
app.secret_key = 'internal-testing-secret-key-2025888'
CORS(app)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- 用户认证配置 ---
USERS_FILE = 'users.json'
INVITATION_CODE = '2025888'

def load_users():
    if not os.path.exists(USERS_FILE):
        with open(USERS_FILE, 'w') as f:
            json.dump({}, f)
        return {}
    with open(USERS_FILE, 'r') as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return {}

def save_user(email, password):
    users = load_users()
    # 警告：密码以明文形式存储，仅适用于内部测试。
    users[email] = password
    with open(USERS_FILE, 'w') as f:
        json.dump(users, f, indent=4)

# --- 认证路由 ---

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        users = load_users()
        if email in users and users[email] == password:
            session['user_email'] = email
            flash('登录成功！', 'success')
            return redirect(url_for('welcome'))
        else:
            flash('邮箱或密码错误。', 'error')
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        invite_code = request.form.get('invite_code')
        email = request.form.get('email')
        password = request.form.get('password')

        if invite_code != INVITATION_CODE:
            flash('无效的邀请码。', 'error')
            return redirect(url_for('register'))

        users = load_users()
        if email in users:
            flash('该邮箱已被注册。', 'error')
            return redirect(url_for('register'))

        if not email or not password:
            flash('邮箱和密码不能为空。', 'error')
            return redirect(url_for('register'))

        save_user(email, password)
        session['user_email'] = email
        flash('注册成功！', 'success')
        return redirect(url_for('welcome'))
    return render_template('register.html')

# [FIX] Added the missing /logout route
@app.route('/logout')
def logout():
    session.pop('user_email', None)
    flash('您已成功登出。', 'success')
    return redirect(url_for('login'))


# --- 核心API和页面路由 ---

SCOPUS_API_KEY = "da6f08ebbd87aba16ec3f2cb78f02d23"
SCOPUS_BASE_URL = "https://api.elsevier.com"
OPENALEX_BASE_URL = "https://api.openalex.org"
OPENALEX_MAILTO = "library@your-institution.edu"

class ApiException(Exception):
    def __init__(self, message, status_code=400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code

@app.errorhandler(ApiException)
def handle_api_exception(error): return jsonify({"success": False, "error": error.message}), error.status_code

@app.errorhandler(Exception)
def handle_generic_exception(error):
    if isinstance(error, HTTPException): return error
    logging.error(f"发生未捕-捕获的异常: {error}", exc_info=True)
    return jsonify({"success": False, "error": f"服务器发生内部错误: {str(error)}"}), 500

def make_scopus_request(endpoint, params=None):
    params = params or {}
    headers = {'Accept': 'application/json', 'X-ELS-APIKey': SCOPUS_API_KEY}
    url = f"{SCOPUS_BASE_URL}/{endpoint.lstrip('/')}"
    logging.info(f"向 Scopus 发送请求: URL={url}, Params={params}")
    try:
        response = requests.get(url, params=params, headers=headers, timeout=40)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.HTTPError as e:
        status_code = e.response.status_code
        message = f"Scopus API 请求失败 (代码: {status_code})。"
        if status_code == 401: message = "API密钥权限不足。请尝试使用OpenAlex。"
        elif status_code == 400: message = "API查询语法错误，请检查输入内容。"
        else:
            try: error_details = e.response.json(); error_text = error_details.get('service-error',{}).get('status',{}).get('statusText'); message += f" 详情: {error_text}" if error_text else ""
            except: pass
        logging.error(f"Scopus API HTTP 错误: {message}")
        raise ApiException(message, status_code)
    except requests.exceptions.RequestException as e:
        raise ApiException("无法连接到 Scopus API。", 503)

def make_openalex_request(endpoint, params=None):
    params = params or {}
    if OPENALEX_MAILTO: params['mailto'] = OPENALEX_MAILTO
    headers = {'User-Agent': 'CitationAnalysisPlatform/1.7'}
    url = f"{OPENALEX_BASE_URL}/{endpoint.lstrip('/')}"
    logging.info(f"向 OpenAlex 发送请求: URL={url}, Params={params}")
    try:
        response = requests.get(url, params=params, headers=headers, timeout=40)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.HTTPError as e:
        status_code = e.response.status_code
        message = f"OpenAlex API 请求失败 (代码: {status_code})。"
        try: error_details = e.response.json(); error_msg = error_details.get('message', str(error_details)); message += f" 详情: {error_msg}"
        except: pass
        logging.error(f"OpenAlex API HTTP 错误: {message}")
        raise ApiException(message, status_code)
    except requests.exceptions.RequestException as e:
        raise ApiException("无法连接到 OpenAlex API。", 503)

def reconstruct_abstract(inverted_index):
    if not inverted_index: return "摘要不可用。"
    try:
        abstract_length = inverted_index['length']; index = inverted_index['index']; abstract_list = [''] * abstract_length
        for word, positions in index.items():
            for pos in positions: abstract_list[pos] = word
        return ' '.join(filter(None, abstract_list))
    except (TypeError, KeyError, IndexError): return "摘要解析失败。"

def process_article_results(results, database):
    return process_scopus_article_results(results) if database == 'scopus' else process_openalex_article_results(results)

def process_scopus_article_results(results):
    articles = [];
    for doc in results:
        eid = doc.get('eid', doc.get('dc:identifier', '').replace('SCOPUS_ID:', '2-s2.0-'));
        if not eid.startswith('2-s2.0-'): continue
        articles.append({"id": f"scopus:{eid}", "doi": doc.get('prism:doi'), "title": doc.get('dc:title'), "publicationName": doc.get('prism:publicationName'), "coverDate": doc.get('prism:coverDate'), "url": next((link['@href'] for link in doc.get('link', []) if link.get('@ref') == 'scopus'), '#'), "authors": ', '.join([a.get('authname', 'N/A') for a in doc.get('author', [])]), "citedby_count": int(doc.get('citedby-count', 0)), "abstract": doc.get('dc:description', '摘要不可用。')});
    return articles

def process_openalex_article_results(results):
    articles = [];
    for doc in results:
        articles.append({"id": doc.get('id', '').replace('https://openalex.org/', 'openalex:'), "doi": doc.get('doi', '').replace('https://doi.org/', '') if doc.get('doi') else None, "title": doc.get('display_name'), "publicationName": doc.get('primary_location', {}).get('source', {}).get('display_name') if doc.get('primary_location', {}).get('source') else 'N/A', "coverDate": doc.get('publication_date'), "url": doc.get('id', '#'), "authors": ', '.join([auth['author'].get('display_name', 'N/A') for auth in doc.get('authorships', [])]), "citedby_count": int(doc.get('cited_by_count', 0)), "abstract": reconstruct_abstract(doc.get('abstract_inverted_index'))});
    return articles

def process_author_results(results, database):
    return process_scopus_author_results(results) if database == 'scopus' else process_openalex_author_results(results)

def process_scopus_author_results(results):
    authors = []
    for author_data in results:
        profile = author_data.get('author-profile', {}); coredata = author_data.get('coredata', author_data)
        name_obj = coredata.get('preferred-name', {}); name = f"{name_obj.get('given-name', '')} {name_obj.get('surname', '')}".strip() or coredata.get('name') or coredata.get('authname')
        author_id_raw = coredata.get('dc:identifier', 'AUTHOR_ID:').split(':')[-1] or coredata.get('authid')
        affiliation_doc = (profile.get('affiliation-current', {}).get('affiliation', {}) or {}).get('ip-doc', {})
        affiliation = affiliation_doc.get('afdispname') if affiliation_doc else 'N/A'
        authors.append({"author_id": author_id_raw, "name": name, "orcid": coredata.get('orcid'), "affiliation": affiliation, "url": next((link['@href'] for link in coredata.get('link', []) if link.get('@ref') == 'self'), f"https://www.scopus.com/authid/detail.uri?authorId={author_id_raw}"), "cited_by_count": int(coredata.get('cited-by-count', 0)), "works_count": coredata.get('document-count', 'N/A'), "h_index": profile.get('h-index'), "i10_index": None, "x_concepts": "N/A", "country_code": "N/A", "cited_by_count_2yr": None, "works_year_range": "N/A"})
    return authors

def process_openalex_author_results(results):
    authors = []
    for author in results:
        author_id_raw = author.get('id', 'https://openalex.org/A0').split('/')[-1]
        concepts = [c.get('display_name') for c in author.get('x_concepts', [])[:2] if c.get('display_name')]
        summary_stats = author.get('summary_stats', {})
        last_known_institution = author.get('last_known_institution', {})
        years = [item['year'] for item in author.get('counts_by_year', []) if item.get('year')]
        year_range = f"{min(years)}–{max(years)}" if years else "N/A"
        authors.append({"author_id": author_id_raw, "name": author.get('display_name'), "orcid": author.get('orcid', '').replace('https://orcid.org/', '') if author.get('orcid') else None, "affiliation": last_known_institution.get('display_name') if last_known_institution else 'N/A', "country_code": last_known_institution.get('country_code'), "url": author.get('id', '#'), "cited_by_count": int(author.get('cited_by_count', 0)), "works_count": author.get('works_count', 0), "h_index": summary_stats.get('h_index'), "i10_index": summary_stats.get('i10_index'), "cited_by_count_2yr": summary_stats.get('2yr_cited_by_count'), "works_year_range": year_range, "x_concepts": ', '.join(concepts) if concepts else '领域未知'})
    return authors

def run_paginated_query(database, query_builder_func, max_results=500):
    all_articles = []; page_limit = 20
    if database == 'scopus':
        start_index, page_size = 0, 25
        while len(all_articles) < max_results and page_limit > 0:
            page_limit -= 1
            params = {'query': query_builder_func(), 'start': start_index, 'count': page_size, 'view': 'STANDARD'}
            response = make_scopus_request("content/search/scopus", params)
            entries = response.get('search-results', {}).get('entry', [])
            if not entries: break
            all_articles.extend(process_article_results(entries, database))
            total_results = int(response.get('search-results', {}).get('opensearch:totalResults', 0))
            if len(all_articles) >= total_results or len(all_articles) >= 5000: break
            start_index += page_size
    elif database == 'openalex':
        page, per_page = 1, 25
        while len(all_articles) < max_results and page_limit > 0:
            page_limit -= 1
            params = query_builder_func()
            params.update({'per-page': per_page, 'page': page})
            response = make_openalex_request("works", params)
            entries = response.get('results', [])
            if not entries: break
            all_articles.extend(process_article_results(entries, database))
            total_results = response.get('meta', {}).get('count', 0)
            if len(all_articles) >= total_results: break
            page += 1
    return all_articles[:max_results]

# [FIX] Added protection to page routes
@app.route('/')
def welcome():
    if 'user_email' not in session:
        return redirect(url_for('login'))
    return render_template('welcome.html')

@app.route('/tool')
def tool():
    if 'user_email' not in session:
        return redirect(url_for('login'))
    return render_template('index.html')

# [FIX] Added protection to API routes
@app.route('/api/search-author-by-name', methods=['POST'])
def search_author_by_name_endpoint():
    if 'user_email' not in session: return jsonify({"success": False, "error": "Unauthorized"}), 401
    data = request.get_json(); name = data.get('name', '').strip(); database = data.get('database', 'scopus')
    if not name: raise ApiException("作者姓名是必填项。")
    if database == 'scopus':
        response = make_scopus_request("content/search/author", {'query': f'AUTHOR-NAME("{name}")', 'count': 25})
    else: # openalex
        response = make_openalex_request("authors", {'search': name, 'per-page': 25})
    authors = process_author_results(response.get('results', []) or response.get('search-results', {}).get('entry', []), database)
    return jsonify({"success": True, "authors": authors})

@app.route('/api/get-author-by-orcid', methods=['POST'])
def get_author_by_orcid_endpoint():
    if 'user_email' not in session: return jsonify({"success": False, "error": "Unauthorized"}), 401
    data = request.get_json(); orcid = data.get('orcid', '').strip(); database = data.get('database', 'scopus')
    if not orcid: raise ApiException("ORCID 是必填项。")
    if database == 'openalex':
        response = make_openalex_request("authors", {'filter': f"orcid:{orcid}"})
        author_details = process_openalex_author_results(response.get('results', []))[0] if response.get('results') else None
        if not author_details: raise ApiException(f"在 OpenAlex 中未找到 ORCID 为 {orcid} 的作者。")
    else: # Scopus
        article_search_response = make_scopus_request("content/search/scopus", {'query': f'ORCID({orcid})', 'count': 1})
        entries = article_search_response.get('search-results', {}).get('entry', [])
        if not entries: raise ApiException(f"未找到与 ORCID {orcid} 关联的 Scopus 文章。")
        found_author_in_article = next((a for a in entries[0].get('author', []) if a.get('orcid') == orcid), None)
        if not found_author_in_article: raise ApiException("在文章中无法匹配到指定的 ORCID。")
        author_id = found_author_in_article.get('authid')
        if not author_id: raise ApiException("从文章中无法解析出作者 Scopus ID。")
        author_profile_response = make_scopus_request(f"author/retrieve/{author_id}", {'view': 'METRICS'})
        author_data = author_profile_response.get('author-retrieval-response', [])
        if not author_data: raise ApiException(f"通过 AU-ID {author_id} 获取作者详情失败。")
        author_details = process_scopus_author_results(author_data)[0]
    return jsonify({"success": True, "author": author_details})

@app.route('/api/get-author-works', methods=['POST'])
def get_author_works_endpoint():
    if 'user_email' not in session: return jsonify({"success": False, "error": "Unauthorized"}), 401
    data = request.get_json(); author_id = data.get('author_id'); database = data.get('database', 'scopus')
    if database == 'scopus':
        response = make_scopus_request("content/search/scopus", {'query': f'AU-ID({author_id})', 'count': 25, 'view': 'STANDARD', 'sort': 'citedby-count'})
    else: # openalex
        response = make_openalex_request("works", {'filter': f'authorships.author.id:{author_id}', 'per-page': 25, 'sort': 'cited_by_count:desc'})
    articles = process_article_results(response.get('results', []) or response.get('search-results', {}).get('entry', []), database)
    return jsonify({"success": True, "articles": articles})

@app.route('/api/search-journal-citations', methods=['POST'])
def search_journal_citations_endpoint():
    if 'user_email' not in session: return jsonify({"success": False, "error": "Unauthorized"}), 401
    data = request.get_json(); database = data.get('database', 'scopus')
    if not all([data.get('source_journals', ''), data.get('target_journal', '')]): raise ApiException("源期刊和目标期刊均为必填项。")
    
    def scopus_query_builder():
        source_titles = [f'SRCTITLE("{title.strip()}")' for title in data['source_journals'].split(',') if title.strip()]
        target_journal = f'REFSRCTITLE("{data["target_journal"].strip()}")'
        return f"({ ' OR '.join(source_titles) }) AND {target_journal} AND PUBYEAR > {int(data['start_year']) - 1} AND PUBYEAR < {int(data['end_year']) + 1}"

    def openalex_query_builder():
        source_journals_str = " OR ".join([f'"{name.strip()}"' for name in data['source_journals'].split(',') if name.strip()])
        target_journal_str = f'"{data["target_journal"].strip()}"'
        search_query = f'({source_journals_str}) AND ({target_journal_str})'
        filters = [ f"publication_year:{data['start_year']}-{data['end_year']}" ]
        return {'filter': ','.join(filters), 'search': search_query}

    articles = run_paginated_query(database, scopus_query_builder if database == 'scopus' else openalex_query_builder)
    return jsonify({"success": True, "count": len(articles), "articles": articles})

@app.route('/api/find-article', methods=['POST'])
def find_article_endpoint():
    if 'user_email' not in session: return jsonify({"success": False, "error": "Unauthorized"}), 401
    data = request.get_json(); identifier = data.get('identifier', '').strip(); database = data.get('database', 'scopus')
    if not identifier: raise ApiException("请输入文章标识。")
    doi_match = re.search(r'(10\.\d{4,9}/[-._;()/:A-Z0-9]+)', identifier, re.IGNORECASE)
    if database == 'scopus':
        query = f'DOI("{doi_match.group(1).rstrip(".,; ")}")' if doi_match else f'TITLE({{{identifier}}})'
        response = make_scopus_request("content/search/scopus", {'query': query, 'count': 10, 'view': 'STANDARD'})
    else: # openalex
        params = {'per-page': 10}
        if doi_match:
             params['filter'] = f"doi:{doi_match.group(1).rstrip('.,; ')}"
        else:
             params['search'] = identifier
        response = make_openalex_request("works", params=params)
    articles = process_article_results(response.get('results', []) or response.get('search-results', {}).get('entry', []), database)
    return jsonify({"success": True, "articles": articles})

if __name__ == '__main__':
    app.run(debug=True, port=5000)

# --- END OF FILE app.py ---
