"""The share card: a 1080x1350 SVG styled as a terminal window, plus PNG export
through whatever converter the machine already has."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from xml.sax.saxutils import escape

from termwrapped import PROJECT_URL
from termwrapped.insights import THEMES, Wrapped

W, H = 1080, 1350
# Best-looking fonts first; every Linux box has at least one of the last few.
SANS = ("Inter, 'Adwaita Sans', Geist, 'Noto Sans', 'Open Sans', Roboto, Ubuntu, Cantarell, "
        "'DejaVu Sans', 'Liberation Sans', sans-serif")
MONO = ("'JetBrains Mono', 'Fira Code', 'Cascadia Code', 'Source Code Pro', 'Noto Sans Mono', "
        "'Adwaita Mono', 'DejaVu Sans Mono', 'Liberation Mono', monospace")
BASIC_RENDERERS = ("magick", "convert")  # ImageMagick's built-in SVG support


def _rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _mix(a: str, b: str, t: float) -> str:
    """Blend colour a over b with weight t. Done here, not with SVG opacity,
    because several SVG converters ignore opacity and gradients."""
    ra, rb = _rgb(a), _rgb(b)
    return "#" + "".join(f"{round(y + (x - y) * t):02x}" for x, y in zip(ra, rb))


def _text(x, y, s, size, fill="#ffffff", weight=400, family=SANS, anchor="start", extra=""):
    return (
        f'<text x="{x}" y="{y}" font-family="{family}" font-size="{size}" font-weight="{weight}" '
        f'fill="{fill}" text-anchor="{anchor}" {extra}>{escape(s)}</text>'
    )


def _gradient(gid: str, c1: str, c2: str) -> str:
    return (
        f'<linearGradient id="{gid}" x1="0" y1="0" x2="1" y2="0">'
        f'<stop offset="0" stop-color="{c1}"/><stop offset="1" stop-color="{c2}"/></linearGradient>'
    )


def _fit(s: str, size: float, max_w: float, char_w: float = 0.6) -> str:
    """Trim text that would overflow, estimating width from font size."""
    max_chars = int(max_w / (size * char_w))
    return s if len(s) <= max_chars else s[: max(1, max_chars - 1)] + "…"


def _title_layout(title: str, max_w: int) -> tuple[int, list[str]]:
    """Shrink the title onto one line if that keeps it big; otherwise wrap."""
    size = min(80, int(max_w / (len(title) * 0.6)))
    if size >= 60:
        return size, [title]
    words = title.split()
    best = min(range(1, len(words)), key=lambda i: abs(len(" ".join(words[:i])) - len(" ".join(words[i:]))))
    return 72, [" ".join(words[:best]), " ".join(words[best:])]


def render_svg(w: Wrapped, basic: bool = False) -> str:
    """basic=True avoids what ImageMagick's own SVG renderer gets wrong
    (gradients, <tspan> positioning), at the cost of a plain-coloured title."""
    bg1, bg2, accent, accent2 = THEMES[w.archetype.theme]
    top = _mix("#ffffff", bg1, 0.08)
    win = "#0b0b12"
    white = "#ffffff"
    soft = lambda t: _mix(white, win, t)  # noqa: E731  white text at opacity t

    o: list[str] = []
    o.append(f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">')
    if not basic:
        o.append("<defs>" + _gradient("title", accent, accent2) + "</defs>")
    # background gradient as overlapping bands
    bands = 60
    for i in range(bands):
        y0 = i * H / bands
        o.append(f'<rect x="0" y="{y0:.1f}" width="{W}" height="{H / bands + 1.5:.1f}" fill="{_mix(bg2, top, i / (bands - 1))}"/>')
    mid = _mix(bg2, top, 0.5)
    o.append(f'<circle cx="980" cy="130" r="300" fill="{_mix(accent, _mix(bg2, top, 0.1), 0.30)}"/>')
    o.append(f'<circle cx="70" cy="1250" r="360" fill="{_mix(accent2, _mix(bg2, top, 0.9), 0.24)}"/>')
    o.append(f'<circle cx="1010" cy="1160" r="140" fill="{_mix(accent2, mid, 0.35)}"/>')

    # terminal window
    wx, wy, ww, wh = 60, 60, W - 120, 1210
    o.append(f'<rect x="{wx}" y="{wy}" width="{ww}" height="{wh}" rx="28" fill="{win}" stroke="{soft(0.18)}" stroke-width="2"/>')
    o.append(f'<line x1="{wx}" y1="{wy + 64}" x2="{wx + ww}" y2="{wy + 64}" stroke="{soft(0.12)}" stroke-width="2"/>')
    for i, c in enumerate(("#ff5f57", "#febc2e", "#28c840")):
        o.append(f'<circle cx="{wx + 40 + i * 32}" cy="{wy + 32}" r="10" fill="{c}"/>')
    o.append(_text(W / 2, wy + 41, f"~/{w.year} — termwrapped", 22, soft(0.5), 400, MONO, "middle"))

    x0, inner = wx + 48, ww - 96
    y = wy + 140
    # A shell prompt carries the name: "ethem@bazzite:~$ termwrapped --year 2026"
    max_chars = int(inner / (30 * 0.6))
    who = f"{w.name or 'you'}@{w.host}"
    cmd = f"termwrapped --year {w.year}"
    if len(who) + 4 + len(cmd) > max_chars:
        cmd = "termwrapped"
    who = _fit(who, 30, (max_chars - 4 - len(cmd)) * 18, 0.6)
    # Separate elements at monospace offsets (30px * 0.6 per character):
    # every renderer places those correctly, unlike <tspan> runs.
    o.append(_text(x0, y, who, 30, accent, 700, MONO))
    o.append(_text(x0 + len(who) * 18, y, ":~$", 30, soft(0.6), 400, MONO))
    o.append(_text(x0 + (len(who) + 4) * 18, y, cmd, 30, soft(0.9), 400, MONO))

    y += 80
    o.append(_text(x0, y, f"MY {w.year} TERMINAL PERSONALITY", 24, soft(0.6), 700))
    size, lines = _title_layout(w.archetype.title, inner)
    for line in lines:
        y += size + 10
        o.append(_text(x0, y, line, size, accent if basic else "url(#title)", 800))
    y += 56
    o.append(_text(x0, y, _fit(w.archetype.tagline, 30, inner, 0.5), 30, soft(0.8), 400, SANS, extra='font-style="italic"'))

    # stat tiles
    tiles = w.tiles if len(lines) == 1 else w.tiles[:4]
    tile_w, tile_h, gap = (inner - 24) / 2, 118, 18
    y += 40
    for i, (label, value) in enumerate(tiles):
        tx = x0 + (i % 2) * (tile_w + 24)
        ty = y + (i // 2) * (tile_h + gap)
        o.append(f'<rect x="{tx:.0f}" y="{ty}" width="{tile_w:.0f}" height="{tile_h}" rx="18" fill="{soft(0.08)}"/>')
        o.append(_text(tx + 26, ty + 40, label.upper(), 20, soft(0.55), 700))
        mono = label == "top command"
        o.append(_text(tx + 26, ty + 96, _fit(value, 48, tile_w - 52, 0.62), 48, white, 800, MONO if mono else SANS))
    y += ((len(tiles) + 1) // 2) * (tile_h + gap) + 40

    # top commands
    if w.top_commands:
        o.append(_text(x0, y, "TOP COMMANDS", 22, soft(0.6), 700))
        y += 18
        top_n = max(n for _, n in w.top_commands)
        bar_x, bar_max = x0 + 300, inner - 300 - 110
        shown = w.top_commands[:5]
        for i, (cmd, n) in enumerate(shown):
            y += 46
            colour = _mix(accent2, accent, i / max(1, len(shown) - 1))
            o.append(_text(x0, y, f"{i + 1}", 26, accent, 700, MONO))
            o.append(_text(x0 + 44, y, _fit(cmd, 28, 240, 0.62), 28, white, 700, MONO))
            bw = max(24, bar_max * n / top_n)
            o.append(f'<rect x="{bar_x}" y="{y - 22}" width="{bw:.0f}" height="24" rx="12" fill="{colour}"/>')
            o.append(_text(x0 + inner, y, f"{n:,}", 26, soft(0.85), 700, MONO, "end"))

    # footer inside the window
    o.append(_text(x0, wy + wh - 40, _fit(w.system_line, 22, inner, 0.6), 22, soft(0.5), 400, MONO))

    # under the window
    brand = "#TerminalWrapped" + (f" · {PROJECT_URL}" if PROJECT_URL else "")
    o.append(_text(W / 2, H - 32, brand, 24, white, 400, SANS, "middle"))
    o.append("</svg>")
    return "\n".join(o)


def _converters(svg: str, png: str, width: int, height: int) -> list[list[str]]:
    url = "file://" + os.path.abspath(svg)
    W, H = width, height  # noqa: N806
    cmds = [
        ["rsvg-convert", "-w", str(W), "-h", str(H), "-o", png, svg],
        # ships with gdk-pixbuf on GNOME desktops and renders through librsvg
        ["gdk-pixbuf-thumbnailer", "-s", str(max(W, H)), svg, png],
        ["inkscape", svg, "--export-type=png", f"--export-filename={png}", f"--export-width={W}"],
        ["ksvgtopng6", str(W), str(H), svg, png],
        ["ksvgtopng5", str(W), str(H), svg, png],
    ]
    for chrome in ("chromium", "chromium-browser", "google-chrome", "google-chrome-stable", "brave-browser", "microsoft-edge"):
        cmds.append([
            chrome, "--headless", "--disable-gpu", "--hide-scrollbars", f"--screenshot={png}",
            f"--window-size={W},{H}", "--default-background-color=00000000", url,
        ])
    cmds.append(["firefox", "--headless", "--screenshot", png, f"--window-size={W},{H}", url])
    cmds.append(["magick", "-background", "none", svg, png])
    cmds.append(["convert", "-background", "none", svg, png])
    return cmds


def svg_to_png(svg: str, png: str, width: int = W, height: int = H, basic_svg: str | None = None) -> str | None:
    """Try converters from best to worst quality. Returns the tool used.
    ImageMagick gets basic_svg instead, when one is given."""
    for cmd in _converters(svg, png, width, height):
        if not shutil.which(cmd[0]):
            continue
        if basic_svg and cmd[0] in BASIC_RENDERERS:
            cmd = [basic_svg if part == svg else part for part in cmd]
        try:
            if os.path.exists(png):
                os.remove(png)
            subprocess.run(cmd, capture_output=True, timeout=60, stdin=subprocess.DEVNULL)
        except (OSError, subprocess.SubprocessError):
            continue
        if os.path.exists(png) and os.path.getsize(png) > 10_000:
            return cmd[0]
    return None


def default_path(year: int) -> str:
    pictures = None
    try:
        out = subprocess.run(["xdg-user-dir", "PICTURES"], capture_output=True, text=True, timeout=3)
        pictures = out.stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        pass
    for d in (pictures, os.path.expanduser("~/Pictures")):
        if d and os.path.isdir(d) and d != os.path.expanduser("~"):
            return os.path.join(d, f"terminal-wrapped-{year}.png")
    return os.path.abspath(f"terminal-wrapped-{year}.png")


def save(w: Wrapped, path: str) -> tuple[str, str | None]:
    """Write the card. Returns (path written, converter used or None for SVG only)."""
    svg_data = render_svg(w)
    base, ext = os.path.splitext(path)
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    svg_path = base + ".svg"
    with open(svg_path, "w", encoding="utf-8") as f:
        f.write(svg_data)
    if ext.lower() == ".svg":
        return svg_path, None
    with tempfile.TemporaryDirectory() as tmp:
        tmp_png = os.path.join(tmp, "card.png")
        basic = os.path.join(tmp, "basic.svg")
        with open(basic, "w", encoding="utf-8") as f:
            f.write(render_svg(w, basic=True))
        tool = svg_to_png(svg_path, tmp_png, basic_svg=basic)
        if tool:
            shutil.move(tmp_png, base + ".png")
            return base + ".png", tool
    return svg_path, None
