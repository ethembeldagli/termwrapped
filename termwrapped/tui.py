"""The slideshow: full-screen gradients, pixel-font numbers, count-up animations.

Pure ANSI escape codes, no curses, no dependencies.
"""

from __future__ import annotations

import os
import select
import shutil
import sys
import time
import unicodedata

from termwrapped.insights import THEMES, Slide

# --- colour ---------------------------------------------------------------

RGB = tuple


def hex_rgb(h: str) -> RGB:
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def lerp(a: RGB, b: RGB, t: float) -> RGB:
    t = max(0.0, min(1.0, t))
    return tuple(round(x + (y - x) * t) for x, y in zip(a, b))


def truecolor_supported() -> bool:
    if os.environ.get("COLORTERM", "").lower() in ("truecolor", "24bit"):
        return True
    term = os.environ.get("TERM", "")
    return any(k in term for k in ("direct", "kitty", "alacritty", "wezterm", "foot", "ghostty"))


def _to_256(c: RGB) -> int:
    r, g, b = c
    if abs(r - g) < 10 and abs(g - b) < 10:
        if r < 8:
            return 16
        if r > 238:
            return 231
        return 232 + round((r - 8) / 247 * 24)
    q = lambda v: 0 if v < 48 else 1 if v < 115 else (v - 35) // 40  # noqa: E731
    return 16 + 36 * q(r) + 6 * q(g) + q(b)


class Palette:
    def __init__(self, truecolor: bool):
        self.truecolor = truecolor

    def fg(self, c: RGB) -> str:
        return f"\x1b[38;2;{c[0]};{c[1]};{c[2]}m" if self.truecolor else f"\x1b[38;5;{_to_256(c)}m"

    def bg(self, c: RGB) -> str:
        return f"\x1b[48;2;{c[0]};{c[1]};{c[2]}m" if self.truecolor else f"\x1b[48;5;{_to_256(c)}m"


WHITE = (255, 255, 255)


def cell_width(ch: str) -> int:
    if unicodedata.combining(ch):
        return 0
    return 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1


def text_width(s: str) -> int:
    return sum(cell_width(c) for c in s)


def clip(s: str, width: int) -> str:
    if text_width(s) <= width:
        return s
    out, w = "", 0
    for c in s:
        if w + cell_width(c) > width - 1:
            break
        out += c
        w += cell_width(c)
    return out + "…"


# --- a tiny 5px pixel font -------------------------------------------------

FONT = {
    "0": ["###", "#.#", "#.#", "#.#", "###"], "1": [".#.", "##.", ".#.", ".#.", "###"],
    "2": ["##.", "..#", ".#.", "#..", "###"], "3": ["##.", "..#", ".#.", "..#", "##."],
    "4": ["#.#", "#.#", "###", "..#", "..#"], "5": ["###", "#..", "##.", "..#", "##."],
    "6": [".##", "#..", "###", "#.#", "###"], "7": ["###", "..#", ".#.", ".#.", ".#."],
    "8": ["###", "#.#", "###", "#.#", "###"], "9": ["###", "#.#", "###", "..#", "##."],
    "A": [".#.", "#.#", "###", "#.#", "#.#"], "B": ["##.", "#.#", "##.", "#.#", "##."],
    "C": [".##", "#..", "#..", "#..", ".##"], "D": ["##.", "#.#", "#.#", "#.#", "##."],
    "E": ["###", "#..", "##.", "#..", "###"], "F": ["###", "#..", "##.", "#..", "#.."],
    "G": [".##", "#..", "#.#", "#.#", ".##"], "H": ["#.#", "#.#", "###", "#.#", "#.#"],
    "I": ["###", ".#.", ".#.", ".#.", "###"], "J": ["..#", "..#", "..#", "#.#", ".#."],
    "K": ["#.#", "#.#", "##.", "#.#", "#.#"], "L": ["#..", "#..", "#..", "#..", "###"],
    "M": ["#...#", "##.##", "#.#.#", "#...#", "#...#"], "N": ["#..#", "##.#", "#.##", "#..#", "#..#"],
    "O": [".#.", "#.#", "#.#", "#.#", ".#."], "P": ["##.", "#.#", "##.", "#..", "#.."],
    "Q": [".#.", "#.#", "#.#", "##.", ".##"], "R": ["##.", "#.#", "##.", "#.#", "#.#"],
    "S": [".##", "#..", ".#.", "..#", "##."], "T": ["###", ".#.", ".#.", ".#.", ".#."],
    "U": ["#.#", "#.#", "#.#", "#.#", "###"], "V": ["#.#", "#.#", "#.#", "#.#", ".#."],
    "W": ["#...#", "#...#", "#.#.#", "##.##", "#...#"], "X": ["#.#", "#.#", ".#.", "#.#", "#.#"],
    "Y": ["#.#", "#.#", ".#.", ".#.", ".#."], "Z": ["###", "..#", ".#.", "#..", "###"],
    " ": ["..", "..", "..", "..", ".."], "-": ["...", "...", "###", "...", "..."],
    ".": [".", ".", ".", ".", "#"], ",": ["..", "..", "..", ".#", "#."],
    "%": ["#.#", "..#", ".#.", "#..", "#.#"], ":": [".", "#", ".", "#", "."],
    "+": ["...", ".#.", "###", ".#.", "..."], "!": ["#", "#", "#", ".", "#"],
    "'": ["#", "#", ".", ".", "."], "?": ["##.", "..#", ".#.", "...", ".#."],
    "/": ["..#", "..#", ".#.", "#..", "#.."], "h": ["#..", "#..", "##.", "#.#", "#.#"],
    "x": ["...", "#.#", ".#.", "#.#", "..."],
}


def glyph_rows(text: str) -> list[str] | None:
    """Combine glyphs into five pixel rows, or None if a character is missing."""
    rows = [""] * 5
    for i, ch in enumerate(text):
        g = FONT.get(ch) or FONT.get(ch.upper())
        if g is None:
            return None
        for r in range(5):
            rows[r] += ("." if i else "") + g[r]
    return rows


def pixel_width(text: str, scale: int) -> int:
    rows = glyph_rows(text)
    return len(rows[0]) * scale if rows else 10**6


# --- layout: blocks become rows of coloured cells --------------------------
# A row is a list of segments (text, colour, bold).

def ease_out(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return 1 - (1 - t) ** 3


def block_duration(block) -> float:
    kind = block[0]
    if kind == "text":
        return min(0.7, 0.015 * len(block[1]) + 0.1)
    if kind == "number":
        return 1.2
    if kind == "word":
        return 0.6
    if kind == "bars":
        return 1.0
    if kind == "list":
        return 0.12 * len(block[1]) + 0.1
    return 0.0


INTRO = 0.35  # background cross-fade


def slide_duration(slide: Slide) -> float:
    return INTRO + sum(block_duration(b) for b in slide.blocks)


def _fmt_number(v: float, suffix: str) -> str:
    return f"{int(round(v)):,}{suffix}"


def _pixel_rows(text: str, scale: int, accent: RGB, accent2: RGB, reveal: float = 1.0) -> list[list]:
    rows = glyph_rows(text)
    if rows is None:
        return []
    width = len(rows[0])
    visible = int(round(width * reveal))
    colour_at = lambda x: lerp(accent, accent2, x / max(1, width - 1))  # noqa: E731
    out = []
    if scale == 2:
        for r in rows:
            out.append([("██" if (px == "#" and x < visible) else "  ", colour_at(x), True) for x, px in enumerate(r)])
    else:
        # half blocks: two pixel rows per terminal row
        padded = rows + ["." * width]
        for r in range(0, 5, 2):
            top, bot = padded[r], padded[r + 1]
            segs = []
            for x in range(width):
                t_on = top[x] == "#" and x < visible
                b_on = bot[x] == "#" and x < visible
                ch = "█" if t_on and b_on else "▀" if t_on else "▄" if b_on else " "
                segs.append((ch, colour_at(x), True))
            out.append(segs)
    return out


def _wrap_words(text: str, max_px: int, scale: int) -> list[str] | None:
    lines, cur = [], ""
    for w in text.split():
        cand = f"{cur} {w}" if cur else w
        if pixel_width(cand, scale) <= max_px:
            cur = cand
        elif pixel_width(w, scale) <= max_px:
            lines.append(cur)
            cur = w
        else:
            return None
    lines.append(cur)
    return [line for line in lines if line]


def render_block(block, p: float, width: int, height: int, theme) -> list[list]:
    """Render one block at animation progress p (0..1) into rows."""
    _, _, accent, accent2 = theme
    # Keep every colour close to white so it stays readable on any theme.
    dim = lerp(WHITE, theme[1], 0.25)
    quip = lerp(accent2, WHITE, 0.45)
    kind = block[0]

    if kind == "gap":
        return [[]]

    if kind == "text":
        _, s, style = block
        s = clip(s, width - 4)
        shown = s[: int(len(s) * ease_out(p) + 0.999)] if p < 1 else s
        colour, bold = {
            "title": (WHITE, True), "body": (WHITE, False), "dim": (dim, False),
            "quip": (quip, True), "accent": (lerp(accent, WHITE, 0.3), True),
        }[style]
        return [[(shown, colour, bold)]]

    if kind == "number":
        _, value, suffix = block
        text = _fmt_number(value * ease_out(p), suffix)
        final = _fmt_number(value, suffix)
        for scale in (2, 1):
            if pixel_width(final, scale) <= width - 4 and (scale == 1 or height >= 22):
                return _pixel_rows(text, scale, accent, accent2)
        return [[(text, accent, True)]]

    if kind == "word":
        s = block[1]
        budget = max(5, height // 3)
        for scale in (2, 1):
            lines = _wrap_words(s, width - 6, scale)
            rows_per_line = 5 if scale == 2 else 3
            if lines and len(lines) * (rows_per_line + 1) - 1 <= budget:
                out: list[list] = []
                for i, line in enumerate(lines):
                    if i:
                        out.append([])
                    out += _pixel_rows(line, scale, accent, accent2, ease_out(p * 1.2 - i * 0.2))
                return out
        return [[(clip(s, width - 4), accent, True)]]

    if kind == "bars":
        _, rows, unit = block
        if not rows:
            return []
        label_w = min(max(text_width(str(r[0])) for r in rows), 26)
        count_w = max(len(f"{v:,}{unit}") for _, v in rows)
        bar_w = max(6, min(40, width - label_w - count_w - 10))
        top = max(v for _, v in rows) or 1
        out = []
        for i, (label, v) in enumerate(rows):
            local = ease_out(p * 1.4 - i * 0.1)
            frac = (v / top) * local
            full = int(frac * bar_w)
            eighth = int((frac * bar_w - full) * 8)
            bar = "█" * full + (" ▏▎▍▌▋▊▉"[eighth] if eighth else "")
            label = clip(str(label), label_w)
            segs = [(f"{i + 1}  ", dim, False), (label + " " * (label_w - text_width(label)) + "  ", WHITE, True)]
            for x, ch in enumerate(bar):
                segs.append((ch, lerp(accent, accent2, x / max(1, bar_w - 1)), False))
            segs.append((" " * (bar_w - len(bar) + 2), WHITE, False))
            segs.append((f"{int(v * local):,}{unit}".rjust(count_w), WHITE, True))
            out.append(segs)
        return out

    if kind == "list":
        rows = block[1]
        shown = int(len(rows) * min(1.0, p * 1.05) + 0.999)
        inner = min(56, width - 6)
        out = []
        for label, value in rows[:shown]:
            value = clip(str(value), inner // 2)
            label = clip(label, inner - text_width(value) - 3)
            dots = " " + "·" * (inner - text_width(label) - text_width(value) - 2) + " "
            out.append([(label, dim, False), (dots, lerp(dim, theme[1], 0.6), False), (value, WHITE, True)])
        return out
    return []


def layout(slide: Slide, t: float, width: int, height: int) -> list[list]:
    theme = tuple(hex_rgb(c) for c in THEMES[slide.theme])
    rows: list[list] = []
    clock = INTRO
    kicker = " ".join(slide.kicker)  # letter-spaced
    rows.append([(clip(kicker, width - 4), lerp(theme[2], WHITE, 0.2), True)])
    rows.append([])
    for block in slide.blocks:
        dur = block_duration(block)
        if t < clock:
            if block[0] in ("number", "word", "bars", "list"):
                # Reserve space so the layout doesn't jump when it appears.
                rows += [[]] * len(render_block(block, 1.0, width, height, theme))
            else:
                rows.append([])
            continue
        p = 1.0 if dur == 0 else (t - clock) / dur
        rows += render_block(block, min(1.0, p), width, height, theme)
        clock += dur
    return rows


# --- drawing ----------------------------------------------------------------

class Screen:
    def __init__(self, truecolor: bool):
        self.pal = Palette(truecolor)
        self.out = sys.stdout

    def draw(self, slide: Slide, t: float, index: int, count: int, prev_theme: str | None) -> None:
        width, height = shutil.get_terminal_size((80, 24))
        theme = tuple(hex_rgb(c) for c in THEMES[slide.theme])
        old = tuple(hex_rgb(c) for c in THEMES[prev_theme or slide.theme])
        fade = ease_out(t / INTRO) if prev_theme else 1.0
        top_c, bot_c = lerp(old[0], theme[0], fade), lerp(old[1], theme[1], fade)

        content = layout(slide, t, width, height)
        # Centre each row, but left-align a block of bar/list rows together.
        body_h = len(content)
        y0 = max(2, (height - body_h) // 2)

        grid: list[list] = [[(" ", WHITE, False)] * width for _ in range(height)]

        def put(y: int, x: int, segs) -> None:
            if not 0 <= y < height:
                return
            for text, colour, bold in segs:
                for ch in text:
                    w = cell_width(ch)
                    if 0 <= x < width - (w - 1):
                        grid[y][x] = (ch, colour, bold)
                        if w == 2:
                            grid[y][x + 1] = ("", colour, bold)
                    x += w

        for i, segs in enumerate(content):
            w = sum(text_width(s[0]) for s in segs)
            put(y0 + i, max(0, (width - w) // 2), segs)

        # Story-style progress bar on the first row.
        seg_w = max(1, (width - 4 - (count - 1)) // count)
        x = 2
        dur = slide_duration(slide)
        for i in range(count):
            if i < index:
                fill = seg_w
            elif i == index:
                fill = max(1, round(seg_w * min(1.0, t / dur)))
            else:
                fill = 0
            put(0, x, [("━" * fill, WHITE, False), ("━" * (seg_w - fill), lerp(WHITE, top_c, 0.7), False)])
            x += seg_w + 1

        hint = "◂ back    space ▸ next    q quit"
        put(height - 1, max(0, (width - len(hint)) // 2), [(hint, lerp(WHITE, bot_c, 0.35), False)])

        buf = ["\x1b[H"]
        for y in range(height):
            bg = lerp(top_c, bot_c, y / max(1, height - 1))
            buf.append(f"\x1b[{y + 1};1H" + self.pal.bg(bg))
            cur = None
            for ch, colour, bold in grid[y]:
                if ch == "":
                    continue
                key = (colour, bold)
                if key != cur:
                    buf.append(("\x1b[1m" if bold else "\x1b[22m") + self.pal.fg(colour))
                    cur = key
                buf.append(ch)
        buf.append("\x1b[0m")
        self.out.write("".join(buf))
        self.out.flush()


def _read_key(fd: int, timeout: float) -> str | None:
    r, _, _ = select.select([fd], [], [], timeout)
    if not r:
        return None
    data = os.read(fd, 64)
    if data in (b"\x1b[D", b"h", b"\x1b[A", b"k", b"\x7f"):
        return "back"
    if data in (b"q", b"Q", b"\x03", b"\x1b"):
        return "quit"
    return "next"


def play(slides: list[Slide], auto: float | None = None) -> None:
    import termios
    import tty

    fd = sys.stdin.fileno()
    saved = termios.tcgetattr(fd)
    screen = Screen(truecolor_supported())
    out = sys.stdout
    out.write("\x1b[?1049h\x1b[?25l")
    try:
        tty.setcbreak(fd)
        index, prev = 0, None
        start = time.monotonic()
        while index < len(slides):
            slide = slides[index]
            t = time.monotonic() - start
            dur = slide_duration(slide)
            screen.draw(slide, t, index, len(slides), prev)
            done = t >= dur
            key = _read_key(fd, 0.25 if done else 1 / 40)
            if key is None and auto and t >= dur + auto:
                key = "next"
            if key == "quit":
                break
            if key == "next":
                if not done:
                    start = time.monotonic() - dur  # finish the animation first
                else:
                    prev, index = slide.theme, index + 1
                    start = time.monotonic()
            elif key == "back" and index > 0:
                prev, index = slide.theme, index - 1
                start = time.monotonic() - slide_duration(slides[index]) + INTRO
    except KeyboardInterrupt:
        pass
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, saved)
        out.write("\x1b[0m\x1b[?25h\x1b[?1049l")
        out.flush()


def print_plain(slides: list[Slide]) -> None:
    """For pipes, NO_COLOR and dumb terminals."""
    for slide in slides:
        print(f"\n== {slide.kicker} ==")
        for block in slide.blocks:
            kind = block[0]
            if kind == "text":
                print(("  " if block[2] == "dim" else "") + block[1])
            elif kind == "number":
                print(f"  >> {_fmt_number(block[1], block[2])}")
            elif kind == "word":
                print(f"  >> {block[1]}")
            elif kind == "bars":
                top = max(v for _, v in block[1]) or 1
                for i, (label, v) in enumerate(block[1], 1):
                    print(f"  {i}. {str(label)[:24]:<24} {'#' * int(20 * v / top):<20} {v:,}{block[2]}")
            elif kind == "list":
                for label, value in block[1]:
                    print(f"  {label:<28} {value}")
