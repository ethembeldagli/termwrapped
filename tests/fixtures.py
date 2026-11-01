"""Builds fake home folders for tests and for the example card.

    python3 tests/fixtures.py /tmp/demo-home   # then: HOME=/tmp/demo-home python3 -m termwrapped --year 2025
"""

from __future__ import annotations

import datetime as dt
import json
import os
import random
import subprocess
import sys

YEAR = 2025
EMAIL = "you@example.com"


def ts(month: int, day: int, hour: int, minute: int = 0) -> int:
    return int(dt.datetime(YEAR, month, day, hour, minute, tzinfo=dt.timezone.utc).timestamp())


def write(path: str, data, mode: str = "w") -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, mode) as f:
        f.write(data)


# A small, exactly countable bash history.
BASH_COMMANDS = [
    (ts(1, 5, 10), "git status"),
    (ts(1, 5, 10), "git status"),
    (ts(1, 5, 11), "vim notes.md"),
    (ts(1, 6, 2), "sudo dnf install htop btop"),
    (ts(1, 6, 2), "gti status"),
    (ts(1, 6, 3), ":q"),
    (ts(1, 7, 14), "rm -rf build"),
    (ts(1, 7, 14), "curl -fsSL https://example.com/install.sh | sh"),
    (ts(1, 8, 23), "git push --force origin main"),
    (ts(1, 8, 23), "FOO=1 sudo -u root ls -la /root | grep x && cd /tmp"),
    (ts(1, 9, 9), "cat > notes.txt <<EOF"),
    (ts(2, 1, 9), "fastfetch"),
    (None, "echo from-2024"),  # will be replaced with an old timestamp below
]
HEREDOC_BODY = ["bogusword one", "bogusword two", "EOF"]


def bash_history(path: str) -> None:
    lines = []
    for stamp, cmd in BASH_COMMANDS:
        stamp = stamp or int(dt.datetime(YEAR - 1, 6, 1, tzinfo=dt.timezone.utc).timestamp())
        lines += [f"#{stamp}", cmd]
        if cmd.startswith("cat > notes.txt"):
            lines += HEREDOC_BODY
    write(path, "\n".join(lines) + "\n")


def git_repo(path: str) -> None:
    os.makedirs(path, exist_ok=True)

    def git(*args, date=None, email=EMAIL):
        env = dict(os.environ)
        if date:
            env["GIT_AUTHOR_DATE"] = env["GIT_COMMITTER_DATE"] = date
        subprocess.run(
            ["git", "-c", f"user.email={email}", "-c", "user.name=Test", "-c", "commit.gpgsign=false", *args],
            cwd=path, env=env, check=True, capture_output=True,
        )

    git("init", "-q")
    for i, (date, email) in enumerate([
        (f"{YEAR - 1}-12-31T15:00:00+0000", EMAIL),
        (f"{YEAR}-03-01T02:15:00+0000", EMAIL),   # night owl
        (f"{YEAR}-03-02T14:00:00+0000", EMAIL),
        (f"{YEAR}-03-03T15:00:00+0000", EMAIL),   # 3-day streak
        (f"{YEAR}-03-04T15:00:00+0000", "someone@else.org"),
    ]):
        write(os.path.join(path, f"file{i}.py"), "print('hi')\n" * (i + 1))
        git("add", ".")
        git("commit", "-q", "-m", f"fix thing {i}", date=date, email=email)


def steam(home: str) -> None:
    root = os.path.join(home, ".local/share/Steam")
    write(os.path.join(root, "steamapps/appmanifest_123.acf"),
          '"AppState"\n{\n\t"appid"\t\t"123"\n\t"name"\t\t"Space Goose Simulator"\n}\n')
    write(os.path.join(root, "steamapps/appmanifest_456.acf"),
          '"AppState"\n{\n\t"appid"\t\t"456"\n\t"name"\t\t"Old Game"\n}\n')
    write(os.path.join(root, "steamapps/appmanifest_789.acf"),
          '"AppState"\n{\n\t"appid"\t\t"789"\n\t"name"\t\t"Proton 9.0"\n}\n')
    write(os.path.join(root, "userdata/42/config/localconfig.vdf"), f'''"UserLocalConfigStore"
{{
	"Software"
	{{
		"Valve"
		{{
			"Steam"
			{{
				"apps"
				{{
					"123" {{ "LastPlayed" "{ts(5, 1, 20)}" "Playtime" "600" }}
					"456" {{ "LastPlayed" "{ts(1, 1, 0) - 86400 * 30}" "Playtime" "6000" }}
					"789" {{ "LastPlayed" "{ts(5, 1, 20)}" "Playtime" "50" }}
				}}
			}}
		}}
	}}
}}
''')


def small_home(home: str) -> None:
    """Exactly countable data used by the tests."""
    bash_history(os.path.join(home, ".bash_history"))
    git_repo(os.path.join(home, "code/demo"))
    steam(home)


def demo_home(home: str) -> None:
    """A busy, believable year for the example card in the README."""
    rng = random.Random(7)
    weights = {
        "git": 900, "vim": 640, "ls": 610, "cd": 580, "nvim": 0, "make": 210, "cargo": 260,
        "grep": 190, "rg": 170, "ssh": 120, "docker": 90, "htop": 40, "man": 35, "fastfetch": 22,
        "claude": 60, "python3": 150, "cat": 140, "tmux": 80, "curl": 50,
    }
    subs = {"git": ["status", "commit -m wip", "push", "pull", "diff", "log --oneline", "rebase -i HEAD~3"],
            "cargo": ["build", "run", "test", "clippy"], "docker": ["ps", "compose up -d", "logs -f api"]}
    lines = []
    for prog, n in weights.items():
        for _ in range(n):
            hour = rng.choice([0, 1, 1, 2, 2, 3, 10, 14, 16, 21, 22, 23, 23, 23])
            stamp = ts(rng.randint(1, 12), rng.randint(1, 28), hour, rng.randint(0, 59))
            cmd = f"{prog} {rng.choice(subs[prog])}" if prog in subs else prog
            if rng.random() < 0.12:
                cmd = "sudo " + cmd
            lines.append((stamp, cmd))
    lines += [(ts(4, 1, 2), "gti status")] * 23 + [(ts(4, 2, 2), ":wq")] * 9
    lines += [(ts(6, 6, 3), "git push --force")] * 4 + [(ts(6, 7, 3), "rm -rf target")] * 11
    lines.sort()
    write(os.path.join(home, ".bash_history"), "".join(f"#{t}\n{c}\n" for t, c in lines))
    git_repo(os.path.join(home, "code/demo"))
    steam(home)


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "demo-home"
    (demo_home if "--small" not in sys.argv else small_home)(target)
    print(json.dumps({"home": os.path.abspath(target), "year": YEAR}))
