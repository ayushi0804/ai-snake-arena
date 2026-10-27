"""All drawing for the desktop game. No game rules here."""
from __future__ import annotations

BG, GRID, PANEL = (30, 40, 30), (60, 75, 60), (40, 40, 40)
WHITE, GREY, GOLD, CYAN, RED = (255, 255, 255), (200, 200, 200), (255, 210, 63), (124, 200, 255), (255, 80, 80)


class Renderer:
    def __init__(self, pg, screen, cell, grid_w, grid_h, panel_h):
        self.pg, self.screen, self.cell, self.gw, self.gh, self.panel_h = pg, screen, cell, grid_w, grid_h, panel_h
        self.width, self.board_h = grid_w * cell, grid_h * cell
        fam = "segoeui,calibri,arial"
        self.f_big = pg.font.SysFont(fam, 56, bold=True)
        self.f_mid = pg.font.SysFont(fam, 26)
        self.f_ui = pg.font.SysFont(fam, 21)
        self.f_small = pg.font.SysFont(fam, 16)

    def text(self, s, font, color, x, y, center=False, shadow=False):
        surf = font.render(s, True, color)
        r = surf.get_rect()
        r.center = (x, y) if center else r.center
        if not center:
            r.topleft = (x, y)
        if shadow:
            self.screen.blit(font.render(s, True, (0, 0, 0)), (r.x + 3, r.y + 3))
        self.screen.blit(surf, r)

    def px(self, c):
        return (c[0] * self.cell, c[1] * self.cell)

    def board(self, st, path, show_path):
        pg, s, c = self.pg, self.screen, self.cell
        s.fill(BG)
        for x in range(0, self.width + 1, c):
            pg.draw.line(s, GRID, (x, 0), (x, self.board_h))
        for y in range(0, self.board_h + 1, c):
            pg.draw.line(s, GRID, (0, y), (self.width, y))
        if st.grid.wrap:
            pg.draw.rect(s, GOLD, (0, 0, self.width, self.board_h), 2)
        for o in st.obstacles:
            x, y = self.px(o)
            pg.draw.rect(s, (110, 125, 150), (x + 3, y + 3, c - 6, c - 6), border_radius=5)
        if show_path and path:
            for i, p in enumerate(path):
                x, y = self.px(p)
                pg.draw.circle(s, (255, 200, 87), (x + c // 2, y + c // 2), max(3, c // (3 if i == len(path) - 1 else 6)))
        self._apple(st.apple.pos if st.apple else None, (220, 20, 60), (255, 100, 100))
        if st.bonus:
            self._apple(st.bonus.pos, GOLD, (255, 245, 170))
        if st.powerup:
            x, y = self.px(st.powerup.pos)
            pg.draw.rect(s, CYAN, (x + 4, y + 4, c - 8, c - 8), border_radius=8)
            self.text({"slow": "S", "double": "x2", "shrink": "-"}[st.powerup.kind], self.f_small, (10, 10, 10), x + c // 2, y + c // 2, center=True)
        n = len(st.snake)
        for i, seg in enumerate(st.snake):
            x, y = self.px(seg)
            shade = 50 + int(205 * i / max(1, n))
            r = pg.Rect(x, y, c, c)
            pg.draw.rect(s, (shade if i else 120, 180, 30 if i else 90), r, border_radius=6)
            pg.draw.rect(s, (20, 100, 0), r, 2, border_radius=6)
        hx, hy = self.px(st.snake[0])
        o, e = c // 4, max(2, c // 8)
        eyes = {"left": [(o, o), (o, c - o)], "right": [(c - o, o), (c - o, c - o)],
                "up": [(o, o), (c - o, o)], "down": [(o, c - o), (c - o, c - o)]}[st.direction]
        for ex, ey in eyes:
            pg.draw.circle(s, (0, 0, 0), (hx + ex, hy + ey), e)

    def _apple(self, pos, color, shine):
        if pos is None:
            return
        x, y = self.px(pos)
        c = self.cell
        self.pg.draw.circle(self.screen, color, (x + c // 2, y + c // 2), c // 2 - 5)
        self.pg.draw.circle(self.screen, shine, (x + c // 2 - c // 7, y + c // 2 - c // 7), max(2, c // 8))

    def panel(self, row1, row2, row3):
        pg = self.pg
        pg.draw.rect(self.screen, PANEL, (0, self.board_h, self.width, self.panel_h))
        x = 10
        for label, value in row1:
            surf = self.f_ui.render(f"{label}: {value}", True, WHITE)
            self.screen.blit(surf, (x, self.board_h + 4))
            x += surf.get_width() + 26
        self.text(row2, self.f_small, GOLD, 10, self.board_h + 34)
        self.text(row3, self.f_small, GREY, 10, self.board_h + 54)

    def overlay(self, title, lines, color=RED):
        ov = self.pg.Surface((self.width, self.board_h + self.panel_h), self.pg.SRCALPHA)
        ov.fill((0, 0, 0, 180))
        self.screen.blit(ov, (0, 0))
        cx, y = self.width // 2, self.board_h // 2 - 60
        self.text(title, self.f_big, color, cx, y, center=True, shadow=True)
        for i, ln in enumerate(lines):
            self.text(ln, self.f_mid, WHITE, cx, y + 70 + i * 36, center=True, shadow=True)

    def menu(self, rows, index):
        self.screen.fill((18, 26, 20))
        cx = self.width // 2
        self.text("AI Snake Arena", self.f_big, (125, 255, 176), cx, 56, center=True, shadow=True)
        y = 120
        for i, (label, value) in enumerate(rows):
            sel = i == index
            color = GOLD if sel else WHITE
            self.text(("> " if sel else "  ") + label, self.f_mid, color, cx - 230, y)
            self.text(str(value), self.f_mid, color, cx + 40, y)
            y += 38
        self.text("Up/Down select - Left/Right change - Enter start - Esc quit", self.f_small, GREY, cx, y + 20, center=True)
