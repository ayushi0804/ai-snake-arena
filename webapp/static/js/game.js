/* Play page controller: fixed-timestep loop (simulation) decoupled from rendering (rAF). */
(function () {
  'use strict';
  const A = window.Arena, $ = A.$, AI = A.AI;
  const S = A.settings.get();
  const canvas = $('board'), ctx = canvas.getContext('2d'), wrap = $('board-wrap'), overlay = $('overlay');
  let state, phase = 'ready', acc = 0, last = 0, simTime = 0, cell = 20, dirty = true;
  let aiStats, lastDec = null, matchId = A.newMatchId(), best = A.store.get('arena.highscore', 0);
  const cssv = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
  const dims = () => A.BOARDS[S.board] || A.BOARDS.classic;
  const stallLimit = () => (S.mode === 'ai' ? state.grid.size * 4 : null);
  const OUTCOME = { wall: 'Hit the wall', self: 'Ran into itself', obstacle: 'Hit an obstacle', won: 'Board completed!', stalled: 'AI stalled (no apple for too long)' };

  function newGame() {
    const [w, h] = dims();
    state = new A.GameState({ w, h, wrap: S.wrap, difficulty: S.difficulty, obstacles: S.obstacles, powerups: S.powerups });
    aiStats = { decisions: 0, total_time_ms: 0, total_nodes: 0, total_path_len: 0, paths_found: 0 };
    lastDec = null; acc = 0; simTime = 0; matchId = A.newMatchId(); phase = 'ready';
    layout(); showOverlay('Ready?', S.mode === 'ai' ? 'The ' + S.strategy.toUpperCase() + ' AI will play. Press Start.' : 'Arrow keys or swipe to steer. Press Start or any arrow.', 'Start', false);
    updateHud(); updateAI(); $('btn-pause').textContent = 'Pause'; dirty = true;
  }
  function showOverlay(title, body, primary, link) {
    $('ov-title').textContent = title; $('ov-body').textContent = body; $('ov-primary').textContent = primary; $('ov-link').hidden = !link;
    overlay.hidden = false; $('ov-primary').focus({ preventScroll: true });
  }
  function layout() {
    const [w, h] = [state.grid.w, state.grid.h], dpr = window.devicePixelRatio || 1;
    const dp = $('board-wrap').parentElement.querySelector('.dpad'), reserve = (dp && getComputedStyle(dp).display !== 'none' ? 150 : 20) + 70;
    const availW = wrap.clientWidth || 300, availH = Math.max(160, window.innerHeight - wrap.getBoundingClientRect().top - reserve - (window.innerWidth < 760 ? 70 : 0));
    cell = Math.max(8, Math.floor(Math.min(availW / w, availH / h)));
    canvas.style.width = cell * w + 'px'; canvas.style.height = cell * h + 'px';
    canvas.width = Math.round(cell * w * dpr); canvas.height = Math.round(cell * h * dpr); ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    overlay.style.width = cell * w + 'px'; overlay.style.height = cell * h + 'px'; dirty = true;
  }

  // ---------- drawing ----------
  function rr(x, y, w, h, r) { ctx.beginPath(); ctx.roundRect ? ctx.roundRect(x, y, w, h, r) : ctx.rect(x, y, w, h); }
  function draw() {
    const g = state.grid, c = cell, W = g.w * c, H = g.h * c;
    ctx.clearRect(0, 0, W, H); ctx.fillStyle = cssv('--board-bg'); ctx.fillRect(0, 0, W, H);
    ctx.strokeStyle = cssv('--grid'); ctx.lineWidth = 1; ctx.beginPath();
    for (let x = 1; x < g.w; x++) { ctx.moveTo(x * c + .5, 0); ctx.lineTo(x * c + .5, H); }
    for (let y = 1; y < g.h; y++) { ctx.moveTo(0, y * c + .5); ctx.lineTo(W, y * c + .5); } ctx.stroke();
    if (g.wrap) { ctx.setLineDash([6, 6]); ctx.strokeStyle = cssv('--warn') || '#ffc857'; ctx.strokeRect(1, 1, W - 2, H - 2); ctx.setLineDash([]); }
    ctx.fillStyle = cssv('--obstacle'); state.obstacles.forEach(o => { rr(g.x(o) * c + 2, g.y(o) * c + 2, c - 4, c - 4, 4); ctx.fill(); });
    if (S.showPath && S.mode === 'ai' && lastDec && lastDec.path.length) {
      ctx.fillStyle = cssv('--path'); lastDec.path.forEach((p, i) => { ctx.beginPath(); ctx.arc(g.x(p) * c + c / 2, g.y(p) * c + c / 2, Math.max(2, c * (i === lastDec.path.length - 1 ? .22 : .13)), 0, 6.3); ctx.fill(); });
    }
    const item = (it, fill, ch) => { if (!it) return; const x = g.x(it.pos) * c, y = g.y(it.pos) * c; ctx.fillStyle = fill; ctx.beginPath(); ctx.arc(x + c / 2, y + c / 2, c * .36, 0, 6.3); ctx.fill();
      if (ch) { ctx.fillStyle = '#111'; ctx.font = 'bold ' + Math.round(c * .45) + 'px system-ui'; ctx.textAlign = 'center'; ctx.textBaseline = 'middle'; ctx.fillText(ch, x + c / 2, y + c / 2 + 1); } };
    item(state.apple, cssv('--apple')); item(state.bonus, cssv('--gold'), '★');
    if (state.powerup) item(state.powerup, '#7cc8ff', { slow: 'S', double: '×2', shrink: '–' }[state.powerup.kind]);
    const n = state.snake.length, a = cssv('--snake-a'), b = cssv('--snake-b');
    for (let i = n - 1; i >= 0; i--) {
      const s = state.snake[i], x = g.x(s) * c, y = g.y(s) * c;
      ctx.globalAlpha = 1; ctx.fillStyle = i === 0 ? b : a; rr(x + 1, y + 1, c - 2, c - 2, Math.max(3, c * .25)); ctx.fill();
      if (i > 0 && n > 1) { ctx.globalAlpha = .55 * (i / n); ctx.fillStyle = b; ctx.fill(); ctx.globalAlpha = 1; }
    }
    const hd = state.snake[0], hx = g.x(hd) * c, hy = g.y(hd) * c, o = c * .25, e = c * .1;
    const eyes = { up: [[o, o], [c - o, o]], down: [[o, c - o], [c - o, c - o]], left: [[o, o], [o, c - o]], right: [[c - o, o], [c - o, c - o]] }[state.direction];
    ctx.fillStyle = '#04210f'; eyes.forEach(([ex, ey]) => { ctx.beginPath(); ctx.arc(hx + ex, hy + ey, Math.max(1.5, e), 0, 6.3); ctx.fill(); });
    dirty = false;
  }
  function updateHud() {
    $('hud-score').textContent = state.score; $('hud-best').textContent = Math.max(best, state.score); $('hud-length').textContent = state.snake.length;
    $('hud-speed').textContent = (state.speed * S.speed).toFixed(1);
    const fx = $('hud-effects'); fx.textContent = '';
    ['double', 'slow'].forEach(k => { if (state.effects[k] > 0) fx.append(A.el('span', { className: 'chip', textContent: (k === 'double' ? '×2 ' : 'Slow ') + state.effects[k] }), ' '); });
  }
  function updateAI() {
    const d = lastDec, set = (id, v) => { $(id).textContent = v; };
    if (S.mode !== 'ai' || !d) { ['ai-strategy', 'ai-reason', 'ai-path', 'ai-explored', 'ai-time', 'ai-safe'].forEach(i => set(i, '–')); if (S.mode === 'ai') set('ai-strategy', S.strategy); return; }
    set('ai-strategy', d.strategy + (d.strategy === 'adaptive' ? ' (' + d.algorithm + ')' : '')); set('ai-reason', d.reason.replace(/_/g, ' '));
    set('ai-path', d.found ? d.pathLength + ' steps' : (d.reason === 'hamiltonian_cycle' ? 'cycle' : 'no path'));
    set('ai-explored', d.reason === 'hamiltonian_cycle' ? 'n/a' : d.explored); set('ai-time', d.timeMs.toFixed(2) + ' ms');
    const m = d.moves.filter(x => x.legal);
    set('ai-safe', (d.safe ? 'safe' : 'RISKY') + ' · ' + m.length + ' legal move' + (m.length === 1 ? '' : 's') + (m.some(x => x.deadEnd) ? ' · dead end(s) avoided' : ''));
  }

  // ---------- simulation ----------
  function aiTurn() {
    state.cfg.stallLimit = stallLimit();
    const dec = AI.chooseMove(state.situation(), S.strategy, S.base); lastDec = dec;
    if (dec.reason !== 'hamiltonian_cycle') {
      aiStats.decisions++; aiStats.total_time_ms += dec.timeMs; aiStats.total_nodes += dec.explored;
      if (dec.found) { aiStats.paths_found++; aiStats.total_path_len += dec.pathLength; }
    } else aiStats.hamiltonianDecisions = (aiStats.hamiltonianDecisions || 0) + 1;
    if (dec.direction) state.setDirection(dec.direction);
  }
  function tick(interval) {
    if (S.mode === 'ai') aiTurn(); else state.cfg.stallLimit = null;
    const ev = state.step(); simTime += interval;
    ev.forEach(e => A.sound.play(e === 'died' ? 'die' : e));
    updateHud(); updateAI(); dirty = true;
    if (!state.alive) finish();
  }
  function frame(ts) {
    requestAnimationFrame(frame);
    if (phase === 'running') {
      acc += Math.min(ts - last, 250); let guard = 0;
      for (let iv = 1000 / (state.speed * S.speed); acc >= iv && phase === 'running' && guard++ < 6; iv = 1000 / (state.speed * S.speed)) { acc -= iv; tick(iv); }
    }
    last = ts; if (dirty) draw();
  }
  async function finish() {
    phase = 'over'; const s = state; draw();
    const isBest = s.score > best; if (isBest) { best = s.score; A.store.set('arena.highscore', best); }
    A.sound.play(s.outcome === 'won' ? 'won' : 'die');
    const total = aiStats.decisions + (aiStats.hamiltonianDecisions || 0), aiMode = total * 2 >= s.steps && S.mode === 'ai';
    const payload = { client_match_id: matchId, mode: aiMode ? 'ai' : 'manual', difficulty: S.difficulty, board_w: s.grid.w, board_h: s.grid.h,
      wrap: S.wrap, obstacles: s.obstacles.size > 0, score: s.score, apples_collected: s.apples, steps: s.steps, duration_ms: Math.round(simTime), outcome: s.outcome };
    if (aiMode) { payload.algorithm = S.strategy; payload.ai_metrics = { decisions: aiStats.decisions, total_time_ms: +aiStats.total_time_ms.toFixed(3), total_nodes: aiStats.total_nodes, total_path_len: aiStats.total_path_len, paths_found: aiStats.paths_found }; }
    const head = (s.outcome === 'won' ? '🏆 ' : '') + (OUTCOME[s.outcome] || 'Game over');
    const base = 'Score ' + s.score + (isBest ? ' (new best!)' : ' · best ' + best) + '\nApples ' + s.apples + ' · length ' + s.snake.length + ' · ' + (simTime / 1000).toFixed(1) + 's';
    showOverlay(head, base + '\nSaving…', 'Play again', true); $('btn-pause').textContent = 'Pause';
    const r = await A.api.submitMatch(payload);
    if (phase === 'over') $('ov-body').textContent = base + '\n' + r.message; updateHud();
  }

  // ---------- controls ----------
  function start() { if (phase !== 'ready') return; A.sound.unlock(); phase = 'running'; overlay.hidden = true; last = performance.now(); canvas.focus({ preventScroll: true }); }
  function pause(force) {
    if (phase === 'running' && force !== false) { phase = 'paused'; showOverlay('Paused', 'Press Space or Resume.', 'Resume', false); $('btn-pause').textContent = 'Resume'; }
    else if (phase === 'paused') { phase = 'running'; overlay.hidden = true; last = performance.now(); acc = 0; $('btn-pause').textContent = 'Pause'; }
  }
  const primary = () => { if (phase === 'ready') start(); else if (phase === 'paused') pause(); else if (phase === 'over') newGame(); };
  function turn(d) { if (phase === 'ready') start(); if (phase === 'running' && S.mode === 'manual') state.setDirection(d); }
  const save = patch => { Object.assign(S, patch); A.settings.set(patch); };
  function syncControls() {
    $('sel-mode').value = S.mode; $('sel-strategy').value = S.strategy; $('sel-base').value = S.base; $('sel-difficulty').value = S.difficulty; $('sel-board').value = S.board;
    $('chk-wrap').checked = S.wrap; $('chk-obstacles').checked = S.obstacles; $('chk-powerups').checked = S.powerups; $('chk-path').checked = S.showPath;
    $('rng-speed').value = S.speed; $('out-speed').textContent = (+S.speed).toFixed(1);
    $('btn-mute').textContent = (S.sound ? '🔊' : '🔇') + ' Sound'; $('btn-mute').setAttribute('aria-pressed', String(!S.sound)); A.sound.configure(S);
  }
  function bind() {
    const live = (id, key, conv) => $(id).addEventListener('change', e => { save({ [key]: conv ? conv(e.target) : e.target.value }); syncControls(); updateAI(); dirty = true; });
    live('sel-mode', 'mode'); live('sel-strategy', 'strategy'); live('sel-base', 'base'); live('chk-path', 'showPath', t => t.checked);
    const restart = (id, key, conv) => $(id).addEventListener('change', e => { save({ [key]: conv ? conv(e.target) : e.target.value }); syncControls(); newGame(); });
    restart('sel-difficulty', 'difficulty'); restart('sel-board', 'board'); restart('chk-wrap', 'wrap', t => t.checked); restart('chk-obstacles', 'obstacles', t => t.checked); restart('chk-powerups', 'powerups', t => t.checked);
    $('rng-speed').addEventListener('input', e => { save({ speed: +e.target.value }); syncControls(); updateHud(); });
    $('btn-pause').addEventListener('click', () => pause()); $('btn-restart').addEventListener('click', newGame); $('ov-primary').addEventListener('click', primary);
    $('btn-mute').addEventListener('click', () => { save({ sound: !S.sound }); syncControls(); });
    document.querySelectorAll('.dpad [data-dir]').forEach(b => b.addEventListener('pointerdown', e => { e.preventDefault(); turn(b.dataset.dir); }));
    const KEYS = { ArrowUp: 'up', ArrowDown: 'down', ArrowLeft: 'left', ArrowRight: 'right' };
    document.addEventListener('keydown', e => {
      if (e.ctrlKey || e.metaKey || e.altKey) return;
      const t = e.target, tag = t.tagName, formish = tag === 'SELECT' || tag === 'TEXTAREA' || (tag === 'INPUT' && t.type !== 'checkbox');
      if (formish) return;                                                         // arrows change a focused select/input
      if (KEYS[e.key]) { e.preventDefault(); turn(KEYS[e.key]); return; }
      const k = e.key.toLowerCase(), onButton = tag === 'BUTTON' || tag === 'A';
      if ((k === ' ' || k === 'enter') && onButton) return;                          // let focused buttons activate
      if (k === ' ' || k === 'p') { e.preventDefault(); phase === 'ready' || phase === 'over' ? primary() : pause(); }
      else if (k === 'enter') { if (phase === 'over' || phase === 'ready') primary(); }
      else if (k === 'r') newGame();
      else if (k === 'm') { save({ mode: S.mode === 'ai' ? 'manual' : 'ai' }); syncControls(); updateAI(); if (phase === 'ready') newGame(); }
      else if ('abdsh'.includes(k) && k.length === 1) { save({ strategy: { a: 'astar', b: 'bfs', d: 'dijkstra', s: 'adaptive', h: 'hamiltonian' }[k] }); syncControls(); updateAI(); }
      else if (k === 'v') { save({ showPath: !S.showPath }); syncControls(); dirty = true; }
      else if (k === 'n') { save({ sound: !S.sound }); syncControls(); }
      else if (k === '+' || k === '=') { save({ speed: Math.min(2, +(S.speed + .1).toFixed(1)) }); syncControls(); updateHud(); }
      else if (k === '-') { save({ speed: Math.max(.5, +(S.speed - .1).toFixed(1)) }); syncControls(); updateHud(); }
    });
    // swipe: pointer events cover touch + mouse; #board-wrap has touch-action:none so the page never scrolls here
    let ox = 0, oy = 0, down = false;
    wrap.addEventListener('pointerdown', e => { if (e.target.closest('.overlay')) return; down = true; ox = e.clientX; oy = e.clientY; try { wrap.setPointerCapture(e.pointerId); } catch (x) { /* ignore */ } });
    wrap.addEventListener('pointermove', e => {
      if (!down) return; const dx = e.clientX - ox, dy = e.clientY - oy, min = Math.max(18, cell * .8);
      if (Math.abs(dx) < min && Math.abs(dy) < min) return;
      turn(Math.abs(dx) > Math.abs(dy) ? (dx > 0 ? 'right' : 'left') : (dy > 0 ? 'down' : 'up')); ox = e.clientX; oy = e.clientY;
    });
    const up = () => { down = false; }; wrap.addEventListener('pointerup', up); wrap.addEventListener('pointercancel', up);
    wrap.addEventListener('contextmenu', e => e.preventDefault());
    document.addEventListener('visibilitychange', () => { if (document.hidden && phase === 'running') pause(); });
    let rt; const rl = () => { clearTimeout(rt); rt = setTimeout(layout, 100); };
    window.addEventListener('resize', rl); window.addEventListener('orientationchange', rl); window.addEventListener('arena:theme', () => { dirty = true; });
    if ('ResizeObserver' in window) new ResizeObserver(rl).observe(wrap);
  }
  syncControls(); bind(); newGame(); requestAnimationFrame(frame);
  window.ArenaGame = { get state() { return state; }, get phase() { return phase; }, turn, start, pause, newGame };   // handy for debugging/tests
})();
