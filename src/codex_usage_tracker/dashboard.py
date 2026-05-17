"""Static dashboard generation from aggregate-only usage rows."""

from __future__ import annotations

import html
import json
from pathlib import Path

from codex_usage_tracker.paths import DEFAULT_DASHBOARD_PATH, DEFAULT_PRICING_PATH
from codex_usage_tracker.pricing import annotate_rows_with_efficiency, load_pricing_config
from codex_usage_tracker.store import query_dashboard_events


def generate_dashboard(
    db_path: Path,
    output_path: Path = DEFAULT_DASHBOARD_PATH,
    limit: int = 5000,
    pricing_path: Path = DEFAULT_PRICING_PATH,
    since: str | None = None,
) -> Path:
    rows = query_dashboard_events(db_path=db_path, limit=limit, since=since)
    pricing = load_pricing_config(pricing_path)
    rows = annotate_rows_with_efficiency(rows, pricing)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(
        {
            "rows": rows,
            "pricing_configured": pricing.loaded and not pricing.error,
            "pricing_source": pricing.source,
        },
        ensure_ascii=True,
    ).replace("</", "<\\/")
    output_path.write_text(_html(payload), encoding="utf-8")
    return output_path


def _html(payload: str) -> str:
    title = html.escape("Codex Usage Dashboard")
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <link rel="icon" href="data:,">
  <title>{title}</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f7f8fb;
      --panel: #ffffff;
      --ink: #172033;
      --muted: #69758a;
      --line: #dde3ee;
      --blue: #2563eb;
      --green: #047857;
      --amber: #b45309;
      --red: #b91c1c;
      --violet: #6d28d9;
      --shadow: 0 12px 32px rgba(23, 32, 51, 0.09);
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: var(--bg);
      color: var(--ink);
    }}
    header {{
      padding: 24px 28px 16px;
      border-bottom: 1px solid var(--line);
      background: var(--panel);
    }}
    h1 {{ margin: 0 0 6px; font-size: 24px; font-weight: 720; }}
    header p {{ margin: 0; color: var(--muted); max-width: 920px; line-height: 1.45; }}
    .source-line {{ margin-top: 6px; font-size: 12px; }}
    main {{ padding: 22px 28px 36px; }}
    .filters {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
      gap: 12px;
      margin-bottom: 18px;
    }}
    label {{ display: grid; gap: 6px; font-size: 12px; font-weight: 680; color: var(--muted); }}
    input, select {{
      width: 100%;
      min-height: 38px;
      padding: 7px 10px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
      color: var(--ink);
      font: inherit;
    }}
    .cards {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
      gap: 12px;
      margin-bottom: 18px;
    }}
    .card {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 14px;
      box-shadow: var(--shadow);
    }}
    .card span {{ display: block; color: var(--muted); font-size: 12px; font-weight: 680; }}
    .card strong {{ display: block; margin-top: 7px; font-size: 22px; }}
    .grid {{
      display: grid;
      grid-template-columns: minmax(0, 1.4fr) minmax(320px, 0.8fr);
      gap: 16px;
      align-items: start;
    }}
    section {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      overflow: hidden;
      box-shadow: var(--shadow);
    }}
    section h2 {{
      margin: 0;
      padding: 14px 16px;
      border-bottom: 1px solid var(--line);
      font-size: 15px;
    }}
    table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
    th, td {{ padding: 10px 12px; border-bottom: 1px solid var(--line); text-align: left; vertical-align: top; }}
    th {{ color: var(--muted); font-size: 12px; background: #fbfcfe; position: sticky; top: 0; }}
    tr:hover {{ background: #eff6ff; }}
    button {{
      font: inherit;
    }}
    .sort-header {{
      display: inline-flex;
      align-items: center;
      gap: 4px;
      max-width: 100%;
      min-height: 24px;
      padding: 0;
      border: 0;
      background: transparent;
      color: inherit;
      font-size: inherit;
      font-weight: 760;
      cursor: pointer;
    }}
    th.num .sort-header {{
      width: 100%;
      justify-content: flex-end;
    }}
    th[data-sort-active="true"] .sort-header {{
      color: var(--ink);
    }}
    .sort-indicator {{
      display: inline-block;
      min-width: 12px;
      color: var(--blue);
      font-size: 11px;
    }}
    .table-tools {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 12px;
      padding: 12px 16px;
      border-bottom: 1px solid var(--line);
      background: #fbfcfe;
    }}
    .segmented {{
      display: inline-flex;
      gap: 2px;
      padding: 3px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #eef2f8;
    }}
    .segmented button {{
      min-width: 82px;
      min-height: 30px;
      border: 0;
      border-radius: 6px;
      background: transparent;
      color: var(--muted);
      font-size: 12px;
      font-weight: 760;
      cursor: pointer;
    }}
    .segmented button[aria-pressed="true"] {{
      background: var(--panel);
      color: var(--ink);
      box-shadow: 0 1px 4px rgba(23, 32, 51, 0.12);
    }}
    .table-caption {{
      color: var(--muted);
      font-size: 12px;
      font-weight: 680;
    }}
    .num {{ text-align: right; font-variant-numeric: tabular-nums; }}
    .pill {{
      display: inline-flex;
      align-items: center;
      min-height: 22px;
      padding: 2px 8px;
      border-radius: 999px;
      background: #e0ecff;
      color: #184fc5;
      font-weight: 680;
      font-size: 12px;
    }}
    .flags {{
      display: flex;
      flex-wrap: wrap;
      gap: 4px;
      justify-content: flex-end;
    }}
    .flag {{
      display: inline-flex;
      min-height: 20px;
      align-items: center;
      padding: 1px 7px;
      border-radius: 999px;
      background: #f5e8ff;
      color: var(--violet);
      font-size: 11px;
      font-weight: 680;
      white-space: nowrap;
    }}
    .thread-row {{
      cursor: pointer;
    }}
    .thread-row[aria-expanded="true"] {{
      background: #f8fbff;
    }}
    .thread-title {{
      display: flex;
      gap: 8px;
      align-items: center;
      min-width: 0;
    }}
    .thread-toggle {{
      flex: 0 0 auto;
      display: inline-grid;
      place-items: center;
      width: 22px;
      height: 22px;
      border: 1px solid var(--line);
      border-radius: 999px;
      background: var(--panel);
      color: var(--blue);
      font-size: 13px;
      font-weight: 820;
    }}
    .thread-meta {{
      display: grid;
      gap: 2px;
      min-width: 0;
    }}
    .thread-name {{
      font-weight: 760;
      overflow-wrap: anywhere;
    }}
    .thread-subtle {{
      color: var(--muted);
      font-size: 12px;
    }}
    .child-cell {{
      padding: 0;
      background: #f8fafd;
    }}
    .thread-call-table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 12px;
    }}
    .thread-call-table th {{
      position: static;
      background: #eef3fb;
    }}
    .thread-call-table td, .thread-call-table th {{
      padding: 8px 10px;
    }}
    .thread-call-table tr:last-child td {{
      border-bottom: 0;
    }}
    .empty-state {{
      padding: 18px 16px;
      color: var(--muted);
      text-align: center;
    }}
    .detail {{
      padding: 14px 16px;
      min-height: 280px;
      color: var(--muted);
      line-height: 1.45;
    }}
    .detail dl {{ display: grid; grid-template-columns: minmax(120px, 0.6fr) minmax(0, 1fr); gap: 8px 14px; margin: 0; }}
    .detail dt {{ font-weight: 720; color: var(--ink); }}
    .detail dd {{ margin: 0; overflow-wrap: anywhere; }}
    .context-actions {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-top: 14px;
      padding-top: 12px;
      border-top: 1px solid var(--line);
    }}
    .context-button {{
      min-height: 32px;
      padding: 6px 10px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
      color: var(--blue);
      font-size: 12px;
      font-weight: 760;
      cursor: pointer;
    }}
    .context-button:hover {{ background: #eff6ff; }}
    .context-button.secondary {{ color: var(--muted); }}
    .context-result {{
      margin-top: 12px;
      padding-top: 12px;
      border-top: 1px solid var(--line);
    }}
    .context-note {{ margin: 0 0 10px; font-size: 12px; color: var(--muted); }}
    .context-entry {{
      margin: 10px 0;
      border: 1px solid var(--line);
      border-radius: 8px;
      overflow: hidden;
      background: #fbfcfe;
    }}
    .context-entry-header {{
      display: flex;
      justify-content: space-between;
      gap: 10px;
      padding: 8px 10px;
      border-bottom: 1px solid var(--line);
      color: var(--muted);
      font-size: 12px;
      font-weight: 720;
    }}
    .context-entry pre {{
      margin: 0;
      padding: 10px;
      max-height: 360px;
      overflow: auto;
      white-space: pre-wrap;
      overflow-wrap: anywhere;
      color: var(--ink);
      font: 12px/1.45 ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace;
    }}
    @media (max-width: 980px) {{
      .filters, .cards, .grid {{ grid-template-columns: 1fr; }}
      main, header {{ padding-left: 16px; padding-right: 16px; }}
      table {{ font-size: 12px; }}
      th, td {{ padding: 8px; }}
      .table-tools {{ align-items: stretch; flex-direction: column; }}
      .segmented, .segmented button {{ width: 100%; }}
    }}
  </style>
</head>
<body>
  <header>
    <h1>Codex Usage Dashboard</h1>
    <p>Aggregate-only token analytics from local Codex logs. Hover a table row to inspect exact usage fields; raw logged context is loaded only on demand from the local dashboard server.</p>
    <p id="pricingSource" class="source-line"></p>
  </header>
  <main>
    <div class="filters">
      <label>Search<input id="search" type="search" placeholder="Thread, cwd, model, session"></label>
      <label>Model<select id="model"><option value="">All models</option></select></label>
      <label>Reasoning<select id="effort"><option value="">All efforts</option></select></label>
      <label>Pricing<select id="pricingStatus"><option value="">All pricing</option><option value="official">Official/configured</option><option value="estimated">Estimated</option><option value="unpriced">Unpriced</option></select></label>
      <label>Sort<select id="sort"><option value="time" selected>Newest calls</option><option value="thread">Thread name</option><option value="model">Model</option><option value="effort">Reasoning</option><option value="total">Most tokens</option><option value="cost">Highest estimated cost</option><option value="cache">Lowest cache ratio</option><option value="signals">Most signals</option><option value="context">Highest context use</option></select></label>
    </div>
    <div class="cards">
      <div class="card"><span>Visible Calls</span><strong id="visibleCalls">0</strong></div>
      <div class="card"><span>Total Tokens</span><strong id="totalTokens">0</strong></div>
      <div class="card"><span>Cached Input</span><strong id="cachedTokens">0</strong></div>
      <div class="card"><span>Reasoning Output</span><strong id="reasoningTokens">0</strong></div>
      <div class="card"><span>Estimated Cost</span><strong id="estimatedCost">$0.00</strong></div>
      <div class="card"><span>Price Coverage</span><strong id="priceCoverage">0.0%</strong></div>
      <div class="card"><span>Estimated Tokens</span><strong id="estimatedTokens">0</strong></div>
      <div class="card"><span>Unpriced Tokens</span><strong id="unpricedTokens">0</strong></div>
    </div>
    <div class="grid">
      <section>
        <h2 id="tableTitle">Model Calls</h2>
        <div class="table-tools">
          <div class="segmented" role="group" aria-label="Dashboard view">
            <button id="callsView" type="button" aria-pressed="true">Calls</button>
            <button id="threadsView" type="button" aria-pressed="false">Threads</button>
          </div>
          <div id="tableCaption" class="table-caption">Showing individual model calls.</div>
        </div>
        <table>
          <thead>
            <tr>
              <th data-sort-header="time"><button class="sort-header" type="button" data-sort-key="time">Time <span class="sort-indicator" data-sort-indicator="time"></span></button></th>
              <th data-sort-header="thread"><button class="sort-header" type="button" data-sort-key="thread">Thread <span class="sort-indicator" data-sort-indicator="thread"></span></button></th>
              <th data-sort-header="model"><button class="sort-header" type="button" data-sort-key="model">Model <span class="sort-indicator" data-sort-indicator="model"></span></button></th>
              <th data-sort-header="effort"><button class="sort-header" type="button" data-sort-key="effort">Effort <span class="sort-indicator" data-sort-indicator="effort"></span></button></th>
              <th class="num" data-sort-header="total"><button class="sort-header" type="button" data-sort-key="total">Tokens <span class="sort-indicator" data-sort-indicator="total"></span></button></th>
              <th class="num" data-sort-header="cost"><button class="sort-header" type="button" data-sort-key="cost">Cost <span class="sort-indicator" data-sort-indicator="cost"></span></button></th>
              <th class="num" data-sort-header="cache"><button class="sort-header" type="button" data-sort-key="cache">Cache <span class="sort-indicator" data-sort-indicator="cache"></span></button></th>
              <th class="num" data-sort-header="signals"><button class="sort-header" type="button" data-sort-key="signals">Signals <span class="sort-indicator" data-sort-indicator="signals"></span></button></th>
            </tr>
          </thead>
          <tbody id="rows"></tbody>
        </table>
      </section>
      <section>
        <h2>Hover Details</h2>
        <div id="detail" class="detail">Hover a row to inspect aggregate usage fields.</div>
      </section>
    </div>
  </main>
  <script id="usage-data" type="application/json">{payload}</script>
  <script>
    const payload = JSON.parse(document.getElementById('usage-data').textContent);
    const data = Array.isArray(payload) ? payload : payload.rows;
    const pricingConfigured = Boolean(payload.pricing_configured);
    const pricingSource = payload.pricing_source || {{}};
    const rowsEl = document.getElementById('rows');
    const detailEl = document.getElementById('detail');
    const searchEl = document.getElementById('search');
    const modelEl = document.getElementById('model');
    const effortEl = document.getElementById('effort');
    const pricingStatusEl = document.getElementById('pricingStatus');
    const sortEl = document.getElementById('sort');
    const tableTitleEl = document.getElementById('tableTitle');
    const tableCaptionEl = document.getElementById('tableCaption');
    const callsViewEl = document.getElementById('callsView');
    const threadsViewEl = document.getElementById('threadsView');
    const number = new Intl.NumberFormat();
    const rowByRecordId = new Map(data.map(row => [row.record_id, row]));
    const parentCandidates = buildParentCandidates(data);
    const threadAttachmentByRecordId = new Map(data.map(row => [row.record_id, resolveThreadAttachment(row)]));
    const expandedThreads = new Set();
    let activeView = 'calls';
    let sortKey = sortEl.value || 'time';
    let sortDirection = defaultSortDirection(sortKey);
    const money = (value, missingLabel = 'No price') => {{
      if (value === null || value === undefined) return missingLabel;
      const amount = Number(value) || 0;
      if (amount > 0 && amount < 0.01) return `$${{amount.toFixed(4)}}`;
      return `$${{amount.toFixed(2)}}`;
    }};
    const pct = value => `${{((Number(value) || 0) * 100).toFixed(1)}}%`;
    const short = (value, fallback = 'Unknown') => value || fallback;
    const escapeHtml = value => String(value).replace(/[&<>"']/g, char => ({{
      '&': '&amp;',
      '<': '&lt;',
      '>': '&gt;',
      '"': '&quot;',
      "'": '&#39;',
    }}[char]));
    const truncate = (value, size = 54) => {{
      const text = short(value, '');
      return text.length > size ? `${{text.slice(0, size - 1)}}…` : text;
    }};
    function defaultSortDirection(key) {{
      return {{
        cache: 'asc',
        effort: 'asc',
        model: 'asc',
        thread: 'asc',
      }}[key] || 'desc';
    }}
    function textValue(value) {{
      return short(value, '').toLowerCase();
    }}
    function compareValues(left, right) {{
      if (typeof left === 'number' || typeof right === 'number') {{
        return (Number(left) || 0) - (Number(right) || 0);
      }}
      return String(left || '').localeCompare(String(right || ''));
    }}
    function directional(compareResult) {{
      return sortDirection === 'asc' ? compareResult : -compareResult;
    }}
    function sortLabel(key) {{
      return {{
        cache: 'Cache',
        context: 'Context use',
        cost: 'Cost',
        effort: 'Effort',
        model: 'Model',
        signals: 'Signals',
        thread: 'Thread',
        time: 'Time',
        total: 'Tokens',
      }}[key] || 'Sort';
    }}
    function setSort(key, direction = null) {{
      sortKey = key;
      sortDirection = direction || defaultSortDirection(key);
      sortEl.value = key;
      render();
    }}
    function handleHeaderSort(key) {{
      if (sortKey === key) {{
        sortDirection = sortDirection === 'asc' ? 'desc' : 'asc';
      }} else {{
        sortKey = key;
        sortDirection = defaultSortDirection(key);
      }}
      sortEl.value = key;
      render();
    }}
    function updateSortControls() {{
      sortEl.value = sortKey;
      document.querySelectorAll('[data-sort-header]').forEach(header => {{
        const active = header.dataset.sortHeader === sortKey;
        header.dataset.sortActive = active ? 'true' : 'false';
        header.setAttribute('aria-sort', active ? (sortDirection === 'asc' ? 'ascending' : 'descending') : 'none');
      }});
      document.querySelectorAll('[data-sort-indicator]').forEach(indicator => {{
        indicator.textContent = indicator.dataset.sortIndicator === sortKey ? (sortDirection === 'asc' ? '▲' : '▼') : '';
      }});
      tableCaptionEl.dataset.sortDescription = `${{sortLabel(sortKey)}} ${{sortDirection === 'asc' ? 'ascending' : 'descending'}}`;
    }}
    function optionize(select, values) {{
      [...new Set(values.filter(Boolean))].sort().forEach(value => {{
        const option = document.createElement('option');
        option.value = value;
        option.textContent = value;
        select.appendChild(option);
      }});
    }}
    optionize(modelEl, data.map(row => row.model));
    optionize(effortEl, data.map(row => row.effort));
    if (pricingConfigured && pricingSource.url) {{
      const sourceParts = [
        pricingSource.name || 'Pricing source',
        pricingSource.tier ? `${{pricingSource.tier}} tier` : '',
        pricingSource.fetched_at ? `fetched ${{pricingSource.fetched_at}}` : '',
      ].filter(Boolean);
      document.getElementById('pricingSource').textContent = `Estimated costs use ${{sourceParts.join(', ')}}; internal Codex labels may use marked best-guess estimates.`;
    }}
    function filtered() {{
      const term = searchEl.value.trim().toLowerCase();
      const model = modelEl.value;
      const effort = effortEl.value;
      const pricingStatus = pricingStatusEl.value;
      const rows = data.filter(row => {{
        const haystack = [
          rowThreadLabel(row),
          row.cwd,
          row.model,
          row.effort,
          row.session_id,
          row.turn_id,
          row.thread_source,
          row.subagent_type,
          row.agent_role,
          row.agent_nickname,
          row.parent_session_id,
        ].join(' ').toLowerCase();
        const statusMatches = !pricingStatus
          || (pricingStatus === 'official' && row.pricing_model && !row.pricing_estimated)
          || (pricingStatus === 'estimated' && row.pricing_estimated)
          || (pricingStatus === 'unpriced' && !row.pricing_model);
        return (!term || haystack.includes(term)) && (!model || row.model === model) && (!effort || row.effort === effort) && statusMatches;
      }});
      rows.sort(compareCalls);
      return rows;
    }}
    function callSortValue(row, key) {{
      if (key === 'cache') return Number(row.cache_ratio || 0);
      if (key === 'context') return Number(row.context_window_percent || 0);
      if (key === 'cost') return Number(row.estimated_cost_usd || 0);
      if (key === 'effort') return textValue(row.effort);
      if (key === 'model') return textValue(row.model);
      if (key === 'signals') return Array.isArray(row.efficiency_flags) ? row.efficiency_flags.length : 0;
      if (key === 'thread') return textValue(rowThreadLabel(row));
      if (key === 'time') return String(row.event_timestamp || '');
      return Number(row.total_tokens || 0);
    }}
    function compareCalls(a, b) {{
      const primary = directional(compareValues(callSortValue(a, sortKey), callSortValue(b, sortKey)));
      if (primary !== 0) return primary;
      const timeFallback = String(b.event_timestamp || '').localeCompare(String(a.event_timestamp || ''));
      if (timeFallback !== 0) return timeFallback;
      return String(a.record_id || '').localeCompare(String(b.record_id || ''));
    }}
    function buildParentCandidates(rows) {{
      const bySession = new Map();
      const byCwd = new Map();
      for (const row of rows) {{
        if (!row.thread_name || row.thread_source === 'subagent') continue;
        const key = `thread:${{row.thread_name}}`;
        if (!bySession.has(row.session_id)) {{
          bySession.set(row.session_id, {{
            key,
            label: row.thread_name,
            sessionId: row.session_id,
            cwd: row.cwd,
            first: row.event_timestamp || '',
            latest: row.event_timestamp || '',
          }});
        }}
        const candidate = bySession.get(row.session_id);
        if (String(row.event_timestamp || '') < String(candidate.first || '')) candidate.first = row.event_timestamp || '';
        if (String(row.event_timestamp || '') > String(candidate.latest || '')) candidate.latest = row.event_timestamp || '';
      }}
      for (const candidate of bySession.values()) {{
        if (!candidate.cwd) continue;
        if (!byCwd.has(candidate.cwd)) byCwd.set(candidate.cwd, []);
        byCwd.get(candidate.cwd).push(candidate);
      }}
      return {{ bySession, byCwd }};
    }}
    function rowTime(row) {{
      const value = Date.parse(row.event_timestamp || '');
      return Number.isNaN(value) ? 0 : value;
    }}
    function candidateDistance(row, candidate) {{
      const eventTime = rowTime(row);
      const first = Date.parse(candidate.first || '');
      const latest = Date.parse(candidate.latest || '');
      if (!eventTime || Number.isNaN(first) || Number.isNaN(latest)) return 0;
      if (eventTime >= first && eventTime <= latest) return 0;
      return Math.min(Math.abs(eventTime - first), Math.abs(eventTime - latest));
    }}
    function basenamePath(path) {{
      const text = short(path, 'Unknown project');
      const parts = text.split('/').filter(Boolean);
      return parts.length ? parts[parts.length - 1] : text;
    }}
    function isAutoReview(row) {{
      return row.model === 'codex-auto-review' || row.subagent_type === 'guardian';
    }}
    function isSubagent(row) {{
      return row.thread_source === 'subagent' || Boolean(row.subagent_type || row.parent_session_id);
    }}
    function sourceLabel(row) {{
      if (isAutoReview(row)) return 'Auto-review';
      if (row.subagent_type === 'thread_spawn') {{
        return row.agent_role ? `Subagent: ${{row.agent_role}}` : 'Subagent';
      }}
      if (isSubagent(row)) return 'Subagent';
      return 'User';
    }}
    function resolveThreadAttachment(row) {{
      if (row.thread_name) {{
        return {{ key: `thread:${{row.thread_name}}`, label: row.thread_name, relation: 'direct' }};
      }}
      if (row.parent_session_id && parentCandidates.bySession.has(row.parent_session_id)) {{
        const parent = parentCandidates.bySession.get(row.parent_session_id);
        return {{
          key: parent.key,
          label: parent.label,
          relation: 'explicit parent',
          parentSessionId: row.parent_session_id,
        }};
      }}
      if (row.parent_session_id) {{
        return {{
          key: `session:${{row.parent_session_id}}`,
          label: `Parent ${{row.parent_session_id}}`,
          relation: 'explicit parent',
          parentSessionId: row.parent_session_id,
        }};
      }}
      if (isAutoReview(row)) {{
        const candidates = parentCandidates.byCwd.get(row.cwd) || [];
        if (candidates.length) {{
          const nearest = candidates.slice().sort((a, b) => candidateDistance(row, a) - candidateDistance(row, b))[0];
          return {{
            key: nearest.key,
            label: nearest.label,
            relation: 'inferred by cwd/time',
          }};
        }}
        return {{
          key: `auto:${{row.cwd || row.session_id}}`,
          label: `Auto-review: ${{basenamePath(row.cwd)}}`,
          relation: 'unmatched auto-review',
        }};
      }}
      return {{
        key: `session:${{row.session_id || 'unknown'}}`,
        label: row.session_id || 'Unknown thread',
        relation: isSubagent(row) ? 'unmatched subagent' : 'session',
      }};
    }}
    function rowAttachment(row) {{
      return threadAttachmentByRecordId.get(row.record_id) || resolveThreadAttachment(row);
    }}
    function rowThreadLabel(row) {{
      return rowAttachment(row).label;
    }}
    function chronological(a, b) {{
      const timeCompare = String(a.event_timestamp || '').localeCompare(String(b.event_timestamp || ''));
      if (timeCompare !== 0) return timeCompare;
      return Number(a.cumulative_total_tokens || 0) - Number(b.cumulative_total_tokens || 0);
    }}
    function sortThreads(groups) {{
      groups.sort(compareThreads);
      return groups;
    }}
    function threadSortValue(group, key) {{
      if (key === 'cache') return group.cacheRatio;
      if (key === 'context') return group.maxContextUse;
      if (key === 'cost') return group.estimatedCost;
      if (key === 'effort') return textValue(group.effortSummary);
      if (key === 'model') return textValue(group.modelSummary);
      if (key === 'signals') return group.signalCount;
      if (key === 'thread') return textValue(group.label);
      if (key === 'time') return String(group.latestActivity || '');
      return group.totalTokens;
    }}
    function compareThreads(a, b) {{
      const primary = directional(compareValues(threadSortValue(a, sortKey), threadSortValue(b, sortKey)));
      if (primary !== 0) return primary;
      const timeFallback = String(b.latestActivity || '').localeCompare(String(a.latestActivity || ''));
      if (timeFallback !== 0) return timeFallback;
      return String(a.label || '').localeCompare(String(b.label || ''));
    }}
    function compactListSummary(values, fallback = 'Mixed') {{
      const unique = [...new Set(values.filter(Boolean))].sort();
      if (!unique.length) return 'Unknown';
      if (unique.length === 1) return unique[0];
      return `${{unique[0]}} +${{unique.length - 1}} ${{fallback.toLowerCase()}}`;
    }}
    function pricingStatusFor(rows) {{
      const priced = rows.filter(row => row.pricing_model);
      const estimated = rows.filter(row => row.pricing_estimated);
      if (priced.length === 0) return 'No price';
      if (estimated.length === rows.length) return 'Estimated';
      if (estimated.length > 0 || priced.length < rows.length) return 'Mixed';
      return 'Configured';
    }}
    function groupThreads(rows) {{
      const map = new Map();
      for (const row of rows) {{
        const attachment = rowAttachment(row);
        const key = attachment.key;
        if (!map.has(key)) {{
          map.set(key, {{ key, label: attachment.label, rows: [] }});
        }}
        map.get(key).rows.push(row);
      }}
      return sortThreads([...map.values()].map(group => {{
        const calls = group.rows.slice().sort(chronological);
        const totalTokens = calls.reduce((sum, row) => sum + Number(row.total_tokens || 0), 0);
        const inputTokens = calls.reduce((sum, row) => sum + Number(row.input_tokens || 0), 0);
        const cachedTokens = calls.reduce((sum, row) => sum + Number(row.cached_input_tokens || 0), 0);
        const estimatedCost = calls.reduce((sum, row) => sum + Number(row.estimated_cost_usd || 0), 0);
        const signalCount = calls.reduce((sum, row) => sum + (Array.isArray(row.efficiency_flags) ? row.efficiency_flags.length : 0), 0);
        const latestActivity = calls.reduce((latest, row) => String(row.event_timestamp || '') > latest ? String(row.event_timestamp || '') : latest, '');
        const maxContextUse = calls.reduce((max, row) => Math.max(max, Number(row.context_window_percent || 0)), 0);
        const subagentCount = calls.filter(isSubagent).length;
        const autoReviewCount = calls.filter(isAutoReview).length;
        const attachedCount = calls.filter(row => rowAttachment(row).relation !== 'direct' && rowAttachment(row).relation !== 'session').length;
        const modelSummary = compactListSummary(calls.map(row => row.model), 'models');
        const effortSummary = compactListSummary(calls.map(row => row.effort), 'efforts');
        return {{
          key: group.key,
          label: group.label,
          calls,
          callCount: calls.length,
          latestActivity,
          modelSummary,
          effortSummary,
          totalTokens,
          estimatedCost,
          cacheRatio: inputTokens ? cachedTokens / inputTokens : 0,
          maxContextUse,
          pricingStatus: pricingStatusFor(calls),
          signalCount,
          subagentCount,
          autoReviewCount,
          attachedCount,
        }};
      }}));
    }}
    function render() {{
      const rows = filtered();
      rowsEl.textContent = '';
      updateSortControls();
      document.getElementById('visibleCalls').textContent = number.format(rows.length);
      document.getElementById('totalTokens').textContent = number.format(rows.reduce((sum, row) => sum + Number(row.total_tokens || 0), 0));
      document.getElementById('cachedTokens').textContent = number.format(rows.reduce((sum, row) => sum + Number(row.cached_input_tokens || 0), 0));
      document.getElementById('reasoningTokens').textContent = number.format(rows.reduce((sum, row) => sum + Number(row.reasoning_output_tokens || 0), 0));
      const estimatedCost = rows.reduce((sum, row) => sum + Number(row.estimated_cost_usd || 0), 0);
      const pricedTokens = rows.reduce((sum, row) => sum + (row.pricing_model ? Number(row.total_tokens || 0) : 0), 0);
      const estimatedTokens = rows.reduce((sum, row) => sum + (row.pricing_estimated ? Number(row.total_tokens || 0) : 0), 0);
      const unpricedTokens = rows.reduce((sum, row) => sum + (!row.pricing_model ? Number(row.total_tokens || 0) : 0), 0);
      const totalTokens = rows.reduce((sum, row) => sum + Number(row.total_tokens || 0), 0);
      document.getElementById('estimatedCost').textContent = pricingConfigured ? money(estimatedCost) : 'Not configured';
      document.getElementById('priceCoverage').textContent = pct(totalTokens ? pricedTokens / totalTokens : 0);
      document.getElementById('estimatedTokens').textContent = number.format(estimatedTokens);
      document.getElementById('unpricedTokens').textContent = number.format(unpricedTokens);
      callsViewEl.setAttribute('aria-pressed', activeView === 'calls' ? 'true' : 'false');
      threadsViewEl.setAttribute('aria-pressed', activeView === 'threads' ? 'true' : 'false');
      if (activeView === 'threads') {{
        renderThreads(rows);
      }} else {{
        renderCalls(rows);
      }}
    }}
    function renderCalls(rows) {{
      tableTitleEl.textContent = 'Model Calls';
      tableCaptionEl.textContent = `Showing individual model calls sorted by ${{tableCaptionEl.dataset.sortDescription}}.`;
      for (const row of rows.slice(0, 500)) {{
        const tr = document.createElement('tr');
        const flags = Array.isArray(row.efficiency_flags) ? row.efficiency_flags : [];
        tr.innerHTML = `
          <td>${{escapeHtml(truncate(row.event_timestamp, 20))}}</td>
          <td title="${{escapeHtml(short(row.session_id))}}">${{escapeHtml(truncate(rowThreadLabel(row)))}}</td>
          <td><span class="pill">${{escapeHtml(short(row.model))}}</span></td>
          <td>${{escapeHtml(short(row.effort))}}</td>
          <td class="num">${{number.format(row.total_tokens || 0)}}</td>
          <td class="num">${{escapeHtml(row.pricing_estimated ? `${{money(row.estimated_cost_usd)}}*` : money(row.estimated_cost_usd))}}</td>
          <td class="num">${{pct(row.cache_ratio)}}</td>
          <td><div class="flags">${{flags.slice(0, 2).map(flag => `<span class="flag">${{escapeHtml(flag)}}</span>`).join('')}}</div></td>
        `;
        tr.addEventListener('mouseenter', () => showDetail(row));
        rowsEl.appendChild(tr);
      }}
      if (!rows.length) {{
        rowsEl.innerHTML = '<tr><td class="empty-state" colspan="8">No calls match the current filters.</td></tr>';
      }}
    }}
    function renderThreads(rows) {{
      const groups = groupThreads(rows);
      tableTitleEl.textContent = 'Threads';
      tableCaptionEl.textContent = `Showing ${{number.format(groups.length)}} threads from ${{number.format(rows.length)}} filtered calls, sorted by ${{tableCaptionEl.dataset.sortDescription}}. Click a thread to expand its calls.`;
      for (const group of groups.slice(0, 500)) {{
        const tr = document.createElement('tr');
        const expanded = expandedThreads.has(group.key);
        const threadNotes = [
          `${{number.format(group.callCount)}} calls`,
          group.pricingStatus,
          group.subagentCount ? `${{number.format(group.subagentCount)}} subagent` : '',
          group.autoReviewCount ? `${{number.format(group.autoReviewCount)}} auto-review` : '',
          group.attachedCount ? 'attached' : '',
        ].filter(Boolean).join(' - ');
        tr.className = 'thread-row';
        tr.setAttribute('aria-expanded', expanded ? 'true' : 'false');
        tr.innerHTML = `
          <td>${{escapeHtml(truncate(group.latestActivity, 20))}}</td>
          <td>
            <div class="thread-title">
                <span class="thread-toggle" aria-hidden="true">${{expanded ? '-' : '+'}}</span>
              <span class="thread-meta">
                <span class="thread-name">${{escapeHtml(truncate(group.label, 72))}}</span>
                <span class="thread-subtle">${{escapeHtml(threadNotes)}}</span>
              </span>
            </div>
          </td>
          <td><span class="pill">${{escapeHtml(truncate(group.modelSummary, 28))}}</span></td>
          <td>${{escapeHtml(truncate(group.effortSummary, 28))}}</td>
          <td class="num">${{number.format(group.totalTokens)}}</td>
          <td class="num">${{pricingConfigured ? money(group.estimatedCost) : 'Not configured'}}</td>
          <td class="num">${{pct(group.cacheRatio)}}</td>
          <td class="num">${{number.format(group.signalCount)}}</td>
        `;
        tr.addEventListener('click', () => {{
          if (expandedThreads.has(group.key)) {{
            expandedThreads.delete(group.key);
          }} else {{
            expandedThreads.add(group.key);
          }}
          render();
        }});
        tr.addEventListener('mouseenter', () => showThreadDetail(group));
        rowsEl.appendChild(tr);
        if (expanded) {{
          rowsEl.appendChild(renderThreadCalls(group));
        }}
      }}
      if (!groups.length) {{
        rowsEl.innerHTML = '<tr><td class="empty-state" colspan="8">No threads match the current filters.</td></tr>';
      }}
    }}
    function renderThreadCalls(group) {{
      const tr = document.createElement('tr');
      tr.className = 'thread-child-row';
      const calls = group.calls.map(row => {{
        const flags = Array.isArray(row.efficiency_flags) ? row.efficiency_flags : [];
        return `
          <tr class="thread-call-row" data-record-id="${{escapeHtml(row.record_id || '')}}">
            <td>${{escapeHtml(truncate(row.event_timestamp, 20))}}</td>
            <td>${{escapeHtml(short(row.model))}}</td>
            <td>${{escapeHtml(short(row.effort))}}</td>
            <td>${{escapeHtml(sourceLabel(row))}}</td>
            <td class="num">${{number.format(row.total_tokens || 0)}}</td>
            <td class="num">${{escapeHtml(row.pricing_estimated ? `${{money(row.estimated_cost_usd)}}*` : money(row.estimated_cost_usd))}}</td>
            <td class="num">${{pct(row.cache_ratio)}}</td>
            <td><div class="flags">${{flags.slice(0, 2).map(flag => `<span class="flag">${{escapeHtml(flag)}}</span>`).join('')}}</div></td>
          </tr>
        `;
      }}).join('');
      tr.innerHTML = `
        <td class="child-cell" colspan="8">
          <table class="thread-call-table" aria-label="${{escapeHtml(group.label)}} calls">
            <thead><tr><th>Time</th><th>Model</th><th>Effort</th><th>Source</th><th class="num">Last Call</th><th class="num">Cost</th><th class="num">Cache</th><th>Signals</th></tr></thead>
            <tbody>${{calls}}</tbody>
          </table>
        </td>
      `;
      return tr;
    }}
    function contextControls(row) {{
      const fileMode = window.location.protocol === 'file:';
      const disabled = fileMode ? ' disabled' : '';
      const hint = fileMode
        ? 'Open this dashboard with codex-usage-tracker serve-dashboard to load raw context on demand.'
        : 'Context is not embedded in this dashboard. Press a button to read this call from the local JSONL source.';
      return `
        <div class="context-actions">
          <button class="context-button" type="button" data-context-load${{disabled}}>Load context</button>
          <button class="context-button secondary" type="button" data-context-load-output${{disabled}}>Include tool output</button>
        </div>
        <div id="contextResult" class="context-result"><p class="context-note">${{escapeHtml(hint)}}</p></div>
      `;
    }}
    function bindContextButtons(row) {{
      const loadButton = detailEl.querySelector('[data-context-load]');
      const outputButton = detailEl.querySelector('[data-context-load-output]');
      if (loadButton) loadButton.addEventListener('click', () => loadContext(row, false));
      if (outputButton) outputButton.addEventListener('click', () => loadContext(row, true));
    }}
    async function loadContext(row, includeToolOutput) {{
      const target = document.getElementById('contextResult');
      if (!target) return;
      if (!row.record_id) {{
        target.innerHTML = '<p class="context-note">This row has no record id for context lookup.</p>';
        return;
      }}
      target.innerHTML = '<p class="context-note">Loading local context...</p>';
      const params = new URLSearchParams({{ record_id: row.record_id }});
      if (includeToolOutput) params.set('include_tool_output', '1');
      try {{
        const response = await fetch(`/api/context?${{params.toString()}}`, {{
          headers: {{ 'Accept': 'application/json' }},
          cache: 'no-store',
        }});
        if (!response.ok) {{
          const errorText = response.status === 404
            ? 'Context API is unavailable here. Run codex-usage-tracker serve-dashboard --open for on-demand context loading.'
            : `Context API returned HTTP ${{response.status}}.`;
          throw new Error(errorText);
        }}
        const payload = await response.json();
        target.innerHTML = renderContext(payload);
      }} catch (error) {{
        target.innerHTML = `<p class="context-note">${{escapeHtml(error.message || String(error))}}</p>`;
      }}
    }}
    function renderContext(payload) {{
      const entries = Array.isArray(payload.entries) ? payload.entries : [];
      const source = payload.source || {{}};
      const omitted = payload.omitted || {{}};
      const note = [
        'Loaded on demand from local JSONL.',
        payload.raw_context_persisted === false ? 'Not persisted to SQLite or dashboard HTML.' : '',
        payload.include_tool_output ? 'Tool output included with redaction and size limits.' : 'Tool output omitted by default.',
        source.file ? `Source: ${{source.file}}:${{source.line_number || ''}}` : '',
        omitted.older_entries ? `${{number.format(omitted.older_entries)}} older entries omitted.` : '',
        omitted.over_budget_chars ? `${{number.format(omitted.over_budget_chars)}} chars over budget omitted.` : '',
      ].filter(Boolean).join(' ');
      const body = entries.map(entry => `
        <div class="context-entry">
          <div class="context-entry-header">
            <span>${{escapeHtml(entry.label || entry.type || 'entry')}}</span>
            <span>${{escapeHtml([entry.timestamp, entry.line_number ? `line ${{entry.line_number}}` : ''].filter(Boolean).join(' - '))}}</span>
          </div>
          <pre>${{escapeHtml(entry.text || '')}}</pre>
        </div>
      `).join('');
      return `<p class="context-note">${{escapeHtml(note)}}</p>${{body || '<p class="context-note">No context entries found for this call.</p>'}}`;
    }}
    function showDetail(row) {{
      const attachment = rowAttachment(row);
      const fields = [
        ['Thread', attachment.label],
        ['Thread attachment', attachment.relation],
        ['Session', row.session_id],
        ['Thread source', row.thread_source || 'user'],
        ['Subagent type', row.subagent_type || 'None'],
        ['Agent role', row.agent_role || 'None'],
        ['Agent nickname', row.agent_nickname || 'None'],
        ['Parent session', row.parent_session_id || 'None'],
        ['Turn', row.turn_id],
        ['Timestamp', row.event_timestamp],
        ['Model', row.model],
        ['Reasoning', row.effort],
        ['Cwd', row.cwd],
        ['Last call total', number.format(row.total_tokens || 0)],
        ['Last call input', number.format(row.input_tokens || 0)],
        ['Cached input', number.format(row.cached_input_tokens || 0)],
        ['Uncached input', number.format(row.uncached_input_tokens || 0)],
        ['Output', number.format(row.output_tokens || 0)],
        ['Reasoning output', number.format(row.reasoning_output_tokens || 0)],
        ['Estimated cost', money(row.estimated_cost_usd)],
        ['Pricing model', row.pricing_model || 'No configured price'],
        ['Pricing status', row.pricing_estimated ? 'Best-guess estimate' : row.pricing_model ? 'Configured price' : 'No configured price'],
        ['Estimated cache savings', money(row.estimated_cache_savings_usd)],
        ['Efficiency signals', Array.isArray(row.efficiency_flags) && row.efficiency_flags.length ? row.efficiency_flags.join(', ') : 'None'],
        ['Session cumulative', number.format(row.cumulative_total_tokens || 0)],
        ['Context window', number.format(row.model_context_window || 0)],
        ['Context use', pct(row.context_window_percent)],
        ['Source line', `${{row.source_file}}:${{row.line_number}}`],
      ];
      detailEl.innerHTML = '<dl>' + fields.map(([key, value]) => `<dt>${{escapeHtml(key)}}</dt><dd>${{escapeHtml(short(value))}}</dd>`).join('') + '</dl>' + contextControls(row);
      bindContextButtons(row);
    }}
    function showThreadDetail(group) {{
      const fields = [
        ['Thread', group.label],
        ['Latest activity', group.latestActivity],
        ['Calls', number.format(group.callCount)],
        ['Total tokens', number.format(group.totalTokens)],
        ['Estimated cost', pricingConfigured ? money(group.estimatedCost) : 'Not configured'],
        ['Cache ratio', pct(group.cacheRatio)],
        ['Pricing status', group.pricingStatus],
        ['Efficiency signals', number.format(group.signalCount)],
        ['Subagent calls', number.format(group.subagentCount)],
        ['Auto-review calls', number.format(group.autoReviewCount)],
        ['Attached calls', number.format(group.attachedCount)],
        ['Max context use', pct(group.maxContextUse)],
      ];
      detailEl.innerHTML = '<dl>' + fields.map(([key, value]) => `<dt>${{escapeHtml(key)}}</dt><dd>${{escapeHtml(short(value))}}</dd>`).join('') + '</dl>';
    }}
    function setView(view) {{
      activeView = view;
      render();
    }}
    callsViewEl.addEventListener('click', () => setView('calls'));
    threadsViewEl.addEventListener('click', () => setView('threads'));
    document.querySelectorAll('[data-sort-key]').forEach(button => {{
      button.addEventListener('click', () => handleHeaderSort(button.dataset.sortKey));
    }});
    rowsEl.addEventListener('mouseover', event => {{
      const callRow = event.target.closest('.thread-call-row');
      if (!callRow || !rowsEl.contains(callRow)) return;
      const row = rowByRecordId.get(callRow.dataset.recordId);
      if (row) showDetail(row);
    }});
    [searchEl, modelEl, effortEl, pricingStatusEl].forEach(el => el.addEventListener('input', render));
    sortEl.addEventListener('input', () => setSort(sortEl.value, defaultSortDirection(sortEl.value)));
    render();
  </script>
</body>
</html>
"""
