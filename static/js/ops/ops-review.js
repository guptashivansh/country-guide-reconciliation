// ops-review.js — Review tab rendering and review actions

//  TAB COUNTS
// ═══════════════════════════════════════════════════
function renderTabCounts() {
  const pending = DATA.queue.filter(q => q.status === 'pending' || q.status === 'escalated');
  document.getElementById('tabReviewCt').textContent = pending.length;
  const driftCount = DATA.drift.filter(d => d.drift_detected).length;
  document.getElementById('tabDriftCt').textContent = driftCount;
  const failCtEl = document.getElementById('tabSourcesCt');
  if (failCtEl) failCtEl.textContent = DATA.metrics.sources_monitored || 0;
}

// ═══════════════════════════════════════════════════
//  REVIEW TAB
// ═══════════════════════════════════════════════════
function sortItems(items) {
  const sevOrd = {critical:0, major:1, minor:2};
  return [...items].sort((a,b) => {
    if (sortMode === 'severity') {
      const sa = sevOrd[(a.severity||'').toLowerCase()] ?? 3;
      const sb = sevOrd[(b.severity||'').toLowerCase()] ?? 3;
      if (sa !== sb) return sa - sb;
      return (b.confidence||0) - (a.confidence||0);
    }
    if (sortMode === 'time') return new Date(b.created_at||0) - new Date(a.created_at||0);
    if (sortMode === 'confidence') return (b.confidence||0) - (a.confidence||0);
    return 0;
  });
}

function applyFilter(items) {
  if (currentFilter === 'all') return items;
  if (currentFilter === 'escalated') return items.filter(i => i.status === 'escalated');
  if (currentFilter === 'unassigned') return items.filter(i => !i.reviewer_assignee || i.reviewer_assignee === 'Unassigned');
  if (currentFilter === 'minor') return items.filter(i => { const s = (i.severity||'').toLowerCase(); return s !== 'critical' && s !== 'major'; });
  return items.filter(i => (i.severity||'').toLowerCase() === currentFilter);
}

function renderReview() {
  const list = document.getElementById('reviewList');
  let items = DATA.queue.filter(q => q.status === 'pending' || q.status === 'escalated');
  if (activeCountryFilter) items = items.filter(q => q.country === activeCountryFilter);

  // chip counts
  const all = items.length;
  const crit = items.filter(i=>(i.severity||'').toLowerCase()==='critical').length;
  const major = items.filter(i=>(i.severity||'').toLowerCase()==='major').length;
  const minor = items.filter(i=>{ const s=(i.severity||'').toLowerCase(); return s!=='critical'&&s!=='major'; }).length;
  const esc = items.filter(i=>i.status==='escalated').length;
  const unassigned = items.filter(i=>!i.reviewer_assignee || i.reviewer_assignee==='Unassigned').length;
  document.getElementById('chipAll').textContent = all;
  document.getElementById('chipCrit').textContent = crit;
  document.getElementById('chipMajor').textContent = major;
  document.getElementById('chipMinor').textContent = minor;
  document.getElementById('chipEsc').textContent = esc;
  document.getElementById('chipUnassigned').textContent = unassigned;

  let filtered = sortItems(applyFilter(applyTriageToItems(items)));

  // bulk bar
  const minorItems = items.filter(i=>{ const s=(i.severity||'').toLowerCase(); return s!=='critical'&&s!=='major'; });
  const bulkMinorEl = document.getElementById('bulkMinorCount');
  if (bulkMinorEl) bulkMinorEl.textContent = '(' + minorItems.length + ')';
  document.getElementById('selectedTotal').textContent = all;

  if (!filtered.length) {
    list.innerHTML = '';
    document.getElementById('reviewEmpty').style.display = 'block';
    document.getElementById('reviewMore').style.display = 'none';
    return;
  }
  document.getElementById('reviewEmpty').style.display = 'none';

  // pagination
  const totalFiltered = filtered.length;
  const page = filtered.slice(0, reviewShowing);
  const hasMore = totalFiltered > reviewShowing;
  const moreEl = document.getElementById('reviewMore');
  if (hasMore) {
    moreEl.style.display = 'flex';
    document.getElementById('reviewShowingText').textContent = 'Showing ' + page.length + ' of ' + totalFiltered + ' ·';
  } else {
    moreEl.style.display = 'none';
  }

  filtered = page;

  if (!expandedInit && filtered.length) {
    expandedIds.add(filtered[0].id);
    expandedInit = true;
  }

  list.innerHTML = filtered.map((item, idx) => {
    const sc = sevClass(item.severity);
    const conf = item.confidence != null ? Math.round(item.confidence * 100) : null;
    const checked = selectedIds.has(item.id) ? 'checked' : '';
    const collapsed = expandedIds.has(item.id) ? '' : 'collapsed';
    const isMinor = (item.severity||'').toLowerCase() === 'minor' || (conf !== null && conf >= 90);
    const isAutoApprovable = conf !== null && conf >= 90 && (item.severity||'').toLowerCase() !== 'critical';

    // AI recommendation: derive verdict from confidence + severity
    const verdict = getVerdict(conf, item.severity);

    // Find related drift sections for this country
    const driftReport = DATA.drift.find(d => d.country === item.country);
    const driftSections = driftReport ? (driftReport.affected_sections || []) : [];
    const relatedSections = driftSections.filter(s => s.section !== item.section);

    // Find related audit entries for this country+section
    const relatedAudit = DATA.audit.filter(a => a.country === item.country && a.section === item.section).slice(0, 3);

    // Country code for meta line
    const countryCode = item.country.slice(0,2).toUpperCase();

    return `
    <article class="rcard ${sc} ${collapsed}" data-id="${item.id}" data-mat="${sc}">
      <div class="top-strip"></div>
      <div class="rcard-body" onclick="cardBodyClick(event, this)">
        <div class="rcard-head">
          <span class="rcard-check ${checked}" onclick="toggleCheck(event, ${item.id})"></span>
          <span class="flag">${flag(item.country)}</span>
          <h3 class="rcard-title" onclick="openFullDiff(${item.id}); event.stopPropagation();">${escHtml(item.country)} · ${sectionLabel(item.section)}</h3>
          <span class="badge ${sc}"><span class="d"></span>${sevLabel(item.severity)}</span>
          ${item.change_type ? '<span class="badge info">' + escHtml(item.change_type) + '</span>' : ''}
          ${item.status === 'escalated' ? '<span class="badge major">Escalated</span>' : ''}
          <span class="rcard-meta">${countryCode} · ${sectionLabel(item.section)}</span>
          <span class="rcard-spacer"></span>
          ${isAutoApprovable ? '<span class="auto-approvable">' + conf + '% · auto-approvable</span>' : ''}
          <span class="rcard-time" title="Detected ${item.created_at ? fmtTime(item.created_at) : ''}">Detected ${timeAgo(item.created_at)}${item.created_at ? ' · ' + fmtDate(item.created_at) : ''}${item.source_url ? ' · ' + extractHost(item.source_url) : ''}</span>
          <button class="rcard-expand" onclick="toggleCollapse(this)" title="Expand/Collapse">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 12 15 18 9"/></svg>
          </button>
        </div>

        <p class="rcard-summary">${truncate(item.new_value || item.source_paragraph || '', 150)}</p>

        <div class="rcard-grid">
          <div>
            <div class="diff">
              <div class="diff-head">
                <div class="label-prev">Previous guidance <span class="src">${escHtml(item.country)}</span></div>
                <div class="label-new">New source${item.source_url ? ' <span class="src">' + extractHost(item.source_url) + '</span>' : ''}</div>
              </div>
              <div class="diff-body">
                <div class="diff-side diff-old">${item.old_value ? escHtml(item.old_value) : '<em style="color:var(--ink-4);">(no previous value)</em>'}</div>
                <div class="diff-side diff-new">${escHtml(item.new_value || '')}</div>
              </div>
            </div>

            ${(() => {
              const snippet = String(item.source_paragraph || '').trim();
              const hasEvidence = snippet.length > 0;
              const preview = snippet.length > 120 ? snippet.slice(0, 120) + '…' : snippet;
              const srcDisplay = item.source_url ? extractHost(item.source_url) : '';
              return hasEvidence ? `
            <details class="src-evidence">
              <summary class="src-evidence-toggle">
                <div class="src-evidence-heading">
                  <div class="src-evidence-title"><span class="src-evidence-icon">"</span> Source Evidence</div>
                  <div class="src-evidence-preview">${escHtml(preview)}</div>
                </div>
                <span class="src-evidence-action"></span>
              </summary>
              <div class="src-evidence-body">
                <pre class="src-snippet">${escHtml(snippet)}</pre>
                <div class="src-attribution">
                  <span>Extracted from ${item.source_url ? '<a href="' + escAttr(item.source_url) + '" target="_blank" rel="noopener">' + escHtml(srcDisplay) + '</a>' : 'source'}</span>
                  <span style="color:var(--paper-line-2);">·</span>
                  <span>${item.created_at ? fmtTime(item.created_at) : ''}</span>
                  <span style="color:var(--paper-line-2);">·</span>
                  <span>${sectionLabel(item.section)}</span>
                  ${item.source_url ? '<span style="color:var(--paper-line-2);">·</span><a href="' + escAttr(item.source_url) + '" target="_blank" rel="noopener" style="display:inline-flex;align-items:center;gap:4px;"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" width="12" height="12"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg> View source page</a>' : ''}
                </div>
              </div>
            </details>` : '';
            })()}

            ${(() => {
              const job = DATA.jobs.find(j => j.source_snapshot_id && j.source_snapshot_id === item.source_snapshot_id);
              const trustLevel = (conf !== null && conf >= 90) ? 'verified' : (conf !== null && conf >= 70) ? 'review' : 'unknown';
              const trustLabel = trustLevel === 'verified' ? 'Verified' : trustLevel === 'review' ? 'Review required' : 'Unverified';
              const srcType = item.source_url ? (item.source_url.startsWith('seed://') ? 'Seed data' : item.source_url.includes('notion') ? 'Notion import' : 'Government source') : 'Unknown';
              const srcConfMap = { 'Government source': 95, 'Notion import': 75, 'Seed data': 60, 'Unknown': 0 };
              const srcConf = srcConfMap[srcType] || 0;
              const srcConfTip = { 'Government source': 'Government sources are primary legal authorities and receive the highest source confidence rating.', 'Notion import': 'Notion imports are curated internal references verified by the compliance team.', 'Seed data': 'Seed data is baseline information loaded during initial setup; accuracy may vary.', 'Unknown': 'Source type could not be determined.' };
              const parserConfTip = 'Parser confidence reflects how accurately the extraction model identified and parsed this data point from the source document.';
              return `
            <details class="prov-drawer">
              <summary class="prov-toggle">
                <div class="prov-title">
                  <span class="prov-caret">›</span>
                  <span class="prov-label">Provenance</span>
                </div>
                <span class="prov-trust ${trustLevel}">${trustLabel}</span>
              </summary>
              <div class="prov-body">
                <div class="prov-grid">
                  <div class="prov-field-wide">
                    <div class="prov-key">Source URL</div>
                    <div class="prov-value">${item.source_url ? '<a href="' + escAttr(item.source_url) + '" target="_blank" rel="noopener">' + escHtml(item.source_url) + '</a>' : 'Not recorded'}</div>
                  </div>
                  <div>
                    <div class="prov-key">Source type</div>
                    <div class="prov-value">${escHtml(srcType)}</div>
                  </div>
                  <div>
                    <div class="prov-key">Detected at</div>
                    <div class="prov-value">${item.created_at ? fmtTime(item.created_at) : '—'}</div>
                  </div>
                  <div>
                    <div class="prov-key">Section</div>
                    <div class="prov-value">${sectionLabel(item.section)}</div>
                  </div>
                  <div>
                    <div class="prov-key">Source confidence <span class="prov-info-icon" title="${srcConfTip[srcType] || srcConfTip['Unknown']}">ⓘ</span></div>
                    <div class="prov-value">${srcConf}%</div>
                  </div>
                  <div>
                    <div class="prov-key">Parser confidence <span class="prov-info-icon" title="${parserConfTip}">ⓘ</span></div>
                    <div class="prov-value">${conf !== null ? conf + '%' : '—'}</div>
                  </div>
                  <div>
                    <div class="prov-key">Model version</div>
                    <div class="prov-value">llama-3.3-70b-versatile</div>
                  </div>
                  <div>
                    <div class="prov-key">Trust level</div>
                    <div class="prov-value"><span class="prov-trust ${trustLevel}">${trustLabel}</span></div>
                  </div>
                  ${job ? `
                  <div>
                    <div class="prov-key">Pipeline job</div>
                    <div class="prov-value">#${job.id} · ${job.state}</div>
                  </div>
                  <div>
                    <div class="prov-key">Fetched at</div>
                    <div class="prov-value">${job.fetched_at ? fmtTime(job.fetched_at) : '—'}</div>
                  </div>` : ''}
                </div>
              </div>
            </details>`;
            })()}
          </div>

          <aside class="rai">
            <div class="rai-block">
              <div class="lbl"><span class="ai-pill">AI</span> Why flagged</div>
              <p class="reason">${buildWhyFlagged(item, driftSections)}</p>
            </div>

            <div class="rai-block">
              <div class="lbl">Recommendation</div>
              <div class="verdict ${verdict.cls}">
                ${verdict.icon}
                ${verdict.label}
              </div>
              ${conf !== null ? `
              <div class="conf">
                <span>${conf}%</span>
                <div class="conf-track"><div class="conf-fill ${conf < 75 ? 'warn' : ''}" style="width:${conf}%"></div></div>
              </div>
              <p class="reason" style="margin-top:6px;">${verdict.reason}</p>` : ''}
            </div>

            ${relatedSections.length > 0 ? `
            <div class="rai-block">
              <div class="lbl">Impacted sections (${relatedSections.length})</div>
              <div class="section-chips" id="sections-${item.id}">
                ${relatedSections.map(s => '<span class="section-chip">' + sectionLabel(s.section) + '</span>').join('')}
              </div>
              ${relatedSections.length > 3 ? '<a class="section-toggle" id="sectoggle-' + item.id + '" onclick="toggleSections(' + item.id + ')">View all ' + relatedSections.length + ' sections</a>' : ''}
            </div>` : `
            <div class="rai-block">
              <div class="lbl">Section</div>
              <div class="section-chips">
                <span class="section-chip">${escHtml(item.country)}</span>
                <span class="section-chip">${sectionLabel(item.section)}</span>
                ${item.materiality_level ? '<span class="section-chip">' + escHtml(item.materiality_level) + '</span>' : ''}
              </div>
            </div>`}

            ${relatedAudit.length > 0 ? `
            <div class="rai-block">
              <div class="lbl">Audit · latest</div>
              <div class="audit-mini">
                ${relatedAudit.map(a => `
                <div class="row ${a.decision === 'approved' ? 'human' : ''}">
                  <span class="dot"></span>
                  <span>${sevLabel(a.decision || a.action)} · ${sectionLabel(a.section)}</span>
                  <span class="t">${fmtTime(a.timestamp).slice(0,5)}</span>
                </div>`).join('')}
              </div>
              <a class="audit-mini-link" onclick="goTab('audit')">View full trail →</a>
            </div>` : `
            <div class="rai-block">
              <a class="audit-mini-link" onclick="goTab('audit')">View audit trail →</a>
            </div>`}
          </aside>
        </div>

        <div class="rcard-actions">
          <button class="btn btn-ghost" onclick="viewHistory('${escAttr(item.country)}','${escAttr(item.section)}')">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" width="14" height="14"><path d="M12 8v4l3 3"/><circle cx="12" cy="12" r="10"/></svg>
            Compare versions
          </button>
          <span class="hint">Decision is logged immutably to audit trail</span>
        </div>
      </div>
    </article>`;
  }).join('');

  // init section chip toggles after DOM update
  setTimeout(initSectionToggles, 0);
}

// ═══════════════════════════════════════════════════

//  ACTIONS
// ═══════════════════════════════════════════════════
async function doAction(action, id, extra) {
  try {
    const payload = Object.assign({ notes: '', assignee: 'Regulift Compliance' }, extra || {});
    const res = await fetch(`/api/${action}/${id}`, {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify(payload)
    });
    const data = await res.json();
    if (data.success) {
      const msgs = { approve: 'Approved & published', reject: 'Rejected', escalate: 'Escalated' };
      const kinds = { approve: 'ok', reject: 'danger', escalate: 'warn' };
      toast(`${msgs[action]} · item #${id}`, kinds[action]);
      loadAll();
    } else {
      toast(data.message || 'Action failed', 'danger');
    }
  } catch (err) {
    toast('Error: ' + err.message, 'danger');
  }
}

// ── Reject modal ──
function openRejectModal(id) {
  document.getElementById('rejectItemId').value = id;
  document.getElementById('rejectRationale').value = 'Outdated or superseded source';
  document.getElementById('rejectNotes').value = '';
  document.getElementById('rejectModal').classList.add('open');
}
function closeRejectModal() {
  document.getElementById('rejectModal').classList.remove('open');
}
async function confirmReject() {
  const id = document.getElementById('rejectItemId').value;
  const rationale = document.getElementById('rejectRationale').value;
  const notes = document.getElementById('rejectNotes').value;
  closeRejectModal();
  await doAction('reject', id, { rationale, notes });
}

// ── Section chips trim / view more ──
function toggleSections(itemId) {
  const el = document.getElementById('sections-' + itemId);
  const btn = document.getElementById('sectoggle-' + itemId);
  if (!el || !btn) return;
  el.classList.toggle('expanded');
  btn.textContent = el.classList.contains('expanded') ? 'Show fewer' : 'View all';
}
function initSectionToggles() {
  document.querySelectorAll('.section-chips').forEach(el => {
    const id = el.id ? el.id.replace('sections-', '') : '';
    const btn = document.getElementById('sectoggle-' + id);
    if (!btn) return;
    // Show toggle only if chips overflow the trimmed height
    if (el.scrollHeight > 40) { btn.style.display = 'inline'; }
    else { btn.style.display = 'none'; }
  });
}

// ── Global triage (all filters apply across all tabs) ──
var triageFilters = { severity: '', confidence: '', changeType: '', status: '' };

function populateTriageOptions() {
  const countries = new Set();
  const changeTypes = new Set();
  (DATA.queue || []).forEach(q => { if (q.country) countries.add(q.country); if (q.change_type) changeTypes.add(q.change_type); });
  (DATA.drift || []).forEach(d => { if (d.country) countries.add(d.country); });
  (DATA.audit || []).forEach(a => { if (a.country) countries.add(a.country); });
  (DATA.jobs || []).forEach(j => { if (j.country) countries.add(j.country); });

  const cSel = document.getElementById('globalTriageCountry');
  const ctSel = document.getElementById('triageChangeType');
  const prev = cSel.value;
  cSel.innerHTML = '<option value="">All</option>' + [...countries].sort().map(c => '<option value="' + escHtml(c) + '">' + escHtml(c) + '</option>').join('');
  if (prev) cSel.value = prev;
  ctSel.innerHTML = '<option value="">All</option>' + [...changeTypes].sort().map(t => '<option value="' + escHtml(t) + '">' + escHtml(t) + '</option>').join('');

  if (activeCountryFilter) {
    cSel.value = activeCountryFilter;
  }
}

function readTriageSelects() {
  activeCountryFilter = document.getElementById('globalTriageCountry').value || null;
  triageFilters.severity = document.getElementById('triageSeverity').value;
  triageFilters.confidence = document.getElementById('triageConfidence').value;
  triageFilters.changeType = document.getElementById('triageChangeType').value;
  triageFilters.status = document.getElementById('triageStatus').value;
}

function applyGlobalTriage() {
  readTriageSelects();
  reviewShowing = reviewPageSize;
  updateTriageCount();
  renderSummary();
  renderDriftPills();
  renderReview();
  renderDrift();
  renderAudit();
  renderPipeline();
}

function resetGlobalTriage() {
  document.getElementById('globalTriageCountry').value = '';
  document.getElementById('triageSeverity').value = '';
  document.getElementById('triageConfidence').value = '';
  document.getElementById('triageChangeType').value = '';
  document.getElementById('triageStatus').value = '';
  activeCountryFilter = null;
  triageFilters = { severity: '', confidence: '', changeType: '', status: '' };
  reviewShowing = reviewPageSize;
  updateTriageCount();
  renderSummary();
  renderDriftPills();
  renderReview();
  renderDrift();
  renderAudit();
  renderPipeline();
}

function updateTriageCount() {
  const el = document.getElementById('globalTriageCount');
  const parts = [];
  if (activeCountryFilter) parts.push(activeCountryFilter);
  if (triageFilters.severity) parts.push(triageFilters.severity);
  if (triageFilters.confidence) parts.push('conf: ' + triageFilters.confidence);
  if (triageFilters.changeType) parts.push(triageFilters.changeType);
  if (triageFilters.status) parts.push(triageFilters.status);
  el.textContent = parts.length ? parts.join(' · ') : 'All data';
}

function applyTriageToItems(items) {
  let r = items;
  if (triageFilters.severity) r = r.filter(i => (i.severity||'').toLowerCase() === triageFilters.severity);
  if (triageFilters.confidence) {
    r = r.filter(i => {
      const c = i.confidence != null ? i.confidence * 100 : null;
      if (c === null) return false;
      if (triageFilters.confidence === 'high') return c >= 90;
      if (triageFilters.confidence === 'mid') return c >= 70 && c < 90;
      if (triageFilters.confidence === 'low') return c < 70;
      return true;
    });
  }
  if (triageFilters.changeType) r = r.filter(i => i.change_type === triageFilters.changeType);
  if (triageFilters.status) r = r.filter(i => i.status === triageFilters.status);
  return r;
}

async function bulkApproveSelected() {
  if (!selectedIds.size) return;
  let approved = 0;
  for (const id of selectedIds) {
    try {
      const res = await fetch('/api/approve/' + id, {
        method: 'POST',
        headers: {'Content-Type':'application/json'},
        body: JSON.stringify({ notes: 'Bulk approval from ops dashboard', assignee: 'Regulift Compliance' })
      });
      const data = await res.json();
      if (data.success) approved++;
    } catch {}
  }
  toast('Approved ' + approved + ' of ' + selectedIds.size + ' items', 'ok');
  selectedIds.clear();
  document.getElementById('bulkBar').style.display = 'none';
  loadAll();
}

