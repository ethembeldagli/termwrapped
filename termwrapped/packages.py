"""Package manager logs: apt, dnf/dnf5, pacman and flatpak."""

from __future__ import annotations

import glob
import gzip
import os
import re
from dataclasses import dataclass, field

from termwrapped.util import open_sqlite_ro, read_text, run, year_bounds

RUNTIME_PREFIXES = (
    "org.freedesktop.", "org.gnome.Platform", "org.gnome.Sdk", "org.kde.Platform",
    "org.kde.Sdk", "org.kde.KStyle", "org.kde.PlatformTheme", "org.kde.WaylandDecoration",
    "org.gtk.Gtk3theme", "org.winehq.", "com.valvesoftware.Steam.CompatibilityTool",
    "com.valvesoftware.Steam.Utility", "io.qt.", "runtime/",
)
RUNTIME_SUFFIXES = (".Locale", ".Debug", ".Sources", ".GL", ".Codecs", ".openh264")


@dataclass
class PackageStats:
    managers: dict = field(default_factory=dict)   # name -> {"installed": n, "removed": n, "upgraded": n}
    flatpak_apps_now: int = 0
    flatpak_installed: list = field(default_factory=list)

    @property
    def installed(self) -> int:
        return sum(m.get("installed", 0) for m in self.managers.values())

    @property
    def removed(self) -> int:
        return sum(m.get("removed", 0) for m in self.managers.values())

    def to_dict(self) -> dict:
        return {
            "managers": self.managers,
            "installed": self.installed,
            "removed": self.removed,
            "flatpak_apps_now": self.flatpak_apps_now,
            "flatpak_installed": self.flatpak_installed,
        }


def _read_maybe_gz(path: str) -> str:
    if path.endswith(".gz"):
        try:
            with gzip.open(path, "rt", encoding="utf-8", errors="replace") as f:
                return f.read()
        except OSError:
            return ""
    return read_text(path) or ""


def apt(year: int) -> dict | None:
    files = glob.glob("/var/log/apt/history.log*")
    if not files:
        return None
    res = {"installed": 0, "removed": 0, "upgraded": 0}
    for f in files:
        for block in _read_maybe_gz(f).split("\n\n"):
            m = re.search(r"Start-Date: (\d{4})-", block)
            if not m or int(m.group(1)) != year:
                continue
            for kind, key in (("Install", "installed"), ("Remove", "removed"), ("Purge", "removed"), ("Upgrade", "upgraded")):
                line = re.search(rf"^{kind}: (.*)$", block, re.M)
                if not line:
                    continue
                pkgs = re.findall(r"[^,(]+\([^)]*\)", line.group(1))
                if kind == "Install":
                    pkgs = [p for p in pkgs if "automatic" not in p]  # count what you asked for
                res[key] += len(pkgs)
    return res if any(res.values()) else None


def is_image_based() -> bool:
    """Atomic distros (Silverblue, Bazzite, Aurora, bootc...) ship a dnf history
    written while the vendor built the image. It says nothing about the user."""
    return os.path.exists("/run/ostree-booted") or os.path.exists("/run/host/run/ostree-booted")


def dnf(year: int) -> dict | None:
    if is_image_based():
        return None
    start, end = year_bounds(year)
    for path in ("/usr/lib/sysimage/libdnf5/transaction_history.sqlite", "/var/lib/dnf/history.sqlite"):
        con = open_sqlite_ro(path)
        if not con:
            continue
        try:
            cols = {r[1] for r in con.execute("PRAGMA table_info(trans)")}
            text_col = "description" if "description" in cols else "cmdline"
            rows = con.execute(
                f"SELECT {text_col} FROM trans WHERE dt_begin >= ? AND dt_begin < ?", (start, end)
            ).fetchall()
        except Exception:
            rows = []
        finally:
            con.close()
        res = {"installed": 0, "removed": 0, "upgraded": 0}
        verbs = ("install", "remove", "erase", "upgrade", "update")
        for (text,) in rows:
            words = (text or "").split()
            i = next((i for i, w in enumerate(words) if w in verbs), None)
            if i is None:
                continue
            n = max(1, sum(not w.startswith("-") for w in words[i + 1:]))
            if words[i] == "install":
                res["installed"] += n
            elif words[i] in ("remove", "erase"):
                res["removed"] += n
            else:
                res["upgraded"] += 1
        if any(res.values()):
            return res
    return None


def pacman(year: int) -> dict | None:
    text = read_text("/var/log/pacman.log")
    if not text:
        return None
    res = {"installed": 0, "removed": 0, "upgraded": 0}
    rx = re.compile(r"^\[(\d{4})-\d\d-\d\d[^\]]*\] \[ALPM\] (installed|removed|upgraded) ", re.M)
    for y, action in rx.findall(text):
        if int(y) == year:
            res[action] += 1
    return res if any(res.values()) else None


def zypper(year: int) -> dict | None:
    text = read_text("/var/log/zypp/history")
    if not text:
        return None
    res = {"installed": 0, "removed": 0, "upgraded": 0}
    for line in text.splitlines():
        cols = line.split("|")
        if len(cols) < 3 or not cols[0].startswith(str(year)):
            continue
        if cols[1] == "install":
            res["installed"] += 1
        elif cols[1] == "remove":
            res["removed"] += 1
    return res if any(res.values()) else None


def _is_app(app_id: str) -> bool:
    return not app_id.startswith(RUNTIME_PREFIXES) and not app_id.endswith(RUNTIME_SUFFIXES)


def flatpak(year: int, stats: PackageStats) -> dict | None:
    now = run(["flatpak", "list", "--app", "--columns=application"])
    if now is None:
        return None
    apps_now = {a.strip() for a in now.splitlines() if a.strip()}
    stats.flatpak_apps_now = len(apps_now)
    hist = run([
        "flatpak", "history", f"--since={year}-01-01", f"--until={year + 1}-01-01",
        "--columns=change,application",
    ], timeout=30)
    res = {"installed": 0, "removed": 0, "upgraded": 0}
    seen_install: set[str] = set()
    for line in (hist or "").splitlines():
        cols = line.split("\t")
        if len(cols) < 2:
            continue
        change, app = cols[0].strip(), cols[1].strip()
        if not (app in apps_now or _is_app(app)):
            continue
        if change == "deploy install" and app not in seen_install:
            seen_install.add(app)
            res["installed"] += 1
        elif change in ("uninstall", "deploy uninstall"):
            res["removed"] += 1
        elif change == "deploy update":
            res["upgraded"] += 1
    stats.flatpak_installed = sorted(a for a in seen_install if a in apps_now)
    return res


def collect(year: int) -> PackageStats:
    st = PackageStats()
    for name, fn in (("apt", apt), ("dnf", dnf), ("pacman", pacman), ("zypper", zypper)):
        res = fn(year)
        if res:
            st.managers[name] = res
    fp = flatpak(year, st)
    if fp and any(fp.values()):
        st.managers["flatpak"] = fp
    return st

