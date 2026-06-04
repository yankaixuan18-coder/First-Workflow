/**
 * Amazon Category Research Tool — frontend JS
 * Handles form submission, SSE progress stream, and status polling.
 */

let currentTaskId = null;
let eventSource = null;
let pollInterval = null;

// -------------------------------------------------------------------------
// UI helpers
// -------------------------------------------------------------------------

function setStatus(label, cssClass) {
  const badge = document.getElementById('statusBadge');
  badge.textContent = label;
  badge.className = `${cssClass} text-xs font-semibold px-2.5 py-1 rounded-full`;
}

function appendLog(text, extraClass) {
  const box = document.getElementById('logBox');
  const line = document.createElement('div');
  if (extraClass) line.classList.add(extraClass);
  line.textContent = text;
  box.appendChild(line);
  box.scrollTop = box.scrollHeight;
}

function setProductCount(n) {
  const el = document.getElementById('productCount');
  el.textContent = n > 0 ? `共 ${n} 个商品` : '';
}

function showDownloadButton(taskId) {
  const section = document.getElementById('downloadSection');
  const btn = document.getElementById('downloadBtn');
  btn.href = `/download/${taskId}`;
  section.classList.remove('hidden');
}

function showError(msg) {
  const el = document.getElementById('errorMsg');
  el.textContent = msg;
  el.classList.remove('hidden');
}

function hideError() {
  document.getElementById('errorMsg').classList.add('hidden');
}

function clearLog() {
  document.getElementById('logBox').innerHTML = '';
}

// -------------------------------------------------------------------------
// Start collection
// -------------------------------------------------------------------------

async function startCollection() {
  hideError();

  const keyword = document.getElementById('kwInput').value.trim();
  if (!keyword) {
    showError('请输入关键词或 URL / Please enter a keyword or URL.');
    return;
  }

  const payload = {
    keyword_or_url: keyword,
    marketplace: document.getElementById('marketplace').value,
    max_pages: parseInt(document.getElementById('maxPages').value, 10) || 5,
    max_products: parseInt(document.getElementById('maxProducts').value, 10) || 100,
    fetch_details: document.getElementById('fetchDetails').checked,
    chrome_user_data_dir: document.getElementById('chromeDir').value.trim(),
    chrome_profile: document.getElementById('chromeProfile').value.trim(),
  };

  // Reset UI
  clearLog();
  setProductCount(0);
  document.getElementById('downloadSection').classList.add('hidden');
  document.getElementById('startBtn').disabled = true;
  document.getElementById('startBtn').textContent = '采集中… / Running…';
  setStatus('运行中 Running', 'badge-running');

  // Stop any previous task streams
  stopStreams();

  let taskId;
  try {
    const resp = await fetch('/start', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    const data = await resp.json();
    if (!resp.ok || data.error) {
      throw new Error(data.error || `HTTP ${resp.status}`);
    }
    taskId = data.task_id;
    currentTaskId = taskId;
  } catch (err) {
    showError(`启动失败 / Failed to start: ${err.message}`);
    resetStartButton();
    setStatus('错误 Error', 'badge-error');
    return;
  }

  appendLog(`任务已启动 Task started: ${taskId}`);

  // Open SSE stream
  openSSE(taskId);

  // Start polling as fallback (in case SSE drops)
  pollInterval = setInterval(() => pollStatus(taskId), 3000);
}

// -------------------------------------------------------------------------
// SSE stream
// -------------------------------------------------------------------------

function openSSE(taskId) {
  if (eventSource) {
    eventSource.close();
  }
  eventSource = new EventSource(`/progress/${taskId}`);

  eventSource.onmessage = function (e) {
    const text = e.data;
    if (!text) return;  // keep-alive blank line

    if (text.startsWith('STATUS:done')) {
      setStatus('完成 Done', 'badge-done');
      showDownloadButton(taskId);
      resetStartButton();
      stopStreams();
      return;
    }
    if (text.startsWith('STATUS:error')) {
      setStatus('错误 Error', 'badge-error');
      resetStartButton();
      stopStreams();
      return;
    }
    if (text.startsWith('ERROR:')) {
      appendLog(text, 'log-error');
    } else {
      appendLog(text);
    }
  };

  eventSource.onerror = function () {
    // SSE connection dropped — polling will handle the rest
    if (eventSource) {
      eventSource.close();
      eventSource = null;
    }
  };
}

// -------------------------------------------------------------------------
// Status polling (fallback)
// -------------------------------------------------------------------------

async function pollStatus(taskId) {
  try {
    const resp = await fetch(`/status/${taskId}`);
    if (!resp.ok) return;
    const data = await resp.json();

    setProductCount(data.product_count || 0);

    if (data.status === 'done') {
      setStatus('完成 Done', 'badge-done');
      showDownloadButton(taskId);
      resetStartButton();
      stopStreams();
    } else if (data.status === 'error') {
      setStatus('错误 Error', 'badge-error');
      if (data.error) showError(data.error);
      resetStartButton();
      stopStreams();
    }
  } catch (_) {
    // Silently ignore poll errors
  }
}

// -------------------------------------------------------------------------
// Cleanup helpers
// -------------------------------------------------------------------------

function stopStreams() {
  if (eventSource) {
    eventSource.close();
    eventSource = null;
  }
  if (pollInterval) {
    clearInterval(pollInterval);
    pollInterval = null;
  }
}

function resetStartButton() {
  const btn = document.getElementById('startBtn');
  btn.disabled = false;
  btn.textContent = '🚀 开始采集';
}
