// ═══════════════════════════════════════════════════
//  CONSTANTS & STATE
// ═══════════════════════════════════════════════════
let FLAGS = {};
const SECTION_LABELS = {annual_leave:"Annual Leave",sick_leave:"Sick Leave",maternity_leave:"Maternity Leave",public_holidays:"Public Holidays",working_hours:"Working Hours",overtime:"Overtime",probation:"Probation",minimum_wage:"Minimum Wage",income_tax:"Income Tax",payroll_tax:"Payroll Tax",withholding_tax:"Withholding Tax",health_insurance:"Health Insurance",social_security:"Social Security",pension:"Pension",employee_benefits:"Employee Benefits",termination_notice:"Termination Notice",employer_obligations:"Employer Obligations",industrial_relations:"Industrial Relations",work_permit:"Work Permit",work_visa:"Work Visa",expatriate_employment:"Expatriate Employment",workplace_safety:"Workplace Safety",osh_obligations:"OSH Obligations"};

let DATA = { queue: [], audit: [], drift: [], jobs: [], metrics: {}, coverage: {} };
let selectedIds = new Set();
let expandedIds = new Set();
let expandedInit = false;
let currentFilter = 'all';
let selectedDriftCountries = new Set();
let reviewPageSize = 10;
let reviewShowing = 10;
let sortMode = 'severity'; // 'severity' | 'time' | 'confidence'
let activeCountryFilter = new URLSearchParams(location.search).get('country') || null;

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

