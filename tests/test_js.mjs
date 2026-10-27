// Run: node --test tests/test_js.mjs   (uses the same vectors as the Python tests)
import test from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import fs from 'node:fs';
const require = createRequire(import.meta.url);
const root = new URL('../webapp/static/js/', import.meta.url).pathname;
const E = require(root + 'engine.js');
globalThis.Arena = globalThis.Arena || {}; globalThis.Arena.AI = require(root + 'ai.js');
const AI = globalThis.Arena.AI;
const vectors = JSON.parse(fs.readFileSync(new URL('./vectors/pathfinding.json', import.meta.url)));

test('shared pathfinding vectors', () => {
  for (const v of vectors) {
    const g = new E.Grid(v.w, v.h, v.wrap), id = ([x, y]) => g.id(x, y), blocked = new Set(v.blocked.map(id));
    for (const [name, fn] of Object.entries(AI.ALGORITHMS)) {
      const r = fn(g, id(v.start), id(v.goal), blocked);
      if (v.length === null) { assert.equal(r.found, false, `${v.name}/${name}`); assert.deepEqual(r.path, []); }
      else { assert.equal(r.found, true, `${v.name}/${name}`); assert.equal(r.path.length, v.length, `${v.name}/${name}`); }
    }
  }
});
test('invalid positions', () => {
  const g = new E.Grid(5, 5);
  assert.equal(AI.astar(g, -1, 3).reason, 'invalid_start');
  assert.equal(AI.bfs(g, 0, 99).reason, 'invalid_goal');
  assert.equal(AI.dijkstra(g, 0, 12, new Set([12])).reason, 'goal_blocked');
});
test('hamiltonian cycles valid, serpentine/odd rejected', () => {
  for (const [w, h] of [[2, 2], [5, 4], [4, 5], [25, 12], [30, 16]]) assert.ok(AI.isValidCycle(AI.buildCycle(w, h), w, h));
  assert.equal(AI.buildCycle(5, 5), null);
});
function play(strategy, seed, w = 8, h = 6, diff = 'classic', limit = 1200) {
  const s = new E.GameState({ w, h, difficulty: diff, seed, stallLimit: limit });
  while (s.alive && s.steps < 3000) { const d = AI.chooseMove(s.situation(), strategy); if (d.direction) s.setDirection(d.direction); s.step(); }
  return s;
}
test('hamiltonian strategy wins; adaptive does not die on open board', () => {
  for (let seed = 0; seed < 4; seed++) assert.equal(play('hamiltonian', seed).outcome, 'won');
  for (let seed = 0; seed < 5; seed++) { const s = play('adaptive', seed, 12, 8, 'normal', 600); assert.ok([null, 'won', 'stalled'].includes(s.outcome), `seed ${seed}: ${s.outcome}`); }
});
test('engine rules: reversal, tail move, growth, wall, apple spawn', () => {
  const s = new E.GameState({ w: 10, h: 8, difficulty: 'classic', seed: 1 });
  s.apple.pos = s.grid.id(2, 3); s.step();
  assert.deepEqual([s.score, s.apples, s.snake.length], [1, 1, 2]);
  assert.ok(!s.snake.includes(s.apple.pos));
  s.direction = 'right'; s.queue = [];
  assert.equal(s.setDirection('left'), false); assert.equal(s.setDirection('right'), false);
  assert.equal(s.setDirection('up'), true); assert.equal(s.setDirection('down'), false);
  const t = new E.GameState({ w: 10, h: 8, difficulty: 'classic', seed: 1 });
  t.snake = [t.grid.id(2, 2), t.grid.id(3, 2), t.grid.id(3, 3), t.grid.id(2, 3)]; t.direction = 'down'; t.apple.pos = t.grid.id(8, 6);
  t.step(); assert.ok(t.alive, 'entering the moving tail is legal');
  const w = new E.GameState({ w: 10, h: 8, difficulty: 'classic', seed: 1 });
  w.snake = [w.grid.id(0, 0)]; w.direction = 'up'; w.step(); assert.equal(w.outcome, 'wall');
  const wr = new E.GameState({ w: 10, h: 8, difficulty: 'classic', seed: 1, wrap: true });
  wr.snake = [wr.grid.id(0, 3)]; wr.direction = 'left'; wr.apple.pos = wr.grid.id(5, 5); wr.step();
  assert.equal(wr.snake[0], wr.grid.id(9, 3));
});
test('obstacles keep board connected', () => {
  for (let seed = 0; seed < 10; seed++) {
    const s = new E.GameState({ w: 20, h: 12, difficulty: 'insane', seed });
    assert.ok(s.obstacles.size > 0);
    assert.equal(AI.reachableArea(s.grid, s.snake[0], s.obstacles), 240 - s.obstacles.size);
  }
});
