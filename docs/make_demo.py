#!/usr/bin/env python3
"""Regenerate the README images from made-up data (never your real history):

    docs/demo.gif            the slideshow, rendered frame by frame
    docs/example-card.png    a share card
    docs/social-preview.png  1280x640 image for GitHub's social preview setting

Needs ImageMagick (for the GIF) and ideally rsvg-convert or gdk-pixbuf-thumbnailer
(librsvg) for crisp text. Run:  python3 docs/make_demo.py
Inside a distrobox/toolbox, the host's fonts are used too.
"""

from __future__ import annotations

import concurrent.futures
import datetime as dt
import os
import shutil
import subprocess
import sys
import tempfile
import time
from xml.sax.saxutils import escape

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS = os.path.join(ROOT, "docs")
sys.path[:0] = [ROOT, os.path.join(ROOT, "tests")]

import fixtures  # noqa: E402

# Inside a distrobox/toolbox, render with the host's (nicer) fonts as well.
if os.path.isdir("/run/host/usr/share/fonts") and "FONTCONFIG_FILE" not in os.environ:
    _fc = os.path.join(tempfile.mkdtemp(prefix="termwrapped-fc-"), "fonts.conf")
    with open(_fc, "w") as _f:
        _f.write('<?xml version="1.0"?><fontconfig><include ignore_missing="yes">/etc/fonts/fonts.conf</include>'
                 f'<dir>/run/host/usr/share/fonts</dir><cachedir>{os.path.dirname(_fc)}</cachedir></fontconfig>')
    os.environ["FONTCONFIG_FILE"] = _fc

# termwrapped reads $HOME when imported, so point it at the fake home first.
HOME = tempfile.mkdtemp(prefix="termwrapped-demo-")
fixtures.demo_home(HOME)
os.environ.update(HOME=HOME, TZ="UTC")
for var in ("HISTFILE", "XDG_DATA_HOME", "ZDOTDIR"):
    os.environ.pop(var, None)
time.tzset()

from termwrapped import card, games, insights, shell, system, tui  # noqa: E402

MAGICK = shutil.which("magick") or shutil.which("convert")
RSVG = shutil.which("rsvg-convert") or shutil.which("gdk-pixbuf-thumbnailer")
YEAR = fixtures.YEAR

COLS, ROWS = 80, 24          # terminal size in the GIF
CW, CH = 12, 25              # cell size in pixels
FONT = "'JetBrains Mono', 'Fira Code', 'DejaVu Sans Mono', monospace"  # 0.6em wide: 12px cells at 20px
FPS = 10
GIF_SLIDES = ["TERMINAL WRAPPED", "COMMANDS", "YOUR TOP 5", "OOPS", "GAMING",
              "TERMINAL PERSONALITY", "THAT'S A WRAP"]


def hexc(c) -> str:
    return "#%02x%02x%02x" % tuple(c)


# --- terminal grid -> SVG ---------------------------------------------------

EIGHTHS = {"▏": 1, "▎": 2, "▍": 3, "▌": 4, "▋": 5, "▊": 6, "▉": 7}


def grid_svg(grid, backgrounds) -> str:
    """Block characters become exact rectangles so pixel-font digits line up
    perfectly; everything else is drawn as text, one word at a time."""
    w, h = COLS * CW, ROWS * CH
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">']
    for y, row in enumerate(grid):
        top = y * CH
        out.append(f'<rect x="0" y="{top}" width="{w}" height="{CH + 1}" fill="{hexc(backgrounds[y])}"/>')
        word, word_x, word_style = "", 0, None

        def flush():
            if word:
                colour, bold = word_style
                weight = ' font-weight="700"' if bold else ""
                out.append(
                    f'<text x="{word_x * CW}" y="{top + CH * 0.74:.1f}" font-family="{FONT}" '
                    f'font-size="20"{weight} fill="{hexc(colour)}">{escape(word)}</text>'
                )

        for x, (ch, colour, bold) in enumerate(row):
            left = x * CW
            block = None
            if ch == "█":
                block = (left, top, CW, CH)
            elif ch == "▀":
                block = (left, top, CW, CH / 2)
            elif ch == "▄":
                block = (left, top + CH / 2, CW, CH / 2)
            elif ch == "━":
                block = (left, top + CH * 0.42, CW, CH * 0.16)
            elif ch in EIGHTHS:
                block = (left, top, CW * EIGHTHS[ch] / 8, CH)
            if block or ch in (" ", "") or (word and (colour, bold) != word_style):
                flush()
                word = ""
            if block:
                bx, by, bw, bh = block
                out.append(f'<rect x="{bx}" y="{by:.1f}" width="{bw + 0.6:.1f}" height="{bh + 0.6:.1f}" fill="{hexc(colour)}"/>')
            elif ch not in (" ", ""):
                if not word:
                    word_x, word_style = x, (colour, bold)
                word += ch
        flush()
    out.append("</svg>")
    return "\n".join(out)


def shell_grid(lines) -> tuple[list[list], list]:
    """A plain dark terminal showing `lines` (lists of (text, colour, bold))."""
    bg = (13, 14, 20)
    grid = [[(" ", (255, 255, 255), False)] * COLS for _ in range(ROWS)]
    for y, segs in enumerate(lines[:ROWS]):
        x = 1
        for text, colour, bold in segs:
            for ch in text:
                if x < COLS:
                    grid[y][x] = (ch, colour, bold)
                x += 1
    return grid, [bg] * ROWS


# --- the recording ------------------------------------------------------------

def frames(slides) -> list[tuple[tuple, int]]:
    """Returns [((grid, backgrounds), delay in 1/100 s), ...]."""
    out = []
    green, blue, dim, white = (80, 250, 123), (139, 233, 253), (130, 135, 150), (235, 235, 240)
    prompt = [("you@arch", green, True), (" ~ ", blue, True), ("$ ", white, False)]

    typed = "termwrapped"
    out.append((shell_grid([[], prompt]), 80))
    for i in range(1, len(typed) + 1):
        out.append((shell_grid([[], prompt + [(typed[:i], white, False)]]), 7))
    steps = ["reading shell history", "counting your commits", "checking package managers",
             "looking for games", "inspecting the machine", "designing your share card"]
    log = [[], prompt + [(typed, white, False)], [], [(f" Terminal Wrapped {YEAR}", white, True)], []]
    for step in steps:
        log.append([(" › ", dim, False), (f"{step}…", white, False), (" ✓", green, True)])
        out.append((shell_grid(log), 14))
    out[-1] = (out[-1][0], 60)

    prev = None
    for i, slide in enumerate(slides):
        dur = tui.slide_duration(slide)
        t = 0.0
        while t < dur:
            out.append((tui.compose(slide, t, i, len(slides), prev, COLS, ROWS), 100 // FPS))
            t += 1 / FPS
        hold = 240 if "PERSONALITY" in slide.kicker else 130
        out.append((tui.compose(slide, dur + 1, i, len(slides), prev, COLS, ROWS), hold))
        prev = slide.theme
    return out


def to_png(svg: str, png: str, width: int, height: int) -> None:
    if RSVG and RSVG.endswith("rsvg-convert"):
        cmd = [RSVG, "-w", str(width), "-h", str(height), "-o", png, svg]
    elif RSVG:
        cmd = [RSVG, "-s", str(max(width, height)), svg, png]
    else:
        cmd = [MAGICK, svg, png]
    subprocess.run(cmd, check=True, capture_output=True)


def render_png(args) -> None:
    svg, png = args
    to_png(svg, png, COLS * CW, ROWS * CH)


def make_gif(slides) -> str:
    tmp = tempfile.mkdtemp(prefix="termwrapped-frames-")
    jobs, delays = [], []
    for n, ((grid, bgs), delay) in enumerate(frames(slides)):
        svg = os.path.join(tmp, f"{n:04d}.svg")
        with open(svg, "w", encoding="utf-8") as f:
            f.write(grid_svg(grid, bgs))
        jobs.append((svg, svg[:-4] + ".png"))
        delays.append(delay)
    with concurrent.futures.ThreadPoolExecutor(max_workers=os.cpu_count() or 4) as pool:
        list(pool.map(render_png, jobs))
    cmd = [MAGICK, "-loop", "0"]
    for (_, png), delay in zip(jobs, delays):
        cmd += ["-delay", str(delay), png]
    gif = os.path.join(DOCS, "demo.gif")
    # No dithering: it turns smooth gradients into visible grain.
    cmd += ["+dither", "-layers", "Optimize", gif]
    subprocess.run(cmd, check=True)
    shutil.rmtree(tmp)
    return gif


# --- social preview -----------------------------------------------------------

def social_preview(card_png: str) -> str:
    """Background and text as SVG, then the rendered card pasted on top as an
    image (SVG renderers disagree about nested transforms; bitmaps don't)."""
    W, H = 1280, 640
    bg1, bg2, a1, a2 = insights.THEMES["night"]
    mix = card._mix
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">',
         "<defs>" + card._gradient("title", a1, a2) + "</defs>"]
    for i in range(40):
        o.append(f'<rect x="0" y="{i * H / 40:.1f}" width="{W}" height="{H / 40 + 1.5:.1f}" fill="{mix(bg1, bg2, 1 - i / 39)}"/>')
    o.append(f'<circle cx="1030" cy="330" r="300" fill="{mix(a1, bg1, 0.20)}"/>')
    o.append(f'<circle cx="120" cy="660" r="250" fill="{mix(a2, bg2, 0.14)}"/>')
    x = 72
    o.append(card._text(x, 196, "Terminal", 116, "url(#title)", 800))
    o.append(card._text(x, 316, "Wrapped", 116, "url(#title)", 800))
    o.append(card._text(x, 382, "Spotify Wrapped for your Linux terminal.", 32, "#ffffff", 700))
    soft = mix("#ffffff", bg1, 0.72)
    o.append(card._text(x, 430, "Your year in commands, git, packages and games,", 25, soft))
    o.append(card._text(x, 464, "plus your terminal personality and a share card.", 25, soft))
    o.append(f'<rect x="{x}" y="510" width="586" height="58" rx="29" fill="#0b0b12" stroke="{mix(a1, "#0b0b12", 0.6)}" stroke-width="2"/>')
    o.append(card._text(x + 30, 548, "github.com/ethembeldagli/termwrapped", 24, "#ffffff", 400, card.MONO))
    o.append("</svg>")

    tmp = tempfile.mkdtemp(prefix="termwrapped-social-")
    svg, bg = os.path.join(tmp, "social.svg"), os.path.join(tmp, "bg.png")
    with open(svg, "w", encoding="utf-8") as f:
        f.write("\n".join(o))
    to_png(svg, bg, W, H)
    png = os.path.join(DOCS, "social-preview.png")
    subprocess.run([
        MAGICK, bg,
        "(", card_png, "-resize", "40%", "-background", "none", "-rotate", "4",
        "(", "+clone", "-background", "black", "-shadow", "55x14+0+12", ")",
        "+swap", "-background", "none", "-layers", "merge", "+repage", ")",
        "-geometry", "+790+12", "-composite", "-flatten", png,
    ], check=True)
    shutil.rmtree(tmp)
    return png


def main() -> None:
    if not MAGICK:
        sys.exit("Needs ImageMagick (magick or convert).")
    info = system.SystemInfo(
        distro="Arch Linux", distro_id="arch", kernel="6.17.8-arch1-1", desktop="Hyprland",
        session="wayland", shell="zsh", home_born=dt.datetime(2021, 3, 14).timestamp(), uptime_hours=31,
    )
    sh = shell.collect(YEAR)
    gm = games.collect(YEAR)
    w = insights.build(YEAR, "you", sh, None, gm, None, info)
    all_slides = w.slides + [insights.outro(w, f"~/Pictures/terminal-wrapped-{YEAR}.png")]
    slides = [s for s in all_slides if any(k in s.kicker for k in GIF_SLIDES)]

    card_png = card.save(w, os.path.join(DOCS, "example-card.png"))[0]
    os.remove(os.path.join(DOCS, "example-card.svg"))
    print("card:", card_png)
    print("social preview:", social_preview(card_png))
    print(f"gif ({len(slides)} slides):", make_gif(slides))
    shutil.rmtree(HOME)


if __name__ == "__main__":
    main()
