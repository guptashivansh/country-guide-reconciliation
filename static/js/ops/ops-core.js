// ops-core.js — Constants, state, utilities, data loading

// ═══════════════════════════════════════════════════
//  CONSTANTS & STATE
// ═══════════════════════════════════════════════════
var FLAGS = {};
var SECTION_LABELS = {annual_leave:"Annual Leave",sick_leave:"Sick Leave",maternity_leave:"Maternity Leave",public_holidays:"Public Holidays",working_hours:"Working Hours",overtime:"Overtime",probation:"Probation",minimum_wage:"Minimum Wage",income_tax:"Income Tax",payroll_tax:"Payroll Tax",withholding_tax:"Withholding Tax",health_insurance:"Health Insurance",social_security:"Social Security",pension:"Pension",employee_benefits:"Employee Benefits",termination_notice:"Termination Notice",employer_obligations:"Employer Obligations",industrial_relations:"Industrial Relations",work_permit:"Work Permit",work_visa:"Work Visa",expatriate_employment:"Expatriate Employment",workplace_safety:"Workplace Safety",osh_obligations:"OSH Obligations"};

var DATA = { queue: [], audit: [], drift: [], jobs: [], metrics: {}, coverage: {} };
var selectedIds = new Set();
var expandedIds = new Set();
var expandedInit = false;
var currentFilter = 'all';
var selectedDriftCountries = new Set();
var reviewPageSize = 10;
var reviewShowing = 10;
var sortMode = 'severity'; // 'severity' | 'time' | 'confidence'
var activeCountryFilter = new URLSearchParams(location.search).get('country') || null;

function flag(country) { return FLAGS[country] || '🌐'; }
function sectionLabel(s) { return SECTION_LABELS[s] || s.replace(/_/g,' ').replace(/\b\w/g,c=>c.toUpperCase()); }
function sevClass(s) { s = (s||'').toLowerCase(); return s === 'critical' ? 'crit' : s === 'major' ? 'major' : s === 'minor' ? 'minor' : 'info'; }
function sevLabel(s) { s = (s||'').toLowerCase(); return s.charAt(0).toUpperCase() + s.slice(1); }

function timeAgo(iso) {
  if (!iso) return '—';
  const d = new Date(iso), now = new Date(), ms = now - d;
  if (ms < 0) return 'just now';
  const mins = Math.floor(ms/60000), hrs = Math.floor(ms/3600000), days = Math.floor(ms/86400000);
  if (mins < 1) return 'just now';
  if (mins < 60) return mins + 'm ago';
  if (hrs < 24) return hrs + 'h ago';
  return days + 'd ago';
}
function fmtTime(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  return d.toLocaleTimeString('en-US',{hour:'2-digit',minute:'2-digit',second:'2-digit',hour12:false}) + ' UTC';
}
function fmtDate(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  return d.toLocaleDateString('en-US',{month:'short',day:'numeric',year:'numeric'});
}
function extractHost(url) {
  try { return new URL(url).hostname; } catch { return url || '—'; }
}
function extractPath(url) {
  try { return new URL(url).pathname; } catch { return ''; }
}

// ═══════════════════════════════════════════════════
//  DATA LOADING
// ═══════════════════════════════════════════════════
async function loadAll() {
  const [metrics, queue, audit, drift, jobs, flags, coverage, sourceCountries] = await Promise.all([
    fetch('/api/metrics').then(r=>r.json()).catch(()=>({})),
    fetch('/api/queue').then(r=>r.json()).catch(()=>[]),
    fetch('/api/audit').then(r=>r.json()).catch(()=>[]),
    fetch('/api/drift').then(r=>r.json()).catch(()=>[]),
    fetch('/api/ingestion-jobs').then(r=>r.json()).catch(()=>[]),
    fetch('/api/flags').then(r=>r.json()).catch(()=>({})),
    fetch('/api/coverage').then(r=>r.json()).catch(()=>({})),
    fetch('/api/sources/countries').then(r=>r.json()).catch(()=>[]),
  ]);
  FLAGS = flags;
  DATA = { metrics, queue, audit, drift, jobs, coverage, sourceCountries };
  renderAll();
}

function renderAll() {
  renderMetrics();
  renderSummary();
  renderDriftPills();
  renderTabCounts();
  populateTriageOptions();
  renderReview();
  renderDrift();
  renderAudit();
  renderPipeline();
  renderSyncModal();
  renderFooter();
}


//  HELPERS
// ═══════════════════════════════════════════════════
function escHtml(s) { const d = document.createElement('div'); d.textContent = s; return d.innerHTML; }
function escAttr(s) { return s.replace(/"/g, '&quot;').replace(/'/g, '&#39;'); }
function truncate(s, n) { return s && s.length > n ? s.slice(0, n) + '…' : (s || ''); }

function getVerdict(conf, severity) {
  const sev = (severity||'').toLowerCase();
  if (conf === null) return { cls:'info', label:'Review required', icon: svgInfo(), reason:'Insufficient data for automated recommendation.' };
  if (sev === 'critical') return { cls: conf >= 85 ? 'ok' : 'warn', label: conf >= 85 ? 'Approve & publish' : 'Review carefully', icon: conf >= 85 ? svgCheck() : svgWarn(), reason: conf >= 85 ? 'High-confidence match against canonical source. Verify impacted sections.' : 'Critical change — human confirmation required before publishing.' };
  if (conf >= 90) return { cls:'ok', label:'Approve (auto)', icon: svgCheck(), reason:'High-confidence, non-critical change. Safe to auto-publish.' };
  if (conf >= 75) return { cls:'ok', label:'Approve & publish', icon: svgCheck(), reason:'Good confidence match. Review diff to confirm.' };
  return { cls:'warn', label:'Review carefully', icon: svgWarn(), reason:'Lower confidence — manual review recommended before publishing.' };
}
function svgCheck() { return '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>'; }
function svgWarn() { return '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M12 9v4"/><path d="M12 17h.01"/><path d="m10.29 3.86-8.18 14.55A2 2 0 0 0 3.83 21h16.34a2 2 0 0 0 1.72-2.59L13.71 3.86a2 2 0 0 0-3.42 0z"/></svg>'; }
function svgInfo() { return '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><path d="M12 16v-4"/><path d="M12 8h.01"/></svg>'; }

function buildWhyFlagged(item, driftSections) {
  const sev = (item.severity||'').toLowerCase();
  const conf = item.confidence != null ? Math.round(item.confidence * 100) : null;
  const section = sectionLabel(item.section);
  const driftMatch = driftSections.find(s => s.section === item.section);

  if (driftMatch && driftMatch.evidence) return escHtml(driftMatch.evidence);

  let reason = '<b>' + escHtml(section) + '</b> change detected';
  if (sev === 'critical') reason += ' — <b>critical severity</b>, requires immediate review';
  else if (sev === 'major') reason += ' — <b>major change</b> affecting compliance scope';
  if (item.source_url) reason += '. Source: <b>' + extractHost(item.source_url) + '</b>';
  if (conf !== null) reason += ' (confidence ' + conf + '%)';
  reason += '.';
  if (item.source_paragraph) reason += ' ' + escHtml(truncate(item.source_paragraph, 120));
  return reason;
}

function openFullDiff(id) {
  const card = document.querySelector('[data-id="' + id + '"]');
  if (card && card.classList.contains('collapsed')) card.classList.remove('collapsed');
  if (card) card.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

let _verData = null; // cached version data for compare modal

async function viewHistory(country, section) {
  try {
    const res = await fetch('/api/guide/' + encodeURIComponent(country) + '/' + encodeURIComponent(section) + '/history');
    if (!res.ok) { toast('No version history available for ' + country + ' · ' + sectionLabel(section), 'info'); return; }
    const data = await res.json();
    const allVersions = [];
    if (data.current) allVersions.push(Object.assign({}, data.current, { _isCurrent: true }));
    (data.history || []).forEach(v => allVersions.push(v));
    if (!allVersions.length) { toast('No previous versions found', 'info'); return; }
    // sort newest first
    allVersions.sort((a, b) => (b.version_number || 0) - (a.version_number || 0));
    _verData = { country, section, versions: allVersions };
    renderCompareModal(0, Math.min(1, allVersions.length - 1));
  } catch { toast('Could not load version history', 'danger'); }
}

function renderCompareModal(leftIdx, rightIdx) {
  const d = _verData;
  if (!d) return;
  const vs = d.versions;
  const left = vs[leftIdx];
  const right = vs[rightIdx];

  // build version select options
  const opts = vs.map((v, i) => {
    const label = 'v' + (v.version_number || '?') + (v._isCurrent ? ' (current)' : '') + ' · ' + fmtDate(v.effective_date);
    return '<option value="' + i + '"' + '>' + escHtml(label) + '</option>';
  }).join('');

  const leftSrc = left.source_url ? extractHost(left.source_url) : '—';
  const rightSrc = right.source_url ? extractHost(right.source_url) : '—';
  const leftRef = left.approval_reference || '—';
  const rightRef = right.approval_reference || '—';

  let html = `
    <div class="ver-header">
      <span class="flag">${flag(d.country)}</span>
      <h3>${escHtml(d.country)} · ${sectionLabel(d.section)}</h3>
    </div>
    <p class="sub">${vs.length} version${vs.length !== 1 ? 's' : ''} recorded — select two to compare side-by-side</p>

    <div class="ver-selector">
      <label>Left</label>
      <select id="verLeft" onchange="renderCompareModal(+this.value, +document.getElementById('verRight').value)">
        ${opts.replace('value="' + leftIdx + '"', 'value="' + leftIdx + '" selected')}
      </select>
      <span class="vs-label">vs</span>
      <label>Right</label>
      <select id="verRight" onchange="renderCompareModal(+document.getElementById('verLeft').value, +this.value)">
        ${opts.replace('value="' + rightIdx + '"', 'value="' + rightIdx + '" selected')}
      </select>
    </div>

    <div class="ver-meta-grid">
      <div><div class="mk">Left version</div><div class="mv">v${left.version_number || '?'}${left._isCurrent ? ' (current)' : ''}</div></div>
      <div><div class="mk">Effective</div><div class="mv">${fmtDate(left.effective_date)}</div></div>
      <div><div class="mk">Right version</div><div class="mv">v${right.version_number || '?'}${right._isCurrent ? ' (current)' : ''}</div></div>
      <div><div class="mk">Effective</div><div class="mv">${fmtDate(right.effective_date)}</div></div>
      <div><div class="mk">Source</div><div class="mv">${escHtml(leftSrc)}</div></div>
      <div><div class="mk">Approval ref</div><div class="mv" style="word-break:break-all;">${escHtml(leftRef)}</div></div>
      <div><div class="mk">Source</div><div class="mv">${escHtml(rightSrc)}</div></div>
      <div><div class="mk">Approval ref</div><div class="mv" style="word-break:break-all;">${escHtml(rightRef)}</div></div>
    </div>

    <div class="ver-diff">
      <div class="ver-diff-head">
        <div>v${left.version_number || '?'} <span style="font-weight:400;text-transform:none;letter-spacing:0;color:var(--ink-4);font-size:11px;margin-left:auto;">${fmtDate(left.effective_date)}</span></div>
        <div>v${right.version_number || '?'} <span style="font-weight:400;text-transform:none;letter-spacing:0;color:var(--ink-4);font-size:11px;margin-left:auto;">${fmtDate(right.effective_date)}</span></div>
      </div>
      <div class="ver-diff-body">
        <div class="ver-diff-side ${left.value ? '' : 'empty'}">${left.value ? escHtml(left.value) : '(no value)'}</div>
        <div class="ver-diff-side ${right.value ? '' : 'empty'}">${right.value ? escHtml(right.value) : '(no value)'}</div>
      </div>
    </div>

    <details style="margin-top:4px;">
      <summary style="cursor:pointer;font-family:var(--font-mono);font-size:10.5px;font-weight:700;letter-spacing:0.12em;text-transform:uppercase;color:var(--ink-3);user-select:none;">All versions (${vs.length})</summary>
      <div class="ver-timeline" style="margin-top:10px;">
        ${vs.map((v, i) => `
          <div class="ver-row ${v._isCurrent ? 'current' : ''} ${i === leftIdx || i === rightIdx ? 'active' : ''}" onclick="renderCompareModal(${leftIdx === i ? rightIdx : i}, ${rightIdx === i ? leftIdx : i})">
            <span class="vn">v${v.version_number || '?'}</span>
            <span class="vval">${escHtml(truncate(v.value || '', 80))}</span>
            <span class="vdate">${fmtDate(v.effective_date)}</span>
            <span class="vsrc">${v.source_url ? extractHost(v.source_url) : '—'}</span>
          </div>
        `).join('')}
      </div>
    </details>
  `;

  // use a dedicated modal with ver-modal class
  let modal = document.getElementById('verModal');
  if (!modal) {
    modal = document.createElement('div');
    modal.id = 'verModal';
    modal.className = 'modal-scrim ver-modal';
    modal.onclick = e => { if (e.target === modal) modal.classList.remove('open'); };
    modal.innerHTML = '<div class="modal"><button class="close" onclick="document.getElementById(\'verModal\').classList.remove(\'open\')" aria-label="Close"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg></button><div id="verModalContent"></div></div>';
    document.body.appendChild(modal);
  }
  document.getElementById('verModalContent').innerHTML = html;
  modal.classList.add('open');
}

function showInfoModal(contentHtml) {
  let modal = document.getElementById('infoModal');
  if (!modal) {
    modal = document.createElement('div');
    modal.id = 'infoModal';
    modal.className = 'modal-scrim';
    modal.onclick = e => { if (e.target === modal) modal.classList.remove('open'); };
    modal.innerHTML = '<div class="modal" style="max-width:700px;"><button class="close" onclick="document.getElementById(\'infoModal\').classList.remove(\'open\')" aria-label="Close"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg></button><div id="infoModalContent"></div></div>';
    document.body.appendChild(modal);
  }
  document.getElementById('infoModalContent').innerHTML = contentHtml;
  modal.classList.add('open');
}

async function loadPipeline() {
  try {
    const jobs = await fetch('/api/ingestion-jobs').then(r=>r.json()).catch(()=>[]);
    DATA.jobs = jobs;
    renderPipeline();
    toast('Pipeline refreshed', 'info');
  } catch { toast('Failed to refresh pipeline', 'danger'); }
}

// ═══════════════════════════════════════════════════
