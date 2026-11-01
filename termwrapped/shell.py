"""Shell history: bash, zsh, fish and atuin.

Only aggregates leave this module (command names, counts, hours). Full command
lines are never returned, because they routinely contain tokens and passwords.
"""

from __future__ import annotations

import collections
import datetime as dt
import glob
import os
import re
import shlex
import shutil
from dataclasses import dataclass, field

from termwrapped.util import HOME, in_year, open_sqlite_ro, read_text

# --- reading history files -------------------------------------------------


@dataclass
class Entry:
    cmd: str
    ts: float | None
    exit: int | None = None


def _bash_files() -> list[str]:
    files = [os.path.join(HOME, ".bash_history")]
    if os.environ.get("HISTFILE"):
        files.append(os.environ["HISTFILE"])
    return files


def read_bash(path: str) -> list[Entry]:
    text = read_text(path)
    if not text:
        return []
    entries, ts, heredoc_end = [], None, None
    skipped: list[str] = []
    for line in text.splitlines():
        if heredoc_end is not None:
            # bash writes heredoc bodies as separate lines; they are not commands
            if line.strip() == heredoc_end:
                heredoc_end = None
                skipped = []
            else:
                skipped.append(line)
            continue
        if re.fullmatch(r"#\d{9,11}", line):
            ts = float(line[1:])
            continue
        if line.strip():
            entries.append(Entry(line, ts))
            m = re.search(r"<<-?\s*['\"]?(\w+)['\"]?", line)
            if m and not re.search(r"<<<", line):
                heredoc_end = m.group(1)
        ts = None
    # A "heredoc" that never closed was probably a false match; keep those lines.
    entries.extend(Entry(s, None) for s in skipped if s.strip())
    return entries


def _unmetafy(raw: bytes) -> bytes:
    # zsh stores some bytes as 0x83 followed by the byte XOR 32.
    out, it = bytearray(), iter(raw)
    for b in it:
        if b == 0x83:
            nxt = next(it, None)
            if nxt is not None:
                out.append(nxt ^ 32)
        else:
            out.append(b)
    return bytes(out)


def read_zsh(path: str) -> list[Entry]:
    try:
        with open(path, "rb") as f:
            text = _unmetafy(f.read()).decode("utf-8", errors="replace")
    except OSError:
        return []
    entries: list[Entry] = []
    pending = ""
    for line in text.splitlines():
        if pending:
            pending += "\n" + line
        else:
            pending = line
        if pending.endswith("\\"):
            continue
        m = re.match(r": (\d+):\d+;(.*)", pending, re.S)
        if m:
            entries.append(Entry(m.group(2), float(m.group(1))))
        elif pending.strip():
            entries.append(Entry(pending, None))
        pending = ""
    return entries


def read_fish(path: str) -> list[Entry]:
    text = read_text(path)
    if not text:
        return []
    entries: list[Entry] = []
    for line in text.splitlines():
        if line.startswith("- cmd: "):
            cmd = line[7:].replace("\\n", "\n").replace("\\\\", "\\")
            entries.append(Entry(cmd, None))
        elif line.startswith("  when: ") and entries:
            try:
                entries[-1].ts = float(line[8:])
            except ValueError:
                pass
    return entries


def read_atuin(path: str) -> list[Entry]:
    con = open_sqlite_ro(path)
    if not con:
        return []
    try:
        rows = con.execute(
            "SELECT command, timestamp, exit FROM history WHERE deleted_at IS NULL"
        ).fetchall()
    except Exception:
        try:
            rows = con.execute("SELECT command, timestamp, exit FROM history").fetchall()
        except Exception:
            rows = []
    finally:
        con.close()
    # atuin stores nanoseconds
    return [Entry(c, ts / 1e9 if ts else None, ex) for c, ts, ex in rows if c]


def load_history() -> tuple[list[Entry], list[str]]:
    """Return all history entries plus the names of the sources used."""
    data_home = os.environ.get("XDG_DATA_HOME") or os.path.join(HOME, ".local/share")
    atuin = read_atuin(os.path.join(data_home, "atuin/history.db"))
    if atuin:
        # atuin records everything the shell does, so the plain files would
        # only double count.
        return atuin, ["atuin"]

    entries: list[Entry] = []
    sources: list[str] = []
    seen: set[str] = set()

    def add(kind: str, path: str, reader) -> None:
        real = os.path.realpath(path)
        if real in seen or not os.path.isfile(real):
            return
        seen.add(real)
        got = reader(real)
        if got:
            entries.extend(got)
            sources.append(kind)

    for p in _bash_files():
        add("bash", p, read_bash)
    zdot = os.environ.get("ZDOTDIR", HOME)
    for name in (".zsh_history", ".zhistory", ".histfile"):
        add("zsh", os.path.join(zdot, name), read_zsh)
        add("zsh", os.path.join(HOME, name), read_zsh)
    add("fish", os.path.join(data_home, "fish/fish_history"), read_fish)
    return entries, sorted(set(sources))


# --- understanding commands ------------------------------------------------

WRAPPERS = {"sudo", "doas", "run0", "pkexec"}
PASSTHROUGH = {"time", "nohup", "env", "nice", "ionice", "exec", "command", "builtin", "stdbuf"}
SEPARATORS = {"|", "||", "&&", ";", "&", "|&", ";;", "(", ")"}

# Commands where the second word is the interesting part ("git push").
SUBCOMMAND_TOOLS = {
    "git", "docker", "podman", "flatpak", "apt", "apt-get", "dnf", "dnf5", "yum",
    "zypper", "systemctl", "npm", "pnpm", "yarn", "cargo", "go", "kubectl",
    "distrobox", "toolbox", "rpm-ostree", "bootc", "ujust", "brew", "snap", "pip",
    "pip3", "uv", "gh", "journalctl", "nmcli", "bluetoothctl",
}

EDITORS = {
    "vim": "Vim", "vi": "Vim", "nvim": "Neovim", "nano": "nano", "emacs": "Emacs",
    "emacsclient": "Emacs", "micro": "micro", "hx": "Helix", "helix": "Helix",
    "code": "VS Code", "codium": "VSCodium", "kate": "Kate", "gedit": "gedit",
    "gnome-text-editor": "Text Editor", "kak": "Kakoune", "zed": "Zed", "ed": "ed",
}

FETCHES = {"neofetch", "fastfetch", "screenfetch", "hyfetch", "pfetch", "macchina", "cpufetch", "uwufetch", "nitch"}
AI_TOOLS = {"claude", "ollama", "aider", "gemini", "codex", "llm", "sgpt", "chatgpt", "opencode", "goose", "crush"}
CONTAINER_TOOLS = {"docker", "podman", "distrobox", "toolbox", "kubectl", "lxc", "incus", "docker-compose", "podman-compose"}
BUILD_TOOLS = {"make", "cmake", "cargo", "npm", "pnpm", "yarn", "bun", "gcc", "g++", "clang", "go", "gradle", "mvn", "meson", "ninja", "rustc", "zig"}
PKG_TOOLS = {"apt", "apt-get", "dnf", "dnf5", "yum", "pacman", "yay", "paru", "zypper", "flatpak", "snap", "rpm-ostree", "brew", "emerge", "xbps-install", "nix-env", "apk"}
VIM_QUITS = {":q", ":wq", ":q!", ":wq!", ":x", ":qa", ":qa!", "ZZ", ":w"}

# Classic typos and what they meant. Anything else is caught by edit distance.
KNOWN_TYPOS = {
    "sl": "ls", "gti": "git", "got": "git", "gi": "git", "claer": "clear", "clea": "clear",
    "celar": "clear", "cler": "clear", "pyhton": "python", "pytohn": "python",
    "pyton": "python", "sudp": "sudo", "suod": "sudo", "sduo": "sudo", "grpe": "grep",
    "gerp": "grep", "mkae": "make", "amke": "make", "ehco": "echo", "exti": "exit",
    "eixt": "exit", "cd..": "cd ..", "sl-la": "ls -la", "ls-la": "ls -la", "ls-l": "ls -l",
    "nnao": "nano", "nanp": "nano", "vmi": "vim", "ivm": "vim", "cta": "cat",
}

# Real commands that may simply not be installed where we run (e.g. inside a
# distrobox), so they must never be reported as typos.
WELL_KNOWN = set(
    "npm npx node pnpm yarn bun deno cargo rustc rustup go java javac mvn gradle python python3 "
    "pip pip3 pipx uv ruby gem php perl lua make cmake gcc g++ clang docker podman kubectl helm "
    "distrobox toolbox flatpak snap apt apt-get dnf dnf5 yum rpm rpm-ostree bootc ujust brh "
    "pacman yay paru zypper brew nix emerge apk xbps-install git gh vim nvim nano emacs code "
    "codium micro hx tmux screen zellij htop btop top ssh scp rsync curl wget jq yq fzf rg fd "
    "bat eza exa lsd zoxide z tldr man systemctl journalctl nmcli ip ping sudo doas su "
    "steam lutris heroic gamescope mangohud protontricks winetricks wine ffmpeg yt-dlp mpv "
    "neofetch fastfetch claude ollama aider gemini codex sl cowsay figlet lolcat".split()
)
SHELL_KEYWORDS = set("do done then fi else elif esac in case for while until if select function time".split())

# Common aliases that will not show up on PATH.
COMMON_ALIASES = {"ll", "la", "l", "..", "...", "g", "k", "py", "lla", "lt"}

SHELL_BUILTINS = set(
    "alias bg bind break builtin caller cd command compgen complete compopt continue declare "
    "dirs disown echo enable eval exec exit export false fc fg getopts hash help history jobs "
    "kill let local logout mapfile popd printf pushd pwd read readarray readonly return set "
    "shift shopt source suspend test times trap true type typeset ulimit umask unalias unset "
    "wait . [ [[ if then else fi for while do done case esac function select until time "
    "functions abbr set_color string math funced funcsave rehash setopt unsetopt autoload "
    "bindkey zle compdef where whence".split()
)

DANGER_PATTERNS = {
    "rm -rf": re.compile(r"\brm\s+(-\w*r\w*f\w*|-\w*f\w*r\w*|-r\s+-f|-f\s+-r|--recursive\s+--force|--force\s+--recursive)\b", re.I),
    "chmod 777": re.compile(r"\bchmod\s+(-R\s+)?0?777\b"),
    "curl | sh": re.compile(r"\b(curl|wget)\b[^|]*\|\s*(sudo\s+)?(ba|z|fi|da)?sh\b"),
    "git push --force": re.compile(r"\bgit\s+push\b[^|;&]*\s(--force\b|-f\b|--force-with-lease\b)"),
    "dd of=/dev/…": re.compile(r"\bdd\b[^|;&]*\bof=/dev/"),
}

INSTALL_VERBS = {"install", "in", "add", "-S", "-Syu", "-Sy", "-U"}
REMOVE_VERBS = {"remove", "rm", "erase", "purge", "uninstall", "autoremove", "-R", "-Rs", "-Rns", "-Rn", "-Rsc"}

_ENV_ASSIGN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
_SAFE_WORD = re.compile(r"^[a-z][a-z0-9._+-]{0,24}$")


def tokenize(cmd: str) -> list[str]:
    try:
        lex = shlex.shlex(cmd, posix=True, punctuation_chars=True)
        lex.whitespace_split = True
        lex.commenters = ""
        return list(lex)
    except ValueError:
        return re.findall(r"\|\||&&|[|;&()]|[^\s|;&()]+", cmd)


def segments(tokens: list[str]) -> list[list[str]]:
    segs, cur = [], []
    for t in tokens:
        if t in SEPARATORS:
            if cur:
                segs.append(cur)
            cur = []
        else:
            cur.append(t)
    if cur:
        segs.append(cur)
    return segs


def osa_distance(a: str, b: str) -> int:
    """Optimal string alignment distance (Levenshtein + adjacent swaps)."""
    if abs(len(a) - len(b)) > 2:
        return 3
    d = [[0] * (len(b) + 1) for _ in range(len(a) + 1)]
    for i in range(len(a) + 1):
        d[i][0] = i
    for j in range(len(b) + 1):
        d[0][j] = j
    for i in range(1, len(a) + 1):
        for j in range(1, len(b) + 1):
            cost = a[i - 1] != b[j - 1]
            d[i][j] = min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + cost)
            if i > 1 and j > 1 and a[i - 1] == b[j - 2] and a[i - 2] == b[j - 1]:
                d[i][j] = min(d[i][j], d[i - 2][j - 2] + 1)
    return d[len(a)][len(b)]


def _user_aliases() -> set[str]:
    names: set[str] = set()
    files = [
        "~/.bashrc", "~/.bash_aliases", "~/.bash_profile", "~/.profile", "~/.zshrc",
        "~/.config/fish/config.fish", "/etc/bashrc", "/etc/bash.bashrc",
    ]
    files += glob.glob("/etc/profile.d/*.sh")
    files += glob.glob(os.path.expanduser("~/.config/fish/functions/*.fish"))
    files += glob.glob(os.path.expanduser("~/.bashrc.d/*"))
    for f in files:
        f = os.path.expanduser(f)
        if f.endswith(".fish") and "/functions/" in f:
            names.add(os.path.basename(f)[:-5])
            continue
        text = read_text(f) or ""
        names.update(re.findall(r"^\s*alias\s+(?:-\w+\s+)?([\w.+-]+)[=\s]", text, re.M))
        names.update(re.findall(r"^\s*(?:function\s+)?([\w.+-]+)\s*\(\)", text, re.M))
        names.update(re.findall(r"^\s*function\s+([\w.+-]+)", text, re.M))
        names.update(re.findall(r"^\s*abbr\s+(?:-a\s+)?(?:--\w+\s+)?([\w.+-]+)\s", text, re.M))
    return names


class CommandOracle:
    """Answers "is this a real command on this machine?" including the host
    filesystem when we're running inside a distrobox/toolbox container."""

    HOST_BINS = ["/run/host/usr/bin", "/run/host/usr/sbin", "/run/host/usr/local/bin", "/run/host/bin"]

    def __init__(self) -> None:
        self.aliases = _user_aliases() | COMMON_ALIASES
        self.cache: dict[str, bool] = {}
        self.extra_dirs = [d for d in self.HOST_BINS if os.path.isdir(d)]
        self.extra_dirs += [os.path.expanduser(p) for p in ("~/.local/bin", "~/bin", "~/.cargo/bin", "~/go/bin")]
        for d in ("/var/lib/flatpak/exports/bin", os.path.expanduser("~/.local/share/flatpak/exports/bin")):
            if os.path.isdir(d):
                self.extra_dirs.append(d)

    def exists(self, name: str) -> bool:
        if name in self.cache:
            return self.cache[name]
        ok = (
            name in WELL_KNOWN
            or name in SHELL_BUILTINS
            or name in self.aliases
            or "/" in name
            or shutil.which(name) is not None
            or any(os.path.exists(os.path.join(d, name)) for d in self.extra_dirs)
        )
        self.cache[name] = ok
        return ok


@dataclass
class ShellStats:
    sources: list[str] = field(default_factory=list)
    total: int = 0                      # command lines considered
    timed: bool = False                 # did we have timestamps?
    filtered_to_year: bool = False
    programs: collections.Counter = field(default_factory=collections.Counter)
    combos: collections.Counter = field(default_factory=collections.Counter)
    sudo: int = 0
    editors: collections.Counter = field(default_factory=collections.Counter)
    typos: collections.Counter = field(default_factory=collections.Counter)  # "typo -> meant"
    vim_quits: int = 0
    danger: collections.Counter = field(default_factory=collections.Counter)
    fetches: int = 0
    fetch_tool: str = ""
    ai: collections.Counter = field(default_factory=collections.Counter)
    containers: int = 0
    builds: int = 0
    pkg_cmds: int = 0
    installs_requested: int = 0
    removes_requested: int = 0
    rebases: int = 0
    man_pages: int = 0
    clears: int = 0
    cd_ls: int = 0
    hours: collections.Counter = field(default_factory=collections.Counter)
    failed: int | None = None
    longest_words: int = 0

    def to_dict(self) -> dict:
        d = dict(self.__dict__)
        for k, v in d.items():
            if isinstance(v, collections.Counter):
                d[k] = dict(v.most_common())
        return d


def _strip_prefix(seg: list[str]) -> tuple[list[str], bool]:
    """Drop env assignments and sudo/time-like wrappers. Returns (rest, used_sudo)."""
    used_sudo = False
    i = 0
    while i < len(seg):
        t = seg[i]
        if _ENV_ASSIGN.match(t):
            i += 1
        elif t in WRAPPERS:
            used_sudo = True
            i += 1
            while i < len(seg) and seg[i].startswith("-"):
                takes_arg = seg[i] in ("-u", "-g", "-C", "-h", "-p", "-U", "-r", "-t")
                i += 2 if takes_arg else 1
        elif t in PASSTHROUGH:
            i += 1
            while i < len(seg) and seg[i].startswith("-"):
                i += 1
        else:
            break
    return seg[i:], used_sudo


def analyze(entries: list[Entry], year: int) -> ShellStats:
    st = ShellStats()
    st.timed = any(e.ts is not None for e in entries)
    # If most of the history has timestamps, scope it to the year.
    timed_share = sum(e.ts is not None for e in entries) / max(1, len(entries))
    if timed_share > 0.5:
        st.filtered_to_year = True
        entries = [e for e in entries if in_year(e.ts, year)]

    oracle = CommandOracle()
    failed = 0
    have_exit = any(e.exit is not None for e in entries)
    unknown_first: collections.Counter = collections.Counter()

    for e in entries:
        cmd = e.cmd.strip()
        if not cmd or cmd.startswith("#"):
            continue
        st.total += 1
        if e.ts is not None:
            st.hours[dt.datetime.fromtimestamp(e.ts).hour] += 1
        if have_exit and e.exit not in (0, None):
            failed += 1

        for name, rx in DANGER_PATTERNS.items():
            if rx.search(cmd):
                st.danger[name] += 1

        segs = segments(tokenize(cmd))
        sudo_here = False
        for seg in segs:
            rest, used_sudo = _strip_prefix(seg)
            sudo_here |= used_sudo
            if not rest:
                continue
            first = rest[0]
            if first in VIM_QUITS:
                st.vim_quits += 1
                continue
            prog = os.path.basename(first) if first.startswith("/") else first
            if prog in SHELL_KEYWORDS or (not _SAFE_WORD.match(prog) and not prog.startswith("./")):
                continue
            if prog.startswith("./"):
                prog = "./script"
            st.programs[prog] += 1

            if prog in KNOWN_TYPOS and not oracle.exists(prog):
                st.typos[f"{prog} -> {KNOWN_TYPOS[prog]}"] += 1
            elif not oracle.exists(prog):
                unknown_first[prog] += 1

            sub = next((t for t in rest[1:] if not t.startswith("-")), None)
            if prog in SUBCOMMAND_TOOLS and sub and _SAFE_WORD.match(sub):
                st.combos[f"{prog} {sub}"] += 1
            if prog in EDITORS:
                st.editors[EDITORS[prog]] += 1
            if prog in FETCHES:
                st.fetches += 1
                st.fetch_tool = st.fetch_tool or prog
            if prog in AI_TOOLS:
                st.ai[prog] += 1
            if prog in CONTAINER_TOOLS:
                st.containers += 1
            if prog in BUILD_TOOLS:
                st.builds += 1
            if prog in ("cd", "ls", "ll", "la", "eza", "exa", "lsd"):
                st.cd_ls += 1
            if prog == "man" or prog == "tldr":
                st.man_pages += 1
            if prog in ("clear", "cls", "reset"):
                st.clears += 1
            if prog in PKG_TOOLS or prog in ("pip", "pip3", "pipx", "cargo", "ujust"):
                if prog in PKG_TOOLS or prog == "ujust":
                    st.pkg_cmds += 1
                words = [t for t in rest[1:] if not t.startswith("--")]
                if words:
                    verb = words[0]
                    names = [w for w in words[1:] if not w.startswith("-")]
                    if verb in INSTALL_VERBS and (prog not in ("cargo",) or verb == "install"):
                        st.installs_requested += max(1, len(names))
                    elif verb in REMOVE_VERBS:
                        st.removes_requested += max(1, len(names))
                    if verb == "rebase" or (prog == "bootc" and verb == "switch"):
                        st.rebases += 1
            if prog in ("brh", "bazzite-rollback-helper") and "rebase" in rest:
                st.rebases += 1
        if sudo_here:
            st.sudo += 1
        st.longest_words = max(st.longest_words, len(cmd.split()))

    # Unknown commands one edit away from something the user really runs are typos.
    real_top = [
        p for p, _ in st.programs.most_common(80)
        if oracle.exists(p) and len(p) >= 2 and p not in SHELL_BUILTINS
    ]
    for word, n in unknown_first.items():
        if len(word) < 3 or word in KNOWN_TYPOS:
            continue
        target = next((p for p in real_top if p != word and osa_distance(word, p) == 1), None)
        # Something you typed far more often than its "correct" spelling is a habit, not a typo.
        if target and st.programs[target] >= n:
            st.typos[f"{word} -> {target}"] += n

    # Typos are not programs; keep them out of the top list.
    for key in st.typos:
        st.programs.pop(key.split(" -> ")[0], None)

    st.failed = failed if have_exit else None
    return st


def collect(year: int) -> ShellStats | None:
    entries, sources = load_history()
    if not entries:
        return None
    st = analyze(entries, year)
    st.sources = sources
    return st if st.total else None
