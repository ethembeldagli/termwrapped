"""The machine itself: distro, desktop, kernel, container, uptime, boots."""

from __future__ import annotations

import datetime as dt
import json
import os
import platform
import re
from dataclasses import dataclass

from termwrapped.util import HOME, in_container, in_year, read_text, run


@dataclass
class SystemInfo:
    distro: str = "Linux"
    distro_id: str = ""
    variant: str = ""
    kernel: str = ""
    desktop: str = ""
    session: str = ""
    shell: str = ""
    container: str = ""        # name of the distrobox/toolbox we run in, if any
    container_distro: str = ""
    home_born: float | None = None
    uptime_hours: float = 0
    boots: int | None = None
    longest_boot_hours: float | None = None

    def to_dict(self) -> dict:
        return dict(self.__dict__)


def _os_release(path: str) -> dict:
    out = {}
    for line in (read_text(path) or "").splitlines():
        k, _, v = line.partition("=")
        if k:
            out[k.strip()] = v.strip().strip('"')
    return out


def _boots(year: int, journal_dir: str | None) -> tuple[int | None, float | None]:
    args = ["journalctl", "--list-boots", "--no-pager", "-q", "-o", "json"]
    if journal_dir:
        args[1:1] = ["-D", journal_dir]
    out = run(args, timeout=20)
    spans: list[tuple[float, float]] = []
    if out:
        try:
            for b in json.loads(out):
                # microseconds since the epoch
                spans.append((b["first_entry"] / 1e6, b["last_entry"] / 1e6))
        except (ValueError, KeyError, TypeError):
            spans = []
    if not spans:
        out = run(args[:-2], timeout=20)
        for line in (out or "").splitlines():
            stamps = re.findall(r"\d{4}-\d\d-\d\d \d\d:\d\d:\d\d", line)
            if len(stamps) == 2:
                a, b = (dt.datetime.fromisoformat(s).timestamp() for s in stamps)
                spans.append((a, b))
    spans = [s for s in spans if in_year(s[0], year)]
    if len(spans) < 3:
        return None, None  # too little journal to say anything honest
    return len(spans), max(b - a for a, b in spans) / 3600


def collect(year: int) -> SystemInfo:
    info = SystemInfo()
    local = _os_release("/etc/os-release")
    host = _os_release("/run/host/etc/os-release") if in_container() else {}
    rel = host or local
    info.distro = rel.get("PRETTY_NAME") or rel.get("NAME") or "Linux"
    info.distro_id = rel.get("ID", "")
    info.variant = rel.get("VARIANT_ID", "")
    if in_container():
        info.container = os.environ.get("CONTAINER_ID") or "a container"
        envfile = read_text("/run/.containerenv") or ""
        m = re.search(r'^name="([^"]+)"', envfile, re.M)
        if m:
            info.container = m.group(1)
        info.container_distro = local.get("PRETTY_NAME", "")

    info.kernel = platform.release()
    info.desktop = (os.environ.get("XDG_CURRENT_DESKTOP") or "").split(":")[-1]
    info.session = os.environ.get("XDG_SESSION_TYPE", "")
    info.shell = os.path.basename(os.environ.get("SHELL", ""))

    born = run(["stat", "-c", "%W", HOME])
    if born and born.strip().isdigit() and int(born) > 0:
        info.home_born = float(born)

    up = read_text("/proc/uptime")
    if up:
        info.uptime_hours = float(up.split()[0]) / 3600

    host_journal = "/run/host/var/log/journal" if in_container() else None
    if host_journal and os.access(host_journal, os.R_OK):
        info.boots, info.longest_boot_hours = _boots(year, host_journal)
    elif not in_container():
        info.boots, info.longest_boot_hours = _boots(year, None)
    return info
