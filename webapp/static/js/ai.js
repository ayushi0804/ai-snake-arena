/* Arena.AI - pathfinding, safety validation and move selection. Mirrors snake_core/*.py. */
(function (root) {
  'use strict';
  const E = (typeof require !== 'undefined' && typeof module !== 'undefined') ? require('./engine.js') : root.Arena;
  const { DIR_NAMES } = E;
  const now = () => (typeof performance !== 'undefined' ? performance.now() : Date.now());

  class Heap {
    constructor() { this.a = []; }
    get size() { return this.a.length; }
    push(item) {
      const a = this.a; a.push(item); let i = a.length - 1;
      while (i > 0) { const p = (i - 1) >> 1; if (this._lt(a[i], a[p])) { [a[i], a[p]] = [a[p], a[i]]; i = p; } else break; }
    }
    pop() {
      const a = this.a, top = a[0], last = a.pop();
      if (a.length) {
        a[0] = last; let i = 0;
        for (;;) {
          const l = 2 * i + 1, r = l + 1; let m = i;
          if (l < a.length && this._lt(a[l], a[m])) m = l;
          if (r < a.length && this._lt(a[r], a[m])) m = r;
          if (m === i) break; [a[i], a[m]] = [a[m], a[i]]; i = m;
        }
      }
      return top;
    }
    _lt(x, y) { return x[0] < y[0] || (x[0] === y[0] && x[1] < y[1]); }
  }

  function finish(name, t0, found, came, start, goal, explored, cost, reason) {
    const path = [];
    if (found) { let c = goal; while (c !== start) { path.push(c); c = came.get(c); } path.reverse(); }
    return { algorithm: name, found, path, explored, cost: cost == null ? path.length : cost, timeMs: now() - t0,
      reason: reason || (found ? 'ok' : 'unreachable') };
  }
  function precheck(grid, start, goal, blocked) {
    if (!grid.inBounds(start)) return 'invalid_start';
    if (!grid.inBounds(goal)) return 'invalid_goal';
    if (blocked.has(goal)) return 'goal_blocked';
    return null;
  }

  function bfs(grid, start, goal, blocked = new Set()) {
    const t0 = now(), err = precheck(grid, start, goal, blocked);
    if (err) return finish('bfs', t0, false, new Map(), start, goal, 0, 0, err);
    const came = new Map(), seen = new Set([start]), q = [start]; let head = 0, explored = 0;
    while (head < q.length) {
      const cur = q[head++]; explored++;
      if (cur === goal) return finish('bfs', t0, true, came, start, goal, explored);
      for (const n of grid.neighbors(cur)) if (!seen.has(n) && !blocked.has(n)) { seen.add(n); came.set(n, cur); q.push(n); }
    }
    return finish('bfs', t0, false, came, start, goal, explored);
  }

  function weighted(name, grid, start, goal, blocked, costs, useH) {
    const t0 = now(), err = precheck(grid, start, goal, blocked);
    if (err) return finish(name, t0, false, new Map(), start, goal, 0, 0, err);
    let minCost = 1;
    if (costs) for (const v of costs.values()) { if (!(v > 0)) throw new Error('costs must be > 0'); minCost = Math.min(minCost, v); }
    const h = useH ? (c => grid.distance(c, goal) * minCost) : (() => 0);
    const g = new Map([[start, 0]]), came = new Map(), closed = new Set(), heap = new Heap(); let tie = 0, explored = 0;
    heap.push([h(start), tie++, start]);
    while (heap.size) {
      const cur = heap.pop()[2];
      if (closed.has(cur)) continue;
      closed.add(cur); explored++;
      if (cur === goal) return finish(name, t0, true, came, start, goal, explored, g.get(cur));
      for (const n of grid.neighbors(cur)) {
        if (blocked.has(n) || closed.has(n)) continue;
        const ng = g.get(cur) + ((costs && costs.get(n)) || 1);
        if (!g.has(n) || ng < g.get(n)) { g.set(n, ng); came.set(n, cur); heap.push([ng + h(n), tie++, n]); }
      }
    }
    return finish(name, t0, false, came, start, goal, explored);
  }
  const astar = (g, s, t, b = new Set(), c) => weighted('astar', g, s, t, b, c, true);
  const dijkstra = (g, s, t, b = new Set(), c) => weighted('dijkstra', g, s, t, b, c, false);
  const ALGORITHMS = { astar, bfs, dijkstra };

  function distancesFrom(grid, start, blocked) {
    const dist = new Map([[start, 0]]), q = [start]; let head = 0;
    while (head < q.length) {
      const cur = q[head++];
      for (const n of grid.neighbors(cur)) if (!dist.has(n) && !blocked.has(n)) { dist.set(n, dist.get(cur) + 1); q.push(n); }
    }
    return dist;
  }
  const reachableArea = (grid, start, blocked) => distancesFrom(grid, start, blocked).size;

  // ---- safety ----
  const grows = (sit, cell) => cell === sit.apple || (sit.extraGrowth && sit.extraGrowth.has(cell));
  function planningBlocked(sit) {
    const b = new Set(sit.snake.slice(0, -1)); sit.obstacles.forEach(c => b.add(c)); return b;
  }
  function tailReachable(grid, snake, obstacles) {
    if (snake.length <= 1) return true;
    const blocked = new Set(snake.slice(1)); obstacles.forEach(c => blocked.add(c));
    const dist = distancesFrom(grid, snake[0], blocked);
    return grid.neighbors(snake[snake.length - 1]).some(n => dist.has(n));
  }
  function evaluateMove(sit, direction) {
    const { grid, snake } = sit, cell = grid.step(snake[0], direction);
    const info = { direction, cell, legal: false, grows: false, area: 0, tailReachable: false, deadEnd: false };
    if (cell < 0 || sit.obstacles.has(cell)) return info;
    info.grows = grows(sit, cell);
    if (snake.length > 1 && cell === snake[1]) return info;            // reversal never allowed
    const bodyAfter = info.grows ? snake : snake.slice(0, -1);       // moving tail
    if (bodyAfter.includes(cell)) return info;
    const newSnake = [cell].concat(bodyAfter);
    const blocked = new Set(newSnake.slice(1)); sit.obstacles.forEach(c => blocked.add(c));
    const dist = distancesFrom(grid, cell, blocked);
    info.legal = true; info.area = dist.size;
    info.tailReachable = newSnake.length <= 1 || grid.neighbors(newSnake[newSnake.length - 1]).some(n => dist.has(n));
    info.deadEnd = !info.tailReachable && info.area < newSnake.length;
    return info;
  }
  const evaluateMoves = sit => DIR_NAMES.map(d => evaluateMove(sit, d));
  function simulatePath(sit, path) {
    let snake = sit.snake.slice();
    for (const cell of path) {
      const g = grows(sit, cell), occ = g ? snake : snake.slice(0, -1);
      if (sit.obstacles.has(cell) || occ.includes(cell)) return { snake, survived: false };
      snake = [cell].concat(g ? snake : snake.slice(0, -1));
    }
    return { snake, survived: true };
  }

  // ---- Hamiltonian cycle ----
  function cycleEvenHeight(w, h) {
    const cyc = [[0, 0]];
    for (let y = 0; y < h; y++) {
      if (y % 2 === 0) for (let x = 1; x < w; x++) cyc.push([x, y]);
      else for (let x = w - 1; x >= 1; x--) cyc.push([x, y]);
    }
    for (let y = h - 1; y >= 1; y--) cyc.push([0, y]);
    return cyc;
  }
  function buildCycle(w, h) {
    if (w < 2 || h < 2 || (w % 2 === 1 && h % 2 === 1)) return null;
    return h % 2 === 0 ? cycleEvenHeight(w, h) : cycleEvenHeight(h, w).map(([x, y]) => [y, x]);
  }
  function isValidCycle(cyc, w, h) {
    if (!cyc || cyc.length !== w * h || new Set(cyc.map(c => c[1] * w + c[0])).size !== w * h) return false;
    return cyc.every((a, i) => { const b = cyc[(i + 1) % cyc.length]; return a[0] >= 0 && a[0] < w && a[1] >= 0 && a[1] < h && Math.abs(a[0] - b[0]) + Math.abs(a[1] - b[1]) === 1; });
  }
  const cycleCache = new Map();
  function getCycle(w, h) {
    const k = w + 'x' + h;
    if (!cycleCache.has(k)) {
      const c = buildCycle(w, h);
      cycleCache.set(k, c && isValidCycle(c, w, h) ? { cells: c.map(([x, y]) => y * w + x), idx: new Map(c.map(([x, y], i) => [y * w + x, i])) } : null);
    }
    return cycleCache.get(k);
  }

  const STRATEGIES = ['astar', 'bfs', 'dijkstra', 'adaptive', 'hamiltonian'];
  function bestByArea(legal) {
    return legal.reduce((a, b) => {
      const ka = [!a.deadEnd, a.tailReachable, a.area], kb = [!b.deadEnd, b.tailReachable, b.area];
      for (let i = 0; i < 3; i++) { if (kb[i] > ka[i]) return b; if (kb[i] < ka[i]) return a; }
      return a;
    });
  }
  function chooseMove(sit, strategy = 'adaptive', base = 'astar') {
    if (!STRATEGIES.includes(strategy)) throw new Error('unknown strategy');
    const t0 = now(), moves = evaluateMoves(sit), legal = moves.filter(m => m.legal);
    const algo = strategy === 'adaptive' ? base : (ALGORITHMS[strategy] ? strategy : 'astar');
    const dec = { direction: null, strategy, algorithm: algo, found: false, path: [], explored: 0, pathLength: 0, timeMs: 0, safe: false, reason: '', moves };
    const done = (m, reason, safe) => { dec.direction = m ? m.direction : null; dec.reason = reason; dec.safe = safe; dec.timeMs = now() - t0; return dec; };
    if (sit.apple < 0 || !legal.length) return done(null, legal.length ? 'no_target' : 'no_legal_move', false);
    let prefix = '';
    if (strategy === 'hamiltonian') {
      const cyc = sit.obstacles.size ? null : getCycle(sit.grid.w, sit.grid.h);
      if (cyc) {
        const n = cyc.cells.length, h = cyc.idx.get(sit.snake[0]);
        const appleD = (cyc.idx.get(sit.apple) - h + n) % n;
        const tailD = sit.snake.length === 1 ? n : (cyc.idx.get(sit.snake[sit.snake.length - 1]) - h + n) % n;
        let best = null, bestD = 0;
        for (const m of legal) {
          const d = (cyc.idx.get(m.cell) - h + n) % n;
          if ((d === 1 || (d > 1 && d <= appleD && d <= tailD - 1)) && d > bestD) { best = m; bestD = d; }
        }
        if (best) return done(best, 'hamiltonian_cycle', true);
      }
      prefix = 'hamiltonian_unavailable;';
    }
    const res = ALGORITHMS[algo](sit.grid, sit.snake[0], sit.apple, planningBlocked(sit));
    Object.assign(dec, { found: res.found, path: res.path, explored: res.explored, pathLength: res.path.length });
    const byCell = new Map(legal.map(m => [m.cell, m]));
    if (strategy === 'astar' || strategy === 'bfs' || strategy === 'dijkstra') {
      if (res.found && byCell.has(res.path[0])) { const m = byCell.get(res.path[0]); return done(m, 'raw_path', !m.deadEnd); }
      return done(bestByArea(legal), 'recovery_max_area', false);
    }
    if (res.found && byCell.has(res.path[0])) {
      const sim = simulatePath(sit, res.path);
      if (sim.survived && tailReachable(sit.grid, sim.snake, sit.obstacles)) return done(byCell.get(res.path[0]), prefix + 'safe_path', true);
    }
    const tail = sit.snake[sit.snake.length - 1];
    const safe = legal.filter(m => m.tailReachable && !m.deadEnd);
    if (safe.length) {
      const m = safe.reduce((a, b) => {
        const da = sit.grid.distance(a.cell, tail), db = sit.grid.distance(b.cell, tail);
        return db > da || (db === da && b.area > a.area) ? b : a;
      });
      return done(m, prefix + 'recovery_follow_tail', true);
    }
    return done(bestByArea(legal), prefix + 'recovery_max_area', false);
  }

  const api = { bfs, astar, dijkstra, ALGORITHMS, STRATEGIES, distancesFrom, reachableArea, evaluateMoves, simulatePath,
    tailReachable, planningBlocked, buildCycle, isValidCycle, getCycle, chooseMove };
  root.Arena = root.Arena || {};
  root.Arena.AI = api;
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
})(typeof window !== 'undefined' ? window : globalThis);
