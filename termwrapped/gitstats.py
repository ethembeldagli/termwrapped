"""Git activity: your own commits across the repos under your home folder."""

from __future__ import annotations

import collections
import datetime as dt
import os
import re
from dataclasses import dataclass, field

from termwrapped.util import HOME, run

SKIP_DIRS = {
    "node_modules", "venv", ".venv", "__pycache__", "target", "build", "dist", "snap",
    "Steam", "steamapps", "go", "vendor", "site-packages", "Trash", "proc",
}
MAX_DIRS = 25000

LANGUAGES = {
    ".py": "Python", ".rs": "Rust", ".go": "Go", ".js": "JavaScript", ".mjs": "JavaScript",
    ".ts": "TypeScript", ".tsx": "TypeScript", ".jsx": "JavaScript", ".c": "C", ".h": "C",
    ".cpp": "C++", ".cc": "C++", ".hpp": "C++", ".java": "Java", ".kt": "Kotlin",
    ".rb": "Ruby", ".php": "PHP", ".cs": "C#", ".swift": "Swift", ".lua": "Lua",
    ".sh": "Shell", ".bash": "Shell", ".zsh": "Shell", ".fish": "Shell", ".nix": "Nix",
    ".zig": "Zig", ".dart": "Dart", ".scala": "Scala", ".hs": "Haskell", ".ex": "Elixir",
    ".exs": "Elixir", ".gd": "GDScript", ".vue": "Vue", ".svelte": "Svelte",
    ".html": "HTML", ".css": "CSS", ".scss": "CSS", ".qml": "QML", ".ml": "OCaml",
    ".jl": "Julia", ".r": "R", ".sql": "SQL", ".vim": "Vim script", ".el": "Emacs Lisp",
}

STOPWORDS = set(
    "a an the and or to of in on for with from by at is it this that be as into up "
    "add added adds update updated updates use using fix fixed fixes remove removed "
    "make change changed changes initial commit merge branch some more new wip".split()
)
SWEARS = re.compile(r"\b(fuck\w*|shit\w*|damn\w*|wtf|crap|ffs|omfg|hell)\b", re.I)


@dataclass
class GitStats:
    emails: list[str] = field(default_factory=list)
    repos_scanned: int = 0
    repos_active: int = 0
    commits: int = 0
    added: int = 0
    deleted: int = 0
    hours: collections.Counter = field(default_factory=collections.Counter)
    weekdays: collections.Counter = field(default_factory=collections.Counter)
    days: collections.Counter = field(default_factory=collections.Counter)
    languages: collections.Counter = field(default_factory=collections.Counter)
    words: collections.Counter = field(default_factory=collections.Counter)
    fix_msgs: int = 0
    wip_msgs: int = 0
    lazy_msgs: int = 0   # ".", "asdf", "stuff", "update"
    swears: int = 0
    longest_streak: int = 0
    top_repo: str = ""

    @property
    def night_commits(self) -> int:
        return sum(self.hours[h] for h in range(0, 5))

    @property
    def weekend_commits(self) -> int:
        return self.weekdays[6] + self.weekdays[7]

    def to_dict(self) -> dict:
        d = dict(self.__dict__)
        for k, v in d.items():
            if isinstance(v, collections.Counter):
                d[k] = dict(v.most_common(25))
        d["night_commits"] = self.night_commits
        d["weekend_commits"] = self.weekend_commits
        return d


def find_repos(roots: list[str], max_depth: int = 4) -> list[str]:
    repos, visited = [], 0
    stack = [(r, 0) for r in roots]
    while stack and visited < MAX_DIRS:
        path, depth = stack.pop()
        visited += 1
        try:
            with os.scandir(path) as it:
                children = list(it)
        except OSError:
            continue
        if any(c.name == ".git" for c in children):
            repos.append(path)
            continue
        if depth >= max_depth:
            continue
        for c in children:
            if c.name.startswith(".") or c.name in SKIP_DIRS:
                continue
            try:
                if c.is_dir(follow_symlinks=False):
                    stack.append((c.path, depth + 1))
            except OSError:
                pass
    return repos


def identities(repos: list[str], extra: list[str]) -> set[str]:
    emails = {e.strip().lower() for e in extra if e.strip()}
    out = run(["git", "config", "--global", "--get-all", "user.email"])
    if out:
        emails.update(e.strip().lower() for e in out.splitlines() if e.strip())
    for r in repos:
        out = run(["git", "-C", r, "config", "--get", "user.email"], timeout=5)
        if out and out.strip():
            emails.add(out.strip().lower())
    return emails


def _streak(days: set[str]) -> int:
    dates = sorted(dt.date.fromisoformat(d) for d in days)
    best = cur = 0
    prev = None
    for d in dates:
        cur = cur + 1 if prev and (d - prev).days == 1 else 1
        best = max(best, cur)
        prev = d
    return best


def collect(year: int, extra_emails: list[str], roots: list[str] | None = None) -> GitStats | None:
    if not run(["git", "--version"]):
        return None
    repos = find_repos(roots or [HOME])
    emails = identities(repos, extra_emails)
    st = GitStats(emails=sorted(emails), repos_scanned=len(repos))
    if not emails:
        return st  # caller explains how to pass --email

    seen: set[str] = set()
    per_repo: collections.Counter = collections.Counter()
    for repo in repos:
        args = [
            "git", "-C", repo, "log", "--all", "--no-merges", "-F",
            # --since/--until use the committer date and stop walking early, so
            # take a wider window here and filter on the author date below.
            f"--since={year - 1}-12-01", f"--until={year + 1}-02-01",
            "--format=%x1e%H%x1f%ae%x1f%ad%x1f%s", "--date=format:%Y-%m-%d %H %u", "--numstat",
        ]
        args += [f"--author={e}" for e in emails]
        out = run(args, timeout=30)
        if not out:
            continue
        for chunk in out.split("\x1e")[1:]:
            head, _, numstat = chunk.partition("\n")
            parts = head.split("\x1f")
            if len(parts) != 4:
                continue
            sha, email, date, subject = parts
            if email.lower() not in emails or sha in seen:
                continue
            seen.add(sha)
            day, hour, wday = date.split()
            if not day.startswith(f"{year}-"):
                continue
            st.commits += 1
            per_repo[os.path.basename(repo)] += 1
            st.days[day] += 1
            st.hours[int(hour)] += 1
            st.weekdays[int(wday)] += 1

            low = subject.lower().strip()
            if re.search(r"\bfix(e[sd])?\b", low):
                st.fix_msgs += 1
            if re.search(r"\bwip\b", low):
                st.wip_msgs += 1
            if low in {".", "..", "asdf", "stuff", "update", "changes", "fix", "test", "a", "x", "commit", "ok"}:
                st.lazy_msgs += 1
            st.swears += len(SWEARS.findall(low))
            for w in re.findall(r"[a-z][a-z'-]{2,}", low):
                if w not in STOPWORDS:
                    st.words[w] += 1

            for line in numstat.splitlines():
                cols = line.split("\t")
                if len(cols) != 3:
                    continue
                a, d, path = cols
                if a.isdigit() and d.isdigit():
                    st.added += int(a)
                    st.deleted += int(d)
                lang = LANGUAGES.get(os.path.splitext(path)[1].lower())
                if lang:
                    st.languages[lang] += 1
    st.repos_active = len(per_repo)
    st.top_repo = per_repo.most_common(1)[0][0] if per_repo else ""
    st.longest_streak = _streak(set(st.days))
    return st
