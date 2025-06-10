// static/js/script.js

document.addEventListener('DOMContentLoaded', () => {
    const cJournals = ["Nature", "Science", "Cell", "The Lancet", "The New England Journal of Medicine", "Foreign Language Teaching and Research", "Contemporary Linguistics"];

    const loadingIndicator = document.getElementById('loading');
    const resultsContainer = document.getElementById('results-container');
    
    // --- “查教授引用” (分步) 的元素 ---
    const findAuthorBtn = document.getElementById('find-author-btn');
    const authorNameInput = document.getElementById('author-name-input');
    const stage2Container = document.getElementById('stage-2-select-author');
    const authorCandidatesContainer = document.getElementById('author-candidates-container');
    const stage3Container = document.getElementById('stage-3-analyze');
    const authorInfoDisplay = document.getElementById('author-info-display');
    const worksListContainer = document.getElementById('works-list-container');
    const analyzeCitationsBtn = document.getElementById('analyze-citations-btn');
    
    // --- 其他功能的按钮 ---
    const journalSearchBtn = document.getElementById('search-btn-journal');
    const citedBySearchBtn = document.getElementById('search-btn-cited-by');

    // --- 状态存储 ---
    let currentAuthorId = null;

    // --- 初始化 ---
    new Awesomplete(document.getElementById('target_journal'), { list: cJournals });
    new Awesomplete(document.getElementById('source_journal'), { list: cJournals });
    new Awesomplete(document.getElementById('target_journal_2'), { list: cJournals });

    // --- 事件监听 ---

    // 步骤一：查找教授按钮
    findAuthorBtn.addEventListener('click', () => {
        const authorName = authorNameInput.value.trim();
        if (!authorName) { alert('请输入教授姓名！'); return; }
        
        // 重置所有后续步骤
        stage2Container.style.display = 'none';
        stage3Container.style.display = 'none';
        resultsContainer.innerHTML = '';
        authorCandidatesContainer.innerHTML = '';
        currentAuthorId = null;

        showLoading();
        
        fetch(`/api/find-author?author=${encodeURIComponent(authorName)}`)
            .then(res => res.json()).then(data => {
                hideLoading();
                if (data.success) {
                    // 智能判断：如果直接返回了author，说明只有一个候选人，直接进入第三步
                    if (data.author) {
                        handleAuthorSelection(data.author.id, data.author.display_name);
                    } 
                    // 如果返回了candidates，说明有多个，需要用户选择
                    else if (data.candidates) {
                        renderAuthorCandidates(data.candidates);
                        stage2Container.style.display = 'block';
                    }
                } else {
                    renderFinalResults(data, resultsContainer);
                }
            }).catch(e => handleError(e, resultsContainer));
    });
    
    // 步骤二：当点击选择某个作者后
    authorCandidatesContainer.addEventListener('click', (event) => {
        const targetButton = event.target.closest('button.select-author-btn');
        if (targetButton) {
            document.querySelectorAll('button.select-author-btn').forEach(btn => btn.classList.remove('active'));
            targetButton.classList.add('active');
            handleAuthorSelection(targetButton.dataset.authorId, targetButton.dataset.authorName);
        }
    });
    
    // 步骤三的触发器：当在第三步修改年份后，也重新获取文章
    document.getElementById('author_start_year').addEventListener('change', fetchAndDisplayWorks);
    document.getElementById('author_end_year').addEventListener('change', fetchAndDisplayWorks);

    // 步骤三：分析引用按钮
    analyzeCitationsBtn.addEventListener('click', () => {
        const targetJournal = document.getElementById('target_journal').value.trim();
        if (!currentAuthorId) { alert('请先选择一位学者！'); return; }
        if (!targetJournal) { alert('请输入目标期刊！'); return; }
        
        // 此处不再需要获取文章列表，因为它们仅用于显示，分析时后端会自己获取
        // 我们需要传递作者ID和年份范围给后端，让后端一次性处理
        showLoading(resultsContainer);
        const startYear = document.getElementById('author_start_year').value;
        const endYear = document.getElementById('author_end_year').value;
        
        // 这是对一个新API的调用，该API应该一步完成所有事情
        // 为了简化，我们复用旧的/analyze-citations，但传递更多信息
        // **修正**：我们仍然需要传递work_ids，所以获取works的逻辑是必要的
        // 我们需要先获取works的scopus ID
        const worksParams = new URLSearchParams({ author_id: currentAuthorId, start_year: startYear, end_year: endYear });
        fetch(`/api/get-works?${worksParams.toString()}`)
            .then(res => res.json())
            .then(worksData => {
                if (!worksData.success || worksData.articles.length === 0) {
                    hideLoading();
                    renderFinalResults({success: true, count: 0, articles: []}, resultsContainer);
                    return;
                }
                const work_ids = worksData.articles.map(article => article['dc:identifier']);
                
                return fetch('/api/analyze-citations', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ work_ids: work_ids, target_journal: targetJournal })
                });
            })
            .then(res => res.json())
            .then(data => {
                hideLoading();
                renderFinalResults(data, resultsContainer);
            })
            .catch(e => handleError(e, resultsContainer));
    });

    // 监听：查期刊引用按钮
    journalSearchBtn.addEventListener('click', () => {
        const params = new URLSearchParams({ source_journal: document.getElementById('source_journal').value, target_journal: document.getElementById('target_journal_2').value, start_year: document.getElementById('journal_start_year').value, end_year: document.getElementById('journal_end_year').value });
        if (!params.get('source_journal') || !params.get('target_journal')) return alert('源期刊和目标期刊不能为空！');
        fetchAPI('/search/journal', params, resultsContainer);
    });
    
    // 监听：查文章被引按钮
    citedBySearchBtn.addEventListener('click', () => {
        const params = new URLSearchParams({ identifier: document.getElementById('article_identifier').value, start_year: document.getElementById('cited_start_year').value, end_year: document.getElementById('cited_end_year').value });
        if (!params.get('identifier')) return alert('文章DOI或标题不能为空！');
        fetchAPI('/search/cited-by', params, resultsContainer);
    });

    // --- 核心功能函数 ---
    
    function handleAuthorSelection(authorId, authorName) {
        currentAuthorId = authorId;
        stage2Container.style.display = 'none'; // 隐藏选择列表
        authorInfoDisplay.innerHTML = `已选定学者: <strong>${authorName}</strong> (ID: ${currentAuthorId})。`;
        stage3Container.style.display = 'block'; // 显示最终分析步骤
        resultsContainer.innerHTML = '';
        fetchAndDisplayWorks(); // 自动加载文章列表
    }

    function fetchAndDisplayWorks() {
        if (!currentAuthorId) return;
        const startYear = document.getElementById('author_start_year').value;
        const endYear = document.getElementById('author_end_year').value;
        worksListContainer.innerHTML = '<p class="text-center text-muted">正在加载文章列表...</p>';
        const params = new URLSearchParams({ author_id: currentAuthorId, start_year: startYear, end_year: endYear });
        fetch(`/api/get-works?${params.toString()}`)
            .then(res => res.json()).then(data => {
                if (data.success && data.articles.length > 0) {
                    let worksHtml = '<ul class="list-group list-group-flush">';
                    data.articles.forEach(article => {
                        const doi = article['prism:doi'];
                        const url = doi ? `https://doi.org/${doi}` : `https://www.scopus.com/record/display.uri?eid=2-s2.0-${article['dc:identifier'].split(':')[1]}`;
                        worksHtml += `<li class="list-group-item small"><a href="${url}" target="_blank" rel="noopener noreferrer">${article['dc:title']}</a></li>`;
                    });
                    worksHtml += '</ul>';
                    worksListContainer.innerHTML = worksHtml;
                } else {
                    worksListContainer.innerHTML = '<p class="text-center text-muted">在该时间范围内未找到文章。</p>';
                }
            }).catch(e => handleError(e, worksListContainer));
    }

    function renderAuthorCandidates(candidates) {
        let html = '<div class="list-group">';
        candidates.forEach(candidate => {
            html += `<button type="button" class="list-group-item list-group-item-action select-author-btn" data-author-id="${candidate.id}" data-author-name="${candidate.name}">
                        <strong>${candidate.name}</strong><br>
                        <small class="text-muted">ID: ${candidate.id} | 最近所属机构: ${candidate.affiliation}</small>
                     </button>`;
        });
        html += '</div>';
        authorCandidatesContainer.innerHTML = html;
    }
    
    function fetchAPI(endpoint, params, resultElement) {
        showLoading(resultElement);
        fetch(`${endpoint}?${params.toString()}`)
            .then(response => response.json())
            .then(data => { hideLoading(); renderFinalResults(data, resultElement); })
            .catch(e => handleError(e, resultElement));
    }

    function renderFinalResults(data, element) {
        if (data.success) {
            let html = `<div class="alert alert-success">查询成功！共找到 <strong>${data.count}</strong> 条相关引用。</div>`;
            if (data.count > 0 && data.articles) {
                html += '<h5>具体文章列表:</h5><ul class="list-group list-group-flush">';
                data.articles.forEach(article => {
                    const url = article.url && article.url.startsWith('http') ? article.url : '#';
                    const link = url !== '#' ? `href="${url}" target="_blank" rel="noopener noreferrer"` : 'href="#" class="text-muted"';
                    const title = article.title || '（标题不可用）';
                    html += `<li class="list-group-item"><a ${link}>${title}</a></li>`;
                });
                html += '</ul>';
            }
            element.innerHTML = html;
        } else {
            element.innerHTML = `<div class="alert alert-danger">检索失败: ${data.error}</div>`;
        }
    }
    
    function showLoading(element) {
        if(element) element.innerHTML = '';
        resultsContainer.innerHTML = ''; // 总是清空主结果区
        loadingIndicator.style.display = 'block';
    }
    function hideLoading() { loadingIndicator.style.display = 'none'; }
    function handleError(error, element) {
        hideLoading();
        const targetElement = element || resultsContainer;
        targetElement.innerHTML = `<div class="alert alert-danger">发生网络错误，请检查后端服务是否开启，或稍后重试。</div>`;
        console.error('Error:', error);
    }
});