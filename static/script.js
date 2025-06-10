document.addEventListener('DOMContentLoaded', () => {
    let currentAuthorId = null, currentAuthorName = null, selectedArticle = null;
    const resultsContainer = document.getElementById('results-container');
    
    // 获取DOM元素
    const authorStage1 = document.getElementById('author-stage-1'), 
          authorStage2 = document.getElementById('author-stage-2'), 
          authorStage3 = document.getElementById('author-stage-3');
          
    const findAuthorBtn = document.getElementById('find-author-btn'), 
          authorCandidatesContainer = document.getElementById('author-candidates-container'), 
          analyzeProfCitationsBtn = document.getElementById('analyze-prof-citations-btn'), 
          backToAuthorSearchBtn = document.getElementById('back-to-author-search');
          
    const searchJournalCitationsBtn = document.getElementById('search-journal-citations-btn');
    
    const citedByStage1 = document.getElementById('cited-by-stage-1'), 
          citedByStage2 = document.getElementById('cited-by-stage-2'), 
          citedByStage3 = document.getElementById('cited-by-stage-3');
          
    const findArticleBtn = document.getElementById('find-article-btn'), 
          articleCandidatesContainer = document.getElementById('article-candidates-container'), 
          searchCitedByBtn = document.getElementById('search-cited-by-btn'), 
          backToArticleSearchBtn = document.getElementById('back-to-article-search');
    
    // 初始化标签切换功能
    document.querySelectorAll('.tab-button').forEach(button => {
        button.addEventListener('click', () => {
            document.querySelectorAll('.tab-button').forEach(btn => btn.classList.remove('active'));
            document.querySelectorAll('.tab-pane').forEach(pane => pane.classList.remove('active'));
            
            button.classList.add('active');
            document.getElementById(button.getAttribute('data-target')).classList.add('active');
            
            resultsContainer.innerHTML = ''; 
            resetAuthorSearch(); 
            resetArticleSearch();
        });
    });
    
    // 封装API请求
    async function fetchAPI(endpoint, body) {
        showLoading();
        
        try {
            const response = await fetch(`http://localhost:5000${endpoint}`, { 
                method: 'POST', 
                headers: { 'Content-Type': 'application/json' }, 
                body: JSON.stringify(body) 
            });
            
            const data = await response.json();
            
            if (!response.ok || !data.success) {
                throw new Error(data.error || `HTTP error! status: ${response.status}`);
            }
            
            resultsContainer.innerHTML = '';
            return data;
        } catch (error) {
            console.error('API Fetch Error:', error);
            showError(error.message);
            return null;
        }
    }
    
    // 重置作者搜索状态
    function resetAuthorSearch() { 
        currentAuthorId = null; 
        currentAuthorName = null; 
        authorStage1.style.display = 'block'; 
        authorStage2.style.display = 'none'; 
        authorStage3.style.display = 'none'; 
    }
    
    // 查找作者按钮点击事件
    findAuthorBtn.addEventListener('click', async () => {
        const lastName = document.getElementById('author-lastname').value.trim();
        
        if (!lastName) { 
            showError("请输入教授的姓氏。"); 
            return; 
        }
        
        const data = await fetchAPI('/api/find-author', { 
            lastName, 
            firstName: document.getElementById('author-firstname').value.trim(), 
            affiliation: document.getElementById('author-affiliation').value.trim() 
        });
        
        if (data) { 
            authorStage1.style.display = 'none'; 
            authorStage2.style.display = 'block'; 
            renderAuthorCandidates(data.authors); 
        }
    });
    
    // 返回搜索按钮点击事件
    backToAuthorSearchBtn.addEventListener('click', () => { 
        resetAuthorSearch(); 
        resultsContainer.innerHTML = ''; 
    });
    
    // 渲染作者候选列表
    function renderAuthorCandidates(authors) {
        if (authors.length === 0) {
            authorCandidatesContainer.innerHTML = `
                <div class="info-message">未找到匹配的作者。</div>
                <button class="btn-secondary" id="back-to-stage1-author">返回搜索</button>
            `;
            
            document.getElementById('back-to-stage1-author').addEventListener('click', resetAuthorSearch); 
            return;
        }
        
        authorCandidatesContainer.innerHTML = authors.map((author, index) => {
            return `
                <label class="author-choice" for="author-${index}">
                    <input type="radio" id="author-${index}" name="author-candidate" value="${author.eid}" data-name="${author.name}">
                    <div class="author-choice-content">
                        <strong>${author.name}</strong>
                        <div class="meta">${author.affiliation || '无当前机构信息'}</div>
                    </div>
                </label>`;
        }).join('');
        
        document.querySelectorAll('input[name="author-candidate"]').forEach(radio => {
            radio.addEventListener('change', (event) => {
                currentAuthorId = event.target.value; 
                currentAuthorName = event.target.dataset.name;
                document.getElementById('selected-author-name').textContent = currentAuthorName;
                authorStage2.style.display = 'none'; 
                authorStage3.style.display = 'block';
            });
        });
    }
    
    // 分析教授引用按钮点击事件
    analyzeProfCitationsBtn.addEventListener('click', async () => {
        const targetJournal = document.getElementById('prof-target-journal').value.trim();
        
        if (!targetJournal) { 
            showError("请输入目标期刊名称。"); 
            return; 
        }
        
        const startYear = document.getElementById('prof-start-year').value, 
              endYear = document.getElementById('prof-end-year').value;
              
        const data = await fetchAPI('/api/analyze-professor-citations', { 
            author_id: currentAuthorId, 
            start_year: startYear, 
            end_year: endYear, 
            target_journal: targetJournal 
        });
        
        if (data) {
            renderSimpleResults(data, `在 ${startYear}-${endYear} 年间，${currentAuthorName} 发表的文章中引用了 <strong>${targetJournal}</strong> 共 <strong>${data.count}</strong> 次。`);
        }
    });
    
    // 检索期刊互引按钮点击事件
    searchJournalCitationsBtn.addEventListener('click', async () => {
        const sourceJournals = document.getElementById('source-journals').value.trim(), 
              targetJournal = document.getElementById('journal-target-journal').value.trim();
              
        if (!sourceJournals || !targetJournal) { 
            showError("源期刊和目标期刊均为必填项。"); 
            return; 
        }
        
        const startYear = document.getElementById('journal-start-year').value, 
              endYear = document.getElementById('journal-end-year').value;
              
        const data = await fetchAPI('/api/search-journal-citations', { 
            source_journals: sourceJournals, 
            target_journal: targetJournal, 
            start_year: startYear, 
            end_year: endYear 
        });
        
        if (data) {
            renderSimpleResults(data, `在 ${startYear}-${endYear} 年间，源期刊共引用了 <strong>${targetJournal}</strong> ${data.count} 次。`);
        }
    });
    
    // 重置文章搜索状态
    function resetArticleSearch() { 
        selectedArticle = null; 
        citedByStage1.style.display = 'block'; 
        citedByStage2.style.display = 'none'; 
        citedByStage3.style.display = 'none'; 
    }
    
    // 查找文章按钮点击事件
    findArticleBtn.addEventListener('click', async () => {
        const identifier = document.getElementById('article-identifier').value.trim();
        
        if (!identifier) { 
            showError("请输入文章标题、DOI或EID。"); 
            return; 
        }
        
        const data = await fetchAPI('/api/find-article', { identifier });
        
        if (data) { 
            citedByStage1.style.display = 'none'; 
            citedByStage2.style.display = 'block'; 
            renderArticleCandidates(data.articles); 
        }
    });
    
    // 返回搜索按钮点击事件
    backToArticleSearchBtn.addEventListener('click', () => { 
        resetArticleSearch(); 
        resultsContainer.innerHTML = ''; 
    });
    
    // 渲染文章候选列表
    function renderArticleCandidates(articles) {
        if (articles.length === 0) {
            articleCandidatesContainer.innerHTML = `
                <div class="info-message">未找到匹配的文章。</div>
                <button class="btn-secondary" id="back-to-stage1-article">返回搜索</button>
            `;
            
            document.getElementById('back-to-stage1-article').addEventListener('click', resetArticleSearch); 
            return;
        }
        
        articleCandidatesContainer.innerHTML = articles.map((article, index) => {
            const articleData = escape(JSON.stringify({ eid: article.eid, title: article.title }));
            
            return `
                <label class="author-choice" for="article-${index}">
                    <input type="radio" id="article-${index}" name="article-candidate" value="${articleData}">
                    <div class="author-choice-content">
                        <strong>${article.title || '无标题'}</strong>
                        <div class="meta">${article.authors || '无作者信息'}</div>
                        <div class="meta">${article.publicationName || '无期刊信息'} (${article.coverDate ? article.coverDate.substring(0, 4) : 'N/A'})</div>
                        <div class="meta">DOI: ${article.doi || 'N/A'}</div>
                    </div>
                </label>`;
        }).join('');
        
        document.querySelectorAll('input[name="article-candidate"]').forEach(radio => {
            radio.addEventListener('change', (event) => {
                selectedArticle = JSON.parse(unescape(event.target.value));
                document.getElementById('selected-article-title').textContent = selectedArticle.title;
                citedByStage2.style.display = 'none'; 
                citedByStage3.style.display = 'block';
            });
        });
    }
    
    // 搜索被引按钮点击事件
    searchCitedByBtn.addEventListener('click', async () => {
        if (!selectedArticle) { 
            showError("请先选择一篇文章。"); 
            return; 
        }
        
        const startYear = document.getElementById('cited-start-year').value, 
              endYear = document.getElementById('cited-end-year').value;
              
        const data = await fetchAPI('/api/search-cited-by', { 
            eid: selectedArticle.eid, 
            start_year: startYear, 
            end_year: endYear 
        });
        
        if (data) {
            renderCitedByResults(data, startYear, endYear);
        }
    });
    
    // 简单结果显示
    function renderSimpleResults(data, summaryText) {
        let html = `<div class="result-summary"><p>${summaryText}</p></div>`;
        
        if (data.count > 0 && data.articles) {
            html += data.articles.map(article => createArticleCard(article)).join('');
        } else if (data.count === 0) {
            html += `<div class="info-message">没有找到符合条件的引用。</div>`;
        }
        
        resultsContainer.innerHTML = html;
        resultsContainer.scrollIntoView({ behavior: 'smooth' });
    }
    
    // 被引结果显示
    function renderCitedByResults(data, startYear, endYear) {
        let summaryHtml = `在 ${startYear}-${endYear} 年间，该文章总被引 <strong>${data.total_citations.count}</strong> 次。`;
        summaryHtml += ` 其中，来自核心外语期刊的引用有 <strong>${data.filtered_citations.count}</strong> 次。`;
        
        let html = `<div class="result-summary">${summaryHtml}</div>`;
        
        if (data.total_citations.count > 0) {
            html += `<div id="cited-by-chart-container" style="height: 250px;"><canvas id="citedByChart"></canvas></div>`;
        }
        
        html += `<h3 style="margin-top: 2rem;">核心外语期刊施引文献 (${data.filtered_citations.count})</h3>`;
        
        if (data.filtered_citations.count > 0) {
            html += data.filtered_citations.articles.map(article => createArticleCard(article)).join('');
        } else {
            html += '<div class="info-message">无指定来源的被引记录。</div>';
        }
        
        html += `<h3 style="margin-top: 2rem;">全部施引文献 (${data.total_citations.count})</h3>`;
        
        if (data.total_citations.count > 0) {
            html += data.total_citations.articles.map(article => createArticleCard(article)).join('');
        } else {
            html += '<div class="info-message">该时间范围内无被引记录。</div>';
        }
        
        resultsContainer.innerHTML = html;
        
        if (data.total_citations.count > 0) {
            renderChart(data.total_citations.count, data.filtered_citations.count);
        }
        
        resultsContainer.scrollIntoView({ behavior: 'smooth' });
    }
    
    // 图表渲染
    function renderChart(total, filtered) {
        const ctx = document.getElementById('citedByChart')?.getContext('2d');
        
        if (!ctx) return;
        
        new Chart(ctx, {
            type: 'bar',
            data: {
                labels: ['被引次数'],
                datasets: [
                    { 
                        label: '总被引', 
                        data: [total], 
                        backgroundColor: 'rgba(54, 162, 235, 0.6)', 
                        borderColor: 'rgba(54, 162, 235, 1)', 
                        borderWidth: 1 
                    },
                    { 
                        label: '核心外语期刊被引', 
                        data: [filtered], 
                        backgroundColor: 'rgba(75, 192, 192, 0.6)', 
                        borderColor: 'rgba(75, 192, 192, 1)', 
                        borderWidth: 1 
                    }
                ]
            },
            options: { 
                responsive: true, 
                maintainAspectRatio: false, 
                scales: { 
                    y: { 
                        beginAtZero: true, 
                        ticks: { color: '#6D6F74', precision: 0 }, 
                        grid: { color: 'rgba(0, 0, 0, 0.05)'} 
                    }, 
                    x: { 
                        ticks: { color: '#6D6F74' }, 
                        grid: { display: false } 
                    } 
                }, 
                plugins: { 
                    legend: { labels: { color: '#202123' } } 
                } 
            }
        });
    }
    
    // 创建文章卡片
    function createArticleCard(article) {
        const url = article.url || (article.doi ? `https://doi.org/${article.doi}`  : '#');
        const link = url !== '#' ? `href="${url}" target="_blank" rel="noopener noreferrer"` : 'href="#" class="disabled-link"';
        const coverYear = article.coverDate ? article.coverDate.substring(0, 4) : 'N/A';
        
        return `
            <div class="article-card">
                <h4 class="article-title">${article.title || '（标题不可用）'}</h4>
                <p class="article-meta">${article.publicationName || 'N/A'} (${coverYear}) | <a ${link}>查看原文</a></p>
            </div>`;
    }
    
    // 显示加载动画
    function showLoading() {
        resultsContainer.innerHTML = `
            <div class="loading-spinner">
                <svg width="48" height="48" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg" fill="#007BFF">
                    <g>
                        <circle cx="12" cy="3" r="1" fill-opacity="0.1">
                            <animate id="a" begin="0;b.end-0.5s" attributeName="fill-opacity" calcMode="spline" dur="1.5s" values="0.1;1;0.1" keySplines=".5 0 .5 1;.5 0 .5 1" repeatCount="indefinite"/>
                        </circle>
                        <circle cx="12" cy="21" r="1" fill-opacity="0.1">
                            <animate begin="a.begin+0.1s" attributeName="fill-opacity" calcMode="spline" dur="1.5s" values="0.1;1;0.1" keySplines=".5 0 .5 1;.5 0 .5 1" repeatCount="indefinite"/>
                        </circle>
                        <circle cx="20.5" cy="16.5" r="1" fill-opacity="0.1">
                            <animate begin="a.begin+0.2s" attributeName="fill-opacity" calcMode="spline" dur="1.5s" values="0.1;1;0.1" keySplines=".5 0 .5 1;.5 0 .5 1" repeatCount="indefinite"/>
                        </circle>
                        <circle cx="3.5" cy="7.5" r="1" fill-opacity="0.1">
                            <animate begin="a.begin+0.3s" attributeName="fill-opacity" calcMode="spline" dur="1.5s" values="0.1;1;0.1" keySplines=".5 0 .5 1;.5 0 .5 1" repeatCount="indefinite"/>
                        </circle>
                        <circle cx="20.5" cy="7.5" r="1" fill-opacity="0.1">
                            <animate begin="a.begin+0.4s" attributeName="fill-opacity" calcMode="spline" dur="1.5s" values="0.1;1;0.1" keySplines=".5 0 .5 1;.5 0 .5 1" repeatCount="indefinite"/>
                        </circle>
                        <circle cx="3.5" cy="16.5" r="1" fill-opacity="0.1">
                            <animate id="b" begin="a.begin+0.5s" attributeName="fill-opacity" calcMode="spline" dur="1.5s" values="0.1;1;0.1" keySplines=".5 0 .5 1;.5 0 .5 1" repeatCount="indefinite"/>
                        </circle>
                    </g>
                </svg>
                <p>正在请求 Scopus API，请稍候...</p>
            </div>`;
            
        resultsContainer.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
    
    // 显示错误消息
    function showError(message) {
        resultsContainer.innerHTML = `<div class="error-message"><strong>错误:</strong> ${message}</div>`;
        resultsContainer.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
});