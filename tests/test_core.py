import json, pathlib, unittest
from snake_core import GameConfig, GameState, choose_move, STRATEGIES, Grid
from snake_core.pathfinding import astar, bfs, dijkstra, reachable_area
from snake_core.safety import Situation, evaluate_moves, simulate_path, tail_reachable
from snake_core.hamilton import build_cycle, is_valid_cycle

VECTORS = json.loads((pathlib.Path(__file__).parent / "vectors" / "pathfinding.json").read_text())
ALGOS = {"astar": astar, "bfs": bfs, "dijkstra": dijkstra}


def mk(cfg=None, **kw):
    base = dict(width=10, height=8, difficulty="classic", seed=1)
    base.update(kw)
    return GameState(GameConfig(**base))


class PathfindingTests(unittest.TestCase):
    def test_vectors_all_algorithms(self):
        for v in VECTORS:
            g = Grid(v["w"], v["h"], v["wrap"])
            blocked = {tuple(b) for b in v["blocked"]}
            for name, fn in ALGOS.items():
                r = fn(g, tuple(v["start"]), tuple(v["goal"]), blocked)
                with self.subTest(v["name"], algo=name):
                    if v["length"] is None:
                        self.assertFalse(r.found)
                        self.assertEqual(r.path, [])
                        self.assertEqual(r.reason, "unreachable")
                    else:
                        self.assertTrue(r.found)
                        self.assertEqual(r.length, v["length"])

    def test_path_reconstruction_is_contiguous(self):
        g = Grid(7, 7)
        for fn in ALGOS.values():
            r = fn(g, (0, 0), (6, 5), {(3, y) for y in range(6)})
            cells = [(0, 0)] + r.path
            self.assertEqual(cells[-1], (6, 5))
            self.assertTrue(all(g.distance(a, b) == 1 for a, b in zip(cells, cells[1:])))
            self.assertFalse(set(r.path) & {(3, y) for y in range(6)})

    def test_invalid_positions(self):
        g = Grid(5, 5)
        self.assertEqual(astar(g, (-1, 0), (2, 2)).reason, "invalid_start")
        self.assertEqual(bfs(g, (0, 0), (9, 9)).reason, "invalid_goal")
        self.assertEqual(dijkstra(g, (0, 0), (2, 2), {(2, 2)}).reason, "goal_blocked")

    def test_weighted_dijkstra_and_astar_agree_and_avoid_expensive(self):
        g = Grid(5, 3)
        costs = {(x, 1): 50.0 for x in range(1, 4)}   # expensive middle row
        d = dijkstra(g, (0, 1), (4, 1), costs=costs)
        a = astar(g, (0, 1), (4, 1), costs=costs)
        self.assertAlmostEqual(d.cost, a.cost)
        self.assertLess(d.cost, 50)
        with self.assertRaises(ValueError):
            astar(g, (0, 0), (1, 1), costs={(1, 0): 0})

    def test_astar_explores_no_more_than_dijkstra_open_grid(self):
        g = Grid(30, 30)
        self.assertLessEqual(astar(g, (0, 0), (25, 25)).explored, dijkstra(g, (0, 0), (25, 25)).explored)

    def test_bfs_equals_dijkstra_length_unweighted(self):
        import random
        rng = random.Random(3)
        g = Grid(12, 12)
        for _ in range(30):
            blocked = {(rng.randrange(12), rng.randrange(12)) for _ in range(30)} - {(0, 0), (11, 11)}
            self.assertEqual(bfs(g, (0, 0), (11, 11), blocked).length, dijkstra(g, (0, 0), (11, 11), blocked).length)
            self.assertEqual(astar(g, (0, 0), (11, 11), blocked).found, bfs(g, (0, 0), (11, 11), blocked).found)


class EngineTests(unittest.TestCase):
    def test_wall_collision(self):
        s = mk()
        s.snake[0] = (0, 0)
        s.set_direction("right"); s.step(); s.direction = "up"
        s.step()
        self.assertEqual(s.outcome, "wall")
        self.assertFalse(s.alive)

    def test_wrap_mode_passes_through_edges(self):
        s = mk(wrap=True)
        s.snake[0] = (0, 3); s.direction = "left"
        s.apple.pos = (5, 5)
        s.step()
        self.assertTrue(s.alive)
        self.assertEqual(s.snake[0], (9, 3))

    def test_reverse_and_repeat_rejected_rapid_input_bounded(self):
        s = mk()
        s.step(); s.set_direction("right"); s.step(); s.set_direction("right")  # len 1: reversal allowed
        s.apple.pos = (9, 7)
        s.snake.extend([(0, 0), (0, 1)])
        s.direction = "right"; s._queue.clear()
        self.assertFalse(s.set_direction("left"))
        self.assertFalse(s.set_direction("right"))
        self.assertTrue(s.set_direction("up"))
        self.assertFalse(s.set_direction("down"))      # opposite of queued 'up'
        self.assertTrue(s.set_direction("left"))
        self.assertFalse(s.set_direction("down"))      # queue capped at 2

    def test_tail_cell_is_enterable_when_not_growing(self):
        s = mk()
        s.snake.clear(); s.snake.extend([(2, 2), (3, 2), (3, 3), (2, 3)])   # head left of tail? ring
        s.direction = "down"; s._queue.clear(); s.apple.pos = (8, 6)
        s.step()                                   # head moves into the tail cell (2,3)
        self.assertTrue(s.alive)
        self.assertEqual(s.snake[0], (2, 3))

    def test_self_collision(self):
        s = mk()
        s.snake.clear(); s.snake.extend([(2, 2), (3, 2), (3, 3), (2, 3), (1, 3), (1, 2)])
        s.direction = "left"; s._queue.clear(); s.apple.pos = (8, 6)
        s.step()    # (1,2) is a body segment that is not the tail... actually it is tail -> legal
        s2 = mk()
        s2.snake.clear(); s2.snake.extend([(2, 2), (3, 2), (3, 3), (2, 3), (1, 3), (1, 2), (1, 1)])
        s2.direction = "left"; s2._queue.clear(); s2.apple.pos = (8, 6)
        s2.step()
        self.assertEqual(s2.outcome, "self")

    def test_growth_and_scoring(self):
        s = mk()
        s.apple.pos = (2, 3)
        s.step()
        self.assertEqual((s.score, s.apples, len(s.snake)), (1, 1, 2))
        self.assertNotIn(s.apple.pos, s.snake)

    def test_double_multiplier_and_speed_increase(self):
        s = mk(difficulty="normal", obstacles=False, powerups=False)
        s.effects["double"] = 10
        s.apple.pos = (2, 3)
        s.step()
        self.assertEqual(s.score, 2)
        s.apples = 20
        self.assertGreater(s.speed, 8.0)
        s.effects["slow"] = 5
        self.assertLess(s.speed, 8.0 + 0.15 * 20)

    def test_apple_never_spawns_on_snake_or_obstacle(self):
        for seed in range(40):
            s = mk(difficulty="insane", seed=seed, width=12, height=8)
            for _ in range(60):
                self.assertNotIn(s.apple.pos, s.snake)
                self.assertNotIn(s.apple.pos, s.obstacles)
                s._spawn_apple()

    def test_obstacles_keep_board_connected_and_start_clear(self):
        for seed in range(15):
            s = mk(difficulty="insane", seed=seed, width=20, height=12)
            self.assertGreater(len(s.obstacles), 0)
            self.assertEqual(reachable_area(s.grid, s.snake[0], s.obstacles), 240 - len(s.obstacles))

    def test_seed_determinism_and_reset_independence(self):
        a, b = mk(seed=5), mk(seed=5)
        self.assertEqual((a.apple.pos, a.obstacles), (b.apple.pos, b.obstacles))
        a.apple.pos = (2, 3); a.step()
        c = mk(seed=5)
        self.assertEqual((c.score, len(c.snake), c.alive), (0, 1, True))

    def test_win_when_board_full(self):
        s = GameState(GameConfig(width=5, height=5, difficulty="classic", seed=1))
        cells = build_cycle(5, 4)    # fill all but last cell artificially
        s.snake.clear(); order = [(x, y) for y in range(5) for x in range(5)]
        free = order[-1]; s.snake.extend(reversed(order[:-1]))   # head = order[-2]
        s.apple.pos = free
        head = s.snake[0]
        s.direction = s.grid.direction_between(head, free)
        s.step()
        self.assertEqual(s.outcome, "won")

    def test_stall_limit_terminates(self):
        s = mk(stall_limit=3)
        s.direction = "right"
        for _ in range(4):
            s.apple.pos = (9, 7); s.step()
        self.assertEqual(s.outcome, "stalled")


class SafetyAndAITests(unittest.TestCase):
    def test_hamiltonian_cycle_validity(self):
        for w, h in [(2, 2), (5, 4), (4, 5), (25, 12), (30, 16), (6, 9)]:
            self.assertTrue(is_valid_cycle(build_cycle(w, h), w, h), (w, h))
        self.assertIsNone(build_cycle(5, 5))
        self.assertIsNone(build_cycle(1, 4))
        serp = [(x if y % 2 == 0 else 4 - x, y) for y in range(4) for x in range(5)]
        self.assertFalse(is_valid_cycle(serp, 5, 4))    # plain serpentine is not a cycle

    def test_moving_tail_makes_move_legal_and_growth_blocks_it(self):
        g = Grid(6, 6)
        snake = ((2, 2), (3, 2), (3, 3), (2, 3))        # tail (2,3) is below head
        sit = Situation(g, snake, frozenset(), (5, 5))
        down = [m for m in evaluate_moves(sit) if m.direction == "down"][0]
        self.assertTrue(down.legal)
        sit2 = Situation(g, snake, frozenset(), (2, 3 + 0) if False else (5, 5), frozenset({(2, 3)}))
        down2 = [m for m in evaluate_moves(sit2) if m.direction == "down"][0]
        self.assertFalse(down2.legal)                   # a growing step keeps the tail in place

    def test_reversal_is_illegal_for_length_two(self):
        g = Grid(6, 6)
        sit = Situation(g, ((3, 3), (2, 3)), frozenset(), (5, 5))
        left = [m for m in evaluate_moves(sit) if m.direction == "left"][0]
        self.assertFalse(left.legal)

    def test_dead_end_detected(self):
        g = Grid(5, 5)
        # snake coils so entering the pocket at (0,0) traps it
        snake = ((0, 1), (1, 1), (1, 0), (2, 0), (2, 1), (2, 2), (1, 2), (0, 2), (0, 3), (1, 3), (2, 3), (3, 3), (3, 2), (3, 1), (3, 0), (4, 0), (4, 1), (4, 2), (4, 3), (4, 4))
        sit = Situation(g, snake, frozenset(), (0, 4))
        up = [m for m in evaluate_moves(sit) if m.direction == "up"][0]
        self.assertTrue(up.legal)
        self.assertTrue(up.dead_end)

    def test_simulate_path_detects_self_trap(self):
        g = Grid(5, 5)
        sit = Situation(g, ((2, 2), (2, 3)), frozenset({(2, 1)}), (4, 4))
        _, ok = simulate_path(sit, [(2, 1)])
        self.assertFalse(ok)

    def test_unreachable_apple_does_not_crash_or_loop(self):
        g = Grid(6, 6)
        wall = frozenset((x, 3) for x in range(6))
        sit = Situation(g, ((0, 0),), wall, (3, 5))
        for strat in STRATEGIES:
            d = choose_move(sit, strat)
            self.assertIsNotNone(d.direction)
            self.assertFalse(d.found if strat != "hamiltonian" else False)

    def test_no_legal_move_returns_none(self):
        g = Grid(5, 5)
        sit = Situation(g, ((0, 0),), frozenset({(1, 0), (0, 1)}), (4, 4))
        self.assertIsNone(choose_move(sit, "adaptive").direction)

    def test_adaptive_beats_raw_and_hamiltonian_wins(self):
        def play(strategy, seed):
            s = GameState(GameConfig(width=8, height=6, difficulty="classic", seed=seed, stall_limit=1000))
            while s.alive:
                d = choose_move(s.situation(), strategy)
                if d.direction:
                    s.set_direction(d.direction)
                s.step()
            return s
        for seed in range(4):
            self.assertEqual(play("hamiltonian", seed).outcome, "won")
        raw = sum(play("astar", sd).score for sd in range(6))
        ad = sum(play("adaptive", sd).score for sd in range(6))
        self.assertGreater(ad, raw)

    def test_adaptive_never_dies_to_wall_or_self_on_open_board(self):
        for seed in range(6):
            s = GameState(GameConfig(width=12, height=8, difficulty="normal", seed=seed, stall_limit=600))
            while s.alive and s.steps < 1500:
                d = choose_move(s.situation(), "adaptive")
                if d.direction:
                    s.set_direction(d.direction)
                s.step()
            self.assertIn(s.outcome, (None, "won", "stalled"), (seed, s.outcome))


if __name__ == "__main__":
    unittest.main()
