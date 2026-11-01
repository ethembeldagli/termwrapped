"""Gaming: Steam, Heroic and Lutris playtime, all read from local files."""

from __future__ import annotations

import datetime as dt
import glob
import json
import os
import re
from dataclasses import dataclass, field

from termwrapped.util import in_year, open_sqlite_ro, read_text

NOT_GAMES = re.compile(
    r"^(Proton|Steam Linux Runtime|Steamworks Common|SteamVR|Steam Audio|Wallpaper Engine)", re.I
)


@dataclass
class Game:
    name: str
    minutes: int
    last_played: float | None
    source: str


@dataclass
class GameStats:
    games: list[Game] = field(default_factory=list)  # played this year, most played first
    sources: list[str] = field(default_factory=list)

    @property
    def hours(self) -> float:
        return sum(g.minutes for g in self.games) / 60

    def to_dict(self) -> dict:
        return {
            "sources": self.sources,
            "hours": round(self.hours, 1),
            "games": [g.__dict__ for g in self.games[:15]],
        }


# --- Valve's text KeyValues format -----------------------------------------

_VDF_TOKEN = re.compile(r'"((?:[^"\\]|\\.)*)"|([{}])|//[^\n]*')


def parse_vdf(text: str) -> dict:
    """Parse Valve's KeyValues text format. Keys are lowercased."""
    root: dict = {}
    stack = [root]
    key = None
    for m in _VDF_TOKEN.finditer(text):
        s, brace = m.group(1), m.group(2)
        if brace == "{":
            child: dict = {}
            if key is not None:
                stack[-1][key.lower()] = child
            stack.append(child)
            key = None
        elif brace == "}":
            if len(stack) > 1:
                stack.pop()
            key = None
        elif s is not None:
            if key is None:
                key = s
            else:
                stack[-1][key.lower()] = s.replace('\\"', '"').replace("\\\\", "\\")
                key = None
    return root


def _dig(d: dict, *path: str):
    for p in path:
        if not isinstance(d, dict):
            return None
        d = d.get(p)
    return d


def steam(year: int) -> list[Game]:
    candidates = [
        os.path.expanduser(p)
        for p in (
            "~/.local/share/Steam", "~/.steam/steam",
            "~/.var/app/com.valvesoftware.Steam/.local/share/Steam",
            "~/.var/app/com.valvesoftware.Steam/data/Steam",
            "~/snap/steam/common/.local/share/Steam",
        )
    ]
    roots = {os.path.realpath(p) for p in candidates if os.path.isdir(p)}
    names: dict[str, str] = {}
    playtime: dict[str, tuple[int, float | None]] = {}
    for root in roots:
        libs = {root}
        lib_vdf = parse_vdf(read_text(os.path.join(root, "steamapps/libraryfolders.vdf")) or "")
        for entry in (lib_vdf.get("libraryfolders") or {}).values():
            if isinstance(entry, dict) and entry.get("path"):
                libs.add(entry["path"])
        for lib in libs:
            for acf in glob.glob(os.path.join(lib, "steamapps/appmanifest_*.acf")):
                st = parse_vdf(read_text(acf) or "").get("appstate") or {}
                if st.get("appid") and st.get("name"):
                    names[st["appid"]] = st["name"]

        for cfg in glob.glob(os.path.join(root, "userdata/*/config/localconfig.vdf")):
            data = parse_vdf(read_text(cfg) or "")
            apps = _dig(data, "userlocalconfigstore", "software", "valve", "steam", "apps") or {}
            for appid, info in apps.items():
                if not isinstance(info, dict):
                    continue
                try:
                    minutes = int(info.get("playtime", 0))
                    last = float(info.get("lastplayed", 0)) or None
                except ValueError:
                    continue
                if minutes <= 0:
                    continue
                old = playtime.get(appid)
                if not old or old[0] < minutes:
                    playtime[appid] = (minutes, last)

    games = []
    for appid, (minutes, last) in playtime.items():
        if not in_year(last, year):
            continue
        name = names.get(appid, f"Steam app {appid}")
        if NOT_GAMES.match(name):
            continue
        games.append(Game(name, minutes, last, "Steam"))
    return games


def _iso_ts(s: str | None) -> float | None:
    if not s:
        return None
    try:
        return dt.datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def _heroic_titles(store_cache: str) -> dict[str, str]:
    titles: dict[str, str] = {}

    def walk(o, depth=0):
        if depth > 6:
            return
        if isinstance(o, dict):
            app = o.get("app_name") or o.get("appName")
            if app and o.get("title"):
                titles[str(app)] = str(o["title"])
            for v in o.values():
                walk(v, depth + 1)
        elif isinstance(o, list):
            for v in o:
                walk(v, depth + 1)

    for f in glob.glob(os.path.join(store_cache, "*_library.json")):
        try:
            with open(f, encoding="utf-8") as fh:
                walk(json.load(fh))
        except (OSError, ValueError):
            pass
    return titles


def heroic(year: int) -> list[Game]:
    games = []
    for base in ("~/.config/heroic", "~/.var/app/com.heroicgameslauncher.hgl/config/heroic"):
        base = os.path.expanduser(base)
        try:
            with open(os.path.join(base, "store/timestamp.json"), encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            continue
        titles = _heroic_titles(os.path.join(base, "store_cache"))
        for app, info in data.items():
            if not isinstance(info, dict):
                continue
            minutes = int(info.get("totalPlayed") or 0)
            last = _iso_ts(info.get("lastPlayed"))
            if minutes > 0 and in_year(last, year):
                games.append(Game(titles.get(app, app), minutes, last, "Heroic"))
    return games


def lutris(year: int) -> list[Game]:
    games = []
    for path in ("~/.local/share/lutris/pga.db", "~/.var/app/net.lutris.Lutris/data/lutris/pga.db"):
        con = open_sqlite_ro(os.path.expanduser(path))
        if not con:
            continue
        try:
            rows = con.execute("SELECT name, playtime, lastplayed FROM games WHERE playtime > 0").fetchall()
        except Exception:
            rows = []
        finally:
            con.close()
        for name, hours, last in rows:
            if in_year(float(last or 0) or None, year):
                games.append(Game(name, int(float(hours) * 60), float(last), "Lutris"))
    return games


def collect(year: int) -> GameStats | None:
    st = GameStats()
    best: dict[str, Game] = {}
    for label, fn in (("Steam", steam), ("Heroic", heroic), ("Lutris", lutris)):
        got = fn(year)
        if got:
            st.sources.append(label)
        for g in got:
            key = re.sub(r"[^a-z0-9]", "", g.name.lower())
            if key not in best or best[key].minutes < g.minutes:
                best[key] = g  # the same game imported into two launchers counts once
    st.games = sorted(best.values(), key=lambda g: g.minutes, reverse=True)
    return st if st.games else None

