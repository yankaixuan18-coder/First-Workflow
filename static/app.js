/**
 * Amazon Category Research Tool — frontend controller.
 * Wizard navigation + SSE progress stream + status polling fallback.
 * Backend contract: POST /start, GET /progress/<id> (SSE), GET /status/<id>, GET /download/<id>
 */

let currentTaskId = null;
let eventSource = null;
let pollInterval = null;
let timerInterval = null;
let startTime = null;
let maxProductsTarget = 100;
let pagesSeen = 0;

// ---------------------------------------------------------------------------
// Wizard navigation
// ---------------------------------------------------------------------------

function goStep(n) {
  // Validate step 1 before advancing
  if (n >= 2 && !document.getElementById('kwInput').value.trim()) {
    flashInput();
    return;
  }
  for (let i = 1; i <= 3; i++) {
    document.getElementById('step' + i).classList.toggle('hidden', i !== n);
  }
  updateStepper(n);
  if (n === 3) renderReview();
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

function updateStepper(active) {
  for (let i = 1; i <= 3; i++) {
    const dot = document.querySelector('#stepIndicator' + i + ' .step-dot');
    const label = document.querySelector('#stepIndicator' + i + ' span:last-child');
    const done = i < active, current = i === active;
    dot.className = 'step-dot w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold ' +
      (current ? 'bg-brand-500 text-white' : done ? 'bg-green-500 text-white' : 'bg-slate-200 text-slate-500');
    dot.innerHTML = done ? '&#10003;' : i;
    if (label) label.className = 'font-medium hidden sm:inline ' + (i <= active ? 'text-slate-700' : 'text-slate-400');
  }
  if (document.getElementById('stepLine1'))
    document.getElementById('stepLine1').className = 'w-8 sm:w-16 h-0.5 ' + (active >= 2 ? 'bg-green-500' : 'bg-slate-200');
  if (document.getElementById('stepLine2'))
    document.getElementById('stepLine2').className = 'w-8 sm:w-16 h-0.5 ' + (active >= 3 ? 'bg-green-500' : 'bg-slate-200');
}

function flashInput() {
  const el = document.getElementById('kwInput');
  el.classList.add('ring-2', 'ring-red-400', 'border-red-400');
  el.focus();
  setTimeout(() => el.classList.remove('ring-2', 'ring-red-400', 'border-red-400'), 1500);
}

function fillExample(text) {
  document.getElementById('kwInput').value = text;
}

// ---------------------------------------------------------------------------
// Step 2: presets & sliders
// ---------------------------------------------------------------------------

function selectPreset(card) {
  document.querySelectorAll('.preset-card').forEach(c => c.classList.remove('active'));
  card.classList.add('active');
  document.getElementById('maxPages').value = card.dataset.pages;
  document.getElementById('maxProducts').value = card.dataset.products;
  onSlider();
}

function onSlider() {
  const pages = document.getElementById('maxPages').value;
  const products = document.getElementById('maxProducts').value;
  document.getElementById('maxPagesVal').textContent = pages;
  document.getElementById('maxProductsVal').textContent = products;
  // De-highlight presets if user customizes away from them
  document.querySelectorAll('.preset-card').forEach(c => {
    if (c.dataset.pages !== pages || c.dataset.products !== products) c.classList.remove('active');
    else c.classList.add('active');
  });
}

// ---------------------------------------------------------------------------
// Step 3: review summary
// ---------------------------------------------------------------------------

function renderReview() {
  document.getElementById('rvTarget').textContent = document.getElementById('kwInput').value.trim() || '—';
  document.getElementById('rvMarket').textContent = document.getElementById('marketplace').value;
  document.getElementById('rvScale').textContent =
    `${document.getElementById('maxProducts').value} 个 / ${document.getElementById('maxPages').value} 页`;
  document.getElementById('rvDetails').textContent =
    document.getElementById('fetchDetails').checked ? '开启（更全更慢）' : '关闭';
}

// ---------------------------------------------------------------------------
// UI helpers
// ---------------------------------------------------------------------------

function setStatus(label, kind) {
  const map = {
    idle:    'bg-slate-100 text-slate-500',
    running: 'bg-amber-100 text-amber-700',
    done:    'bg-green-100 text-green-700',
    error:   'bg-red-100 text-red-700',
  };
  const badge = document.getElementById('statusBadge');
  badge.textContent = label;
  badge.className = 'text-xs font-semibold px-3 py-1 rounded-full ' + (map[kind] || map.idle);
}

function appendLog(text, extraClass) {
  const box = document.getElementById('logBox');
  const line = document.createElement('div');
  if (extraClass) line.classList.add(extraClass);
  line.textContent = text;
  box.appendChild(line);
  box.scrollTop = box.scrollHeight;

  // Track page progress from log lines like "第 N 页"
  const m = text.match(/第\s*(\d+)\s*页|Page\s+(\d+)/);
  if (m) {
    const p = parseInt(m[1] || m[2], 10);
    if (p > pagesSeen) { pagesSeen = p; document.getElementById('statPages').textContent = pagesSeen; }
  }
}

function setProductCount(n) {
  document.getElementById('statProducts').textContent = n;
  const pct = maxProductsTarget > 0 ? Math.min(100, Math.round((n / maxProductsTarget) * 100)) : 0;
  document.getElementById('progressBar').style.width = pct + '%';
}

function setProgressComplete() {
  const bar = document.getElementById('progressBar');
  bar.style.width = '100%';
  bar.classList.remove('progress-shimmer');
}

function showDownloadButton(taskId) {
  const btn = document.getElementById('downloadBtn');
  btn.href = `/download/${taskId}`;
  document.getElementById('downloadSection').classList.remove('hidden');
}

function showError(msg) {
  const el = document.getElementById('errorMsg');
  el.textContent = '❌ ' + msg;
  el.classList.remove('hidden');
}
function hideError() { document.getElementById('errorMsg').classList.add('hidden'); }
function clearLog() { document.getElementById('logBox').innerHTML = ''; }

function startTimer() {
  startTime = Date.now();
  timerInterval = setInterval(() => {
    const s = Math.floor((Date.now() - startTime) / 1000);
    const txt = s < 60 ? `${s}s` : `${Math.floor(s / 60)}m${s % 60}s`;
    document.getElementById('statTime').textContent = txt;
  }, 1000);
}
function stopTimer() { if (timerInterval) { clearInterval(timerInterval); timerInterval = null; } }

// ---------------------------------------------------------------------------
// Start collection
// ---------------------------------------------------------------------------

async function startCollection() {
  hideError();
  const keyword = document.getElementById('kwInput').value.trim();
  if (!keyword) { goStep(1); flashInput(); return; }

  maxProductsTarget = parseInt(document.getElementById('maxProducts').value, 10) || 100;
  pagesSeen = 0;

  const payload = {
    keyword_or_url: keyword,
    marketplace: document.getElementById('marketplace').value,
    max_pages: parseInt(document.getElementById('maxPages').value, 10) || 5,
    max_products: maxProductsTarget,
    fetch_details: document.getElementById('fetchDetails').checked,
    chrome_user_data_dir: document.getElementById('chromeDir').value.trim(),
    chrome_profile: document.getElementById('chromeProfile').value.trim(),
  };

  // Reset UI
  clearLog();
  document.getElementById('statProducts').textContent = '0';
  document.getElementById('statPages').textContent = '0';
  document.getElementById('statTime').textContent = '0s';
  document.getElementById('progressBar').style.width = '0%';
  document.getElementById('progressBar').classList.add('progress-shimmer');
  document.getElementById('downloadSection').classList.add('hidden');

  const btn = document.getElementById('startBtn');
  btn.disabled = true;
  btn.classList.add('opacity-60', 'cursor-not-allowed');
  btn.textContent = '采集中…';
  setStatus('运行中 Running', 'running');
  stopStreams();
  startTimer();

  let taskId;
  try {
    const resp = await fetch('/start', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    const data = await resp.json();
    if (!resp.ok || data.error) throw new Error(data.error || `HTTP ${resp.status}`);
    taskId = data.task_id;
    currentTaskId = taskId;
  } catch (err) {
    showError(`启动失败 / Failed to start: ${err.message}`);
    resetStartButton();
    setStatus('错误 Error', 'error');
    stopTimer();
    return;
  }

  appendLog(`任务已启动 Task started: ${taskId}`, 'log-success');
  openSSE(taskId);
  pollInterval = setInterval(() => pollStatus(taskId), 3000);
}

// ---------------------------------------------------------------------------
// SSE stream
// ---------------------------------------------------------------------------

function openSSE(taskId) {
  if (eventSource) eventSource.close();
  eventSource = new EventSource(`/progress/${taskId}`);

  eventSource.onmessage = function (e) {
    const text = e.data;
    if (!text) return; // keep-alive

    if (text.startsWith('STATUS:done')) return finishDone(taskId);
    if (text.startsWith('STATUS:error')) return finishError();
    if (text.startsWith('ERROR:')) { appendLog(text, 'log-error'); return; }

    appendLog(text, /第\s*\d+\s*页|Page\s+\d+/.test(text) ? 'log-page' : null);
  };

  eventSource.onerror = function () {
    if (eventSource) { eventSource.close(); eventSource = null; } // polling takes over
  };
}

// ---------------------------------------------------------------------------
// Status polling (fallback)
// ---------------------------------------------------------------------------

async function pollStatus(taskId) {
  try {
    const resp = await fetch(`/status/${taskId}`);
    if (!resp.ok) return;
    const data = await resp.json();
    setProductCount(data.product_count || 0);
    if (data.status === 'done') finishDone(taskId);
    else if (data.status === 'error') { if (data.error) showError(data.error); finishError(); }
  } catch (_) { /* ignore */ }
}

// ---------------------------------------------------------------------------
// Terminal states
// ---------------------------------------------------------------------------

function finishDone(taskId) {
  setStatus('完成 Done', 'done');
  setProgressComplete();
  appendLog('✅ 采集完成，可以下载了！', 'log-success');
  showDownloadButton(taskId);
  resetStartButton();
  stopStreams();
  stopTimer();
}

function finishError() {
  setStatus('错误 Error', 'error');
  resetStartButton();
  stopStreams();
  stopTimer();
}

// ---------------------------------------------------------------------------
// Cleanup / reset
// ---------------------------------------------------------------------------

function stopStreams() {
  if (eventSource) { eventSource.close(); eventSource = null; }
  if (pollInterval) { clearInterval(pollInterval); pollInterval = null; }
}

function resetStartButton() {
  const btn = document.getElementById('startBtn');
  btn.disabled = false;
  btn.classList.remove('opacity-60', 'cursor-not-allowed');
  btn.textContent = '🚀 开始采集';
}

function resetAll() {
  stopStreams();
  stopTimer();
  clearLog();
  hideError();
  document.getElementById('downloadSection').classList.add('hidden');
  document.getElementById('progressBar').style.width = '0%';
  setStatus('待机 Idle', 'idle');
  goStep(1);
}

// ---------------------------------------------------------------------------
// Help modal
// ---------------------------------------------------------------------------

function openHelp(e) { if (e) e.preventDefault(); document.getElementById('helpModal').classList.remove('hidden'); }
function closeHelp(e) { if (e) e.stopPropagation(); document.getElementById('helpModal').classList.add('hidden'); }

// Init
document.addEventListener('DOMContentLoaded', () => {
  onSlider();
  document.getElementById('kwInput').addEventListener('keydown', e => {
    if (e.key === 'Enter') goStep(2);
  });
});
