"""Command line entry point."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import pwd
import sys
import time
import traceback

from termwrapped import __version__, card, games, gitstats, insights, packages, shell, system, tui


def _default_name() -> str:
    try:
        return pwd.getpwuid(os.getuid()).pw_name
    except KeyError:
        return os.environ.get("USER", "")


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="termwrapped",
        description="Your year in the Linux terminal, unwrapped. Everything stays on your machine.",
    )
    p.add_argument("--year", type=int, default=dt.date.today().year, help="year to unwrap (default: this year)")
    p.add_argument("--name", help="name shown on the card (default: your username)")
    p.add_argument("--anon", action="store_true", help="leave your name off the card")
    p.add_argument("--email", action="append", default=[], metavar="EMAIL",
                   help="count git commits by this email (repeatable; your git config is used too)")
    p.add_argument("--repos", action="append", default=[], metavar="DIR",
                   help="where to look for git repos (default: your home folder)")
    p.add_argument("--card", metavar="PATH", help="where to save the share card (.png or .svg)")
    p.add_argument("--no-card", action="store_true", help="don't make a share card")
    p.add_argument("--plain", action="store_true", help="print plain text instead of the slideshow")
    p.add_argument("--auto", type=float, nargs="?", const=3.0, metavar="SECONDS",
                   help="advance slides automatically (default 3s after each animation)")
    p.add_argument("--json", action="store_true", help="print the raw stats as JSON and exit")
    p.add_argument("--debug", action="store_true", help="show errors from collectors")
    p.add_argument("--version", action="version", version=f"termwrapped {__version__}")
    return p.parse_args(argv)


class Steps:
    """A tiny boot-log style progress printer on stderr."""

    def __init__(self, quiet: bool):
        self.quiet = quiet
        self.tty = sys.stderr.isatty()

    def run(self, label: str, fn, debug: bool):
        if not self.quiet:
            sys.stderr.write(f"  \x1b[2m›\x1b[0m {label}…" if self.tty else f"  > {label}... ")
            sys.stderr.flush()
        try:
            result = fn()
            mark = "\x1b[32m✓\x1b[0m" if self.tty else "ok"
        except Exception:
            result = None
            mark = "\x1b[33m–\x1b[0m" if self.tty else "skipped"
            if debug:
                traceback.print_exc()
        if not self.quiet:
            sys.stderr.write(f" {mark}\n")
        return result


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    year = args.year
    for stream in (sys.stdout, sys.stderr):
        # Never crash on a C/POSIX locale; worst case a few characters become "?".
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")
    utf8 = (sys.stdout.encoding or "").lower().replace("-", "") == "utf8"
    interactive = sys.stdin.isatty() and sys.stdout.isatty()
    plain = (
        args.plain or not interactive or not utf8 or os.environ.get("NO_COLOR")
        or os.environ.get("TERM") in ("dumb", "linux", "vt100", "vt220")  # the bare Linux console has 16 colours
    )

    steps = Steps(quiet=args.json)
    if not args.json:
        sys.stderr.write(f"\n  \x1b[1mTerminal Wrapped {year}\x1b[0m\n\n" if sys.stderr.isatty() else f"Terminal Wrapped {year}\n")
    sh = steps.run("reading shell history", lambda: shell.collect(year), args.debug)
    git = steps.run("counting your commits", lambda: gitstats.collect(year, args.email, args.repos or None), args.debug)
    pk = steps.run("checking package managers", lambda: packages.collect(year), args.debug)
    gm = steps.run("looking for games", lambda: games.collect(year), args.debug)
    si = steps.run("inspecting the machine", lambda: system.collect(year), args.debug) or system.SystemInfo()

    if args.json:
        data = {
            "year": year,
            "shell": sh.to_dict() if sh else None,
            "git": git.to_dict() if git else None,
            "packages": pk.to_dict() if pk else None,
            "games": gm.to_dict() if gm else None,
            "system": si.to_dict(),
        }
        print(json.dumps(data, indent=2, default=str))
        return 0

    name = "" if args.anon else (args.name or _default_name())
    wrapped = insights.build(year, name, sh, git, gm, pk, si)

    card_path = None
    if not args.no_card:
        target = args.card or card.default_path(year)
        result = steps.run("designing your share card", lambda: card.save(wrapped, target), args.debug)
        if result:
            card_path, tool = result
            if tool is None and not target.endswith(".svg"):
                card_path += "  (install librsvg2-tools for a PNG)"
    slides = wrapped.slides + [insights.outro(wrapped, card_path)]

    if plain:
        tui.print_plain(slides)
    else:
        time.sleep(0.4)
        tui.play(slides, auto=args.auto)

    print(f"\n  {wrapped.share_text}")
    if card_path:
        print(f"  Card: {card_path}")
    if git is not None and not git.emails:
        print("  Tip: no git identity found. Add --email you@example.com to include your commits.")
    if sh and not sh.timed:
        print("  Tip: add `export HISTTIMEFORMAT='%F %T '` to ~/.bashrc so next year's wrap knows *when* you typed.")
    print()
    return 0
