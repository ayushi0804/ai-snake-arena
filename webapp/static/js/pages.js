/* Dashboard, leaderboard, history, benchmark and settings pages. All DOM built with textContent (no innerHTML). */
(function () {
  'use strict';
  const A = window.Arena, $ = A.$, el = A.el, page = document.body.dataset.page;
  const fmtDur = ms => { const s = Math.round(ms / 1000); return s >= 3600 ? Math.floor(s / 3600) + 'h ' + Math.floor(s % 3600 / 60) + 'm' : s >= 60 ? Math.floor(s / 60) + 'm ' + s % 60 + 's' : s + 's'; };
  const fmtDate = iso => { const d = new Date(iso); return isNaN(d) ? '' : d.toLocaleString([], { dateStyle: 'short', timeStyle: 'short' }); };
  const pct = v => v == null ? 'n/a' : (v * 100).toFixed(1) + '%';
  const num = (v, d = 2) => v == null ? 'n/a' : (+v).toFixed(d);
  function setState(node, kind, msg, retry) {
    node.hidden = false; node.className = 'state' + (kind === 'err' ? ' err' : ''); node.textContent = '';
    if (kind === 'loading') node.append(el('div', { className: 'spinner' }), msg || 'Loading…'); else node.append(msg);
    if (retry) node.append(el('br'), el('button', { className: 'btn', type: 'button', textContent: 'Retry', onclick: retry }));
  }
  const errMsg = r => (r.network ? (navigator.onLine === false ? 'You are offline. This page needs a connection; the game still works offline.' : 'Could not reach the server.') : (r.error && r.error.message) || 'Something went wrong.');
  function table(t, cols, rows) {
    t.textContent = ''; t.append(el('thead', {}, el('tr', {}, cols.map(c => el('th', { scope: 'col', textContent: c[0] })))));
    t.append(el('tbody', {}, rows.map(r => el('tr', {}, cols.map(c => el('td', { textContent: c[1](r) }))))));
  }
  const matchCols = [['When', r => fmtDate(r.created_at)], ['Mode', r => r.mode === 'ai' ? 'AI · ' + (r.algorithm || '') : r.mode], ['Difficulty', r => r.difficulty], ['Board', r => r.board_w + '×' + r.board_h + (r.wrap ? ' wrap' : '')],
    ['Score', r => r.score], ['Apples', r => r.apples_collected], ['Time', r => fmtDur(r.duration_ms)], ['Outcome', r => r.outcome], ['Source', r => r.source + ' · ' + r.trust.replace('_', ' ')]];

  async function dashboard() {
    const st = $('dash-state'), body = $('dash-body'); setState(st, 'loading'); body.hidden = true;
    const [s, m] = await Promise.all([A.api.stats(), A.api.algoMetrics()]);
    if (!s.ok) return setState(st, 'err', errMsg(s), dashboard);
    const d = s.data;
    if (!d.total_matches) { setState(st, 'empty', 'No matches yet. Finish a game on the Play page and your statistics will appear here.'); st.append(el('br'), el('a', { className: 'btn primary', href: '/play', textContent: 'Play now' })); return; }
    st.hidden = true; body.hidden = false;
    const cards = [['Matches', d.total_matches], ['Best score', d.best_score], ['Average score', d.average_score], ['Apples collected', d.apples_collected], ['Total play time', fmtDur(d.total_play_time_ms)], ['Avg match length', fmtDur(d.average_duration_ms)], ['Boards completed', d.boards_completed + ' (' + pct(d.completion_rate) + ' of matches)']];
    const box = $('dash-cards'); box.textContent = ''; cards.forEach(c => box.append(el('div', { className: 'stat' }, el('b', { textContent: String(c[1]) }), el('span', { textContent: c[0] }))));
    const prog = d.score_progression, lab = prog.map((_, i) => '#' + (i + 1));
    A.charts.line('ch-score', lab, [{ name: 'Score', values: prog.map(p => p.score) }]);
    A.charts.line('ch-duration', lab, [{ name: 'Seconds', values: prog.map(p => +(p.duration_ms / 1000).toFixed(1)) }]);
    const dk = Object.keys(d.difficulty_distribution), ok = Object.keys(d.outcome_distribution);
    A.charts.bars('ch-diff', dk, [{ name: 'Matches', values: dk.map(k => d.difficulty_distribution[k]) }]);
    A.charts.bars('ch-outcome', ok, [{ name: 'Matches', values: ok.map(k => d.outcome_distribution[k]) }]);
    const note = $('algo-note'), ac = $('algo-charts'); const pm = m.ok ? m.data.played_matches : [];
    if (!m.ok) { note.textContent = errMsg(m); ac.hidden = true; }
    else if (!pm.length) { note.textContent = 'Play a match in AI mode to see algorithm comparisons. For controlled comparisons use the Benchmark Lab.'; ac.hidden = true; }
    else {
      note.textContent = 'Aggregated over all AI matches from every guest in this database (client-reported). Different strategies faced different random boards, so use the Benchmark Lab for controlled comparisons.'; ac.hidden = false;
      const names = pm.map(x => x.algorithm);
      A.charts.bars('ch-a-time', names, [{ name: 'ms', values: pm.map(x => x.avg_decision_ms) }]); A.charts.bars('ch-a-nodes', names, [{ name: 'nodes', values: pm.map(x => x.avg_nodes_explored) }]);
      A.charts.bars('ch-a-len', names, [{ name: 'steps', values: pm.map(x => x.avg_path_length) }]); A.charts.bars('ch-a-rate', names, [{ name: '%', values: pm.map(x => x.path_success_rate == null ? null : +(x.path_success_rate * 100).toFixed(1)) }]);
    }
    table($('tbl-recent'), matchCols, d.recent_matches);
  }

  async function leaderboard() {
    const st = $('lb-state'), wrap = $('lb-wrap');
    const load = async () => {
      setState(st, 'loading'); wrap.hidden = true;
      const r = await A.api.leaderboard({ difficulty: $('lb-diff').value, mode: $('lb-mode').value, limit: 25 });
      if (!r.ok) return setState(st, 'err', errMsg(r), load);
      if (!r.data.entries.length) return setState(st, 'empty', 'No scores for this filter yet. Be the first!');
      st.hidden = true; wrap.hidden = false;
      table($('lb-table'), [['#', e => e.rank], ['Player', e => e.display_name], ['Score', e => e.score], ['Mode', e => e.mode === 'ai' ? 'AI · ' + e.algorithm : e.mode], ['Difficulty', e => e.difficulty], ['Source', e => e.trust.replace('_', ' ')], ['When', e => fmtDate(e.created_at)]], r.data.entries);
    };
    $('lb-diff').addEventListener('change', load); $('lb-mode').addEventListener('change', load); load();
  }

  async function history() {
    const st = $('hi-state'), wrap = $('hi-wrap'), more = $('hi-more'); let rows = [];
    const load = async (reset) => {
      if (reset) { rows = []; setState(st, 'loading'); wrap.hidden = true; }
      const r = await A.api.history(20, rows.length);
      if (!r.ok) return setState(st, 'err', errMsg(r), () => load(true));
      rows = rows.concat(r.data.items);
      if (!rows.length) { setState(st, 'empty', 'No matches yet. Play a game and it will show up here.'); st.append(el('br'), el('a', { className: 'btn primary', href: '/play', textContent: 'Play now' })); return; }
      st.hidden = true; wrap.hidden = false; table($('hi-table'), matchCols, rows); more.hidden = rows.length >= r.data.total;
    };
    more.addEventListener('click', () => load(false)); load(true);
  }

  function benchmark() {
    const st = $('bm-state'), res = $('bm-results'), kind = $('bm-kind');
    const syncKind = () => { const s = kind.value === 'survival'; $('lb-scen').firstChild.textContent = s ? 'Games' : 'Scenarios'; $('bm-n').max = s ? 20 : 500; $('bm-n').value = s ? 5 : 100; $('bm-w').value = s ? 12 : 25; $('bm-h').value = s ? 8 : 12; $('bm-w').max = $('bm-h').max = s ? 20 : 40; $('bm-len').disabled = $('bm-obs').disabled = s; };
    kind.addEventListener('change', syncKind);
    const cols = k => k === 'pathfinding'
      ? [['Algorithm', r => r.algorithm], ['Scenarios', r => r.scenarios], ['Success', r => pct(r.success_rate)], ['Safe path', r => pct(r.safe_rate)], ['Avg time (ms)', r => num(r.avg_time_ms, 4)], ['Avg nodes', r => num(r.avg_nodes, 1)], ['Avg path len', r => num(r.avg_path_len, 2)]]
      : [['Strategy', r => r.algorithm], ['Games', r => r.scenarios], ['No-collision rate', r => pct(r.safe_rate)], ['Completion', r => pct(r.completion_rate)], ['Avg score', r => num(r.avg_score, 1)], ['Avg steps', r => num(r.avg_steps, 0)]];
    function show(kindName, rows) {
      res.hidden = false; table($('bm-table'), cols(kindName), rows); const n = rows.map(r => r.algorithm);
      if (kindName === 'pathfinding') { $('bm-c1t').textContent = 'Avg nodes explored'; $('bm-c2t').textContent = 'Avg time (ms)'; A.charts.bars('bm-c1', n, [{ name: 'nodes', values: rows.map(r => r.avg_nodes) }]); A.charts.bars('bm-c2', n, [{ name: 'ms', values: rows.map(r => r.avg_time_ms) }]); }
      else { $('bm-c1t').textContent = 'Avg score'; $('bm-c2t').textContent = 'No-collision rate (%)'; A.charts.bars('bm-c1', n, [{ name: 'score', values: rows.map(r => r.avg_score) }]); A.charts.bars('bm-c2', n, [{ name: '%', values: rows.map(r => +(r.safe_rate * 100).toFixed(1)) }]); }
    }
    async function hist() {
      const hs = $('bm-hist-state'); setState(hs, 'loading'); const r = await A.api.benchmarks();
      if (!r.ok) { setState(hs, 'err', errMsg(r), hist); $('bm-hist').textContent = ''; return; }
      if (!r.data.length) { setState(hs, 'empty', 'No stored benchmark runs yet.'); $('bm-hist').textContent = ''; return; }
      hs.hidden = true;
      table($('bm-hist'), [['When', x => fmtDate(x.created_at)], ['Kind', x => x.kind], ['Algorithm', x => x.algorithm], ['Seed', x => x.seed], ['Board', x => x.board_w + '×' + x.board_h], ['N', x => x.scenarios], ['Success', x => pct(x.success_rate)], ['Safe', x => pct(x.safe_rate)], ['Time ms', x => num(x.avg_time_ms, 4)], ['Nodes', x => num(x.avg_nodes, 1)], ['Score', x => num(x.avg_score, 1)], ['Provenance', x => x.provenance]], r.data);
    }
    $('bm-form').addEventListener('submit', async e => {
      e.preventDefault(); const k = kind.value, btn = $('bm-run'); btn.disabled = true; setState(st, 'loading', 'Running benchmark… this can take a few seconds.');
      const b = { kind: k, seed: +$('bm-seed').value, board_w: +$('bm-w').value, board_h: +$('bm-h').value };
      if (k === 'pathfinding') Object.assign(b, { scenarios: +$('bm-n').value, snake_len: +$('bm-len').value, obstacle_fraction: +$('bm-obs').value }); else Object.assign(b, { games: +$('bm-n').value });
      const r = await A.api.runBenchmark(b); btn.disabled = false;
      if (!r.ok) { const d = r.error && r.error.details ? ' ' + Object.entries(r.error.details).map(([a, c]) => a + ': ' + c).join('; ') : ''; return setState(st, 'err', errMsg(r) + d); }
      st.hidden = true; show(r.data.kind, r.data.results); hist();
    });
    $('bm-reload').addEventListener('click', hist); syncKind(); hist();
  }

  function settings() {
    const S = A.settings.get(), map = { name: 's-name', theme: 's-theme', mode: 's-mode', strategy: 's-strategy', difficulty: 's-difficulty', board: 's-board', volume: 's-volume', speed: 's-speed', sound: 's-sound', wrap: 's-wrap', obstacles: 's-obstacles', powerups: 's-powerups', showPath: 's-showPath' };
    const status = $('s-status'), read = () => { const o = {}; for (const [k, id] of Object.entries(map)) { const n = $(id); o[k] = n.type === 'checkbox' ? n.checked : n.type === 'range' ? +n.value : n.value; } return o; };
    const fill = s => { for (const [k, id] of Object.entries(map)) { const n = $(id); if (n.type === 'checkbox') n.checked = !!s[k]; else n.value = s[k]; } };
    fill(S); $('s-guest').textContent = 'Guest ID: ' + A.guestId();
    $('set-form').addEventListener('submit', async e => {
      e.preventDefault(); const v = read(); A.settings.set(v); A.applyTheme(v.theme); status.textContent = 'Saved on this device. Syncing…';
      const r = await A.api.putSettings(v); status.textContent = r.ok ? 'Saved on this device and synced to the server.' : 'Saved on this device. Server sync skipped: ' + errMsg(r);
    });
    $('s-reset').addEventListener('click', () => { const s = A.settings.reset(); fill(s); A.applyTheme(s.theme); status.textContent = 'Defaults restored (not yet synced; press Save).'; });
    $('s-clear').addEventListener('click', () => { if (!confirm('Remove this device\'s guest ID, high score, settings and unsent matches?')) return; ['arena.guest', 'arena.settings', 'arena.highscore', 'arena.outbox'].forEach(A.store.remove); status.textContent = 'Local data cleared. A new guest ID will be created next time.'; });
  }

  ({ dashboard, leaderboard, history, benchmark, settings }[page] || function () {})();
})();
