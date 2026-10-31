// Script of the ticket 05 prototype. Prototype only.
const P = {
  alert: '<path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3"/><path d="M12 9v4"/><path d="M12 17h.01"/>',
  check: '<circle cx="12" cy="12" r="10"/><path d="m9 12 2 2 4-4"/>',
  x: '<circle cx="12" cy="12" r="10"/><path d="m15 9-6 6"/><path d="m9 9 6 6"/>',
  info: '<circle cx="12" cy="12" r="10"/><path d="M12 16v-4"/><path d="M12 8h.01"/>',
  help: '<circle cx="12" cy="12" r="10"/><path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3"/><path d="M12 17h.01"/>',
  plus: '<path d="M5 12h14"/><path d="M12 5v14"/>',
  minus: '<path d="M5 12h14"/>',
  trash: '<path d="M3 6h18"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6"/><path d="M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>',
  chev: '<path d="m9 18 6-6-6-6"/>', down: '<path d="m6 9 6 6 6-6"/>', up: '<path d="m18 15-6-6-6 6"/>',
  more: '<circle cx="12" cy="12" r="1"/><circle cx="19" cy="12" r="1"/><circle cx="5" cy="12" r="1"/>',
  merge: '<circle cx="18" cy="18" r="3"/><circle cx="6" cy="6" r="3"/><path d="M6 21V9a9 9 0 0 0 9 9"/>',
  db: '<ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M3 5V19A9 3 0 0 0 21 19V5"/><path d="M3 12A9 3 0 0 0 21 12"/>',
  file: '<path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z"/><path d="M14 2v4a2 2 0 0 0 2 2h4"/>',
  close: '<path d="M18 6 6 18"/><path d="m6 6 12 12"/>',
  search: '<circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/>',
  table: '<path d="M12 3v18"/><rect width="18" height="18" x="3" y="3" rx="2"/><path d="M3 9h18"/><path d="M3 15h18"/>',
  graph: '<circle cx="5" cy="6" r="3"/><circle cx="19" cy="6" r="3"/><circle cx="12" cy="18" r="3"/><path d="M7.5 7.5 10.5 16"/><path d="m16.5 7.5-3 8.5"/>',
  layout: '<rect width="18" height="18" x="3" y="3" rx="2"/><path d="M3 9h18"/><path d="M9 21V9"/>',
  sigma: '<path d="M18 7V4H6l6 8-6 8h12v-3"/>', col: '<rect width="18" height="18" x="3" y="3" rx="2"/><path d="M9 3v18"/>',
  chart: '<path d="M3 3v18h18"/><path d="M18 17V9"/><path d="M13 17V5"/><path d="M8 17v-3"/>',
  filter: '<path d="M22 3H2l8 9.46V19l4 2v-8.54L22 3z"/>', link: '<path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/>',
  shield: '<path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z"/>',
  bot: '<path d="M12 8V4H8"/><rect width="16" height="12" x="4" y="8" rx="2"/><path d="M2 14h2"/><path d="M20 14h2"/><path d="M15 13v2"/><path d="M9 13v2"/>',
  loader: '<path d="M21 12a9 9 0 1 1-6.22-8.56"/>', eyeoff: '<path d="M9.88 9.88a3 3 0 1 0 4.24 4.24"/><path d="M10.73 5.08A10.43 10.43 0 0 1 12 5c7 0 10 7 10 7a13.16 13.16 0 0 1-1.67 2.68"/><path d="M6.61 6.61A13.53 13.53 0 0 0 2 12s3 7 10 7a9.74 9.74 0 0 0 5.39-1.61"/><path d="m2 2 20 20"/>',
  bookmark: '<path d="m19 21-7-4-7 4V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2v16z"/>', page: '<rect width="18" height="14" x="3" y="5" rx="2"/>',
  locate: '<circle cx="12" cy="12" r="3"/><path d="M12 2v4"/><path d="M12 18v4"/><path d="M2 12h4"/><path d="M18 12h4"/>', max: '<path d="M8 3H5a2 2 0 0 0-2 2v3"/><path d="M21 8V5a2 2 0 0 0-2-2h-3"/><path d="M3 16v3a2 2 0 0 0 2 2h3"/><path d="M16 21h3a2 2 0 0 0 2-2v-3"/>',
  refresh: '<path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8"/><path d="M21 3v5h-5"/><path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16"/><path d="M8 16H3v5"/>',
};
const I = (n, label) => `<svg class="i" viewBox="0 0 24 24" ${label ? `role="img" aria-label="${label}"` : 'aria-hidden="true"'}>${P[n]}</svg>`;
const q = new URLSearchParams(window.PROTO_QS ?? location.search);
document.documentElement.dataset.theme = q.get('theme') || 'dark';
const view = q.get('view') || 'table';
const group = q.get('group') || 'breaks';
const scope = q.get('scope') || 'plan';
const paneKind = q.get('pane') || '';
const state = q.get('state') || '';
const proposals = q.get('proposals') === '1';
const complOpen = q.get('compl') === 'open';
const wfList = q.get('wflist') === '1';
const esc = (s) => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;');

const TYPE_ICON = { Measure: 'sigma', Column: 'col', Visual: 'chart', 'Page filter': 'filter', Relationship: 'link', Role: 'shield', Page: 'page', Bookmark: 'bookmark', Table: 'table' };
const STATUS = {
  blocking: (t = 'Blocking') => `<span class="status s-bad">${I('x')}${t}</span>`,
  warning: (t = 'Warning') => `<span class="status s-warn">${I('alert')}${t}</span>`,
  info: (t = 'Information') => `<span class="status s-plain">${I('info')}${t}</span>`,
};
const ACTION = { include_in_rewrite: 'Include in rewrite', set_policy_cascade: 'Cascade', set_policy_repoint: 'Repoint', set_policy_block: 'Keep blocked', add_from_donor: 'Add from donor', map_to_target: 'Map to target', drop_added_object: 'Drop added object', remove_field: 'Remove field' };

const BREAKS = [
  { id: 'b1', st: 'blocking', type: 'Measure', name: '[Net Sales]', where: 'Sales Master', sev: 'Breaks', cert: 'certain', reason: 'Uses a removed column.', path: [['Column', 'Sales[Discount]', 'Removed'], ['used by', '[Net Sales]']], other: 0, primary: 'set_policy_repoint', acts: ['set_policy_cascade', 'set_policy_block'] },
  { id: 'b2', st: 'blocking', type: 'Visual', name: 'Discount by region', where: 'Sales Overview, page Overview', sev: 'Breaks', cert: 'certain', reason: 'A field uses a removed column.', path: [['Column', 'Sales[Discount]', 'Removed'], ['in visual', 'Discount by region']], other: 1, primary: 'set_policy_cascade', acts: ['set_policy_repoint', 'set_policy_block'] },
  { id: 'b3', st: 'blocking', type: 'Measure', name: '[YoY Sales]', where: 'Sales Master', sev: 'Breaks', cert: 'certain', reason: 'Uses a renamed measure (not rewritten).', path: [['Measure', '[Total Sales]', 'Renamed to [Sales Amount]'], ['used by', '[YoY Sales]']], other: 0, primary: 'include_in_rewrite', acts: [] },
  { id: 'b4', st: 'blocking', type: 'Role', name: 'Region managers', where: 'Sales Master', sev: 'Breaks', cert: 'certain', reason: 'The RLS filter uses a removed column.', path: [['Column', 'Sales[Discount]', 'Removed'], ['filters', 'Region managers']], other: 0, primary: 'set_policy_repoint', acts: ['set_policy_cascade', 'set_policy_block'] },
  { id: 'b5', st: 'warning', type: 'Visual', name: 'Margin card', where: 'Sales Overview, page Overview', sev: 'Changes value', cert: 'certain', reason: 'Uses a replaced measure.', path: [['Measure', '[Margin %]', 'Replaced'], ['in visual', 'Margin card']], other: 2, acts: [] },
  { id: 'b6', st: 'warning', type: 'Page filter', name: 'Region', where: 'Sales Overview, page Details', sev: 'Changes value', cert: 'certain', reason: 'The filter uses a replaced column.', path: [['Column', 'Geo[Region]', 'Replaced'], ['filters', 'page Details']], other: 0, acts: [] },
  { id: 'b7', st: 'warning', type: 'Measure', name: '[Avg Price]', where: 'Sales Master', sev: 'Needs review', cert: 'possible', reason: 'Filter context can change.', path: [['Relationship', 'Sales to Date', 'Changed'], ['filters', 'Sales'], ['used by', '[Avg Price]']], other: 0, acts: [] },
  { id: 'b8', st: 'info', type: 'Visual', name: 'Margin trend', where: 'Exec KPIs, page Summary', sev: 'Changes value', cert: 'certain', reason: 'Uses a replaced measure.', path: [['Measure', '[Margin %]', 'Replaced'], ['in visual', 'Margin trend']], other: 0, notChanged: true, acts: [] },
  { id: 'b9', st: 'warning', type: 'Measure', name: '[Promo Lift]', where: 'Sales Master', sev: 'Needs review', cert: 'possible', reason: 'Filter context can change.', path: [['Relationship', 'Sales to Date', 'Changed'], ['filters', 'Sales'], ['used by', '[Promo Lift]']], other: 0, proposed: true, acts: [] },
];
const NEEDS = [
  { id: 'n1', st: 'blocking', type: 'Column', name: 'Product[Brand]', where: 'needed by [Brand Share]', sev: 'Missing', cert: 'certain', reason: 'No donor has this object.', path: [['Measure', '[Brand Share]', 'Added'], ['uses', 'Product[Brand]']], other: 0, primary: 'map_to_target', acts: ['drop_added_object'] },
  { id: 'n2', st: 'blocking', type: 'Measure', name: '[Units]', where: 'needed by [Units per Order]', sev: 'Name clash', cert: 'certain', reason: 'The target has a different object with this name.', path: [['Measure', '[Units per Order]', 'Added'], ['uses', '[Units]']], other: 0, primary: 'map_to_target', acts: ['drop_added_object'] },
  { id: 'n3', st: 'warning', type: 'Column', name: 'Sales[Amount]', where: 'from Sales B, needed by [Net Margin]', sev: 'Will be added', cert: 'certain', reason: 'The target does not have this column.', path: [['Measure', '[Net Margin]', 'Added'], ['uses', 'Sales[Amount]']], other: 1, acts: ['map_to_target', 'drop_added_object'] },
  { id: 'n4', st: 'warning', type: 'Relationship', name: 'Sales to Date', where: 'from Sales B, needed by [Net Margin]', sev: 'Will be added', cert: 'certain', reason: 'The target does not have this relationship.', path: [['Measure', '[Net Margin]', 'Added'], ['uses', 'Sales[Amount]'], ['related by', 'Sales to Date']], other: 0, acts: ['map_to_target', 'drop_added_object'] },
  { id: 'n5', st: 'warning', type: 'Column', name: 'Customer[Segment]', where: 'field of copied visual Top customers', sev: 'Will be added', cert: 'certain', reason: 'A copied visual uses a field that the target does not have.', path: [['Visual', 'Top customers', 'Copied'], ['uses field', 'Customer[Segment]']], other: 0, acts: ['map_to_target', 'remove_field'] },
  { id: 'n6', st: 'info', type: 'Column', name: 'Date[Year]', where: 'mapped to Calendar[Year]', sev: 'Mapped', cert: 'certain', reason: 'Mapped to an existing target column.', path: [['Measure', '[Net Margin]', 'Added'], ['uses', 'Date[Year]']], other: 0, acts: ['add_from_donor', 'map_to_target'] },
];

const sidebar = `<aside class="sidebar"><div class="brand">PBIBrain</div><nav aria-label="Main navigation">${['Overview', 'Search', 'Graph', 'Inspector', 'Review queue', 'Development Center', 'Settings'].map(n => `<button class="nav" ${n === 'Development Center' ? 'aria-current="page"' : ''}>${n === 'Development Center' ? I('merge') : ''}<span>${n}</span></button>`).join('')}</nav></aside>`;
const crumbs = `<header class="topbar"><nav aria-label="Breadcrumb" style="display:flex;align-items:center;gap:2px;min-width:0"><button class="crumb">Development Center</button>${I('chev')}<button class="crumb">Sales master merge</button>${I('chev')}<span class="crumb-now" aria-current="page">Impact</span></nav></header>`;
const header = `<div class="work-head"><div class="work-title"><h1>Sales master merge</h1><div class="target-line"><span>${I('db')}Target model: Sales Master</span><span>${I('file')}Target report: Sales Overview</span></div></div>
  <div class="head-actions"><button class="status s-bad" style="border:0;min-height:28px;cursor:pointer;font-size:13px">${I('x')}Plan not valid: 6 blocking</button><button class="btn only-wide">${I('refresh')}Check sources</button><button class="btn btn-icon" aria-label="More actions">${I('more')}</button></div></div>`;
const tabs = `<div class="tabs" role="tablist" aria-label="Session views">${[['Compare'], ['Impact'], ['Plan', '6', true], ['Agent', '4'], ['Sources'], ['Log']].map(([t, c, bad]) => `<button class="tab" role="tab" aria-selected="${t === 'Impact'}" ${t === 'Impact' ? 'aria-controls="impact-panel"' : 'tabindex="-1"'}>${t}${c ? `<span class="count ${bad ? 'bad' : ''}">${c}<span class="sr"> ${bad ? 'blocking' : 'open'}</span></span>` : ''}</button>`).join('')}</div>`;

const large = state === 'large';
const nB = large ? '5,214' : BREAKS.filter(i => proposals || !i.proposed).length;
const nN = large ? '388' : NEEDS.length;
const seg = (label, items) => `<div class="seg" role="group" aria-label="${label}">${items.map(([t, on, extra]) => `<button aria-pressed="${on}">${t}${extra || ''}</button>`).join('')}</div>`;
function toolbar() {
  const bc = (n) => `<span class="count bad">${n}<span class="sr"> blocking</span></span>`;
  const row1 = `<div class="ibar">
    <button class="trigger" aria-haspopup="listbox" aria-label="Scope: ${scope === 'row' ? 'Row [Net Margin]' : 'Whole plan'}"><span class="lbl">Scope</span>${scope === 'row' ? 'Row: [Net Margin]' : 'Whole plan'}${I('down')}</button>
    ${seg('Impact group', [[`Breaks <span class="muted small">${nB}</span>`, group === 'breaks', bc(large ? 212 : 4)], [`Needs <span class="muted small">${nN}</span>`, group === 'needs', bc(2)], [`Offers <span class="muted small">${large ? 41 : 7}</span>`, group === 'offers']])}
    <span class="grow"></span>
    ${seg('Impact view', [[`${I('table')}Table`, view === 'table'], [`${I('graph')}Graph`, view === 'graph'], [`${I('layout')}Wireframe`, view === 'wireframe']])}
  </div>`;
  const row2 = group === 'offers' ? '' : `<div class="ibar">
    <button class="chip-check" aria-pressed="false">${I('x')}Blocking only</button>
    <button class="trigger" aria-haspopup="listbox"><span class="lbl">Severity</span>All${I('down')}</button>
    <button class="trigger" aria-haspopup="listbox"><span class="lbl">Certainty</span>All${I('down')}</button>
    <button class="trigger" aria-haspopup="listbox"><span class="lbl">Model or report</span>All${I('down')}</button>
    <button class="trigger" aria-haspopup="listbox"><span class="lbl">Type</span>All${I('down')}</button>
    <label class="search">${I('search')}<span class="sr">Find in impact items</span><input placeholder="Find object or reason"></label>
    <span class="grow"></span>
    <button class="switch" role="switch" aria-checked="${proposals}"><span class="track" aria-hidden="true"></span>Include open proposals</button>
  </div>`;
  return row1 + row2;
}
function completeness() {
  if (state === 'loading' || state === 'error') return '';
  if (state === 'empty') return `<div class="compl"><div class="compl-head" style="cursor:default"><span class="status s-ok">${I('check')}Complete</span><span class="sum">All object types and report bindings were checked.</span></div></div>`;
  const areas = [
    ['Not checked object types', 'help', ['Perspectives (2)', 'Translations (14 cultures)']],
    ['Unresolved bindings', 'link', ['Sales Overview, page Details, visual "Old table": field Sales[Disc] (not in any model)']],
    ['Remote reports not read', 'db', ['Finance workspace / Board pack: access refused (403)']],
    ['Bookmarks that refer to a changed object', 'bookmark', ['Sales Overview: "Q4 view" refers to [Margin %]', 'Sales Overview: "Discount focus" refers to Sales[Discount]']],
    ['Possible only', 'help', ['Relationship direction effects on 2 measures']],
  ];
  return `<div class="compl"><button class="compl-head" aria-expanded="${complOpen}" aria-controls="compl-body"><span class="status s-warn">${I('alert')}Incomplete: 5 areas</span><span class="sum">Static impact is a safe superset. Some areas were not checked.</span>${I(complOpen ? 'up' : 'down')}<span class="small muted">${complOpen ? 'Hide' : 'Show'} areas</span></button>
  ${complOpen ? `<div class="compl-body" id="compl-body">${areas.map(([t, ic, items]) => `<section class="compl-area"><h3>${I(ic)}${t} <span class="muted small">(${items.length})</span></h3><ul>${items.map(i => `<li>${esc(i)}</li>`).join('')}</ul></section>`).join('')}</div>` : ''}</div>`;
}
const pathHtml = (p) => `<span class="path"><span class="sr">Path: </span>${p.map((s, k) => k === 0 ? `<span>${esc(s[1])}</span>` : `${I('chev')}<span>${s[0]} ${esc(s[1])}</span>`).join('')}</span>`;
function itemRow(it, sel) {
  const tags = [it.cert === 'possible' ? `<span class="tag">${I('help')}Possible</span>` : '', it.notChanged ? `<span class="tag">Not changed by this plan</span>` : '', it.proposed ? `<span class="tag">${I('bot')}Proposed</span>` : ''].join('');
  const primary = it.primary ? `<button class="btn btn-sm">${ACTION[it.primary]}</button>` : '';
  const menu = (it.acts.length || it.primary) ? `<button class="btn btn-sm btn-ghost btn-icon" aria-label="More actions for ${esc(it.name)}" aria-haspopup="menu">${I('more')}</button>` : '';
  return `<tr class="item" aria-selected="${sel}"><td style="width:40px"><label class="cbwrap"><input type="checkbox" class="cb" aria-label="Select ${esc(it.name)}"></label></td>
  <td><div class="l1">${STATUS[it.st]()}<span class="typeicon">${I(TYPE_ICON[it.type] || 'file', it.type)}</span><button class="oname">${esc(it.name)}</button><span class="small muted">${esc(it.where)}</span><span class="sev">${it.sev}</span>${tags}</div>
  <div class="l2"><span>${esc(it.reason)}</span>${pathHtml(it.path)}${it.other ? `<span class="small">${it.other} other path${it.other > 1 ? 's' : ''}</span>` : ''}</div></td>
  <td style="width:1%"><div class="acts">${primary}${menu}</div></td></tr>`;
}
function tableView(items) {
  if (state === 'large') {
    const gen = []; for (let k = 0; k < 40; k++) { const b = BREAKS[k % 4]; gen.push({ ...b, id: 'g' + k, name: b.type === 'Visual' ? `Visual ${k + 1}` : `[Measure ${k + 1}]` }); }
    items = gen;
  }
  const bulk = q.get('bulk') === '1' ? `<div class="bulkbar"><strong>3 selected</strong><button class="btn btn-sm">Include in rewrite</button><span class="muted small">Only actions that all selected items allow show here.</span><span style="flex:1"></span><button class="btn btn-sm btn-ghost">Clear selection</button></div>` : '';
  return `${bulk}<div class="scroll" tabindex="0" aria-label="Impact items, scroll area"><table class="items"><caption class="sr">${group === 'needs' ? 'Needs' : 'Breaks'} impact items, blocking first</caption><thead><tr><th scope="col"><label class="cbwrap"><input type="checkbox" class="cb" aria-label="Select all shown items"></label></th><th scope="col">Item (status, object, severity; reason and path)</th><th scope="col" style="text-align:right">Actions</th></tr></thead><tbody>
  ${items.map((it, k) => itemRow(it, paneKind && k === 0)).join('')}</tbody></table></div>
  ${state === 'large' ? `<div class="vnote">${I('loader')}Showing rows 1 to 40 of 5,214. The list loads more rows when you scroll (pages of 500).</div>` : ''}`;
}
function offersView() {
  const row = (lvl, ic, name, meta, checked, info) => `<div class="offer-row ${lvl === 2 ? 'lvl2' : ''}">${info ? `<span></span>` : `<label class="cbwrap"><input type="checkbox" class="cb" id="o-${name.replace(/\W/g, '')}" ${checked ? 'checked' : ''}></label>`}<span class="typeicon">${I(ic)}</span>${info ? `<span>${esc(name)} <span class="muted small">${meta}</span></span>` : `<label for="o-${name.replace(/\W/g, '')}">${esc(name)} <span class="muted small">${meta}</span></label>`}${info ? `<span class="tag">${I('info')}Information only</span>` : '<span></span>'}</div>`;
  return `<div class="region-bar"><span>Donor report items that use an added model object. Select items to copy into the target report.</span></div>
  <div class="banner" style="margin:12px 12px 0;border-color:var(--line)">${I('alert').replace('class="i"', 'class="i" style="color:var(--warn)"')}<span class="msg">3 fields need an action before the copy can work.</span><button class="btn btn-sm">Open Needs</button></div>
  <div class="offer-group"><h3 style="margin-bottom:6px">Sales B Overview <span class="muted small">donor report of Sales B</span></h3>
    ${row(1, 'page', 'Page Margin', 'uses [Net Margin] in 3 visuals and 1 filter', true)}
    ${row(2, 'chart', 'Net margin by month', 'Line chart, uses [Net Margin]', true)}
    ${row(2, 'chart', 'Margin by product', 'Bar chart, uses [Net Margin]', true)}
    ${row(2, 'chart', 'Top customers', 'Table, uses [Net Margin], Customer[Segment]', true)}
    ${row(2, 'filter', 'Margin band', 'Page filter, uses [Net Margin]', true)}
    ${row(1, 'page', 'Page Products', 'uses [Brand Share] in 1 visual', false)}
    ${row(2, 'chart', 'Brand share', 'Donut chart, uses [Brand Share]', false)}
    ${row(1, 'bookmark', 'Bookmark Q4 view', 'refers to [Net Margin]. Bookmarks are not copied in version 1.', false, true)}
  </div>`;
}

/* Graph: deterministic layered layout (rank = step index). The real UI uses layoutGraph() from graphLayout.js. */
function graphView(items) {
  if (state === 'large' || q.get('toomany') === '1') return `<div class="center-state">${I('graph')}<h2>Too many items for the graph</h2><p class="muted" style="margin:0">The graph can show 150 objects. These filters give 5,214 items. Use filters, or open the table.</p><button class="btn">${I('table')}Open table</button></div>`;
  const nodes = new Map(); const edges = [];
  items.forEach(it => { let prev = null; it.path.forEach((s, k) => { const id = s[1]; if (!nodes.has(id)) nodes.set(id, { id, rank: k, type: k === 0 ? s[0] : (k === it.path.length - 1 ? it.type : (s[0] === 'filters' ? 'Table' : 'Measure')), cause: k === 0 ? s[2] : null, item: k === it.path.length - 1 ? it : null }); else if (k === it.path.length - 1) nodes.get(id).item = it; if (prev) edges.push({ from: prev, to: id, label: s[0], possible: it.cert === 'possible', sel: it.id === 'b1' }); prev = id; }); });
  const byRank = {}; [...nodes.values()].forEach(n => { (byRank[n.rank] ||= []).push(n); });
  const W = 224, H = 76, GX = 320, GY = 96, M = 32;
  Object.values(byRank).forEach(list => list.forEach((n, k) => { n.x = M + n.rank * GX; n.y = M + k * GY; }));
  const maxR = Math.max(...Object.keys(byRank).map(Number)); const maxN = Math.max(...Object.values(byRank).map(l => l.length));
  const cw = M * 2 + maxR * GX + W, ch = M * 2 + (maxN - 1) * GY + H;
  const stOf = (n) => n.cause ? `<span class="st" style="color:var(--text-2)">${I('merge')}Change: ${esc(n.cause)}</span>` : n.item ? (n.item.st === 'blocking' ? `<span class="st" style="color:var(--bad)">${I('x')}Blocking, ${n.item.sev.toLowerCase()}</span>` : n.item.st === 'warning' ? `<span class="st" style="color:var(--warn)">${I('alert')}Warning, ${n.item.sev.toLowerCase()}</span>` : `<span class="st" style="color:var(--text-2)">${I('info')}Information</span>`) : `<span class="st" style="color:var(--text-2)">On the path</span>`;
  const seen = new Set();
  const edgeSvg = edges.filter(e => { const k = e.from + '>' + e.to; if (seen.has(k)) return false; seen.add(k); return true; }).map(e => { const a = nodes.get(e.from), b = nodes.get(e.to); const x1 = a.x + W, y1 = a.y + H / 2, x2 = b.x, y2 = b.y + H / 2; const mx = (x1 + x2) / 2; const lx = x2 - 48, ly = y2 - 14; const tw = e.label.length * 6 + 10;
    return `<path class="gedge ${e.possible ? 'possible' : ''} ${e.sel ? 'sel' : ''}" d="M ${x1} ${y1} C ${mx} ${y1}, ${mx} ${y2}, ${x2 - 6} ${y2}" marker-end="url(#arr)"/><rect class="glabel-bg" x="${lx - tw / 2}" y="${ly - 9}" width="${tw}" height="16" rx="4"/><text class="glabel" x="${lx}" y="${ly + 3}" text-anchor="middle">${e.label}</text>`; }).join('');
  const nodeHtml = [...nodes.values()].sort((a, b) => a.rank - b.rank || a.y - b.y).map(n => `<button class="gnode ${n.cause ? 'cause' : ''}" style="left:${n.x}px;top:${n.y}px" aria-pressed="${n.item?.id === 'b1' || n.id === 'Sales[Discount]'}" aria-label="${n.type} ${esc(n.id)}, ${n.cause ? 'change: ' + esc(n.cause) : n.item ? n.item.st + ', ' + n.item.sev + ', ' + n.rank + ' steps from the change' : 'on the path, ' + n.rank + ' steps from the change'}"><span class="t">${I(TYPE_ICON[n.type] || 'file')}${n.type}</span><span class="n">${esc(n.id)}</span>${stOf(n)}</button>`).join('');
  return `<div class="region-bar"><div class="legend"><span><svg viewBox="0 0 28 8" aria-hidden="true"><line x1="0" y1="4" x2="28" y2="4" class="gedge"/></svg>Certain</span><span><svg viewBox="0 0 28 8" aria-hidden="true"><line x1="0" y1="4" x2="28" y2="4" class="gedge possible"/></svg>Possible</span><span>${nodes.size} objects, ${seen.size} links. Shortest path of each item.</span></div><span style="flex:1"></span><button class="btn btn-sm">${I('table')}Show as table</button></div>
  <div class="graph-wrap" role="region" aria-label="Impact graph. Tab moves between objects. Enter opens the item."><div class="graph-canvas" style="width:${cw}px;height:${ch}px"><svg class="edges" width="${cw}" height="${ch}" aria-hidden="true"><defs><marker id="arr" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="8" markerHeight="8" orient="auto-start-reverse"><path d="M0 0 10 5 0 10z" style="fill:var(--control-border)"/></marker></defs>${edgeSvg}</svg>${nodeHtml}</div></div>
  <div class="graph-tools" role="group" aria-label="Graph view controls"><button class="btn btn-sm btn-ghost btn-icon" aria-label="Zoom in">${I('plus')}</button><span class="small" style="padding:0 4px">100%</span><button class="btn btn-sm btn-ghost btn-icon" aria-label="Zoom out">${I('minus')}</button><button class="btn btn-sm btn-ghost btn-icon" aria-label="Fit view">${I('max')}</button><button class="btn btn-sm btn-ghost btn-icon" aria-label="Focus selected">${I('locate')}</button></div>`;
}

/* Wireframe: PBIR page 1280 x 720; boxes from position x, y, width, height (percent of the page). */
const VISUALS = [
  { t: 'Total sales', k: 'Card', x: 16, y: 16, w: 300, h: 120, st: 'unchanged' },
  { t: 'Margin card', k: 'Card', x: 332, y: 16, w: 300, h: 120, st: 'changes', why: 'Uses a replaced measure' },
  { t: 'Discount %', k: 'Card', x: 648, y: 16, w: 300, h: 120, st: 'removed', why: 'Removed by Cascade' },
  { t: 'Region', k: 'Slicer', x: 964, y: 16, w: 300, h: 120, st: 'unchecked', why: 'Uses a field parameter' },
  { t: 'Discount by region', k: 'Bar chart', x: 16, y: 152, w: 616, h: 300, st: 'breaks', why: 'Uses removed Sales[Discount]' },
  { t: 'Net margin by month', k: 'Line chart', x: 648, y: 152, w: 616, h: 300, st: 'new', why: 'Copied from Sales B Overview' },
  { t: 'Sales detail', k: 'Table', x: 16, y: 468, w: 940, h: 236, st: 'unchanged' },
  { t: 'Notes', k: 'Text box', x: 972, y: 468, w: 292, h: 236, st: 'unchanged', hidden: true },
];
const WST = { removed: ['trash', 'Removed'], breaks: ['x', 'Breaks'], changes: ['alert', 'Changes'], new: ['plus', 'New'], unchecked: ['help', 'Not checked'], unchanged: ['', 'Unchanged'] };
function wireframeView() {
  const pages = [['Overview', { breaks: 1, changes: 1, removed: 1, new: 1, unchecked: 1 }], ['Details', { changes: 1 }], ['Margin', { new: 4 }], ['Products', {}]];
  const cnt = (o) => Object.entries(o).map(([s, n]) => `<span>${I(WST[s][0])}${n} ${WST[s][1].toLowerCase()}</span>`).join('') || '<span>No change</span>';
  const box = (v, k) => `<button class="vbox st-${v.st}" style="left:${v.x / 12.8}%;top:${v.y / 7.2}%;width:${v.w / 12.8}%;height:${v.h / 7.2}%" aria-pressed="${k === 4}" aria-label="${v.k} ${v.t}, ${WST[v.st][1]}${v.why ? ': ' + v.why : ''}${v.hidden ? ', hidden' : ''}">${v.st !== 'unchanged' ? `<span class="vs">${I(WST[v.st][0])}${WST[v.st][1]}</span>` : ''}<span class="vt">${v.t}</span><span class="vk">${v.k}</span>${v.hidden ? `<span class="tag hidden-tag">${I('eyeoff')}Hidden</span>` : ''}</button>`;
  const legend = `<div class="wf-legend" aria-label="Status legend">${[['removed', 'Removed'], ['breaks', 'Breaks'], ['changes', 'Changes'], ['new', 'New'], ['unchecked', 'Not checked'], ['unchanged', 'Unchanged']].map(([s, t]) => `<span><span class="sw st-${s}" style="position:static"></span>${s !== 'unchanged' ? I(WST[s][0]) : ''} ${t}</span>`).join('')}<span>Order when a visual has more than one status: removed, breaks, changes, new, not checked, unchanged.</span></div>`;
  const list = `<table class="items"><caption class="sr">Visuals on page Overview in reading order</caption><thead><tr><th scope="col">Visual</th><th scope="col">Type</th><th scope="col">Status</th><th scope="col">Cause</th></tr></thead><tbody>${VISUALS.map(v => `<tr class="item"><td>${v.t}${v.hidden ? ' <span class="tag">Hidden</span>' : ''}</td><td class="muted">${v.k}</td><td><span class="l1">${WST[v.st][0] ? I(WST[v.st][0]) : ''}${WST[v.st][1]}</span></td><td class="muted">${v.why || ''}</td></tr>`).join('')}</tbody></table>`;
  return `<div class="region-bar"><button class="trigger" aria-haspopup="listbox"><span class="lbl">Report</span>Sales Overview (target, after apply)${I('down')}</button><span style="flex:1"></span>${seg('Wireframe form', [['Drawing', !wfList], ['Visual list', wfList]])}</div>
  <div class="wf"><nav class="wf-pages" aria-label="Pages">${pages.map(([p, o], k) => `<button class="wf-page" aria-current="${k === 0}"><span>${p}</span><span class="cnt">${cnt(o)}</span></button>`).join('')}</nav>
  <div class="wf-main">${wfList ? list : `<div class="page-canvas" role="group" aria-label="Page Overview, 1280 by 720, 8 visuals">${VISUALS.map(box).join('')}</div>${legend}`}
  <section><h3 style="margin-bottom:6px">Filters</h3><div class="filters-list"><div><span class="muted small">Report</span>Year <span class="muted small">Unchanged</span></div><div><span class="muted small">Page</span>Discount band <span class="status s-bad">${I('trash')}Removed</span><span class="muted small">Uses removed Sales[Discount]</span></div></div></section></div></div>`;
}
function itemPane() {
  const it = group === 'needs' ? NEEDS[0] : BREAKS[0];
  return `<aside class="pane" aria-label="Impact item detail"><div class="pane-head"><div><div class="l1">${STATUS[it.st]()}<span class="sev">${it.sev}</span></div><h2 style="margin-top:6px">${esc(it.name)}</h2><div class="small muted">${it.type} in ${esc(it.where)}</div></div><button class="btn btn-ghost btn-icon" aria-label="Close item detail">${I('close')}</button></div>
  <p style="margin:0">${esc(it.reason)} The plan stays not valid until you resolve this item.</p>
  <section><h3 style="margin-bottom:6px">Shortest path</h3><ol class="steps">${it.path.map((s, k) => `<li class="${k === 0 ? 'first' : k === it.path.length - 1 ? 'last' : ''}"><span class="dot"></span><span>${k === 0 ? `<span class="edge">Change: ${esc(s[2])}</span><br>` : `<span class="edge">${s[0]}</span><br>`}${esc(s[1])}</span></li>`).join('')}</ol><button class="btn btn-sm btn-ghost" style="margin-top:4px">Show other paths</button></section>
  <dl class="kv"><dt>Cause</dt><dd><button class="oname" style="font-weight:400;text-decoration:underline">Remove Sales[Discount]</button> <span class="muted small">(Compare row)</span></dd><dt>Certainty</dt><dd>Certain: a direct reference</dd><dt>Policy</dt><dd>Block (default)</dd></dl>
  <section><h3 style="margin-bottom:6px">Actions</h3><div class="act-list">
  <div class="act"><div>Repoint<p>Use a different column in place of Sales[Discount].</p></div><button class="btn btn-sm">Repoint</button></div>
  <div class="act"><div>Cascade<p>Remove the dependents also. You see the list first.</p></div><button class="btn btn-sm">Cascade</button></div>
  <div class="act"><div>Keep blocked<p>Keep the policy Block. The plan stays not valid.</p></div><button class="btn btn-sm btn-ghost" disabled>Current</button></div></div></section></aside>`;
}
function cascadePane() {
  return `<aside class="pane" aria-label="Cascade preview"><div class="pane-head"><div><div class="small muted">Removal policy</div><h2 style="margin-top:4px">Cascade: Sales[Discount]</h2></div><button class="btn btn-ghost btn-icon" aria-label="Close cascade preview">${I('close')}</button></div>
  <p style="margin:0">Cascade also removes or changes these 5 dependents. Dependents with their own Merge Choice keep it.</p>
  <ul class="eff"><li><span>${I('sigma')} [Net Sales]</span><span class="status s-bad">${I('trash')}Remove object</span></li><li><span>${I('sigma')} [Discount %]</span><span class="status s-bad">${I('trash')}Remove object</span></li><li><span>${I('chart')} Discount by region</span><span class="status s-warn">${I('minus')}Remove field from visual</span></li><li><span>${I('chart')} Discount % card</span><span class="status s-bad">${I('trash')}Remove visual</span></li><li><span>${I('filter')} Discount band (page filter)</span><span class="status s-bad">${I('trash')}Remove filter</span></li></ul>
  <div class="banner">${I('info').replace('class="i"', 'class="i" style="color:var(--info)"')}<span class="msg small">Nothing changes on disk until you apply the plan.</span></div>
  <div style="display:flex;gap:8px;justify-content:flex-end"><button class="btn">Cancel</button><button class="btn btn-danger">${I('trash')}Set Cascade</button></div></aside>`;
}
function regionContent() {
  if (state === 'loading') return `<div class="region-bar"><span class="l1">${I('loader').replace('class="i"', 'class="i spin"')}Computing impact for the whole plan</span></div><div style="padding:12px;display:flex;flex-direction:column;gap:14px" aria-hidden="true">${Array.from({ length: 7 }, (_, k) => `<div style="display:flex;flex-direction:column;gap:6px"><div class="skel" style="width:${50 + (k * 13) % 35}%"></div><div class="skel" style="width:${30 + (k * 17) % 40}%;opacity:.6"></div></div>`).join('')}</div>`;
  if (state === 'error') return `<div class="center-state err" role="alert">${I('x')}<h2>The impact could not be computed</h2><p class="muted" style="margin:0">The backend stopped with "graph build failed for source Sales B: file not found". Check the source, then try again.</p><div style="display:flex;gap:8px"><button class="btn btn-primary">${I('refresh')}Try again</button><button class="btn">Open Sources</button></div></div>`;
  if (state === 'empty') return `<div class="center-state">${I('check')}<h2>${scope === 'row' ? 'This row has no impact' : 'Nothing breaks'}</h2><p class="muted" style="margin:0">${scope === 'row' ? 'No object uses [Net Margin], and it needs nothing that the target does not have.' : 'The plan breaks no object in the target model or its reports.'}</p>${scope === 'row' ? '<button class="btn">Show whole plan</button>' : ''}</div>`;
  if (group === 'offers') return offersView();
  const items = (group === 'needs' ? NEEDS : BREAKS).filter(i => proposals || !i.proposed);
  if (view === 'graph') return graphView(items);
  if (view === 'wireframe') return wireframeView();
  return tableView(items);
}
const pane = paneKind === 'item' ? itemPane() : paneKind === 'cascade' ? cascadePane() : '';
const propBanner = proposals ? `<div class="banner banner-info" role="status">${I('bot')}<span class="msg">This view includes 4 open agent proposals. Apply uses only accepted choices.</span></div>` : '';
const toast = q.get('toast') === '1' ? `<div class="toast" role="status">${I('check').replace('class="i"', 'class="i" style="color:var(--ok)"')}1 item resolved. 5 blocking left.</div>` : '';
document.getElementById('app').innerHTML = `<div class="shell">${sidebar}<div class="main">${crumbs}<main class="content" id="main">${header}${tabs}<div id="impact-panel" role="tabpanel" aria-label="Impact" style="display:flex;flex-direction:column;gap:12px;min-width:0">${toolbar()}${propBanner}${completeness()}<div class="body ${pane ? 'has-pane' : ''}"><div class="region" aria-busy="${state === 'loading'}">${regionContent()}</div>${pane}</div></div></main></div></div>${toast}`;
