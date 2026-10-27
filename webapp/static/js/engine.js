/* Arena.Engine - Snake rules for the browser. Mirrors snake_core/engine.py (cells are ints: y*w+x). */
(function (root) {
  'use strict';
  const DIRS = { up: [0, -1], down: [0, 1], left: [-1, 0], right: [1, 0] };
  const DIR_NAMES = ['up', 'down', 'left', 'right'];
  const OPPOSITE = { up: 'down', down: 'up', left: 'right', right: 'left' };
  const DIFFICULTIES = {
    classic: { base: 8, step: 0, max: 8, obst: 0, extras: false },
    easy: { base: 6, step: 0.10, max: 12, obst: 0, extras: true },
    normal: { base: 8, step: 0.15, max: 16, obst: 0.015, extras: true },
    hard: { base: 10, step: 0.25, max: 20, obst: 0.03, extras: true },
    insane: { base: 12, step: 0.30, max: 24, obst: 0.05, extras: true },
  };
  const BOARDS = { small: [16, 10], classic: [25, 12], large: [30, 16] };
  const POWERUPS = ['slow', 'double', 'shrink'];

  function mulberry32(a) {
    return function () {
      a |= 0; a = (a + 0x6D2B79F5) | 0;
      let t = Math.imul(a ^ (a >>> 15), 1 | a);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }

  class Grid {
    constructor(w, h, wrap) {
      if (!Number.isInteger(w) || !Number.isInteger(h) || w < 2 || h < 2) throw new Error('bad grid');
      this.w = w; this.h = h; this.wrap = !!wrap; this.size = w * h;
    }
    x(c) { return c % this.w; }
    y(c) { return Math.floor(c / this.w); }
    id(x, y) { return y * this.w + x; }
    inBounds(c) { return Number.isInteger(c) && c >= 0 && c < this.size; }
    step(c, d) {
      let x = this.x(c) + DIRS[d][0], y = this.y(c) + DIRS[d][1];
      if (this.wrap) { x = (x + this.w) % this.w; y = (y + this.h) % this.h; }
      else if (x < 0 || x >= this.w || y < 0 || y >= this.h) return -1;
      return y * this.w + x;
    }
    neighbors(c) {
      const out = [];
      for (const d of DIR_NAMES) { const n = this.step(c, d); if (n >= 0 && n !== c && !out.includes(n)) out.push(n); }
      return out;
    }
    distance(a, b) {
      let dx = Math.abs(this.x(a) - this.x(b)), dy = Math.abs(this.y(a) - this.y(b));
      if (this.wrap) { dx = Math.min(dx, this.w - dx); dy = Math.min(dy, this.h - dy); }
      return dx + dy;
    }
  }

  class GameState {
    constructor(cfg) {
      const c = Object.assign({ w: 25, h: 12, wrap: false, difficulty: 'normal', obstacles: true, powerups: true, seed: null, stallLimit: null }, cfg);
      if (!(c.w >= 5 && c.w <= 60 && c.h >= 5 && c.h <= 60)) throw new Error('board must be 5..60');
      if (!DIFFICULTIES[c.difficulty]) throw new Error('unknown difficulty');
      this.cfg = c;
      this.rand = mulberry32(c.seed == null ? (Math.random() * 2 ** 32) >>> 0 : c.seed);
      this.grid = new Grid(c.w, c.h, c.wrap);
      this.diff = DIFFICULTIES[c.difficulty];
      const start = this.grid.id(Math.min(2, c.w - 1), Math.min(2, c.h - 1));
      this.snake = [start];
      this.direction = 'down';
      this.queue = [];
      this.obstacles = new Set();
      this._placeObstacles(start);
      this.apple = this.bonus = this.powerup = null;
      this.effects = { double: 0, slow: 0 };
      this.score = this.apples = this.steps = this.sinceApple = 0;
      this.alive = true; this.outcome = null; this.events = [];
      this._spawnApple();
    }
    _randInt(n) { return Math.floor(this.rand() * n); }
    _placeObstacles(start) {
      if (!this.cfg.obstacles || this.diff.obst <= 0) return;
      const g = this.grid, count = Math.round(g.size * this.diff.obst);
      const cand = [];
      for (let c = 0; c < g.size; c++) if (g.distance(c, start) > 3) cand.push(c);
      for (let i = cand.length - 1; i > 0; i--) { const j = this._randInt(i + 1); [cand[i], cand[j]] = [cand[j], cand[i]]; }
      for (const cell of cand) {
        if (this.obstacles.size >= count) break;
        this.obstacles.add(cell);
        if (Arena.AI.reachableArea(g, start, this.obstacles) !== g.size - this.obstacles.size) this.obstacles.delete(cell);
      }
    }
    freeCells() {
      const used = new Set(this.snake);
      this.obstacles.forEach(c => used.add(c));
      [this.apple, this.bonus, this.powerup].forEach(i => { if (i) used.add(i.pos); });
      const out = [];
      for (let c = 0; c < this.grid.size; c++) if (!used.has(c)) out.push(c);
      return out;
    }
    _spawnApple() {
      const free = this.freeCells();
      if (!free.length) { this.apple = null; return false; }
      this.apple = { pos: free[this._randInt(free.length)], kind: 'normal' };
      return true;
    }
    _spawnItem(kind, ttl) {
      const free = this.freeCells();
      return free.length ? { pos: free[this._randInt(free.length)], kind, ttl } : null;
    }
    setDirection(d) {
      if (!OPPOSITE[d] || this.queue.length >= 2) return false;
      const last = this.queue.length ? this.queue[this.queue.length - 1] : this.direction;
      if (d === last || (d === OPPOSITE[last] && this.snake.length > 1)) return false;
      this.queue.push(d);
      return true;
    }
    get speed() {
      const s = Math.min(this.diff.max, this.diff.base + this.diff.step * this.apples);
      return s * (this.effects.slow > 0 ? 0.6 : 1);
    }
    get multiplier() { return this.effects.double > 0 ? 2 : 1; }
    situation() {
      return { grid: this.grid, snake: this.snake.slice(), obstacles: this.obstacles,
        apple: this.apple ? this.apple.pos : -1, extraGrowth: this.bonus ? new Set([this.bonus.pos]) : new Set() };
    }
    _die(why) { this.alive = false; this.outcome = why; this.events.push('died'); return this.events; }
    step() {
      this.events = [];
      if (!this.alive) return this.events;
      if (this.queue.length) this.direction = this.queue.shift();
      this.steps++; this.sinceApple++;
      const target = this.grid.step(this.snake[0], this.direction);
      if (target < 0) return this._die('wall');
      if (this.obstacles.has(target)) return this._die('obstacle');
      const eatsApple = !!this.apple && target === this.apple.pos;
      const eatsBonus = !!this.bonus && target === this.bonus.pos;
      const grows = eatsApple || eatsBonus;
      const occupied = grows ? this.snake : this.snake.slice(0, -1);
      if (occupied.includes(target)) return this._die('self');
      this.snake.unshift(target);
      if (!grows) this.snake.pop();
      if (eatsApple) {
        this._gain(1); this.sinceApple = 0; this.events.push('apple');
        if (!this._spawnApple()) { this.alive = false; this.outcome = 'won'; this.events.push('won'); return this.events; }
      } else if (eatsBonus) {
        this._gain(3); this.bonus = null; this.events.push('bonus');
      } else if (this.powerup && target === this.powerup.pos) {
        this._applyPowerup(this.powerup.kind); this.powerup = null; this.events.push('powerup');
      }
      for (const k of ['double', 'slow']) if (this.effects[k] > 0) this.effects[k]--;
      for (const n of ['bonus', 'powerup']) if (this[n] && --this[n].ttl <= 0) this[n] = null;
      if (this.diff.extras && this.cfg.powerups) {
        if (!this.bonus && this.rand() < 0.02) this.bonus = this._spawnItem('golden', 40);
        if (!this.powerup && this.rand() < 0.012) this.powerup = this._spawnItem(POWERUPS[this._randInt(3)], 60);
      }
      if (this.cfg.stallLimit && this.sinceApple > this.cfg.stallLimit) { this.alive = false; this.outcome = 'stalled'; this.events.push('died'); }
      return this.events;
    }
    _gain(p) { this.score += p * this.multiplier; this.apples++; }
    _applyPowerup(kind) {
      if (kind === 'shrink') { for (let i = 0; i < Math.min(3, this.snake.length - 1); i++) this.snake.pop(); }
      else this.effects[kind] = 60;
    }
  }

  const api = { Grid, GameState, DIRS, DIR_NAMES, OPPOSITE, DIFFICULTIES, BOARDS, mulberry32 };
  root.Arena = root.Arena || {};
  Object.assign(root.Arena, { Grid, GameState, DIRS, DIR_NAMES, OPPOSITE, DIFFICULTIES, BOARDS });
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
})(typeof window !== 'undefined' ? window : globalThis);
