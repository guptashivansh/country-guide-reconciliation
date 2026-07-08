// ops-ui.js — Sync, toast, keyboard shortcuts, notifications, search, init

//  SYNC MODAL
// ═══════════════════════════════════════════════════
function renderSyncModal() {
  const grid = document.getElementById('countryGrid');
  const countries = new Set();
  (DATA.sourceCountries || []).forEach(c => { if (c.name) countries.add(c.name); });
  DATA.drift.forEach(d => countries.add(d.country));
  DATA.queue.forEach(q => countries.add(q.country));

  if (!countries.size) {
    grid.innerHTML = '<p style="color:var(--ink-3);grid-column:1/-1;">No countries found. Import data first.</p>';
    return;
  }

  grid.innerHTML = [...countries].sort().map(c => `
    <label class="country-cb" data-country="${escAttr(c)}">
      <span class="box"></span>
      <span class="flag">${flag(c)}</span>
      <span class="name">${c}</span>
    </label>
  `).join('');

  grid.querySelectorAll('.country-cb').forEach(cb => {
    cb.addEventListener('click', e => { e.preventDefault(); cb.classList.toggle('checked'); updateModalCount(); });
  });
  updateModalCount();
}

function updateModalCount() {
  const n = document.querySelectorAll('#countryGrid .country-cb.checked').length;
  document.getElementById('modalCount').textContent = n;
}

function filterSyncCountries() {
  const q = document.getElementById('syncCountrySearch').value.trim().toLowerCase();
  const items = document.querySelectorAll('#countryGrid .country-cb');
  let visible = 0;
  items.forEach(cb => {
    const match = !q || cb.dataset.country.toLowerCase().includes(q);
    cb.style.display = match ? '' : 'none';
    if (match) visible++;
  });
  document.getElementById('syncCountryEmpty').style.display = visible ? 'none' : '';
}

function toggleAllCountries() {
  const items = [...document.querySelectorAll('#countryGrid .country-cb')].filter(i => i.style.display !== 'none');
  const allOn = items.every(i => i.classList.contains('checked'));
  items.forEach(i => i.classList.toggle('checked', !allOn));
  updateModalCount();
}

var _syncSource = 'both';

function setSyncSource(src) {
  _syncSource = src;
  document.getElementById('syncSrcBoth').classList.toggle('active', src === 'both');
  document.getElementById('syncSrcExternal').classList.toggle('active', src === 'external');
  document.getElementById('syncSrcNotion').classList.toggle('active', src === 'notion');
  document.getElementById('syncExternalOptions').style.display = '';
  document.getElementById('syncNotionOptions').style.display = src === 'notion' ? '' : 'none';
  document.getElementById('syncModalEst').style.display = '';
}

async function runSync() {
  const source = _syncSource;
  const isNotion = source === 'notion';
  const isBoth = source === 'both';
  const selected = isNotion ? [] : [...document.querySelectorAll('#countryGrid .country-cb.checked')].map(el => el.dataset.country);
  closeSync();

  const banner = document.getElementById('syncBanner');
  const fill = document.getElementById('syncProgFill');
  const status = document.getElementById('syncStatus');
  const count = document.getElementById('syncCount');
  banner.classList.add('open');
  fill.style.width = '10%';
  status.textContent = isNotion ? 'fetching Notion content…' : 'contacting sources…';
  count.textContent = isNotion ? 'Notion' : (selected.length ? selected.length + ' countries' : 'all countries');

  try {
    fill.style.width = '20%';
    status.textContent = isBoth ? 'syncing external sources…' : isNotion ? 'reconciling against Notion…' : 'starting sync…';
    const body = isNotion ? { source: 'notion' } : (selected.length ? { countries: selected } : {});
    const res = await fetch('/api/sync', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify(body) });
    const data = await res.json();
    if (!data.success) { throw new Error(data.message); }
    status.textContent = isBoth ? 'syncing external sources…' : isNotion ? 'reconciling…' : 'syncing sources…';
    fill.style.width = '30%';

    const poll = setInterval(async () => {
      try {
        const sr = await fetch('/api/sync/status');
        const ss = await sr.json();
        if (ss.running) {
          const pct = Math.min(30 + (ss.endpoints_processed || 0) * 0.15, isBoth ? 60 : 95);
          fill.style.width = pct + '%';
          status.textContent = isBoth ? `syncing external… ${ss.endpoints_processed || 0} endpoints` : isNotion ? 'reconciling…' : `syncing… ${ss.endpoints_processed || 0} endpoints processed`;
        } else {
          clearInterval(poll);
          if (isBoth) {
            fill.style.width = '65%';
            status.textContent = 'reconciling against Notion…';
            const nr = await fetch('/api/sync', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({ source: 'notion' }) });
            const nd = await nr.json();
            if (!nd.success) { throw new Error(nd.message); }
            const poll2 = setInterval(async () => {
              try {
                const sr2 = await fetch('/api/sync/status');
                const ss2 = await sr2.json();
                if (ss2.running) {
                  fill.style.width = Math.min(65 + 30 * 0.5, 95) + '%';
                } else {
                  clearInterval(poll2);
                  fill.style.width = '100%';
                  status.textContent = 'complete';
                  setTimeout(() => banner.classList.remove('open'), 1500);
                  toast((ss.message || '') + (ss2.resolved ? ` · ${ss2.resolved} resolved via Notion` : ''), 'info');
                  loadAll();
                }
              } catch (_) {}
            }, 2000);
          } else {
            fill.style.width = '100%';
            status.textContent = 'complete';
            setTimeout(() => banner.classList.remove('open'), 1500);
            toast(ss.message || 'Sync complete', 'info');
            loadAll();
          }
        }
      } catch (_) {}
    }, isBoth ? 5000 : isNotion ? 2000 : 5000);
  } catch (err) {
    fill.style.width = '100%';
    status.textContent = 'failed';
    setTimeout(() => banner.classList.remove('open'), 2000);
    toast('Sync failed: ' + err.message, 'danger');
  }
}

// ═══════════════════════════════════════════════════
//  FOOTER
// ═══════════════════════════════════════════════════
function renderFooter() {
  const m = DATA.metrics;
  document.getElementById('footerLabel').textContent = `Regulift Compliance · ${m.trusted_source_count || 0} countries monitored`;
}

// ═══════════════════════════════════════════════════

//  UI INTERACTIONS
// ═══════════════════════════════════════════════════
function goTab(name) {
  document.querySelectorAll('.tab').forEach(t => t.setAttribute('aria-current', t.dataset.tab === name ? 'true' : 'false'));
  document.querySelectorAll('.tabpanel').forEach(p => p.classList.toggle('active', p.dataset.tab === name));
  const strip = document.getElementById('globalTriageStrip');
  if (strip) strip.style.display = (name === 'sources' || name === 'audit') ? 'none' : '';
  history.replaceState(null, '', '#' + name);
}
const startTab = (location.hash || '#summary').slice(1);
if (startTab === 'pipeline') { goTab('sources'); }
else if (['summary','review','drift','audit','sources'].includes(startTab)) goTab(startTab);

function openQueueForCountry(country) {
  activeCountryFilter = country;
  document.getElementById('globalTriageCountry').value = country;
  updateTriageCount();
  goTab('review');
  currentFilter = 'all';
  reviewShowing = reviewPageSize;
  document.querySelectorAll('#reviewChips .chip').forEach(c => c.classList.toggle('active', c.dataset.filter === 'all'));
  renderReview();
  renderDriftPills();
}

function openDriftForCountry(country) {
  activeCountryFilter = country;
  document.getElementById('globalTriageCountry').value = country;
  updateTriageCount();
  goTab('drift');
  renderDrift();
  renderDriftPills();
}

function toggleMgr() {
  // Manager strip removed — summary tab replaces it
}

function metricClick(action) {
  if (action === 'critical' || action === 'all') {
    goTab('review');
    currentFilter = action === 'critical' ? 'critical' : 'all';
    reviewShowing = reviewPageSize;
    document.querySelectorAll('#reviewChips .chip').forEach(c => c.classList.toggle('active', c.dataset.filter === currentFilter));
    renderReview();
  } else if (action === 'confidence') {
    goTab('review');
    sortMode = 'confidence';
    document.getElementById('sortLabel').textContent = 'Sort: Confidence ↓';
    currentFilter = 'all';
    reviewShowing = reviewPageSize;
    document.querySelectorAll('#reviewChips .chip').forEach(c => c.classList.toggle('active', c.dataset.filter === 'all'));
    renderReview();
  } else if (action === 'drift') {
    goTab('drift');
  } else if (action === 'pipeline') {
    goTab('sources');
  }
}

function toggleCollapse(btn) {
  const card = btn.closest('.rcard');
  card.classList.toggle('collapsed');
  const id = parseInt(card.dataset.id);
  if (card.classList.contains('collapsed')) expandedIds.delete(id);
  else expandedIds.add(id);
}

function cardBodyClick(e, body) {
  // Only expand collapsed cards; don't interfere with interactive elements
  const card = body.closest('.rcard');
  if (!card || !card.classList.contains('collapsed')) return;
  const tag = e.target.tagName;
  if (e.target.closest('button, a, .rcard-check, input, select, textarea')) return;
  card.classList.remove('collapsed');
  const id = parseInt(card.dataset.id);
  expandedIds.add(id);
}

function toggleCheck(e, id) {
  e.stopPropagation();
  if (selectedIds.has(id)) selectedIds.delete(id); else selectedIds.add(id);
  renderReview();
  const bar = document.getElementById('bulkBar');
  document.getElementById('selectedCount').textContent = selectedIds.size;
  bar.style.display = selectedIds.size > 0 ? 'flex' : 'none';
}

function toggleDriftRow(tr) {
  const detail = tr.nextElementSibling;
  if (!detail || !detail.classList.contains('detail-row')) return;
  const expanding = tr.classList.toggle('expanded');
  detail.style.display = expanding ? '' : 'none';
}

function togglePipeRow(tr) { tr.classList.toggle('expanded'); }

function togglePipeCountry(tr) {
  const isExpanded = tr.classList.toggle('expanded');
  const cKey = tr.dataset.pipeCountry;
  document.querySelectorAll(`tr.pipe-source-row[data-pipe-country="${CSS.escape(cKey)}"]`).forEach(row => {
    row.style.display = isExpanded ? '' : 'none';
    if (!isExpanded) row.classList.remove('expanded');
  });
  document.querySelectorAll(`tr.pipe-error-row[data-pipe-country="${CSS.escape(cKey)}"]`).forEach(row => {
    row.style.display = 'none';
  });
}

async function syncCountry(country, event) {
  if (event) event.stopPropagation();
  toast('Syncing ' + country + '…', 'info');
  try {
    const res = await fetch('/api/sync', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ countries: [country] }),
    });
    const data = await res.json();
    if (!data.success) { toast(data.message, 'danger'); return; }
    const poll = setInterval(async () => {
      try {
        const sr = await fetch('/api/sync/status');
        const ss = await sr.json();
        if (!ss.running) {
          clearInterval(poll);
          toast(ss.message || ('Sync complete for ' + country), 'info');
          loadAll();
        }
      } catch (_) {}
    }, 3000);
  } catch (err) {
    toast('Sync failed: ' + err.message, 'danger');
  }
}

async function retryJob(id, event) {
  if (event) event.stopPropagation();
  toast('Re-queuing job #' + id + '…', 'info');
  try {
    const res = await fetch('/api/retry-job/' + id, { method: 'POST', headers: {'Content-Type':'application/json'} });
    const data = await res.json();
    if (data.success) {
      toast(data.message || 'Job re-queued', 'info');
      loadAll();
      loadSourcesTab();
    } else {
      toast('Retry failed: ' + (data.message || 'unknown error'), 'danger');
    }
  } catch (err) {
    toast('Retry failed: ' + err.message, 'danger');
  }
}

function openSync() {
  document.getElementById('syncModal').classList.add('open');
  const search = document.getElementById('syncCountrySearch');
  search.value = '';
  filterSyncCountries();
  setSyncSource('both');
}
function closeSync() { document.getElementById('syncModal').classList.remove('open'); }

function toggleSort() {
  const modes = ['severity', 'time', 'confidence'];
  const labels = { severity: 'Severity ↓', time: 'Newest first', confidence: 'Confidence ↓' };
  const idx = (modes.indexOf(sortMode) + 1) % modes.length;
  sortMode = modes[idx];
  document.getElementById('sortLabel').textContent = 'Sort: ' + labels[sortMode];
  renderReview();
}

function showMoreReview() {
  reviewShowing += reviewPageSize;
  renderReview();
}

function toggleFilterPanel() {
  toast('Advanced filters coming soon', 'info');
}

async function bulkMarkReviewed() {
  if (!selectedIds.size) return;
  let count = 0;
  for (const id of selectedIds) {
    try {
      const res = await fetch('/api/approve/' + id, { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({ notes:'Marked as reviewed', assignee:'Regulift Compliance' }) });
      const data = await res.json();
      if (data.success) count++;
    } catch {}
  }
  toast('Marked ' + count + ' items as reviewed', 'ok');
  selectedIds.clear();
  document.getElementById('bulkBar').style.display = 'none';
  loadAll();
}

async function bulkEscalate() {
  if (!selectedIds.size) return;
  let count = 0;
  for (const id of selectedIds) {
    try {
      const res = await fetch('/api/escalate/' + id, { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({ notes:'Bulk escalation', assignee:'Regulift Compliance' }) });
      const data = await res.json();
      if (data.success) count++;
    } catch {}
  }
  toast('Escalated ' + count + ' items', 'warn');
  selectedIds.clear();
  document.getElementById('bulkBar').style.display = 'none';
  loadAll();
}

async function bulkReject() {
  if (!selectedIds.size) return;
  let count = 0;
  for (const id of selectedIds) {
    try {
      const res = await fetch('/api/reject/' + id, { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({ notes:'Bulk rejection', assignee:'Regulift Compliance' }) });
      const data = await res.json();
      if (data.success) count++;
    } catch {}
  }
  toast('Rejected ' + count + ' items', 'danger');
  selectedIds.clear();
  document.getElementById('bulkBar').style.display = 'none';
  loadAll();
}

// chip filter
document.getElementById('reviewChips').addEventListener('click', e => {
  const chip = e.target.closest('.chip');
  if (!chip) return;
  document.querySelectorAll('#reviewChips .chip').forEach(c => c.classList.remove('active'));
  chip.classList.add('active');
  currentFilter = chip.dataset.filter;
  reviewShowing = reviewPageSize;
  renderReview();
});

document.getElementById('driftChips').addEventListener('click', e => {
  const chip = e.target.closest('.chip');
  if (!chip) return;
  document.querySelectorAll('#driftChips .chip').forEach(c => c.classList.remove('active'));
  chip.classList.add('active');
  currentDriftFilter = chip.dataset.filter;
  filterDriftTable();
});

document.getElementById('driftBody').addEventListener('click', e => {
  const tr = e.target.closest('tr.parent');
  if (!tr) return;
  if (e.target.closest('a, button')) return;
  toggleDriftRow(tr);
});

// ═══════════════════════════════════════════════════
//  TOAST
// ═══════════════════════════════════════════════════
var toastT;
function toast(msg, kind = 'ok') {
  const t = document.getElementById('toast');
  const ic = document.getElementById('toastIc');
  document.getElementById('toastMsg').innerHTML = msg;
  t.classList.remove('danger','info','warn');
  if (kind && kind !== 'ok') t.classList.add(kind);
  ic.textContent = kind === 'danger' ? '✗' : kind === 'warn' ? '!' : kind === 'info' ? 'i' : '✓';
  t.classList.add('show');
  clearTimeout(toastT);
  toastT = setTimeout(() => t.classList.remove('show'), 3200);
}

// ═══════════════════════════════════════════════════
//  KEYBOARD SHORTCUTS
// ═══════════════════════════════════════════════════
document.addEventListener('keydown', e => {
  if (['INPUT','TEXTAREA'].includes(e.target.tagName)) return;
  if (e.metaKey || e.ctrlKey) {
    if (e.key.toLowerCase() === 'k') { e.preventDefault(); document.getElementById('globalSearch').focus(); return; }
  }
  if (e.key === '1') goTab('summary');
  if (e.key === '2') goTab('review');
  if (e.key === '3') goTab('drift');
  if (e.key === '4') goTab('audit');
  if (e.key === '5') goTab('sources');
  if (e.key === 's' || e.key === 'S') openSync();
  if (e.key === 'Escape') { closeSync(); closeNotifPanel(); }
  const activeTab = document.querySelector('.tabpanel.active');
  if (activeTab && activeTab.dataset.tab === 'review') {
    const expanded = activeTab.querySelector('.rcard:not(.collapsed)');
    if (expanded) {
      const id = parseInt(expanded.dataset.id);
      if (e.key === 'a' || e.key === 'A') { doAction('approve', id); }
      if (e.key === 'r' || e.key === 'R') { openRejectModal(id); }
      if (e.key === 'e' || e.key === 'E') { doAction('escalate', id); }
    }
  }
});

// ═══════════════════════════════════════════════════

//  NOTIFICATIONS PANEL
// ═══════════════════════════════════════════════════
var currentNotifTab = 'all';

function toggleNotifPanel() {
  const panel = document.getElementById('notifPanel');
  const isOpen = panel.classList.contains('open');
  if (isOpen) { closeNotifPanel(); return; }
  renderNotifPanel();
  panel.classList.add('open');
}

function closeNotifPanel() {
  document.getElementById('notifPanel').classList.remove('open');
}

// Close panel on outside click
document.addEventListener('click', e => {
  const wrap = document.querySelector('.notif-wrap');
  if (wrap && !wrap.contains(e.target)) closeNotifPanel();
});

function buildNotifications() {
  const notifs = [];

  // Critical review items
  DATA.queue.filter(q => (q.status === 'pending' || q.status === 'escalated') && (q.severity||'').toLowerCase() === 'critical').forEach(q => {
    notifs.push({
      type: 'critical',
      dot: 'crit',
      title: flag(q.country) + ' ' + escHtml(q.country) + ' · ' + sectionLabel(q.section),
      desc: q.status === 'escalated' ? 'Escalated — needs immediate review' : 'Critical change detected — awaiting review',
      time: timeAgo(q.created_at),
      action: () => { goTab('review'); currentFilter = 'critical'; document.querySelectorAll('#reviewChips .chip').forEach(c => c.classList.toggle('active', c.dataset.filter === 'critical')); reviewShowing = reviewPageSize; renderReview(); closeNotifPanel(); }
    });
  });

  // Escalated items (non-critical)
  DATA.queue.filter(q => q.status === 'escalated' && (q.severity||'').toLowerCase() !== 'critical').forEach(q => {
    notifs.push({
      type: 'critical',
      dot: 'warn',
      title: flag(q.country) + ' ' + escHtml(q.country) + ' · ' + sectionLabel(q.section),
      desc: 'Escalated for senior review',
      time: timeAgo(q.created_at),
      action: () => { goTab('review'); currentFilter = 'escalated'; document.querySelectorAll('#reviewChips .chip').forEach(c => c.classList.toggle('active', c.dataset.filter === 'escalated')); reviewShowing = reviewPageSize; renderReview(); closeNotifPanel(); }
    });
  });

  // Drift alerts
  DATA.drift.filter(d => d.drift_detected && d.severity === 'CRITICAL').forEach(d => {
    const ct = d.affected_sections ? d.affected_sections.length : 0;
    notifs.push({
      type: 'drift',
      dot: 'crit',
      title: flag(d.country) + ' ' + escHtml(d.country) + ' — drift alert',
      desc: ct + ' section' + (ct !== 1 ? 's' : '') + ' affected · critical severity',
      time: '',
      action: () => { goTab('drift'); closeNotifPanel(); }
    });
  });

  DATA.drift.filter(d => d.drift_detected && d.severity === 'WARNING').forEach(d => {
    const ct = d.affected_sections ? d.affected_sections.length : 0;
    notifs.push({
      type: 'drift',
      dot: 'warn',
      title: flag(d.country) + ' ' + escHtml(d.country) + ' — drift warning',
      desc: ct + ' section' + (ct !== 1 ? 's' : '') + ' changed',
      time: '',
      action: () => { goTab('drift'); closeNotifPanel(); }
    });
  });

  // System notifications
  const m = DATA.metrics;
  if (m.crawl_failures > 0) {
    notifs.push({
      type: 'system',
      dot: m.crawl_failures > 10 ? 'crit' : 'warn',
      title: m.crawl_failures + ' crawl failure' + (m.crawl_failures !== 1 ? 's' : ''),
      desc: 'Source endpoints unreachable or returning errors',
      time: m.last_successful_sync ? 'last sync ' + timeAgo(m.last_successful_sync) : '',
      action: () => { goTab('sources'); closeNotifPanel(); }
    });
  }

  const failedJobs = DATA.jobs.filter(j => j.state === 'failed');
  if (failedJobs.length) {
    notifs.push({
      type: 'system',
      dot: 'crit',
      title: failedJobs.length + ' pipeline job' + (failedJobs.length !== 1 ? 's' : '') + ' failed',
      desc: 'Ingestion pipeline errors need attention',
      time: '',
      action: () => { goTab('sources'); closeNotifPanel(); }
    });
  }

  if (m.pending_reviews > 20) {
    notifs.push({
      type: 'system',
      dot: 'info',
      title: 'Review queue backlog',
      desc: m.pending_reviews + ' items pending — consider bulk review',
      time: '',
      action: () => { goTab('review'); closeNotifPanel(); }
    });
  }

  return notifs;
}

function renderNotifPanel() {
  const notifs = buildNotifications();
  const filtered = currentNotifTab === 'all' ? notifs : notifs.filter(n => n.type === currentNotifTab);

  // Update tab counts
  const critCount = notifs.filter(n => n.type === 'critical').length;
  const driftCount = notifs.filter(n => n.type === 'drift').length;
  const sysCount = notifs.filter(n => n.type === 'system').length;
  document.getElementById('ntAll').textContent = notifs.length;
  document.getElementById('ntCrit').textContent = critCount;
  document.getElementById('ntDrift').textContent = driftCount;
  document.getElementById('ntSystem').textContent = sysCount;
  document.getElementById('notifTotalBadge').textContent = notifs.length;

  const body = document.getElementById('notifBody');
  if (!filtered.length) {
    body.innerHTML = '<div class="notif-empty">No notifications right now</div>';
    return;
  }

  body.innerHTML = filtered.map((n, i) => `
    <div class="notif-item" data-nidx="${i}">
      <div class="notif-dot ${n.dot}"></div>
      <div class="notif-content">
        <div class="notif-title">${n.title}</div>
        <div class="notif-desc">${escHtml(n.desc)}</div>
        ${n.time ? '<div class="notif-time">' + n.time + '</div>' : ''}
      </div>
    </div>
  `).join('');

  // Wire clicks
  body.querySelectorAll('.notif-item').forEach((el, i) => {
    el.addEventListener('click', () => { if (filtered[i] && filtered[i].action) filtered[i].action(); });
  });
}

// Tab switching
document.getElementById('notifTabs').addEventListener('click', e => {
  const tab = e.target.closest('.notif-tab');
  if (!tab) return;
  document.querySelectorAll('#notifTabs .notif-tab').forEach(t => t.classList.remove('active'));
  tab.classList.add('active');
  currentNotifTab = tab.dataset.ntab;
  renderNotifPanel();
});

// ═══════════════════════════════════════════════════
//  SEARCH
// ═══════════════════════════════════════════════════
document.getElementById('globalSearch').addEventListener('input', e => {
  const q = e.target.value.toLowerCase().trim();
  if (!q) { renderAll(); return; }

  // Find which tab has matches and count them
  const activeTab = document.querySelector('.tabpanel.active');
  const activeTabName = activeTab ? activeTab.dataset.tab : 'review';

  // Search review cards
  let reviewHits = 0;
  document.querySelectorAll('.rcard').forEach(card => {
    const match = card.textContent.toLowerCase().includes(q);
    card.style.display = match ? '' : 'none';
    if (match) reviewHits++;
  });

  // Search drift rows
  let driftHits = 0;
  document.querySelectorAll('#driftBody tr.parent').forEach(tr => {
    const match = tr.textContent.toLowerCase().includes(q);
    tr.style.display = match ? '' : 'none';
    const next = tr.nextElementSibling;
    if (next && next.classList.contains('detail-row')) next.style.display = match && tr.classList.contains('expanded') ? '' : 'none';
    if (match) driftHits++;
  });

  // Search audit rows
  let auditHits = 0;
  document.querySelectorAll('.audit-row').forEach(row => {
    const match = row.textContent.toLowerCase().includes(q);
    row.style.display = match ? '' : 'none';
    if (match) auditHits++;
  });

  // Search pipeline rows
  let pipeHits = 0;
  document.querySelectorAll('.pipe-table tbody tr').forEach(tr => {
    const match = tr.textContent.toLowerCase().includes(q);
    tr.style.display = match ? '' : 'none';
    if (match) pipeHits++;
  });

  // Auto-switch to tab with most matches if current tab has none
  const counts = { review: reviewHits, drift: driftHits, audit: auditHits, pipeline: pipeHits };
  if (counts[activeTabName] === 0) {
    const best = Object.entries(counts).sort((a, b) => b[1] - a[1])[0];
    if (best[1] > 0) goTab(best[0]);
  }
});

// ═══════════════════════════════════════════════════

// ═══════════════════════════════════════════════════
//  INIT
// ═══════════════════════════════════════════════════
// ═══════════════════════════════════════════════════
//  INIT
// ═══════════════════════════════════════════════════
loadAll();
loadSourcesTab();
