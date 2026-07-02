// ops-tabs.js — Summary, drift, audit, pipeline tab rendering

// ═══════════════════════════════════════════════════
//  MANAGER METRICS
// ═══════════════════════════════════════════════════
function renderMetrics() {
  const m = DATA.metrics;
  const lastSync = m.last_successful_sync ? timeAgo(m.last_successful_sync) : 'never';

  document.getElementById('lastSyncLabel').textContent = 'Last sync ' + lastSync;
  const notifEl = document.getElementById('notifCount');
  const totalNotifs = buildNotifications().length;
  notifEl.textContent = totalNotifs;
  notifEl.style.display = totalNotifs > 0 ? '' : 'none';
}

// ═══════════════════════════════════════════════════
//  SUMMARY TAB
// ═══════════════════════════════════════════════════
function renderSummary() {
  const m = DATA.metrics;
  let queue = DATA.queue || [];
  let drift = DATA.drift || [];
  if (activeCountryFilter) { queue = queue.filter(q => q.country === activeCountryFilter); drift = drift.filter(d => d.country === activeCountryFilter); }
  if (triageFilters.severity) { queue = queue.filter(q => (q.severity||'').toLowerCase() === triageFilters.severity); drift = drift.filter(d => (d.severity||'').toLowerCase() === triageFilters.severity); }
  if (triageFilters.status) queue = queue.filter(q => (q.status||'').toLowerCase() === triageFilters.status);
  const jobs = activeCountryFilter ? (DATA.jobs || []).filter(j => j.country === activeCountryFilter) : (DATA.jobs || []);

  const pending = queue.filter(i => i.status === 'pending');
  const critical = pending.filter(i => (i.severity||'').toLowerCase() === 'critical');
  const avgConf = m.avg_confidence != null ? m.avg_confidence + '%' : '—';
  const failures = jobs.filter(j => j.state === 'failed');
  const lastSync = m.last_successful_sync ? timeAgo(m.last_successful_sync) : 'never';

  // Coverage stats
  const covData = DATA.coverage || {};
  const covCountries = covData.countries || {};
  const covKeys = Object.keys(covCountries);
  const fullyCovered = covKeys.filter(c => covCountries[c].pct === 100).length;
  const totalCovCountries = covKeys.length || (m.trusted_source_count || 0);
  const avgCovPct = covKeys.length
    ? Math.round(covKeys.reduce((s, c) => s + covCountries[c].pct, 0) / covKeys.length)
    : null;
  const covKpiClass = avgCovPct === null ? 'info' : avgCovPct === 100 ? 'ok' : avgCovPct >= 80 ? 'warn' : 'crit';

  // KPIs
  document.getElementById('sumKpis').innerHTML = `
    <div class="sum-kpi ${covKpiClass}">
      <div class="strip"></div>
      <div class="kpi-label">Countries covered</div>
      <div class="kpi-value">${fullyCovered} / ${totalCovCountries}</div>
      <div class="kpi-sub">${avgCovPct !== null ? avgCovPct + '% avg core coverage' : (m.sources_monitored || 0) + ' source endpoints'}</div>
    </div>
    <div class="sum-kpi ${critical.length > 0 ? 'crit' : 'info'}">
      <div class="strip"></div>
      <div class="kpi-label">Pending reviews</div>
      <div class="kpi-value">${pending.length}</div>
      <div class="kpi-sub">${critical.length} critical</div>
    </div>
    <div class="sum-kpi info">
      <div class="strip"></div>
      <div class="kpi-label">Sources monitored</div>
      <div class="kpi-value">${m.sources_monitored || 0}</div>
      <div class="kpi-sub">${m.trusted_source_count || 0} countries</div>
    </div>
    <div class="sum-kpi ${m.avg_confidence != null && m.avg_confidence < 80 ? 'warn' : 'ok'}">
      <div class="strip"></div>
      <div class="kpi-label">Avg confidence</div>
      <div class="kpi-value">${avgConf}</div>
      <div class="kpi-sub">AI extraction</div>
    </div>
    <div class="sum-kpi ${failures.length > 0 ? 'crit' : 'ok'}">
      <div class="strip"></div>
      <div class="kpi-label">Last sync</div>
      <div class="kpi-value" style="font-size:20px;">${lastSync}</div>
      <div class="kpi-sub">${failures.length} failure${failures.length !== 1 ? 's' : ''}</div>
    </div>
  `;

  // Donut
  const critDrift = drift.filter(d => d.severity === 'CRITICAL').length;
  const warnDrift = drift.filter(d => d.severity === 'WARNING').length;
  const stableDrift = drift.filter(d => !d.drift_detected || d.severity === 'NONE' || d.severity === 'INFO').length;
  const total = drift.length;

  document.getElementById('sumDonutTotal').textContent = total;
  document.getElementById('sumDonutLegend').innerHTML = `
    <span class="leg"><span class="dot" style="background:var(--crit);"></span>${critDrift} Critical</span>
    <span class="leg"><span class="dot" style="background:var(--warn);"></span>${warnDrift} Warning</span>
    <span class="leg"><span class="dot" style="background:var(--ok);"></span>${stableDrift} Stable</span>
  `;

  const canvas = document.getElementById('sumDonut');
  const ctx = canvas.getContext('2d');
  const dpr = window.devicePixelRatio || 1;
  canvas.width = 180 * dpr;
  canvas.height = 180 * dpr;
  ctx.scale(dpr, dpr);
  const cx = 90, cy = 90, r = 70, lw = 22;
  ctx.clearRect(0, 0, 180, 180);
  const segments = [
    { val: critDrift, color: getComputedStyle(document.documentElement).getPropertyValue('--crit').trim() },
    { val: warnDrift, color: getComputedStyle(document.documentElement).getPropertyValue('--warn').trim() },
    { val: stableDrift, color: getComputedStyle(document.documentElement).getPropertyValue('--ok').trim() },
  ];
  if (total === 0) {
    ctx.beginPath(); ctx.arc(cx, cy, r, 0, Math.PI * 2);
    ctx.strokeStyle = getComputedStyle(document.documentElement).getPropertyValue('--paper-line').trim();
    ctx.lineWidth = lw; ctx.stroke();
  } else {
    let angle = -Math.PI / 2;
    const gap = 0.04;
    segments.forEach(seg => {
      if (seg.val === 0) return;
      const sweep = (seg.val / total) * Math.PI * 2 - gap;
      if (sweep <= 0) return;
      ctx.beginPath();
      ctx.arc(cx, cy, r, angle + gap / 2, angle + sweep + gap / 2);
      ctx.strokeStyle = seg.color;
      ctx.lineWidth = lw;
      ctx.lineCap = 'round';
      ctx.stroke();
      angle += (seg.val / total) * Math.PI * 2;
    });
  }

  // Critical reviews list
  const critItems = critical.slice(0, 5);
  const critListEl = document.getElementById('sumCritList');
  document.getElementById('sumCritCt').textContent = critical.length;
  if (critItems.length === 0) {
    critListEl.innerHTML = '<div class="card-empty">No critical items — all clear</div>';
  } else {
    critListEl.innerHTML = critItems.map(i => `
      <div class="sum-action-item" onclick="goTab('review'); metricClick('critical');">
        <span class="sev-dot crit"></span>
        <div class="item-info">
          <div class="item-title">${flag(i.country)} ${escHtml(i.country)} · ${sectionLabel(i.section)}</div>
          <div class="item-sub">${escHtml(truncate(i.new_value || i.change_summary || '', 60))}</div>
        </div>
        <span class="item-time">${i.created_at ? timeAgo(i.created_at) : ''}</span>
      </div>
    `).join('');
  }

  // Pipeline failures list
  const failItems = failures.slice(0, 5);
  const failListEl = document.getElementById('sumFailList');
  document.getElementById('sumFailCt').textContent = failures.length;
  if (failItems.length === 0) {
    failListEl.innerHTML = '<div class="card-empty">No pipeline failures</div>';
  } else {
    failListEl.innerHTML = failItems.map(j => `
      <div class="sum-action-item" onclick="goTab('sources'); document.getElementById('srcSearch').value = '${escAttr(j.country)}'; renderUnifiedSources();">
        <span class="sev-dot fail"></span>
        <div class="item-info">
          <div class="item-title">${flag(j.country)} ${escHtml(j.country)}</div>
          <div class="item-sub">${escHtml(truncate(j.failure_reason || j.error || j.state || '', 60))}</div>
        </div>
        <span class="item-time">${j.failed_at ? timeAgo(j.failed_at) : (j.started_at ? timeAgo(j.started_at) : '')}</span>
      </div>
    `).join('');
  }

  // Country coverage grid
  const sorted = [...drift].sort((a, b) => {
    const covA = covCountries[a.country];
    const covB = covCountries[b.country];
    const pctA = covA ? covA.pct : 100;
    const pctB = covB ? covB.pct : 100;
    if (pctA !== pctB) return pctA - pctB;
    const ord = { CRITICAL: 0, WARNING: 1, INFO: 2, NONE: 3 };
    const cmp = (ord[a.severity] ?? 3) - (ord[b.severity] ?? 3);
    return cmp !== 0 ? cmp : a.country.localeCompare(b.country);
  });
  document.getElementById('sumCovGrid').innerHTML = sorted.map(d => {
    const cov = covCountries[d.country];
    const pct = cov ? cov.pct : null;
    const cls = pct !== null
      ? (pct === 100 ? 'ok' : pct >= 80 ? 'warn' : 'crit')
      : (d.severity === 'CRITICAL' ? 'crit' : d.severity === 'WARNING' ? 'warn' : 'ok');
    const covTip = cov
      ? `${cov.covered}/${cov.total} core sections (${cov.verified} verified)` + (cov.missing.length ? ` — missing: ${cov.missing.join(', ')}` : '')
      : '';
    const title = `${d.country}: ${pct !== null ? pct + '% coverage' : (d.drift_detected ? d.severity : 'Stable')}${covTip ? '\n' + covTip : ''}`;
    const pctLabel = pct !== null ? `<span class="cov-pct">${pct}%</span>` : '';
    return `<div class="sum-cov-chip ${cls}" onclick="openDriftForCountry('${escAttr(d.country)}')" title="${escAttr(title)}">
      <span class="flag">${flag(d.country)}</span>
      <span>${escHtml(d.country)}</span>
      ${pctLabel}
      <span class="status-dot"></span>
    </div>`;
  }).join('');
}

// ═══════════════════════════════════════════════════
//  DRIFT PILLS (manager strip) — top 5 + view more
// ═══════════════════════════════════════════════════
function renderDriftPills() {
  const el = document.getElementById('mgrPills');
  if (!el) return; // manager strip removed — country selection logic preserved below
  if (!DATA.drift.length) { el.innerHTML = '<span class="label">No drift data</span>'; return; }

  const sorted = [...DATA.drift].sort((a,b) => {
    const ord = {CRITICAL:0,WARNING:1,INFO:2,NONE:3};
    return (ord[a.severity]||3) - (ord[b.severity]||3);
  });

  // On first load, auto-select top 5 with drift
  if (!selectedDriftCountries.size) {
    sorted.filter(d => d.drift_detected).slice(0, 5).forEach(d => selectedDriftCountries.add(d.country));
    if (!selectedDriftCountries.size) sorted.slice(0, 5).forEach(d => selectedDriftCountries.add(d.country));
  }

  // Ensure the actively filtered country always appears in the strip
  if (activeCountryFilter && sorted.some(d => d.country === activeCountryFilter)) {
    selectedDriftCountries.add(activeCountryFilter);
  }
  // Always show Singapore in the strip when drift data exists for it
  if (sorted.some(d => d.country === 'Singapore')) {
    selectedDriftCountries.add('Singapore');
  }

  let visible = sorted.filter(d => selectedDriftCountries.has(d.country));
  // Pin Singapore first, then the active filter, then everything else
  const pinOrder = (c) => c === 'Singapore' ? 0 : (c === activeCountryFilter ? 1 : 2);
  visible = visible.slice().sort((a, b) => pinOrder(a.country) - pinOrder(b.country));
  const remainingCount = sorted.length - visible.length;

  let html = '<span class="label">Country</span>';
  visible.forEach(d => {
    const cls = d.country === activeCountryFilter ? 'selected' : '';
    html += `<span class="country-pill ${cls}" data-country="${escAttr(d.country)}" onclick="toggleCountryFilter(this)" title="Filter by ${escHtml(d.country)}" style="cursor:pointer"><span class="dot"></span><span class="flag">${flag(d.country)}</span> ${escHtml(d.country)}</span>`;
  });
  if (remainingCount > 0) {
    html += `<span class="country-pill more" onclick="openDriftModal()">+${remainingCount} more →</span>`;
  }
  el.innerHTML = html;
}

function toggleCountryFilter(el) {
  const country = el.dataset.country;
  activeCountryFilter = (activeCountryFilter === country) ? null : country;
  document.getElementById('globalTriageCountry').value = activeCountryFilter || '';
  updateTriageCount();
  renderSummary();
  renderDriftPills();
  renderPipeline();
  renderReview();
  renderDrift();
  renderAudit();
}

// ═══════════════════════════════════════════════════
//  DRIFT COUNTRY MODAL
// ═══════════════════════════════════════════════════
function openDriftModal() {
  const grid = document.getElementById('driftCountryGrid');
  const sorted = [...DATA.drift].sort((a,b) => {
    const ord = {CRITICAL:0,WARNING:1,INFO:2,NONE:3};
    return (ord[a.severity]||3) - (ord[b.severity]||3);
  });

  grid.innerHTML = sorted.map(d => {
    const checked = selectedDriftCountries.has(d.country) ? 'checked' : '';
    const sevCls = d.severity === 'CRITICAL' ? 'crit' : d.severity === 'WARNING' ? 'warn' : '';
    const ct = d.affected_sections ? d.affected_sections.length : 0;
    return `<label class="country-cb ${checked}" data-country="${escAttr(d.country)}">
      <span class="box"></span>
      <span class="flag">${flag(d.country)}</span>
      <span class="name">${escHtml(d.country)}</span>
      ${ct ? '<span class="last">' + ct + ' issue' + (ct!==1?'s':'') + '</span>' : '<span class="last" style="color:var(--ok);">stable</span>'}
    </label>`;
  }).join('');

  grid.querySelectorAll('.country-cb').forEach(cb => {
    cb.addEventListener('click', e => { e.preventDefault(); cb.classList.toggle('checked'); updateDriftModalCount(); });
  });
  updateDriftModalCount();
  document.getElementById('driftCountryModal').classList.add('open');
}

function closeDriftModal() { document.getElementById('driftCountryModal').classList.remove('open'); }

function updateDriftModalCount() {
  const n = document.querySelectorAll('#driftCountryGrid .country-cb.checked').length;
  document.getElementById('driftModalCount').textContent = n;
}

function toggleAllDriftCountries() {
  const items = document.querySelectorAll('#driftCountryGrid .country-cb');
  const allOn = [...items].every(i => i.classList.contains('checked'));
  items.forEach(i => i.classList.toggle('checked', !allOn));
  updateDriftModalCount();
}

function applyDriftSelection() {
  selectedDriftCountries.clear();
  document.querySelectorAll('#driftCountryGrid .country-cb.checked').forEach(cb => {
    selectedDriftCountries.add(cb.dataset.country);
  });
  renderDriftPills();
  closeDriftModal();
}

// ═══════════════════════════════════════════════════

//  DRIFT TAB
// ═══════════════════════════════════════════════════
function renderDrift() {
  const body = document.getElementById('driftBody');

  let items = activeCountryFilter ? DATA.drift.filter(d => d.country === activeCountryFilter) : DATA.drift;
  if (triageFilters.severity) items = items.filter(d => (d.severity||'').toLowerCase() === triageFilters.severity);
  const allCount = items.length;
  const critCount = items.filter(d=>d.severity==='CRITICAL').length;
  const warnCount = items.filter(d=>d.severity==='WARNING').length;
  const stableCount = items.filter(d=>!d.drift_detected || d.severity==='NONE' || d.severity==='INFO').length;

  document.getElementById('driftAll').textContent = allCount;
  document.getElementById('driftCritCt').textContent = critCount;
  document.getElementById('driftWarnCt').textContent = warnCount;
  document.getElementById('driftStableCt').textContent = stableCount;

  if (!items.length) {
    body.innerHTML = '';
    document.getElementById('driftEmpty').style.display = 'block';
    return;
  }
  document.getElementById('driftEmpty').style.display = 'none';

  items = [...items].sort((a,b) => {
    const ord = {CRITICAL:0,WARNING:1,INFO:2,NONE:3};
    return (ord[a.severity]||3) - (ord[b.severity]||3);
  });

  // Build per-country last sync lookup from ingestion jobs
  const lastSyncByCountry = {};
  (DATA.jobs || []).forEach(j => {
    const ts = j.reconciled_at || j.fetched_at || j.failed_at || j.queued_at;
    if (!ts || !j.country) return;
    if (!lastSyncByCountry[j.country] || ts > lastSyncByCountry[j.country].ts) {
      lastSyncByCountry[j.country] = { ts, state: j.state };
    }
  });

  const covCountries = (DATA.coverage || {}).countries || {};

  body.innerHTML = items.map(d => {
    const sevCls = d.severity === 'CRITICAL' ? 'crit' : d.severity === 'WARNING' ? 'warn' : 'stable';
    const sections = d.affected_sections || [];
    const critSec = sections.filter(s=>s.severity==='CRITICAL').length;
    const warnSec = sections.filter(s=>s.severity==='WARNING').length;
    const infoSec = sections.filter(s=>s.severity==='INFO').length;

    const cov = covCountries[d.country];
    const covPct = cov ? cov.pct : null;
    const covCls = covPct === null ? '' : covPct === 100 ? 'ok' : covPct >= 80 ? 'warn' : 'crit';
    const covTip = cov ? `${cov.covered}/${cov.total} core sections` + (cov.missing.length ? ` — missing: ${cov.missing.join(', ')}` : '') : '';

    let badges = '';
    if (critSec) badges += `<span class="badge crit">${critSec} critical</span>`;
    if (warnSec) badges += `<span class="badge major">${warnSec} warning</span>`;
    if (infoSec) badges += `<span class="badge minor">${infoSec} info</span>`;
    if (!badges) badges = '<span style="color:var(--ink-3); font-style:italic;">no changes</span>';

    const syncInfo = lastSyncByCountry[d.country];
    const syncDisplay = syncInfo
      ? `<span title="${fmtTime(syncInfo.ts)}">${timeAgo(syncInfo.ts)}</span>`
      : '<span style="color:var(--ink-4); font-style:italic;">never</span>';

    let detailHtml = '';
    if (sections.length) {
      detailHtml = `<tr class="detail-row"><td colspan="8"><div class="drift-row-inner">${
        sections.map(s => {
          const sCls = s.severity === 'CRITICAL' ? 'crit' : s.severity === 'WARNING' ? 'major' : 'minor';
          return `<div class="section-card ${sCls}">
            <div class="name">${sectionLabel(s.section)} <span class="badge ${sCls}"><span class="d"></span>${s.severity}</span></div>
            <div class="why">${escHtml(s.evidence || s.recommended_action || '')}</div>
            <div class="foot"><span>${s.drift_type || ''}</span><a data-country="${escHtml(d.country)}" onclick="openQueueForCountry(this.dataset.country); event.stopPropagation();">open queue →</a></div>
          </div>`;
        }).join('')
      }</div></td></tr>`;
    }

    return `
      <tr class="parent">
        <td>${sections.length ? '<span class="expand-btn"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 12 15 18 9"/></svg></span>' : ''}</td>
        <td><div class="country-cell"><span class="flag">${flag(d.country)}</span><div class="info"><span class="name">${escHtml(d.country)}</span></div></div></td>
        <td title="${escAttr(covTip)}"><span class="drift-sev ${covCls}" style="font-family:var(--font-mono);font-size:12px;">${covPct !== null ? covPct + '%' : '—'}</span></td>
        <td><span class="mono" style="font-size:12px; color:var(--ink-3); white-space:nowrap;">${syncDisplay}</span></td>
        <td><span class="drift-sev ${sevCls}"><span class="d"></span><span class="lbl">${d.drift_detected ? d.severity : 'Stable'}</span></span></td>
        <td>${sections.length} section${sections.length!==1?'s':''}</td>
        <td><div class="dct-counts">${badges}</div></td>
        <td><span style="color:var(--ink-2);">${escHtml(truncate(d.recommended_action||'—', 60))}</span></td>
      </tr>
      ${detailHtml}`;
  }).join('');
}

var currentDriftFilter = 'all';

function filterDrift() {
  filterDriftTable();
}

function filterDriftTable() {
  const q = document.getElementById('driftSearch').value.toLowerCase().trim();
  const filter = currentDriftFilter;
  document.querySelectorAll('#driftBody tr.parent').forEach(tr => {
    const name = tr.querySelector('.country-cell .name');
    const nameMatch = !q || (name && name.textContent.toLowerCase().includes(q));

    const sevEl = tr.querySelector('.drift-sev .lbl');
    const sev = sevEl ? sevEl.textContent.trim().toUpperCase() : '';
    let sevMatch = true;
    if (filter === 'CRITICAL') sevMatch = sev === 'CRITICAL';
    else if (filter === 'WARNING') sevMatch = sev === 'WARNING';
    else if (filter === 'stable') sevMatch = sev === 'STABLE' || sev === 'NONE' || sev === 'INFO';

    const show = nameMatch && sevMatch;
    tr.style.display = show ? '' : 'none';
    const next = tr.nextElementSibling;
    if (next && next.classList.contains('detail-row')) next.style.display = show && tr.classList.contains('expanded') ? '' : 'none';
  });
}

// ═══════════════════════════════════════════════════
//  AUDIT TAB
// ═══════════════════════════════════════════════════
function renderAudit() {
  const el = document.getElementById('auditTimeline');
  let items = DATA.audit;
  if (activeCountryFilter) items = items.filter(a => a.country === activeCountryFilter);
  if (triageFilters.severity) items = items.filter(a => (a.severity||'').toLowerCase() === triageFilters.severity);
  if (triageFilters.status) items = items.filter(a => (a.status||'').toLowerCase() === triageFilters.status);
  document.getElementById('auditCount').textContent = items.length;

  if (!items.length) {
    el.innerHTML = '';
    document.getElementById('auditEmpty').style.display = 'block';
    return;
  }
  document.getElementById('auditEmpty').style.display = 'none';

  el.innerHTML = items.map(a => {
    const decClass = a.decision === 'approved' ? 'human' : a.decision === 'rejected' ? 'reject' : a.decision === 'escalated' ? 'escalate' : 'detect';
    const decBadge = a.decision === 'approved' ? 'minor' : a.decision === 'rejected' ? 'crit' : a.decision === 'escalated' ? 'major' : 'info';

    return `
    <div class="audit-row ${decClass}">
      <div class="ts"><b>${fmtTime(a.timestamp)}</b>${timeAgo(a.timestamp)}</div>
      <div class="dot-wrap"><div class="dot"></div></div>
      <div class="audit-event">
        <div class="head">
          <span class="who">${escHtml(a.reviewer_assignee || 'System')}</span>
          <span class="action">${escHtml(a.decision || a.action || '')}</span>
          <span class="badge ${decBadge}"><span class="d"></span>${sevLabel(a.decision || a.action)}</span>
        </div>
        <div class="target">${flag(a.country)} ${escHtml(a.country)} · <b>${sectionLabel(a.section)}</b></div>
        ${(a.old_value || a.new_value) ? `<div class="audit-diff">
          <div class="audit-diff-side audit-diff-old"><div class="audit-diff-label">Before</div>${escHtml(a.old_value || '—')}</div>
          <div class="audit-diff-side audit-diff-new"><div class="audit-diff-label">After</div>${escHtml(a.new_value || '—')}</div>
        </div>` : ''}
        ${a.reviewer_comment ? '<div class="note">' + escHtml(a.reviewer_comment) + '</div>' : ''}
        ${a.reviewer_rationale ? '<div class="note"><em>' + escHtml(a.reviewer_rationale) + '</em></div>' : ''}
      </div>
      <div class="right">
        <span class="badge neut">${a.decision || a.action}</span>
      </div>
    </div>`;
  }).join('');
}

// ═══════════════════════════════════════════════════
//  PIPELINE TAB
// ═══════════════════════════════════════════════════
const STAGES = ['queued','fetched','normalized','extracted','reconciled'];

function jobStagesHtml(j) {
  const isFailed = j.state === 'failed';
  const curStage = STAGES.indexOf(j.state);
  let failStage = -1;
  if (isFailed) {
    if (j.reconciled_at) failStage = 4;
    else if (j.extracted_at) failStage = 3;
    else if (j.normalized_at) failStage = 2;
    else if (j.fetched_at) failStage = 1;
    else failStage = 0;
  }
  return STAGES.map((s, idx) => {
    let cls = '';
    if (isFailed) {
      if (idx < failStage) cls = 'done';
      else if (idx === failStage) cls = 'fail';
    } else if (j.state === 'reconciled') {
      cls = 'done';
    } else {
      if (idx < curStage) cls = 'done';
      else if (idx === curStage) cls = 'cur';
    }
    return `<div class="stage ${cls}"></div>`;
  }).join('');
}

function countryOverallStatus(cJobs) {
  const hasFailed = cJobs.some(j => j.state === 'failed');
  const hasRunning = cJobs.some(j => ['queued','fetched','normalized','extracted'].includes(j.state));
  const allDone = cJobs.every(j => j.state === 'reconciled');
  if (hasFailed) return { cls: 'fail', label: 'Has failures' };
  if (hasRunning) return { cls: 'run', label: 'Processing' };
  if (allDone) return { cls: 'ok', label: 'All reconciled' };
  return { cls: 'queue', label: 'Queued' };
}

function renderPipeline() {
  let jobs = DATA.jobs;
  if (activeCountryFilter) {
    jobs = jobs.filter(j => j.country === activeCountryFilter);
  }
  if (triageFilters.status === 'pending') jobs = jobs.filter(j => ['queued','fetched','normalized','extracted'].includes(j.state));
  else if (triageFilters.status === 'escalated') jobs = jobs.filter(j => j.state === 'failed');

  const reconciled = jobs.filter(j=>j.state==='reconciled').length;
  const running = jobs.filter(j=>['queued','fetched','normalized','extracted'].includes(j.state)).length;
  const failed = jobs.filter(j=>j.state==='failed').length;

  // Collect all countries from every data source
  const allCountries = new Set();
  DATA.drift.forEach(d => { if (d.country) allCountries.add(d.country); });
  DATA.queue.forEach(q => { if (q.country) allCountries.add(q.country); });
  jobs.forEach(j => { if (j.country) allCountries.add(j.country); });

  const countriesWithJobs = new Set(jobs.filter(j => j.country).map(j => j.country));
  const notSynced = allCountries.size - countriesWithJobs.size;

  document.getElementById('pipeSummary').innerHTML = `
    <div class="pipe-card ok"><div class="strip"></div><div class="v">${reconciled}</div><div class="l">Reconciled</div></div>
    <div class="pipe-card ${running?'run':'queue'}"><div class="strip"></div><div class="v">${running}</div><div class="l">In progress</div></div>
    <div class="pipe-card ${failed?'fail':'ok'}"><div class="strip"></div><div class="v">${failed}</div><div class="l">Failed</div></div>
    <div class="pipe-card queue"><div class="strip"></div><div class="v">${allCountries.size}</div><div class="l">Countries</div></div>
  `;

  const body = document.getElementById('pipeBody');
  if (!allCountries.size) {
    body.innerHTML = '';
    document.getElementById('pipeEmpty').style.display = 'block';
    return;
  }
  document.getElementById('pipeEmpty').style.display = 'none';

  const byCountry = {};
  jobs.forEach(j => {
    const c = j.country || 'Unknown';
    if (!byCountry[c]) byCountry[c] = [];
    byCountry[c].push(j);
  });

  const countryKeys = [...allCountries].sort((a, b) => {
    if (a === 'Unknown') return 1;
    if (b === 'Unknown') return -1;
    const aFail = (byCountry[a] || []).some(j => j.state === 'failed');
    const bFail = (byCountry[b] || []).some(j => j.state === 'failed');
    if (aFail !== bFail) return aFail ? -1 : 1;
    const aHasJobs = byCountry[a] ? 1 : 0;
    const bHasJobs = byCountry[b] ? 1 : 0;
    if (aHasJobs !== bHasJobs) return bHasJobs - aHasJobs;
    return a.localeCompare(b);
  });

  let html = '';
  countryKeys.forEach(country => {
    const cJobs = byCountry[country] || [];
    const cKey = escAttr(country);
    const hasJobs = cJobs.length > 0;

    if (!hasJobs) {
      html += `<tr class="pipe-country-row" data-pipe-country="${cKey}">
        <td></td>
        <td><div class="country-cell"><span class="flag">${flag(country)}</span><span class="name">${escHtml(country)}</span></div></td>
        <td><span class="pip-status queue"><span class="d"></span>Not synced</span></td>
        <td><span class="source-ct muted">0 sources</span></td>
        <td><span class="mono muted">—</span></td>
        <td style="text-align:right;">
          <button class="btn btn-ghost" onclick="syncCountry('${cKey}', event)">Sync</button>
        </td>
      </tr>`;
      return;
    }

    const status = countryOverallStatus(cJobs);
    const hasFail = cJobs.some(j => j.state === 'failed');
    const cReconciled = cJobs.filter(j => j.state === 'reconciled').length;
    const cFailed = cJobs.filter(j => j.state === 'failed').length;
    const lastTime = cJobs.reduce((latest, j) => {
      const t = j.failed_at || j.reconciled_at || j.extracted_at || j.normalized_at || j.fetched_at || j.queued_at;
      return t > latest ? t : latest;
    }, '');

    html += `<tr class="pipe-country-row ${hasFail ? 'has-fail' : ''}" data-pipe-country="${cKey}" onclick="togglePipeCountry(this)">
      <td><button class="expand-btn"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 12 15 18 9"/></svg></button></td>
      <td><div class="country-cell"><span class="flag">${flag(country)}</span><span class="name">${escHtml(country)}</span></div></td>
      <td><span class="pip-status ${status.cls}"><span class="d"></span>${status.label}</span></td>
      <td>
        <span class="source-ct">${cJobs.length} source${cJobs.length !== 1 ? 's' : ''}</span>
        ${cReconciled ? ' <span class="badge minor" style="margin-left:4px;">' + cReconciled + ' ok</span>' : ''}
        ${cFailed ? ' <span class="badge crit" style="margin-left:4px;">' + cFailed + ' failed</span>' : ''}
      </td>
      <td><span class="mono" style="color:var(--ink-3);">${timeAgo(lastTime)}</span></td>
      <td style="text-align:right;">
        <button class="btn btn-ghost" onclick="syncCountry('${cKey}', event)">Sync</button>
      </td>
    </tr>`;

    cJobs.forEach(j => {
      const isFailed = j.state === 'failed';
      const statusCls = isFailed ? 'fail' : j.state === 'reconciled' ? 'ok' : 'run';
      const statusLabel = isFailed ? 'Failed' : j.state === 'reconciled' ? 'Done' : j.state.charAt(0).toUpperCase() + j.state.slice(1);
      const jLastTime = j.failed_at || j.reconciled_at || j.extracted_at || j.normalized_at || j.fetched_at || j.queued_at;

      html += `<tr class="pipe-source-row ${isFailed ? 'fail-row' : ''}" data-pipe-country="${cKey}" style="display:none" ${isFailed ? 'onclick="togglePipeRow(this)"' : ''}>
        <td></td>
        <td class="pipe-source"><span class="host">${extractHost(j.source_url)}</span><span class="path">${extractPath(j.source_url)}</span></td>
        <td><span class="pip-status ${statusCls}"><span class="d"></span>${statusLabel}</span></td>
        <td><div class="stages">${jobStagesHtml(j)}</div></td>
        <td><span class="mono" style="color:var(--ink-3);">${timeAgo(jLastTime)}</span></td>
        <td style="text-align:right;">
          ${isFailed ? `<button class="btn btn-danger" onclick="retryJob(${j.id}, event)">Retry</button>` : ''}
          ${j.state === 'reconciled' ? '<button class="btn btn-ghost" onclick="goTab(\'review\')">View changes</button>' : ''}
        </td>
      </tr>`;
      if (isFailed) {
        html += `<tr class="pipe-error-row" data-pipe-country="${cKey}" style="display:none"><td colspan="6">
          <div class="pipe-error-box">
            <div class="pipe-error-title">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
              <span>Pipeline failure</span>
            </div>
            <div class="pipe-error-msg">${escHtml(j.failure_reason || 'Unknown error')}</div>
          </div>
        </td></tr>`;
      }
    });
  });

  body.innerHTML = html;
}

// ═══════════════════════════════════════════════════
