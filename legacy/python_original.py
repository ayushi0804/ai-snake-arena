# toggle between manual mode and AI mode
import pygame
from pygame.locals import *
import random
from collections import deque
import heapq

# Constants
SIZE = 40
GRID_WIDTH = 25
GRID_HEIGHT = 12
SCREEN_WIDTH = GRID_WIDTH * SIZE
SCREEN_HEIGHT = GRID_HEIGHT * SIZE + 60  # Extra UI panel height

# --------Pathfinding functions--------

def manhattan(p1, p2):
    return abs(p1[0] - p2[0]) + abs(p1[1] - p2[1])

def astar(start, goal, grid_size, snake_body):
    directions = [(-SIZE, 0), (SIZE, 0), (0, -SIZE), (0, SIZE)]
    open_set = []
    heapq.heappush(open_set, (0 + manhattan(start, goal), 0, start))
    came_from = {}
    g_score = {start: 0}
    visited = set()

    while open_set:
        _, cost, current = heapq.heappop(open_set)
        if current == goal:
            path = []
            while current in came_from:
                path.append(current)
                current = came_from[current]
            path.reverse()
            return path

        if current in visited:
            continue
        visited.add(current)

        for dx, dy in directions:
            neighbor = (current[0] + dx, current[1] + dy)
            if 0 <= neighbor[0] < grid_size[0] and 0 <= neighbor[1] < grid_size[1] and neighbor not in snake_body:
                tentative_g = g_score[current] + 1
                if neighbor not in g_score or tentative_g < g_score[neighbor]:
                    came_from[neighbor] = current
                    g_score[neighbor] = tentative_g
                    f_score = tentative_g + manhattan(neighbor, goal)
                    heapq.heappush(open_set, (f_score, tentative_g, neighbor))
    return []

def bfs(start, goal, grid_size, snake_body):
    directions = [(-SIZE, 0), (SIZE, 0), (0, -SIZE), (0, SIZE)]
    queue = deque([start])
    visited = set([start])
    parent = {}
    snake_body_except_tail = set(list(snake_body)[:-1])

    while queue:
        current = queue.popleft()
        if current == goal:
            path = []
            while current != start:
                path.append(current)
                current = parent[current]
            path.reverse()
            return path

        for dx, dy in directions:
            neighbor = (current[0] + dx, current[1] + dy)
            if 0 <= neighbor[0] < grid_size[0] and 0 <= neighbor[1] < grid_size[1]:
                if neighbor not in snake_body_except_tail and neighbor not in visited:
                    visited.add(neighbor)
                    parent[neighbor] = current
                    queue.append(neighbor)
    return []

def generate_hamiltonian_cycle():
    path = []
    for y in range(GRID_HEIGHT):
        row = list(range(GRID_WIDTH))
        if y % 2 == 1:
            row.reverse()
        for x in row:
            path.append((x * SIZE, y * SIZE))
    return path

class Apple:
    def __init__(self, parent_screen):
        self.parent_screen = parent_screen
        self.move()

    def draw(self):
        center = (self.x + SIZE // 2, self.y + SIZE // 2)
        pygame.draw.circle(self.parent_screen, (220, 20, 60), center, SIZE//2 - 5)
        pygame.draw.circle(self.parent_screen, (255, 100, 100), (center[0]-6, center[1]-6), SIZE//4)

    def move(self):
        self.x = SIZE * random.randint(0, GRID_WIDTH - 1)
        self.y = SIZE * random.randint(0, GRID_HEIGHT - 1)

class Snake:
    def __init__(self, parent_screen):
        self.parent_screen = parent_screen
        self.direction = 'down'
        self.length = 1
        self.body = deque([(SIZE * 2, SIZE * 2)])

    def draw(self):
        for i, segment in enumerate(self.body):
            shade = 50 + int((205 / self.length) * i)
            color = (shade, 180, 30)
            rect = pygame.Rect(segment[0], segment[1], SIZE, SIZE)
            pygame.draw.rect(self.parent_screen, color, rect)
            pygame.draw.rect(self.parent_screen, (20, 100, 0), rect, 2)

        head_x, head_y = self.body[0]
        eye_radius = 5
        eye_offset = 10
        eye_color = (0, 0, 0)

        if self.direction == 'left':
            eyes = [(head_x + eye_offset, head_y + eye_offset), (head_x + eye_offset, head_y + SIZE - eye_offset)]
        elif self.direction == 'right':
            eyes = [(head_x + SIZE - eye_offset, head_y + eye_offset), (head_x + SIZE - eye_offset, head_y + SIZE - eye_offset)]
        elif self.direction == 'up':
            eyes = [(head_x + eye_offset, head_y + eye_offset), (head_x + SIZE - eye_offset, head_y + eye_offset)]
        else:
            eyes = [(head_x + eye_offset, head_y + SIZE - eye_offset), (head_x + SIZE - eye_offset, head_y + SIZE - eye_offset)]

        for eye_pos in eyes:
            pygame.draw.circle(self.parent_screen, eye_color, eye_pos, eye_radius)

    def move_left(self):
        if self.direction != 'right':
            self.direction = 'left'

    def move_right(self):
        if self.direction != 'left':
            self.direction = 'right'

    def move_up(self):
        if self.direction != 'down':
            self.direction = 'up'

    def move_down(self):
        if self.direction != 'up':
            self.direction = 'down'

    def walk(self):
        head_x, head_y = self.body[0]
        if self.direction == 'left':
            head_x -= SIZE
        elif self.direction == 'right':
            head_x += SIZE
        elif self.direction == 'up':
            head_y -= SIZE
        elif self.direction == 'down':
            head_y += SIZE

        self.body.appendleft((head_x, head_y))
        if len(self.body) > self.length:
            self.body.pop()

    def grow(self):
        self.length += 1

    def check_collision_with_self(self):
        head = self.body[0]
        return head in list(self.body)[1:]

class Game:
    def __init__(self):
        pygame.init()
        pygame.mixer.init()
        self.screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
        pygame.display.set_caption("Crawling Cobras")

        self.snake = Snake(self.screen)
        self.apple = Apple(self.screen)

        self.score = 0
        self.font = pygame.font.SysFont('arial', 24)
        self.game_over_font = pygame.font.SysFont('arial', 60, bold=True)
        self.info_font = pygame.font.SysFont('arial', 18)

        try:
            with open("highscore.txt", "r") as f:
                self.high_score = int(f.read())
        except:
            self.high_score = 0

        self.ai_enabled = True
        self.hamiltonian_path = generate_hamiltonian_cycle()
        self.hamiltonian_index = 0
        self.search_strategy = "A*"

        self.game_over_sound = None
        try:
            self.game_over_sound = pygame.mixer.Sound("game_over.mp3")
        except:
            pass  # no sound file, ignore

    def draw_grid(self):
        for x in range(0, SCREEN_WIDTH, SIZE):
            pygame.draw.line(self.screen, (180, 180, 180), (x, 0), (x, GRID_HEIGHT * SIZE))
        for y in range(0, GRID_HEIGHT * SIZE, SIZE):
            pygame.draw.line(self.screen, (180, 180, 180), (0, y), (SCREEN_WIDTH, y))

    def draw_ui_panel(self):
        panel_rect = pygame.Rect(0, GRID_HEIGHT * SIZE, SCREEN_WIDTH, 60)
        pygame.draw.rect(self.screen, (40, 40, 40), panel_rect)

        score_text = self.font.render(f"Score: {self.score}", True, (255, 255, 255))
        high_score_text = self.font.render(f"High Score: {self.high_score}", True, (255, 255, 255))
        strategy_text = self.font.render(f"Strategy: {self.search_strategy}", True, (255, 255, 255))
        mode_text = self.font.render(f"Mode: {'AI' if self.ai_enabled else 'Manual'}", True, (255, 255, 255))
        control_text = self.info_font.render("Press A for A*, B for BFS, M to Toggle Mode | ESC to Quit", True, (200, 200, 200))

        self.screen.blit(score_text, (10, GRID_HEIGHT * SIZE + 5))
        self.screen.blit(high_score_text, (180, GRID_HEIGHT * SIZE + 5))
        self.screen.blit(strategy_text, (410, GRID_HEIGHT * SIZE + 5))
        self.screen.blit(mode_text, (600, GRID_HEIGHT * SIZE + 5))
        self.screen.blit(control_text, (10, GRID_HEIGHT * SIZE + 32))

    def show_game_over(self):
        overlay = pygame.Surface(self.screen.get_size(), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 180))
        self.screen.blit(overlay, (0, 0))

        def draw_text_with_shadow(text, font, color, x, y):
            shadow_color = (0, 0, 0)
            shadow_offset = 3
            shadow = font.render(text, True, shadow_color)
            self.screen.blit(shadow, (x + shadow_offset, y + shadow_offset))
            text_surface = font.render(text, True, color)
            self.screen.blit(text_surface, (x, y))

        center_x = self.screen.get_width() // 2
        draw_text_with_shadow("GAME OVER!", self.game_over_font, (255, 50, 50), center_x - 180, 150)
        draw_text_with_shadow("Press Enter to Restart or ESC to Quit", self.font, (255, 255, 255), center_x - 180, 250)
        draw_text_with_shadow(f"Your Score: {self.score}  High Score: {self.high_score}", self.font, (255, 255, 255), center_x - 180, 290)
        pygame.display.flip()

    def reset(self):
        self.snake = Snake(self.screen)
        self.apple = Apple(self.screen)
        self.score = 0
        self.hamiltonian_path = generate_hamiltonian_cycle()
        self.hamiltonian_index = 0

    def is_collision(self, x1, y1, x2, y2):
        r1 = pygame.Rect(x1, y1, SIZE, SIZE)
        r2 = pygame.Rect(x2, y2, SIZE, SIZE)
        return r1.colliderect(r2)

    def run(self):
        running = True
        game_over = False
        clock = pygame.time.Clock()

        while running:
            for event in pygame.event.get():
                if event.type == KEYDOWN:
                    if event.key == K_ESCAPE:
                        running = False
                    if event.key == K_m:
                        self.ai_enabled = not self.ai_enabled  # Toggle AI/manual mode

                    if not game_over and not self.ai_enabled:
                        if event.key == K_UP:
                            self.snake.move_up()
                        elif event.key == K_DOWN:
                            self.snake.move_down()
                        elif event.key == K_LEFT:
                            self.snake.move_left()
                        elif event.key == K_RIGHT:
                            self.snake.move_right()
                    elif game_over:
                        if event.key == K_RETURN:
                            self.reset()
                            game_over = False

                    if event.key == K_b:
                        self.search_strategy = "BFS"
                    elif event.key == K_a:
                        self.search_strategy = "A*"

                elif event.type == QUIT:
                    running = False

            if not game_over:
                self.screen.fill((30, 40, 30))
                self.draw_grid()
                self.draw_ui_panel()

                if self.ai_enabled:
                    snake_head = self.snake.body[0]
                    apple_pos = (self.apple.x, self.apple.y)
                    snake_body_set = set(self.snake.body)
                    grid_bounds = (SCREEN_WIDTH, GRID_HEIGHT * SIZE)

                    if self.search_strategy == "A*":
                        path = astar(snake_head, apple_pos, grid_bounds, snake_body_set)
                    elif self.search_strategy == "BFS":
                        path = bfs(snake_head, apple_pos, grid_bounds, snake_body_set)
                    else:
                        path = []

                    if path:
                        next_move = path[0]
                    else:
                        while self.hamiltonian_index < len(self.hamiltonian_path) and self.hamiltonian_path[self.hamiltonian_index] in self.snake.body:
                            self.hamiltonian_index = (self.hamiltonian_index + 1) % len(self.hamiltonian_path)
                        next_move = self.hamiltonian_path[self.hamiltonian_index]
                        self.hamiltonian_index = (self.hamiltonian_index + 1) % len(self.hamiltonian_path)

                    head_x, head_y = self.snake.body[0]
                    if next_move[0] < head_x:
                        self.snake.move_left()
                    elif next_move[0] > head_x:
                        self.snake.move_right()
                    elif next_move[1] < head_y:
                        self.snake.move_up()
                    elif next_move[1] > head_y:
                        self.snake.move_down()

                self.snake.walk()

                # Check collision with walls
                head_x, head_y = self.snake.body[0]
                if not (0 <= head_x < SCREEN_WIDTH and 0 <= head_y < GRID_HEIGHT * SIZE):
                    game_over = True
                    if self.game_over_sound:
                        self.game_over_sound.play()

                # Check collision with self
                if self.snake.check_collision_with_self():
                    game_over = True
                    if self.game_over_sound:
                        self.game_over_sound.play()

                # Check apple collision
                if self.is_collision(head_x, head_y, self.apple.x, self.apple.y):
                    self.score += 1
                    if self.score > self.high_score:
                        self.high_score = self.score
                        with open("highscore.txt", "w") as f:
                            f.write(str(self.high_score))
                    self.snake.grow()
                    self.apple.move()

                self.snake.draw()
                self.apple.draw()

                pygame.display.flip()
                clock.tick(8)

            else:
                self.show_game_over()
                clock.tick(15)

        pygame.quit()

if __name__== "__main__":
    game = Game()
    game.run()
