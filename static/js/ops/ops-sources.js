// ops-sources.js — Sources tab, source management, source drawer

//  ADD SOURCE MODAL
// ═══════════════════════════════════════════════════
var _addSrcCountries = [];
var _addSrcAuthorities = [];
var _addSrcSectionKeys = Object.keys(SECTION_LABELS);
var _addSrcSelectedSections = new Set();

async function openAddSourceModal() {
  document.getElementById('addSourceModal').style.display = 'flex';
  document.getElementById('addSrcError').style.display = 'none';

  // Load countries if not cached
  if (!_addSrcCountries.length) {
    _addSrcCountries = await fetch('/api/sources/countries').then(r => r.json());
  }
  const sel = document.getElementById('addSrcCountry');
  sel.innerHTML = '<option value="">Select a country…</option>' +
    _addSrcCountries.map(c => `<option value="${c.id}" data-name="${escHtml(c.name)}">${escHtml(c.name)}</option>`).join('');

  document.getElementById('addSrcAuthority').innerHTML = '<option value="">Select a country first…</option>';
  document.getElementById('addSrcAuthority').disabled = true;

  // Render section checkboxes
  _addSrcSelectedSections.clear();
  const sectionsEl = document.getElementById('addSrcSections');
  sectionsEl.innerHTML = _addSrcSectionKeys.map(k =>
    `<label style="display:inline-flex; align-items:center; gap:5px; padding:4px 10px; background:var(--paper-2); border:1px solid var(--paper-line); border-radius:var(--r-s); font-family:var(--font-mono); font-size:11px; font-weight:600; color:var(--ink-2); cursor:pointer; transition:all 0.12s; user-select:none;" onmouseenter="this.style.borderColor='var(--paper-line-2)'" onmouseleave="this.style.borderColor=this.querySelector('input').checked?'var(--purple-line)':'var(--paper-line)'">
      <input type="checkbox" value="${k}" onchange="toggleAddSrcSection(this)" style="accent-color:var(--purple); width:13px; height:13px;" />
      ${sectionLabel(k)}
    </label>`
  ).join('');

  // Reset form
  document.getElementById('addSrcName').value = '';
  document.getElementById('addSrcUrl').value = '';
  document.getElementById('addSrcType').value = 'html';
  document.getElementById('addSrcFreq').value = 'monthly';
  document.getElementById('addSrcStrategy').value = 'html_readability';
  document.getElementById('addSrcLang').value = 'en';
  document.getElementById('addSrcNotes').value = '';
}

function closeAddSourceModal() {
  document.getElementById('addSourceModal').style.display = 'none';
}

async function onAddSrcCountryChange() {
  const countryId = document.getElementById('addSrcCountry').value;
  const authSel = document.getElementById('addSrcAuthority');
  if (!countryId) {
    authSel.innerHTML = '<option value="">Select a country first…</option>';
    authSel.disabled = true;
    return;
  }
  const auths = await fetch('/api/sources/authorities?country_id=' + encodeURIComponent(countryId)).then(r => r.json());
  _addSrcAuthorities = auths;
  authSel.disabled = false;
  authSel.innerHTML = '<option value="">Select an authority…</option>' +
    auths.map(a => `<option value="${a.id}">${escHtml(a.name)} (${escHtml(a.authority_type || 'gov')})</option>`).join('');
}

function toggleAddSrcSection(cb) {
  if (cb.checked) {
    _addSrcSelectedSections.add(cb.value);
    cb.parentElement.style.background = 'var(--purple-soft)';
    cb.parentElement.style.borderColor = 'var(--purple-line)';
    cb.parentElement.style.color = 'var(--purple-2)';
  } else {
    _addSrcSelectedSections.delete(cb.value);
    cb.parentElement.style.background = 'var(--paper-2)';
    cb.parentElement.style.borderColor = 'var(--paper-line)';
    cb.parentElement.style.color = 'var(--ink-2)';
  }
}

async function submitAddSource() {
  const errEl = document.getElementById('addSrcError');
  errEl.style.display = 'none';

  const authorityId = document.getElementById('addSrcAuthority').value;
  const url = document.getElementById('addSrcUrl').value.trim();

  if (!authorityId) { errEl.textContent = 'Please select a country and authority.'; errEl.style.display = ''; return; }
  if (!url) { errEl.textContent = 'URL is required.'; errEl.style.display = ''; return; }

  const btn = document.getElementById('addSrcSubmit');
  btn.disabled = true;
  btn.textContent = 'Creating…';

  try {
    const res = await fetch('/api/sources/endpoints', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        authority_id: authorityId,
        name: document.getElementById('addSrcName').value.trim(),
        url: url,
        source_type: document.getElementById('addSrcType').value,
        crawl_frequency: document.getElementById('addSrcFreq').value,
        extraction_strategy: document.getElementById('addSrcStrategy').value,
        content_language: document.getElementById('addSrcLang').value,
        sections_covered: Array.from(_addSrcSelectedSections),
        notes: document.getElementById('addSrcNotes').value.trim(),
      }),
    });

    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.error || 'Failed to create endpoint');
    }

    closeAddSourceModal();
    toast('Source endpoint created');
    loadSourcesTab();
  } catch (e) {
    errEl.textContent = e.message;
    errEl.style.display = '';
  } finally {
    btn.disabled = false;
    btn.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" width="14" height="14"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg> Create endpoint';
  }
}

// ═══════════════════════════════════════════════════
//  SOURCES CRUD
// ═══════════════════════════════════════════════════
var _editSrcSelectedSections = new Set();
var _pendingDelete = null;

function openEditSourceModal(country, idx) {
  const ep = _groupedByCountry[country]?.[idx];
  if (!ep) return;
  closeSrcDrawer();

  document.getElementById('editSourceModal').style.display = 'flex';
  document.getElementById('editSrcError').style.display = 'none';
  document.getElementById('editSrcId').value = ep.endpoint_id;
  document.getElementById('editSrcName').value = ep.name || '';
  document.getElementById('editSrcUrl').value = ep.url || '';
  document.getElementById('editSrcType').value = ep.source_type || 'html';
  document.getElementById('editSrcFreq').value = ep.crawl_frequency || 'monthly';
  document.getElementById('editSrcStrategy').value = ep.extraction_strategy || 'html_readability';
  document.getElementById('editSrcLang').value = ep.content_language || 'en';
  document.getElementById('editSrcDetection').value = ep.change_detection_strategy || 'semantic';
  document.getElementById('editSrcOwner').value = ep.owner_team || '';
  document.getElementById('editSrcNotes').value = ep.notes || '';
  document.getElementById('editSrcJsHeavy').checked = !!ep.is_javascript_heavy;
  document.getElementById('editSrcAuth').checked = !!ep.requires_authentication;
  document.getElementById('editSrcEscalation').checked = !!ep.escalation_required;

  _editSrcSelectedSections = new Set(ep.sections || []);
  const sectionsEl = document.getElementById('editSrcSections');
  const allKeys = Object.keys(SECTION_LABELS);
  sectionsEl.innerHTML = allKeys.map(k => {
    const checked = _editSrcSelectedSections.has(k);
    return `<label style="display:inline-flex; align-items:center; gap:5px; padding:4px 10px; background:${checked ? 'var(--purple-soft)' : 'var(--paper-2)'}; border:1px solid ${checked ? 'var(--purple-line)' : 'var(--paper-line)'}; border-radius:var(--r-s); font-family:var(--font-mono); font-size:11px; font-weight:600; color:${checked ? 'var(--purple-2)' : 'var(--ink-2)'}; cursor:pointer; transition:all 0.12s; user-select:none;">
      <input type="checkbox" value="${k}" ${checked ? 'checked' : ''} onchange="toggleEditSrcSection(this)" style="accent-color:var(--purple); width:13px; height:13px;" />
      ${sectionLabel(k)}
    </label>`;
  }).join('');
}

function closeEditSourceModal() { document.getElementById('editSourceModal').style.display = 'none'; }

function toggleEditSrcSection(cb) {
  if (cb.checked) {
    _editSrcSelectedSections.add(cb.value);
    cb.parentElement.style.background = 'var(--purple-soft)';
    cb.parentElement.style.borderColor = 'var(--purple-line)';
    cb.parentElement.style.color = 'var(--purple-2)';
  } else {
    _editSrcSelectedSections.delete(cb.value);
    cb.parentElement.style.background = 'var(--paper-2)';
    cb.parentElement.style.borderColor = 'var(--paper-line)';
    cb.parentElement.style.color = 'var(--ink-2)';
  }
}

async function submitEditSource() {
  const errEl = document.getElementById('editSrcError');
  errEl.style.display = 'none';
  const id = document.getElementById('editSrcId').value;
  const url = document.getElementById('editSrcUrl').value.trim();
  if (!url) { errEl.textContent = 'URL is required.'; errEl.style.display = ''; return; }

  const btn = document.getElementById('editSrcSubmit');
  btn.disabled = true; btn.textContent = 'Saving…';
  try {
    const res = await fetch('/api/sources/endpoints/' + encodeURIComponent(id), {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        name: document.getElementById('editSrcName').value.trim(),
        url,
        source_type: document.getElementById('editSrcType').value,
        crawl_frequency: document.getElementById('editSrcFreq').value,
        extraction_strategy: document.getElementById('editSrcStrategy').value,
        content_language: document.getElementById('editSrcLang').value,
        change_detection_strategy: document.getElementById('editSrcDetection').value,
        owner_team: document.getElementById('editSrcOwner').value.trim(),
        notes: document.getElementById('editSrcNotes').value.trim(),
        sections_covered: Array.from(_editSrcSelectedSections),
        is_javascript_heavy: document.getElementById('editSrcJsHeavy').checked,
        requires_authentication: document.getElementById('editSrcAuth').checked,
        escalation_required: document.getElementById('editSrcEscalation').checked,
      }),
    });
    if (!res.ok) throw new Error((await res.json()).error || 'Failed');
    closeEditSourceModal();
    toast('Source endpoint updated');
    loadSourcesTab();
  } catch (e) {
    errEl.textContent = e.message; errEl.style.display = '';
  } finally {
    btn.disabled = false;
    btn.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" width="14" height="14"><path d="M17 3a2.828 2.828 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5L17 3z"/></svg> Save changes';
  }
}

function deleteEndpoint(endpointId) {
  _pendingDelete = { type: 'endpoint', id: endpointId };
  document.getElementById('deleteModalMsg').textContent = 'This will deactivate the endpoint. It can be re-activated later.';
  document.getElementById('confirmDeleteModal').style.display = 'flex';
}

function deleteCountry(countryId, countryName) {
  _pendingDelete = { type: 'country', id: countryId };
  document.getElementById('deleteModalMsg').textContent = `Deactivate "${countryName}" and all its authorities/endpoints?`;
  document.getElementById('confirmDeleteModal').style.display = 'flex';
}

function deleteAuthority(authorityId, authorityName) {
  _pendingDelete = { type: 'authority', id: authorityId };
  document.getElementById('deleteModalMsg').textContent = `Deactivate "${authorityName}" and all its endpoints?`;
  document.getElementById('confirmDeleteModal').style.display = 'flex';
}

function closeDeleteModal() {
  document.getElementById('confirmDeleteModal').style.display = 'none';
  _pendingDelete = null;
}

async function confirmDelete() {
  if (!_pendingDelete) return;
  const { type, id } = _pendingDelete;
  const urlMap = {
    endpoint: '/api/sources/endpoints/',
    country: '/api/sources/countries/',
    authority: '/api/sources/authorities/',
  };
  try {
    await fetch(urlMap[type] + encodeURIComponent(id), { method: 'DELETE' });
    closeDeleteModal();
    closeSrcDrawer();
    toast(`${type.charAt(0).toUpperCase() + type.slice(1)} deactivated`);
    loadSourcesTab();
  } catch (e) {
    toast('Failed to deactivate');
    closeDeleteModal();
  }
}

// ── Country CRUD ──
function openAddCountryModal(editId) {
  document.getElementById('addCountryModal').style.display = 'flex';
  document.getElementById('addCountryError').style.display = 'none';
  document.getElementById('editCountryId').value = editId || '';
  document.getElementById('addCountryName').value = '';
  document.getElementById('addCountryIso').value = '';
  document.getElementById('countryModalTitle').textContent = 'Add country';
  document.getElementById('addCountrySubmit').innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" width="14" height="14"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg> Save';
}

function openEditCountryModal(countryId) {
  const c = Object.values(_countryIndex).find(x => x.id === countryId);
  if (!c) return;
  openAddCountryModal();
  document.getElementById('editCountryId').value = countryId;
  document.getElementById('addCountryName').value = c.name;
  document.getElementById('addCountryIso').value = c.iso_code;
  document.getElementById('countryModalTitle').textContent = 'Edit country';
}

function closeAddCountryModal() { document.getElementById('addCountryModal').style.display = 'none'; }

async function submitCountry() {
  const errEl = document.getElementById('addCountryError');
  errEl.style.display = 'none';
  const name = document.getElementById('addCountryName').value.trim();
  const iso = document.getElementById('addCountryIso').value.trim().toUpperCase();
  if (!name || !iso || iso.length !== 2) { errEl.textContent = 'Name and 2-letter ISO code required.'; errEl.style.display = ''; return; }

  const editId = document.getElementById('editCountryId').value;
  const btn = document.getElementById('addCountrySubmit');
  btn.disabled = true; btn.textContent = 'Saving…';
  try {
    const method = editId ? 'PUT' : 'POST';
    const url = editId ? '/api/sources/countries/' + encodeURIComponent(editId) : '/api/sources/countries';
    const res = await fetch(url, {
      method,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, iso_code: iso }),
    });
    if (!res.ok) throw new Error((await res.json()).error || 'Failed');
    closeAddCountryModal();
    toast(editId ? 'Country updated' : 'Country created');
    _addSrcCountries = [];
    loadSourcesTab();
  } catch (e) {
    errEl.textContent = e.message; errEl.style.display = '';
  } finally {
    btn.disabled = false;
    btn.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" width="14" height="14"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg> Save';
  }
}

// ── Authority CRUD ──
function openAddAuthorityModal(preselectedCountryId) {
  document.getElementById('addAuthorityModal').style.display = 'flex';
  document.getElementById('addAuthError').style.display = 'none';
  document.getElementById('editAuthorityId').value = '';
  document.getElementById('addAuthName').value = '';
  document.getElementById('addAuthType').value = 'government_ministry';
  document.getElementById('addAuthTrust').value = 'official';
  document.getElementById('addAuthUrl').value = '';
  document.getElementById('addAuthNotes').value = '';
  document.getElementById('authorityModalTitle').textContent = 'Add authority';

  const sel = document.getElementById('addAuthCountry');
  const countries = Object.values(_countryIndex);
  sel.innerHTML = '<option value="">Select a country…</option>' +
    countries.map(c => `<option value="${c.id}" ${c.id === preselectedCountryId ? 'selected' : ''}>${escHtml(c.name)}</option>`).join('');
}

function closeAddAuthorityModal() { document.getElementById('addAuthorityModal').style.display = 'none'; }

async function submitAuthority() {
  const errEl = document.getElementById('addAuthError');
  errEl.style.display = 'none';
  const countryId = document.getElementById('addAuthCountry').value;
  const name = document.getElementById('addAuthName').value.trim();
  if (!countryId || !name) { errEl.textContent = 'Country and name are required.'; errEl.style.display = ''; return; }

  const editId = document.getElementById('editAuthorityId').value;
  const btn = document.getElementById('addAuthSubmit');
  btn.disabled = true; btn.textContent = 'Saving…';
  try {
    const method = editId ? 'PUT' : 'POST';
    const url = editId ? '/api/sources/authorities/' + encodeURIComponent(editId) : '/api/sources/authorities';
    const res = await fetch(url, {
      method,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        country_id: countryId,
        name,
        authority_type: document.getElementById('addAuthType').value,
        trust_level: document.getElementById('addAuthTrust').value,
        website_url: document.getElementById('addAuthUrl').value.trim(),
        notes: document.getElementById('addAuthNotes').value.trim(),
      }),
    });
    if (!res.ok) throw new Error((await res.json()).error || 'Failed');
    closeAddAuthorityModal();
    toast(editId ? 'Authority updated' : 'Authority created');
    _addSrcCountries = [];
    loadSourcesTab();
  } catch (e) {
    errEl.textContent = e.message; errEl.style.display = '';
  } finally {
    btn.disabled = false;
    btn.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" width="14" height="14"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg> Save';
  }
}

// ═══════════════════════════════════════════════════
//  SOURCES TAB
// ═══════════════════════════════════════════════════
var _verifyResult = null;
var _allEndpoints = [];
var _allJobs = [];
var _countryIndex = {};

function isJobInProgress(j) {
  return !!j && ['queued', 'fetched', 'normalized', 'extracted'].includes(j.state);
}

async function loadSourcesTab() {
  const [statsRes, classRes, epsRes, countriesRes, jobsRes] = await Promise.all([
    fetch('/api/sources/stats').then(r => r.json()),
    fetch('/api/sources/classifications').then(r => r.json()),
    fetch('/api/sources/endpoints').then(r => r.json()),
    fetch('/api/sources/countries').then(r => r.json()),
    fetch('/api/ingestion-jobs').then(r => r.json()),
  ]);

  _allEndpoints = epsRes;
  _allJobs = jobsRes;
  _countryIndex = {};
  countriesRes.forEach(c => { _countryIndex[c.name] = c; });

  const jobsByUrl = {};
  jobsRes.forEach(j => { if (j.source_url && (!jobsByUrl[j.source_url] || j.id > jobsByUrl[j.source_url].id)) jobsByUrl[j.source_url] = j; });
  _allEndpoints.forEach(ep => { ep._job = jobsByUrl[ep.url] || null; });

  const healthyCt = _allEndpoints.filter(e => e._job && e._job.state === 'reconciled').length;
  const failedCt = _allEndpoints.filter(e => e._job && e._job.state === 'failed').length;
  const queuedCt = _allEndpoints.filter(e => isJobInProgress(e._job)).length;
  const notSyncedCt = _allEndpoints.filter(e => !e._job).length;

  document.getElementById('registryStats').innerHTML = [
    { l: 'Countries', v: statsRes.countries, cls: 'info' },
    { l: 'Endpoints', v: statsRes.endpoints, cls: 'neut' },
    { l: 'Healthy', v: healthyCt, cls: 'ok' },
    { l: 'Failing', v: failedCt, cls: failedCt ? 'crit' : 'ok' },
    { l: 'Queued', v: queuedCt, cls: queuedCt ? 'warn' : 'neut' },
    { l: 'Not synced', v: notSyncedCt, cls: 'neut' },
  ].map(s => `<div class="metric ${s.cls}" style="flex:1; min-width:120px; cursor:default;"><div class="strip"></div><div class="l">${s.l}</div><div class="v">${s.v}</div></div>`).join('');

  document.getElementById('tabSourcesCt').textContent = statsRes.endpoints;

  renderUnifiedSources();
  renderClassifications(classRes);
}

function renderPipelineSteps(j) {
  if (!j) return '';
  const stages = [
    { key: 'crawl', label: 'Crawl', doneIf: j.fetched_at || j.normalized_at, activeState: ['queued', 'fetched'] },
    { key: 'extract', label: 'Extract', doneIf: j.extracted_at, activeState: ['normalized'] },
    { key: 'reconcile', label: 'Reconcile', doneIf: j.reconciled_at, activeState: ['extracted'] },
  ];
  let failedStageFound = false;
  const pills = stages.map((s, i) => {
    let cls, icon;
    if (s.doneIf) {
      cls = 'done'; icon = '&#10003;';
    } else if (j.state === 'failed' && !failedStageFound) {
      const prevDone = i === 0 || stages[i - 1].doneIf;
      if (prevDone) { cls = 'fail'; icon = '&#10007;'; failedStageFound = true; }
      else { cls = 'pending'; icon = '·'; }
    } else if (s.activeState.includes(j.state)) {
      cls = 'active'; icon = '◌';
    } else {
      cls = 'pending'; icon = '·';
    }
    return `<span class="pipeline-step ${cls}">${icon} ${s.label}</span>`;
  });
  return `<div class="pipeline-steps">${pills.join('<span class="pipeline-arrow">→</span>')}</div>`;
}

function renderUnifiedSources() {
  const search = (document.getElementById('srcSearch')?.value || '').toLowerCase();
  const stratFilter = document.getElementById('srcStrategyFilter')?.value || '';
  const healthFilter = document.getElementById('srcHealthFilter')?.value || '';

  const grouped = {};
  _allEndpoints.forEach(ep => {
    if (stratFilter && ep.extraction_strategy !== stratFilter) return;
    if (healthFilter === 'healthy' && !(ep._job && ep._job.state === 'reconciled')) return;
    if (healthFilter === 'failing' && !(ep._job && ep._job.state === 'failed')) return;
    if (healthFilter === 'crawled' && !(ep._job && (ep._job.state === 'fetched' || ep._job.state === 'normalized') || (ep._job && ep._job.state === 'failed' && ep._job.fetched_at && !ep._job.extracted_at))) return;
    if (healthFilter === 'extracted' && !(ep._job && ep._job.state === 'extracted' || (ep._job && ep._job.state === 'failed' && ep._job.extracted_at && !ep._job.reconciled_at))) return;
    if (healthFilter === 'queued' && !isJobInProgress(ep._job)) return;
    if (healthFilter === 'not_synced' && ep._job) return;
    if (search) {
      const hay = [ep.country, ep.authority, ep.name, ep.url, ep.endpoint_id, ...(ep.sections || []), ep.extraction_strategy, ep.owner_team].join(' ').toLowerCase();
      if (!hay.includes(search)) return;
    }
    if (!grouped[ep.country]) grouped[ep.country] = [];
    grouped[ep.country].push(ep);
  });

  _groupedByCountry = grouped;
  const countries = Object.keys(grouped).sort();
  const listEl = document.getElementById('srcList');
  const emptyEl = document.getElementById('srcEmpty');

  if (!countries.length) { listEl.innerHTML = ''; emptyEl.style.display = ''; return; }
  emptyEl.style.display = 'none';

  listEl.innerHTML = countries.map(country => {
    const eps = grouped[country];
    const flag = FLAGS[country] || '';
    const okCt = eps.filter(e => e._job && e._job.state === 'reconciled').length;
    const failCt = eps.filter(e => e._job && e._job.state === 'failed').length;
    const queuedCt = eps.filter(e => isJobInProgress(e._job)).length;
    const notSyncedCt = eps.filter(e => !e._job).length;
    const suspendedCt = eps.filter(e => e.status === 'suspended').length;
    const healthCls = failCt ? 'crit' : okCt === eps.length ? 'ok' : 'warn';
    const healthLabel = failCt ? `${failCt} failing`
      : okCt === eps.length ? 'All healthy'
      : queuedCt ? `${queuedCt} queued`
      : `${notSyncedCt} not synced`;

    const coveredSections = new Set();
    eps.forEach(e => (e.sections || []).forEach(s => coveredSections.add(s)));
    const priorityCovered = [...PRIORITY_SECTIONS].filter(s => coveredSections.has(s)).length;
    const priorityTotal = PRIORITY_SECTIONS.size;
    const coverageCls = priorityCovered === priorityTotal ? 'ok' : priorityCovered >= priorityTotal * 0.6 ? 'warn' : 'crit';

    const latestTime = eps.reduce((t, e) => {
      if (!e._job) return t;
      const jt = e._job.failed_at || e._job.reconciled_at || e._job.queued_at || '';
      return jt > t ? jt : t;
    }, '');

    const cInfo = _countryIndex[country];
    const cId = cInfo ? cInfo.id : '';
    return `
      <div class="src-country-row" onclick="toggleSrcCountry(this)" data-country="${escHtml(country)}">
        <span class="src-country-flag">${flag}</span>
        <span class="src-country-name">${escHtml(country)}</span>
        <div class="src-country-meta">
          <span class="src-country-stat">${eps.length} endpoint${eps.length !== 1 ? 's' : ''}</span>
          <span class="badge ${healthCls}" style="font-size:10px; padding:1px 7px;"><span class="d"></span> ${healthLabel}</span>
          <span class="badge ${coverageCls}" style="font-size:10px; padding:1px 7px;"><span class="d"></span> ${priorityCovered}/${priorityTotal} priority</span>
          ${suspendedCt ? `<span class="badge crit" style="font-size:10px; padding:1px 7px;">${suspendedCt} suspended</span>` : ''}
          ${latestTime ? `<span class="src-country-stat">${timeAgo(latestTime)}</span>` : ''}
          <div class="src-country-actions" onclick="event.stopPropagation()">
            <button title="Add authority" onclick="openAddAuthorityModal('${escHtml(cId)}')"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" width="14" height="14"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg></button>
            <button title="Edit country" onclick="openEditCountryModal('${escHtml(cId)}')"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" width="14" height="14"><path d="M17 3a2.828 2.828 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5L17 3z"/></svg></button>
            <button class="danger" title="Deactivate country" onclick="deleteCountry('${escHtml(cId)}', '${escHtml(country)}')"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" width="14" height="14"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg></button>
          </div>
          <svg class="src-country-chevron" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="9 18 15 12 9 6"/></svg>
        </div>
      </div>
      <div class="src-eps-panel" data-country="${escHtml(country)}">
        ${eps.map((ep, idx) => {
          const j = ep._job;
          const jCls = !j ? 'neut' : j.state === 'reconciled' ? 'ok' : j.state === 'failed' ? 'crit' : 'warn';
          const jLabel = !j ? 'Not synced' : j.state === 'reconciled' ? 'Healthy' : j.state === 'failed' ? 'Failed' : j.state.charAt(0).toUpperCase() + j.state.slice(1);
          const jTime = j ? (j.failed_at || j.reconciled_at || j.queued_at) : '';
          return `
          <div class="src-ep-card" style="cursor:pointer;" onclick="openSrcDrawer('${escHtml(country)}', ${idx})">
            <div class="src-ep-header">
              <span class="src-ep-name" title="${escHtml(ep.endpoint_id)}">${escHtml(ep.name || ep.authority)}</span>
              <span class="badge ${jCls}" style="font-size:10px; padding:1px 7px;"><span class="d"></span> ${jLabel}</span>
              ${ep.status === 'suspended' ? '<span class="badge crit" style="font-size:10px; padding:1px 7px;">Suspended</span>' : ''}
            </div>
            ${ep.name ? `<div class="src-ep-auth">${escHtml(ep.authority)}</div>` : ''}
            <div class="src-ep-url"><a href="${escHtml(ep.url)}" target="_blank" rel="noopener" onclick="event.stopPropagation()">${escHtml(ep.url)}</a></div>
            ${renderPipelineSteps(j)}
            <div style="display:flex; align-items:center; justify-content:space-between; gap:8px;">
              <div>
                <div class="src-ep-sections">
                  ${[...(ep.sections || [])].sort((a,b) => (PRIORITY_SECTIONS.has(a)?0:1) - (PRIORITY_SECTIONS.has(b)?0:1)).map(s => `<span class="s${PRIORITY_SECTIONS.has(s) ? ' priority' : ''}">${escHtml(s.replace(/_/g, ' '))}</span>`).join('')}
                </div>
                <div class="src-ep-tags">
                  ${ep.extraction_strategy ? `<span class="t strategy">${escHtml(ep.extraction_strategy)}</span>` : ''}
                  ${ep.source_type ? `<span class="t type">${escHtml(ep.source_type)}</span>` : ''}
                  ${ep.crawl_frequency ? `<span class="t freq">${escHtml(ep.crawl_frequency)}</span>` : ''}
                </div>
              </div>
              ${jTime ? `<span style="font-family:var(--font-mono); font-size:10.5px; color:var(--ink-4); white-space:nowrap;">${timeAgo(jTime)}</span>` : ''}
            </div>
            ${j && j.state === 'failed' ? `<div style="font-size:11.5px; color:var(--crit); margin-top:2px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;" title="${escHtml(j.failure_reason || '')}">${escHtml(j.failure_reason || 'Unknown error')}</div>` : ''}
          </div>`;
        }).join('')}
      </div>`;
  }).join('');
}

function toggleSrcCountry(row) {
  const country = row.dataset.country;
  const panel = document.querySelector(`.src-eps-panel[data-country="${country}"]`);
  const isOpen = row.classList.contains('open');
  row.classList.toggle('open', !isOpen);
  panel.classList.toggle('open', !isOpen);
}

function renderClassifications(items) {
  const el = document.getElementById('classificationList');
  const empty = document.getElementById('classEmpty');
  if (!items.length) { el.innerHTML = ''; empty.style.display = ''; return; }
  empty.style.display = 'none';

  el.innerHTML = `<div style="display:flex; flex-direction:column; gap:0; border:1px solid var(--paper-line); border-radius:var(--r-l); overflow:hidden; background:var(--paper);">
    ${items.map(c => {
      const cls = c.classification === 'official' ? 'ok' : c.classification === 'unofficial_trusted' ? 'warn' : 'crit';
      const label = c.classification === 'official' ? 'Official' : c.classification === 'unofficial_trusted' ? 'Unofficial · Trusted' : 'Not official';
      const ts = fmtTime(c.created_at);
      return `<div style="display:flex; align-items:center; gap:12px; padding:12px 16px; border-bottom:1px solid var(--paper-line);">
        <span class="badge ${cls}" style="min-width:110px; justify-content:center;"><span class="d"></span> ${label}</span>
        <div style="flex:1; min-width:0;">
          <div style="font-size:13px; font-weight:600; color:var(--ink); overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">
            <a href="${escHtml(c.url)}" target="_blank" rel="noopener" style="color:var(--info); border-bottom:1px solid rgba(47,91,183,0.25);">${escHtml(c.url)}</a>
          </div>
          ${c.matched_country ? `<span style="font-size:11.5px; color:var(--ink-3);">${escHtml(c.matched_country)}${c.matched_authority ? ' · ' + escHtml(c.matched_authority) : ''}</span>` : ''}
        </div>
        ${c.notes ? `<span style="font-size:12px; color:var(--ink-3); max-width:180px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;" title="${escHtml(c.notes)}">${escHtml(c.notes)}</span>` : ''}
        <span style="font-family:var(--font-mono); font-size:10.5px; color:var(--ink-4); white-space:nowrap;">${ts}</span>
      </div>`;
    }).join('')}
  </div>`;
}

function renderPdfs(jobs) {
  const el = document.getElementById('pdfList');
  const empty = document.getElementById('pdfEmpty');
  if (!jobs.length) { el.innerHTML = ''; empty.style.display = ''; return; }
  empty.style.display = 'none';

  el.innerHTML = `<div style="display:flex; flex-direction:column; gap:0; border:1px solid var(--paper-line); border-radius:var(--r-l); overflow:hidden; background:var(--paper);">
    ${jobs.map(j => {
      const stCls = j.state === 'reconciled' ? 'ok' : j.state === 'failed' ? 'crit' : j.state === 'extracted' ? 'info' : 'neut';
      const src = j.source_url || '';
      const title = src.includes('#') ? src.split('#').pop() : src.replace('pdf://', '');
      const ts = fmtTime(j.queued_at);
      const addedBy = j.triggered_by || j.queued_by || '—';
      return `<div style="display:flex; align-items:center; gap:12px; padding:12px 16px; border-bottom:1px solid var(--paper-line); cursor:pointer;" onclick="window.location='/compliance/pipeline/${j.id}'">
        <div style="width:32px; height:32px; border-radius:var(--r-s); background:var(--crit-soft); display:grid; place-items:center; flex-shrink:0;">
          <svg viewBox="0 0 24 24" fill="none" stroke="var(--crit-2)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" width="16" height="16"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
        </div>
        <div style="flex:1; min-width:0;">
          <div style="font-size:13.5px; font-weight:600; color:var(--ink); overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">${escHtml(title)}</div>
          <div style="font-size:11.5px; color:var(--ink-3);">${j.country ? escHtml(j.country) + ' · ' : ''}Job #${j.id}</div>
        </div>
        <span style="font-size:12px; color:var(--ink-3); max-width:140px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;" title="${escHtml(addedBy)}">${escHtml(addedBy)}</span>
        <span class="badge ${stCls}"><span class="d"></span> ${j.state}</span>
        <span style="font-family:var(--font-mono); font-size:10.5px; color:var(--ink-4); white-space:nowrap;">${ts}</span>
      </div>`;
    }).join('')}
  </div>`;
}

async function verifyUrl() {
  const input = document.getElementById('verifyUrlInput');
  const url = input.value.trim();
  if (!url) return;

  const res = await fetch('/api/sources/verify', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ url }),
  });
  _verifyResult = await res.json();
  _verifyResult._url = url;
  renderVerifyResult();
}

function renderVerifyResult() {
  const wrap = document.getElementById('verifyResult');
  const inner = document.getElementById('verifyResultInner');
  wrap.style.display = '';

  const r = _verifyResult;
  const url = r._url;

  if (r.match === 'exact' || r.match === 'domain') {
    const matchLabel = r.match === 'exact' ? 'Exact endpoint match' : 'Domain match';
    inner.innerHTML = `
      <div style="background:var(--ok-soft); border:1px solid var(--ok-line); border-radius:var(--r-l); padding:18px 20px;">
        <div style="display:flex; align-items:center; gap:10px; margin-bottom:12px;">
          <span class="badge ok"><span class="d"></span> Official</span>
          <span style="font-family:var(--font-mono); font-size:11px; color:var(--ok-2); font-weight:600;">${matchLabel}</span>
          ${r.escalation_required ? '<span class="badge major"><span class="d"></span> Escalation required</span>' : ''}
        </div>
        <div style="font-size:15px; font-weight:700; color:var(--ink); margin-bottom:6px;">${escHtml(r.authority || '')}</div>
        <div style="font-size:13px; color:var(--ink-2); margin-bottom:4px;">
          ${r.country ? '<span class="flag" style="font-size:14px;">' + (FLAGS[r.country] || '') + '</span> ' + escHtml(r.country) : ''}
          ${r.authority_type ? ' · <span style="font-family:var(--font-mono); font-size:11px;">' + escHtml(r.authority_type) + '</span>' : ''}
        </div>
        ${r.authority_url ? '<div style="font-size:12.5px; margin-top:4px;"><a href="' + escHtml(r.authority_url) + '" target="_blank" rel="noopener" style="color:var(--info); border-bottom:1px solid rgba(47,91,183,0.25);">' + escHtml(r.authority_url) + '</a></div>' : ''}
        ${r.sections && r.sections.length ? '<div style="margin-top:10px; display:flex; gap:5px; flex-wrap:wrap;">' + r.sections.map(s => '<span class="section-chip">' + escHtml(s) + '</span>').join('') + '</div>' : ''}
        <div style="margin-top:14px; padding-top:12px; border-top:1px solid var(--ok-line); display:flex; gap:8px;">
          <button class="btn btn-primary" style="font-size:12px; height:30px;" onclick="classifyVerified('official')">Confirm official</button>
          <button class="btn" style="font-size:12px; height:30px;" onclick="classifyVerified('unofficial_trusted')">Mark as trusted (unofficial)</button>
        </div>
      </div>`;
  } else if (r.match === 'previously_classified') {
    const cls = r.classification === 'official' ? 'ok' : r.classification === 'unofficial_trusted' ? 'warn' : 'crit';
    const label = r.classification === 'official' ? 'Official' : r.classification === 'unofficial_trusted' ? 'Unofficial · Trusted' : 'Not official';
    inner.innerHTML = `
      <div style="background:var(--${cls}-soft); border:1px solid var(--${cls}-line); border-radius:var(--r-l); padding:18px 20px;">
        <div style="display:flex; align-items:center; gap:10px; margin-bottom:10px;">
          <span class="badge ${cls}"><span class="d"></span> ${label}</span>
          <span style="font-family:var(--font-mono); font-size:11px; color:var(--ink-3); font-weight:600;">Previously classified</span>
        </div>
        ${r.country ? '<div style="font-size:14px; font-weight:600; color:var(--ink); margin-bottom:4px;">' + escHtml(r.country) + (r.authority ? ' · ' + escHtml(r.authority) : '') + '</div>' : ''}
        ${r.notes ? '<div style="font-size:12.5px; color:var(--ink-2); margin-top:6px;">' + escHtml(r.notes) + '</div>' : ''}
        <div style="margin-top:14px; padding-top:12px; border-top:1px solid var(--${cls}-line); display:flex; gap:8px;">
          <button class="btn" style="font-size:12px; height:30px;" onclick="classifyVerified('official')">Reclassify: Official</button>
          <button class="btn" style="font-size:12px; height:30px;" onclick="classifyVerified('unofficial_trusted')">Reclassify: Trusted</button>
          <button class="btn btn-danger" style="font-size:12px; height:30px;" onclick="classifyVerified('not_official')">Reclassify: Not official</button>
        </div>
      </div>`;
  } else {
    inner.innerHTML = `
      <div style="background:var(--paper-2); border:1px solid var(--paper-line); border-radius:var(--r-l); padding:18px 20px;">
        <div style="display:flex; align-items:center; gap:10px; margin-bottom:10px;">
          <span class="badge neut"><span class="d"></span> Unknown</span>
          <span style="font-family:var(--font-mono); font-size:11px; color:var(--ink-3); font-weight:600;">Not in registry · domain: ${escHtml(r.domain || '')}</span>
        </div>
        <div style="font-size:13.5px; color:var(--ink-2); margin-bottom:14px;">This URL doesn't match any known official source. Classify it below.</div>
        <div style="margin-bottom:12px;">
          <div style="font-family:var(--font-mono); font-size:10px; font-weight:700; letter-spacing:0.1em; text-transform:uppercase; color:var(--ink-3); margin-bottom:6px;">Notes (optional)</div>
          <input id="classifyNotes" style="width:100%; height:32px; padding:0 10px; font-family:var(--font-ui); font-size:13px; border:1px solid var(--paper-line); border-radius:var(--r-s); background:var(--paper); color:var(--ink); outline:none;" placeholder="e.g. Well-known law firm, government gazette…" />
        </div>
        <div style="display:flex; gap:8px;">
          <button class="btn btn-primary" style="font-size:12px; height:30px;" onclick="classifyVerified('official')">Official</button>
          <button class="btn btn-warn" style="font-size:12px; height:30px;" onclick="classifyVerified('unofficial_trusted')">Unofficial · Trusted</button>
          <button class="btn btn-danger" style="font-size:12px; height:30px;" onclick="classifyVerified('not_official')">Not official</button>
        </div>
      </div>`;
  }
}

async function classifyVerified(classification) {
  if (!_verifyResult) return;
  const notes = document.getElementById('classifyNotes')?.value || '';
  await fetch('/api/sources/classify', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      url: _verifyResult._url,
      classification,
      notes,
      classified_by: 'Shivansh Gupta | Product',
      matched_authority: _verifyResult.authority || '',
      matched_country: _verifyResult.country || '',
    }),
  });
  document.getElementById('verifyResult').style.display = 'none';
  document.getElementById('verifyUrlInput').value = '';
  _verifyResult = null;
  const classRes = await fetch('/api/sources/classifications').then(r => r.json());
  renderClassifications(classRes);
}

// ═══════════════════════════════════════════════════
//  SOURCE DRAWER
// ═══════════════════════════════════════════════════
var _groupedByCountry = {};

function getRetryLabel(j) {
  if (!j || j.state !== 'failed') return 'Retry';
  if (j.extracted_at) return 'Retry reconciliation';
  if (j.normalized_at || j.fetched_at) return 'Retry extraction';
  return 'Retry';
}

function renderDrawerPipeline(j) {
  const stages = [
    { label: 'Crawl', doneTs: j.fetched_at || j.normalized_at, activeStates: ['queued', 'fetched'] },
    { label: 'Extraction', doneTs: j.extracted_at, activeStates: ['normalized'] },
    { label: 'Reconciliation', doneTs: j.reconciled_at, activeStates: ['extracted'] },
  ];
  let failFound = false;
  const rows = stages.map((s, i) => {
    let statusHtml, tsHtml;
    if (s.doneTs) {
      statusHtml = '<span style="color:var(--ok-2);font-weight:600;">&#10003; Completed</span>';
      tsHtml = `<span style="font-family:var(--font-mono);font-size:11px;color:var(--ink-4);">${timeAgo(s.doneTs)}</span>`;
    } else if (j.state === 'failed' && !failFound) {
      const prevDone = i === 0 || stages[i - 1].doneTs;
      if (prevDone) {
        statusHtml = '<span style="color:var(--crit);font-weight:600;">&#10007; Failed</span>';
        tsHtml = j.failed_at ? `<span style="font-family:var(--font-mono);font-size:11px;color:var(--ink-4);">${timeAgo(j.failed_at)}</span>` : '';
        failFound = true;
      } else {
        statusHtml = '<span style="color:var(--ink-4);">— Pending</span>';
        tsHtml = '';
      }
    } else if (s.activeStates.includes(j.state)) {
      statusHtml = '<span style="color:var(--warn-2);font-weight:600;">◌ Running</span>';
      tsHtml = '';
    } else {
      statusHtml = '<span style="color:var(--ink-4);">— Pending</span>';
      tsHtml = '';
    }
    return `<div style="display:flex;align-items:center;gap:12px;padding:8px 0;border-bottom:1px solid var(--paper-line);">
      <span style="min-width:100px;font-size:12.5px;font-weight:600;color:var(--ink);">${s.label}</span>
      <span style="flex:1;">${statusHtml}</span>
      ${tsHtml}
    </div>`;
  });

  const failureRow = j.state === 'failed' && j.failure_reason
    ? `<div style="margin-top:8px;padding:8px 12px;border-radius:6px;background:var(--crit-soft);border:1px solid var(--crit-line);font-size:12px;color:var(--crit);">${escHtml(j.failure_reason)}</div>`
    : '';

  return `
    <div class="src-drawer-divider"></div>
    <div class="src-drawer-field">
      <div class="src-drawer-label">Pipeline status</div>
      <div style="margin-top:6px;">
        ${rows.join('')}
        ${failureRow}
      </div>
    </div>`;
}

function openSrcDrawer(country, idx) {
  const eps = _groupedByCountry[country];
  if (!eps || !eps[idx]) return;
  const ep = eps[idx];
  const flag = FLAGS[country] || '';

  document.getElementById('srcDrawerTitle').textContent = ep.name || ep.authority;
  document.getElementById('srcDrawerSubtitle').innerHTML = `${flag} ${escHtml(country)} · <span style="font-family:var(--font-mono);font-size:11px;">${escHtml(ep.endpoint_id)}</span>`;

  const body = document.getElementById('srcDrawerBody');
  body.innerHTML = `
    <div class="src-drawer-field">
      <div class="src-drawer-label">Authority</div>
      <div class="src-drawer-value" style="font-weight:600;">${escHtml(ep.authority)}</div>
      <div class="src-drawer-value" style="font-size:12px; color:var(--ink-3); margin-top:2px;">${escHtml(ep.authority_type.replace(/_/g, ' '))}</div>
      ${ep.authority_url ? `<div class="src-drawer-value" style="margin-top:4px;"><a href="${escHtml(ep.authority_url)}" target="_blank" rel="noopener">${escHtml(ep.authority_url)}</a></div>` : ''}
    </div>

    <div class="src-drawer-field">
      <div class="src-drawer-label">Source URL</div>
      <div class="src-drawer-value"><a href="${escHtml(ep.url)}" target="_blank" rel="noopener">${escHtml(ep.url)}</a></div>
    </div>

    ${ep.sections && ep.sections.length ? `
    <div class="src-drawer-field">
      <div class="src-drawer-label">Sections covered</div>
      <div class="src-drawer-tags" style="display:flex;flex-wrap:wrap;gap:5px;">
        ${ep.sections.map(s => `<span style="font-size:11px;padding:3px 9px;border-radius:4px;background:var(--ok-soft);border:1px solid var(--ok-line);color:var(--ok-2);">${escHtml(s.replace(/_/g, ' '))}</span>`).join('')}
      </div>
    </div>` : ''}

    <div class="src-drawer-divider"></div>

    <div class="src-drawer-row">
      <div class="src-drawer-field">
        <div class="src-drawer-label">Source type</div>
        <div class="src-drawer-value">${escHtml(ep.source_type)}</div>
      </div>
      <div class="src-drawer-field">
        <div class="src-drawer-label">Language</div>
        <div class="src-drawer-value">${escHtml(ep.content_language || 'en')}</div>
      </div>
    </div>

    <div class="src-drawer-row">
      <div class="src-drawer-field">
        <div class="src-drawer-label">Extraction strategy</div>
        <div class="src-drawer-value"><span style="font-family:var(--font-mono);font-size:12px;padding:2px 8px;background:var(--purple-soft);border:1px solid var(--purple-line);border-radius:4px;color:var(--purple-2);">${escHtml(ep.extraction_strategy)}</span></div>
      </div>
      <div class="src-drawer-field">
        <div class="src-drawer-label">Parser key</div>
        <div class="src-drawer-value" style="font-family:var(--font-mono); font-size:12px;">${escHtml(ep.parser_key)}</div>
      </div>
    </div>

    <div class="src-drawer-row">
      <div class="src-drawer-field">
        <div class="src-drawer-label">Crawl frequency</div>
        <div class="src-drawer-value">${escHtml(ep.crawl_frequency)}</div>
      </div>
      <div class="src-drawer-field">
        <div class="src-drawer-label">Change detection</div>
        <div class="src-drawer-value">${escHtml(ep.change_detection_strategy || 'semantic')}</div>
      </div>
    </div>

    <div class="src-drawer-row">
      <div class="src-drawer-field">
        <div class="src-drawer-label">Trust level</div>
        <div class="src-drawer-value">${escHtml(ep.trust_level || 'official')}</div>
      </div>
      <div class="src-drawer-field">
        <div class="src-drawer-label">Owner team</div>
        <div class="src-drawer-value">${escHtml(ep.owner_team || '—')}</div>
      </div>
    </div>

    <div class="src-drawer-divider"></div>

    <div class="src-drawer-row">
      <div class="src-drawer-field">
        <div class="src-drawer-label">JavaScript heavy</div>
        <div class="src-drawer-value">${ep.is_javascript_heavy ? '<span style="color:var(--warn);">Yes</span>' : 'No'}</div>
      </div>
      <div class="src-drawer-field">
        <div class="src-drawer-label">Requires auth</div>
        <div class="src-drawer-value">${ep.requires_authentication ? '<span style="color:var(--warn);">Yes</span>' : 'No'}</div>
      </div>
    </div>

    <div class="src-drawer-row">
      <div class="src-drawer-field">
        <div class="src-drawer-label">Escalation required</div>
        <div class="src-drawer-value">${ep.escalation_required ? '<span style="color:var(--crit);">Yes</span>' : 'No'}</div>
      </div>
      <div class="src-drawer-field">
        <div class="src-drawer-label">Supports replay</div>
        <div class="src-drawer-value">${ep.supports_replay ? '<span style="color:var(--ok);">Yes</span>' : 'No'}</div>
      </div>
    </div>

    ${ep.notes ? `
    <div class="src-drawer-divider"></div>
    <div class="src-drawer-field">
      <div class="src-drawer-label">Notes</div>
      <div class="src-drawer-value">${escHtml(ep.notes)}</div>
    </div>` : ''}

    ${ep._job ? renderDrawerPipeline(ep._job) : `
    <div class="src-drawer-divider"></div>
    <div class="src-drawer-field">
      <div class="src-drawer-label">Pipeline status</div>
      <div class="src-drawer-value"><span class="badge neut" style="font-size:11px;padding:2px 8px;"><span class="d"></span> Not synced</span></div>
    </div>`}

    <div class="src-drawer-actions">
      <button class="btn btn-primary" onclick="openEditSourceModal('${escHtml(country)}', ${idx})">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" width="14" height="14"><path d="M17 3a2.828 2.828 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5L17 3z"/></svg>
        Edit
      </button>
      ${ep._job && ep._job.state === 'failed' ? `<button class="btn btn-primary" onclick="event.stopPropagation(); retryJob(${ep._job.id})" style="background:var(--warn);border-color:var(--warn);">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" width="14" height="14"><polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/></svg>
        ${getRetryLabel(ep._job)}
      </button>` : ''}
      <button class="btn btn-danger" onclick="deleteEndpoint('${escHtml(ep.endpoint_id)}')">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" width="14" height="14"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
        Deactivate
      </button>
    </div>
  `;

  document.getElementById('srcDrawerScrim').classList.add('open');
  document.getElementById('srcDrawer').classList.add('open');
  document.body.style.overflow = 'hidden';
}

function closeSrcDrawer() {
  document.getElementById('srcDrawerScrim').classList.remove('open');
  document.getElementById('srcDrawer').classList.remove('open');
  document.body.style.overflow = '';
}

document.addEventListener('keydown', e => { if (e.key === 'Escape') closeSrcDrawer(); });
