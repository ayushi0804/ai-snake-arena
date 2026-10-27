"""Generate PWA PNG icons with the standard library only (no Pillow). Run: python tools/make_icons.py"""
import math, struct, zlib, pathlib

OUT = pathlib.Path(__file__).resolve().parent.parent / "webapp" / "static" / "icons"
BG, GREEN, LIGHT, RED, DARK, WHITE = (11, 18, 32), (61, 220, 132), (125, 255, 176), (255, 77, 109), (11, 18, 32), (255, 255, 255)


def shapes(scale, off):
    """Circles (cx, cy, r, color) in unit space, drawn back to front."""
    pts, out = [], []
    for i in range(24):
        t = i / 23
        x = 0.5 + 0.26 * math.sin(t * math.pi * 2.0 + 0.4)
        y = 0.24 + 0.54 * t
        r = 0.075 - 0.025 * t
        out.append((x, y, r, GREEN))
    hx, hy, hr, _ = out[0]
    out.append((hx, hy, 0.095, LIGHT))
    out += [(hx - 0.03, hy - 0.01, 0.016, DARK), (hx + 0.03, hy - 0.01, 0.016, DARK)]
    out.append((0.78, 0.8, 0.075, RED))
    return [(off + x * scale, off + y * scale, r * scale, c) for x, y, r, c in out]


def render(n, maskable):
    scale, off = (n * 0.8, n * 0.1) if maskable else (n * 0.9, n * 0.05)
    sh = shapes(scale, off)
    corner = 0 if maskable else n * 0.19
    rows = []
    for py in range(n):
        row = bytearray()
        for px in range(n):
            x, y = px + 0.5, py + 0.5
            # rounded-square mask for 'any' icons
            dx, dy = max(corner - x, x - (n - corner), 0), max(corner - y, y - (n - corner), 0)
            a = 255 if corner == 0 else max(0, min(255, int(255 * (corner + 0.5 - math.hypot(dx, dy)))))
            col = BG
            for cx, cy, r, c in sh:
                d = math.hypot(x - cx, y - cy) - r
                if d < 1:
                    k = max(0.0, min(1.0, 0.5 - d))
                    col = tuple(int(col[i] * (1 - k) + c[i] * k) for i in range(3))
            row += bytes((*col, a))
        rows.append(b"\x00" + bytes(row))
    raw = b"".join(rows)
    def chunk(tag, data):
        c = struct.pack(">I", len(data)) + tag + data
        return c + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", n, n, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    for name, n, m in (("icon-192.png", 192, False), ("icon-512.png", 512, False), ("icon-maskable-512.png", 512, True)):
        (OUT / name).write_bytes(render(n, m))
        print("wrote", OUT / name)
