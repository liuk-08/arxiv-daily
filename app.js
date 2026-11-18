const topics={
 sensing:{name:'量子精密测量',category:'Quantum Sensing',icon:'◉',desc:'原子磁力计、自旋压缩、量子传感与低噪声读出'},
 dark:{name:'暗物质',category:'Dark Matter',icon:'✳',desc:'暗物质模型、宇宙学证据与探测实验'},
 foundations:{name:'量子力学基础问题',category:'Quantum Foundations',icon:'⚛',desc:'测量问题、贝尔非定域性与量子理论基础'},
 computing:{name:'量子计算',category:'Quantum Computing',icon:'⊗',desc:'量子算法、量子纠错与计算架构'},
 qgravity:{name:'量子引力',category:'Quantum Gravity',icon:'◇',desc:'时空量子化、黑洞量子效应与全息理论'},
 particle:{name:'粒子物理',category:'Particle Physics',icon:'⊙',desc:'粒子唯象、对撞机实验与标准模型检验'}
};
const dataset=window.DSH_DAILY_DATA||null;
const topicOrder=Object.keys(topics);
const topicFilter=document.getElementById('topic-filter');
for(const key of topicOrder){
 topicFilter.add(new Option(topics[key].name,key));
}
let selectedDate=null;
let selectedTopic='all';
let selectedSource='all';
let searchText='';
function esc(value=''){return String(value).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}
function prettyDate(date){const d=new Date(date+'T12:00:00');return new Intl.DateTimeFormat('zh-CN',{year:'numeric',month:'long',day:'numeric',weekday:'short'}).format(d)}
function papersFor(date){return dataset?.batches?.[date]?.papers||[]}
function topicPapers(papers,key){return papers.filter(p=>(p.topics||[]).includes(key))}
function render(){
 const dates=dataset?.dates||[];selectedDate=selectedDate||dates[0]||null;
 const current=papersFor(selectedDate);
 const sources=document.getElementById('source-filter').options;
 sources.namedItem('arxiv-count').textContent=`arXiv 预印本 (${current.filter(p=>sourceOf(p)==='arxiv').length})`;
 sources.namedItem('journal-count').textContent=`期刊论文 (${current.filter(p=>sourceOf(p)==='journal').length})`;
 document.getElementById('issue-date').textContent=selectedDate?prettyDate(selectedDate):'等待首次数据更新';
 document.getElementById('updated-at').textContent=dataset?.updatedAt?`更新于 ${dataset.updatedAt}`:'数据尚未生成';
 document.getElementById('batch-total').textContent=dates.length?`${dates.length} 个批次`:'暂无批次';
 document.getElementById('topic-grid').innerHTML=topicOrder.map(key=>{
   const t=topics[key], count=topicPapers(current,key).length;
   return `<a href="#papers-panel" class="topic-card ${key}" data-topic-card="${key}"><span class="topic-symbol">${t.icon}</span><span class="topic-label">${esc(t.category)}</span><h2>${t.name}</h2><div class="paper-count">${count}<small>篇</small></div><p>${t.desc}</p></a>`;
 }).join('');
 document.querySelectorAll('[data-topic-card]').forEach(card=>card.addEventListener('click',()=>{selectedTopic=card.dataset.topicCard;document.getElementById('topic-filter').value=selectedTopic;renderPapers();}));
 document.getElementById('batch-list').innerHTML=dates.length?dates.map((date,index)=>`<button class="batch-button${date===selectedDate?' active':''}" data-date="${date}">${date===dates[0]?`${date.slice(5).replace('-','月')}日（最新）`:date}<small>${dataset.batches[date].papers.length} 篇</small></button>`).join(''):'<span class="empty-state">尚无批次数据。运行 update.py 获取每日论文。</span>';
 document.querySelectorAll('[data-date]').forEach(button=>button.addEventListener('click',()=>{selectedDate=button.dataset.date;render()}));
 document.getElementById('papers-eyebrow').textContent=selectedDate?`DAILY BATCH / ${selectedDate}`:'DAILY BATCH';
 document.getElementById('papers-title').textContent=selectedDate?`${prettyDate(selectedDate)} · 相关论文`:'今日相关论文';
 const warning=document.getElementById('data-warning');
 if(!dataset){warning.hidden=false;warning.textContent='当前目录还没有生成每日论文数据。运行 update.py 后即可查看 arXiv 与期刊论文批次。'}else{warning.hidden=true}
 renderPapers();
}
function sourceOf(p){return p.source || 'arxiv'} // Older batches predate the source field.
function sourceMeta(p){
 if(sourceOf(p)==='journal'){
   const verified=p.peerReviewed===true?'<span class="reviewed">★ 同行评审</span>':'';
   return `<span class="source-badge journal">期刊 · ${esc(p.journal||'刊名未提供')}</span>${verified}`;
 }
 return `<span class="source-badge">arXiv 预印本</span><span>${esc(p.id)}</span>`;
}
function paperDate(p){
 const label=sourceOf(p)==='journal'?'发表':'提交';
 return p.published?`${label}于 ${esc(p.published)}`:`${label}日期未提供`;
}
function renderPapers(){
 const papers=papersFor(selectedDate).filter(p=>(selectedSource==='all'||sourceOf(p)===selectedSource)&&(selectedTopic==='all'||(p.topics||[]).includes(selectedTopic))&&(!searchText||`${p.title} ${p.authors} ${p.summary} ${p.journal||''}`.toLowerCase().includes(searchText)));
 const list=document.getElementById('paper-list');
 if(!selectedDate){list.innerHTML='<div class="load-state">等待每日论文数据。</div>';return}
 if(!papers.length){list.innerHTML='<div class="empty-state">该批次没有符合当前来源、主题和关键词的论文。</div>';return}
 list.innerHTML=papers.map(p=>`<article class="paper-row"><h3 class="paper-title"><a href="${esc(p.url)}" target="_blank" rel="noreferrer">${esc(p.title)}</a></h3><div class="paper-meta">${sourceMeta(p)}<span>${esc(p.authors)}</span><span>${paperDate(p)}</span></div><p class="paper-abstract">${esc(p.summary)}</p><div class="paper-tags">${(p.topics||[]).map(k=>`<span class="paper-tag">${esc(topics[k]?.name||k)}</span>`).join('')}${(p.categories||[]).slice(0,3).map(c=>`<span class="paper-tag">${esc(c)}</span>`).join('')}</div></article>`).join('');
}
document.getElementById('source-filter').addEventListener('change',e=>{selectedSource=e.target.value;renderPapers()});
document.getElementById('paper-filter').addEventListener('input',e=>{searchText=e.target.value.trim().toLowerCase();renderPapers()});
document.getElementById('topic-filter').addEventListener('change',e=>{selectedTopic=e.target.value;renderPapers()});
render();
