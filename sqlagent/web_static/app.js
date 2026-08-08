const $ = (selector) => document.querySelector(selector);
const statusClasses = ['ready', 'offline', 'pending'];

function setStatusCard(service, status, detail) {
  const card = document.querySelector(`[data-service="${service}"]`);
  if (!card) return;
  card.classList.remove(...statusClasses);
  card.classList.add(status === 'ready' ? 'ready' : status === 'offline' ? 'offline' : 'pending');
  card.querySelector('.status-value').textContent = status;
  card.querySelector('.status-detail').textContent = detail || '—';
}

function renderTable(rows) {
  if (!rows || !rows.length) return '<p class="table-empty">Query returned no rows.</p>';
  const columns = Object.keys(rows[0]);
  return `<table class="result-table"><thead><tr>${columns.map((column) => `<th>${escapeHtml(column)}</th>`).join('')}</tr></thead><tbody>${rows.map((row) => `<tr>${columns.map((column) => `<td>${escapeHtml(row[column])}</td>`).join('')}</tr>`).join('')}</tbody></table>`;
}

function renderResult(data) {
  if (data.status === 'pipeline_failed' || data.error) {
    const error = data.error || {};
    $('#resultShell').innerHTML = `<div class="clarification-result"><span class="empty-index">FAILED /</span><div><strong>${escapeHtml(error.type || 'internal_error')}</strong><p>${escapeHtml(error.message || 'Query failed')}</p><small>stage ${escapeHtml(error.stage || 'unknown')} · request ${escapeHtml(data.request_id || '—')} · learning job ${escapeHtml(error.learning_job_id || '—')}</small></div></div>`;
    return;
  }
  if (data.telemetry?.clarification_requested) {
    $('#resultShell').innerHTML = `<div class="clarification-result"><span class="empty-index">CLARIFY /</span><div><strong>Metric clarification required</strong><p>${escapeHtml(data.clarification || 'Please choose a metric.')}</p><small>telemetry recorded in the trajectory log</small></div></div>`;
    return;
  }
  const result = data.result || {};
  const explain = data.explain || {};
  const repairMeta = data.react_attempts ? `<span>repaired ${data.react_attempts}×</span>` : '';
  $('#resultShell').innerHTML = `<div class="result-meta"><span>result / verified</span><span>${Number(result.elapsed_ms || 0).toFixed(1)} ms</span><span>${result.rows?.length || 0} rows</span><span>cost ${Number(explain.total_cost || 0).toFixed(0)}</span>${repairMeta}</div><pre class="sql-block">${escapeHtml(data.sql || '')}</pre>${renderTable(result.rows)}`;
}

function renderTraces(items) {
  const body = $('#trajectoryTable');
  if (!items?.length) { body.innerHTML = '<tr><td colspan="4" class="table-empty">No trajectories yet.</td></tr>'; return; }
  body.innerHTML = items.map((item) => `<tr><td>${escapeHtml(item.question || '—')}</td><td>${item.status === 'ok' ? 'verified' : 'failed'}</td><td>${item.elapsed_ms == null ? '—' : `${Number(item.elapsed_ms).toFixed(1)} ms`}</td><td>${formatTime(item.created_at)}</td></tr>`).join('');
}

function jobSummary(job) {
  const result = job.result;
  if (job.status === 'failed') return job.error || 'failed';
  if (!result) return '';
  if (job.name === 'survey') return `${result.tables ?? '?'} tables documented`;
  if (job.name === 'explore') {
    if (result.stop_reason) return `stopped: ${result.stop_reason}`;
    return `${result.rounds_run ?? 0} rounds, ${(result.written || []).length} artifacts written`;
  }
  if (job.name === 'evolve') {
    if (result.status === 'insufficient_trajectories') return `needs ${result.required} trajectories, have ${result.count} — ask questions first`;
    return `${result.branch || ''} · ${(result.changed_files || []).join(', ')}`;
  }
  if (job.name === 'evaluate') {
    const completion = result.completion || {};
    return `${completion.answered ?? 0} answered · ${completion.clarified ?? 0} clarified · ${completion.pipeline_failed ?? 0} failed · unsafe ${result.unsafe ?? 0} · p95 ${Number(result.p95_exec_ms || 0).toFixed(0)} ms`;
  }
  if (job.name === 'promote') return result.status === 'promoted' ? `promoted · tag ${result.tag}` : `rejected by gate${result.branch ? ` · ${result.branch}` : ''}`;
  return '';
}

function renderJobs(items) {
  const list = $('#jobsList');
  if (!items?.length) { list.innerHTML = '<p class="table-empty">No background jobs.</p>'; return; }
  list.innerHTML = items.map((job) => {
    const summary = jobSummary(job);
    return `<div class="job-row ${job.status}"><div><b>${escapeHtml(job.name)}</b><small> / ${escapeHtml(job.id)}</small>${summary ? `<small class="job-summary">${escapeHtml(summary)}</small>` : ''}</div><b>${escapeHtml(job.status)}</b></div>`;
  }).join('');
}

function updateActionStates(data) {
  const workspaceReady = data.workspace?.status === 'ready';
  const hasTrajectories = (data.trajectory_count || 0) > 0;
  const onCandidate = Boolean(data.workspace?.latest_candidate);
  const hints = {
    survey: workspaceReady ? 'workspace exists — re-running overwrites the generated skill' : '',
    explore: workspaceReady ? '' : 'requires a completed survey',
    evaluate: workspaceReady ? '' : 'requires a completed survey',
    evolve: !workspaceReady ? 'requires a completed survey' : (!hasTrajectories ? 'works on trajectories — ask at least one question first' : ''),
    promote: !workspaceReady ? 'requires a completed survey' : (!onCandidate ? 'requires an evolution/* candidate — run evolve first' : `will gate ${data.workspace.latest_candidate} without switching main`),
  };
  Object.entries(hints).forEach(([action, hint]) => {
    const row = document.querySelector(`[data-action="${action}"]`);
    if (!row) return;
    const caption = row.querySelector('small');
    if (!caption.dataset.base) caption.dataset.base = caption.textContent;
    caption.textContent = hint ? `${caption.dataset.base} Note: ${hint}.` : caption.dataset.base;
    row.classList.toggle('attention', Boolean(hint) && action !== 'survey');
  });
}

function renderPipeline(pipeline) {
  Object.entries(pipeline || {}).forEach(([stage, status]) => {
    const node = document.querySelector(`[data-stage="${stage}"]`);
    if (!node) return;
    node.classList.toggle('ready', status === 'ready');
    node.classList.toggle('pending', status !== 'ready');
    node.querySelector('b').textContent = status.replaceAll('_', ' ');
  });
}

function renderSignal(signal) {
  const stages = signal?.stages || {};
  Object.entries(stages).forEach(([stage, value]) => {
    const node = document.querySelector(`[data-signal-stage="${stage}"]`);
    if (!node) return;
    node.dataset.status = value.status || 'pending';
    node.querySelector('i').textContent = value.detail || value.status || 'waiting';
  });
  const hasError = Object.values(stages).some((value) => value.status === 'error');
  $('#signalState').textContent = hasError ? 'attention' : (signal?.state || 'connecting');
}

async function refreshStatus() {
  try {
    const response = await fetch('/api/status');
    const data = await response.json();
    $('#datasetName').textContent = data.dataset || 'unknown';
    setStatusCard('postgres', data.postgres.status === 'error' ? 'offline' : data.postgres.status, data.postgres.detail);
    setStatusCard('ollama', data.ollama.status === 'error' ? 'offline' : data.ollama.status, data.ollama.detail || data.ollama.model);
    setStatusCard('workspace', data.workspace.status === 'ready' ? 'ready' : 'pending', data.workspace.branch ? `branch ${data.workspace.branch}` : 'run survey to build');
    $('#trajectoryCount').textContent = data.trajectory_count || 0;
    $('#branchName').textContent = `branch ${data.workspace.branch || '—'}`;
    renderSignal(data.signal); renderPipeline(data.pipeline); renderTraces(data.latest_trajectories); renderJobs(data.jobs); updateActionStates(data);
    $('#lastUpdated').textContent = `status pulled ${new Date().toLocaleTimeString()}`;
  } catch (error) { $('#lastUpdated').textContent = 'status endpoint unavailable'; }
}

async function submitQuestion(event) {
  event.preventDefault();
  const button = $('.run-button'); const question = $('#question').value.trim();
  if (!question) return;
  button.disabled = true; button.querySelector('span').textContent = 'Processing';
  $('#resultShell').innerHTML = '<p class="table-empty">Routing → EXPLAIN → execute…</p>';
  try {
    const response = await fetch('/api/ask', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({question}) });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || 'Query failed');
    renderResult(data); refreshStatus();
  } catch (error) { $('#resultShell').innerHTML = `<p class="error-text">${escapeHtml(error.message)}</p>`; }
  finally { button.disabled = false; button.querySelector('span').textContent = 'Run query'; refreshStatus(); }
}

async function launchJob(path, button) {
  button.disabled = true;
  try {
    const response = await fetch(path, {method: 'POST'}); const data = await response.json();
    if (!response.ok) throw new Error(data.detail || 'Job could not start');
    refreshStatus();
  } catch (error) { $('#lastUpdated').textContent = error.message; }
  finally { setTimeout(() => { button.disabled = false; refreshStatus(); }, 800); }
}

function escapeHtml(value) { return String(value ?? '—').replace(/[&<>'"]/g, (char) => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[char])); }
function formatTime(value) { return value ? new Date(value).toLocaleTimeString([], {hour:'2-digit', minute:'2-digit'}) : '—'; }

$('#askForm').addEventListener('submit', submitQuestion);
$('#refreshButton').addEventListener('click', refreshStatus);
$('#surveyButton').addEventListener('click', (event) => launchJob('/api/survey', event.currentTarget));
$('#exploreButton').addEventListener('click', (event) => launchJob('/api/explore', event.currentTarget));
$('#evaluateButton').addEventListener('click', (event) => launchJob('/api/evaluate', event.currentTarget));
$('#verifyButton').addEventListener('click', (event) => launchJob('/api/verify', event.currentTarget));
$('#optimizeButton').addEventListener('click', (event) => launchJob('/api/optimize', event.currentTarget));
$('#evolveButton').addEventListener('click', (event) => launchJob('/api/evolve', event.currentTarget));
$('#promoteButton').addEventListener('click', (event) => launchJob('/api/promote', event.currentTarget));
document.querySelectorAll('[data-question]').forEach((button) => button.addEventListener('click', () => { $('#question').value = button.dataset.question; $('#question').focus(); }));
refreshStatus(); setInterval(refreshStatus, 3000);
