/* Arena.store / Arena.settings / Arena.api - local persistence, REST client, offline match outbox. */
(function (root) {
  'use strict';
  const A = root.Arena = root.Arena || {};
  const mem = {};
  A.store = {
    get(k, def) { try { const v = localStorage.getItem(k); return v == null ? (k in mem ? mem[k] : def) : JSON.parse(v); } catch (e) { return k in mem ? mem[k] : def; } },
    set(k, v) { mem[k] = v; try { localStorage.setItem(k, JSON.stringify(v)); return true; } catch (e) { return false; } },
    remove(k) { delete mem[k]; try { localStorage.removeItem(k); } catch (e) { /* ignore */ } },
  };
  const rid = () => (root.crypto && crypto.randomUUID ? crypto.randomUUID() : 'g' + Math.random().toString(36).slice(2) + Date.now().toString(36)).replace(/[^A-Za-z0-9_-]/g, '').slice(0, 40).padEnd(8, 'x');
  A.guestId = () => { let g = A.store.get('arena.guest', null); if (!g || !/^[A-Za-z0-9_-]{8,64}$/.test(g)) { g = rid(); A.store.set('arena.guest', g); } return g; };
  A.newMatchId = rid;

  const DEFAULTS = { name: '', theme: 'dark', mode: 'manual', strategy: 'adaptive', base: 'astar', difficulty: 'normal', board: 'classic',
    wrap: false, obstacles: true, powerups: true, showPath: true, sound: true, volume: 0.5, speed: 1 };
  A.settings = {
    defaults: DEFAULTS,
    get() { return Object.assign({}, DEFAULTS, A.store.get('arena.settings', {})); },
    set(patch) { const s = Object.assign(A.settings.get(), patch); A.store.set('arena.settings', s); return s; },
    reset() { A.store.set('arena.settings', {}); return A.settings.get(); },
  };

  async function request(method, path, body) {
    const ctl = new AbortController(), timer = setTimeout(() => ctl.abort(), 8000);
    try {
      const res = await fetch('/api/v1' + path, { method, signal: ctl.signal, cache: 'no-store',
        headers: Object.assign({ 'X-Guest-Id': A.guestId() }, body ? { 'Content-Type': 'application/json' } : {}),
        body: body ? JSON.stringify(body) : undefined });
      let json = null; try { json = await res.json(); } catch (e) { /* non-JSON */ }
      if (res.ok && json && json.ok) return { ok: true, status: res.status, data: json.data };
      return { ok: false, status: res.status, error: (json && json.error) || { code: 'http_' + res.status, message: 'Request failed (' + res.status + ')' } };
    } catch (e) {
      return { ok: false, network: true, status: 0, error: { code: 'network', message: navigator.onLine === false ? 'You are offline.' : 'Server unreachable.' } };
    } finally { clearTimeout(timer); }
  }
  const qs = o => { const p = new URLSearchParams(); Object.entries(o || {}).forEach(([k, v]) => { if (v !== '' && v != null) p.set(k, v); }); const s = p.toString(); return s ? '?' + s : ''; };

  const OUTBOX = 'arena.outbox';
  A.api = {
    request,
    health: () => request('GET', '/health'),
    stats: () => request('GET', '/players/me/stats'),
    history: (limit, offset) => request('GET', '/matches' + qs({ limit, offset })),
    leaderboard: p => request('GET', '/leaderboard' + qs(p)),
    algoMetrics: () => request('GET', '/metrics/algorithms'),
    benchmarks: () => request('GET', '/benchmarks'),
    runBenchmark: b => request('POST', '/benchmarks/run', b),
    getSettings: () => request('GET', '/settings'),
    putSettings: s => request('PUT', '/settings', s),
    outboxSize: () => A.store.get(OUTBOX, []).length,
    /** Save a finished match. Returns {state: saved|queued|rejected, message}. */
    async submitMatch(payload) {
      const r = await request('POST', '/matches', Object.assign({ player_name: A.settings.get().name || undefined }, payload));
      if (r.ok) return { state: 'saved', message: 'Saved to your history (client-reported).' };
      if (r.network || r.status >= 500) {
        const box = A.store.get(OUTBOX, []); box.push(payload); A.store.set(OUTBOX, box.slice(-50));
        return { state: 'queued', message: 'Offline or server unavailable: saved on this device and will upload automatically.' };
      }
      const d = r.error && r.error.details ? ' ' + JSON.stringify(r.error.details) : '';
      return { state: 'rejected', message: 'Server rejected this match: ' + r.error.message + d };
    },
    async flushOutbox() {
      let box = A.store.get(OUTBOX, []), sent = 0;
      while (box.length) {
        const r = await request('POST', '/matches', box[0]);
        if (r.network || r.status >= 500) break;
        box.shift(); sent++; A.store.set(OUTBOX, box);   // saved, duplicate (idempotent) or permanently rejected
      }
      return sent;
    },
  };
})(window);
