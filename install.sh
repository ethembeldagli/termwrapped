#!/bin/sh
# Terminal Wrapped installer
#
#   curl -fsSL https://raw.githubusercontent.com/ethembeldagli/termwrapped/main/install.sh | sh
#
# Run it and pick: install, update or delete. For scripts, skip the menu with an
# option (when piping, pass them after `sh -s --`):
#   --install        install or reinstall
#   --run            start termwrapped as soon as it's installed
#   --check          is there a newer version? (changes nothing)
#   --update         install only if there's a newer version
#   --version TAG    install a specific release, e.g. v0.1.0
#   --bin-dir DIR    where the command goes (default ~/.local/bin, /usr/local/bin as root)
#   --uninstall      remove termwrapped
#   --from DIR       install from a local checkout (for development and CI)
#
# Needs only Python 3.9+ and curl or wget. No sudo, no pip, nothing else.
# All the work happens in main(), called on the last line, so a download
# that gets cut off half way can never run half a script.

set -eu

REPO="ethembeldagli/termwrapped"

# --- output -----------------------------------------------------------------

if [ -t 1 ] && [ -z "${NO_COLOR:-}" ]; then
    B="$(printf '\033[1m')"; D="$(printf '\033[2m')"; R="$(printf '\033[0m')"
    RED="$(printf '\033[31m')"; GRN="$(printf '\033[32m')"; YEL="$(printf '\033[33m')"; MAG="$(printf '\033[35m')"
else
    B=""; D=""; R=""; RED=""; GRN=""; YEL=""; MAG=""
fi

STEP_OPEN=0
step() { printf '  %s›%s %s… ' "$D" "$R" "$1"; STEP_OPEN=1; }
ok() { STEP_OPEN=0; if [ -n "${1:-}" ]; then printf '%s✓%s %s%s%s\n' "$GRN" "$R" "$D" "$1" "$R"; else printf '%s✓%s\n' "$GRN" "$R"; fi; }
warn() { STEP_OPEN=0; printf '%s!%s %s\n' "$YEL" "$R" "$1"; }
die() {
    if [ "$STEP_OPEN" = 1 ]; then printf '\n' >&2; fi
    printf '\n  %s✗ %s%s\n' "$RED$B" "$1" "$R" >&2
    shift
    for line in "$@"; do printf '    %s\n' "$line" >&2; done
    printf '\n' >&2
    exit 1
}
has() { command -v "$1" >/dev/null 2>&1; }

# Show paths under $HOME as ~/...
tilde() {
    case "$1" in
        "$HOME"/*) printf '~%s' "${1#"$HOME"}" ;;
        *) printf '%s' "$1" ;;
    esac
}

usage() {
    cat <<EOF
Terminal Wrapped installer

  curl -fsSL https://raw.githubusercontent.com/$REPO/main/install.sh | sh

Run it and choose: install, update or delete.

To skip the menu (scripts, CI), add an option after  sh -s --
  --install        install or reinstall
  --run            start termwrapped as soon as it's installed
  --check          is there a newer version? (changes nothing)
  --update         install only if there's a newer version
  --version TAG    install a specific release, e.g. v0.1.0
  --bin-dir DIR    where the command goes (default ~/.local/bin, /usr/local/bin as root)
  --uninstall      remove termwrapped
  --from DIR       install from a local checkout
EOF
}

# --- environment ------------------------------------------------------------

os_field() { # print a field from /etc/os-release (pure sh: minimal images lack sed/awk)
    [ -r /etc/os-release ] || return 0
    while IFS='=' read -r key value; do
        if [ "$key" = "$1" ]; then
            value="${value#\"}"
            printf '%s' "${value%\"}"
            return 0
        fi
    done </etc/os-release
}

python_install_hint() {
    ids=" $(os_field ID) $(os_field ID_LIKE) "
    case "$ids" in
        *" nixos "*) echo "nix-shell -p python3   (or add python3 to your configuration.nix)" ;;
        *" alpine "*) echo "sudo apk add python3" ;;
        *" arch "*) echo "sudo pacman -S python" ;;
        *" opensuse"* | *" suse "* | *" sles "*) echo "sudo zypper install python3" ;;
        *" fedora "* | *" rhel "* | *" centos "*) echo "sudo dnf install python3" ;;
        *" debian "* | *" ubuntu "*) echo "sudo apt install python3" ;;
        *" void "*) echo "sudo xbps-install python3" ;;
        *" gentoo "*) echo "sudo emerge dev-lang/python" ;;
        *" solus "*) echo "sudo eopkg install python3" ;;
        *) echo "install Python 3.9 or newer with your package manager" ;;
    esac
}

find_python() {
    for candidate in python3 python3.14 python3.13 python3.12 python3.11 python3.10 python3.9 python; do
        if has "$candidate" && "$candidate" -c 'import sys; sys.exit(sys.version_info < (3, 9))' >/dev/null 2>&1; then
            PY="$candidate"
            return 0
        fi
    done
    return 1
}

download() { # url destination
    if has curl; then
        curl -fsSL --retry 3 --connect-timeout 20 -o "$2" "$1" </dev/null
    else
        wget -q -O "$2" "$1" </dev/null
    fi
}

# --- getting termwrapped.pyz ------------------------------------------------

# Build the single-file app from a source tarball or a checkout, using only Python.
build_pyz() { # source (dir or .tar.gz)  output
    "$PY" - "$1" "$2" </dev/null <<'PYEOF'
import os, shutil, sys, tarfile, tempfile, zipapp

src, out = sys.argv[1], sys.argv[2]
with tempfile.TemporaryDirectory() as stage:
    pkg = os.path.join(stage, "termwrapped")
    if os.path.isdir(src):
        shutil.copytree(os.path.join(src, "termwrapped"), pkg,
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    else:
        # Extract only termwrapped/*.py, refusing anything that tries to escape.
        with tarfile.open(src) as tf:
            for m in tf.getmembers():
                parts = m.name.split("/")
                if len(parts) != 3 or parts[1] != "termwrapped" or not m.isfile():
                    continue
                if not parts[2].endswith(".py") or ".." in parts:
                    continue
                os.makedirs(pkg, exist_ok=True)
                with tf.extractfile(m) as fsrc, open(os.path.join(pkg, parts[2]), "wb") as fdst:
                    shutil.copyfileobj(fsrc, fdst)
    if not os.path.isfile(os.path.join(pkg, "cli.py")):
        sys.exit("termwrapped sources not found")
    zipapp.create_archive(stage, out, interpreter="/usr/bin/env python3",
                          main="termwrapped.cli:main", compressed=True)
PYEOF
}

sha256_of() {
    "$PY" -c 'import hashlib, sys; print(hashlib.sha256(open(sys.argv[1], "rb").read()).hexdigest())' "$1"
}

# Try the release first (prebuilt, checksummed); fall back to building from source.
fetch() {
    pyz="$TMP/termwrapped.pyz"

    if [ -n "$FROM" ]; then
        step "building from $(tilde "$FROM")"
        [ -f "$FROM/termwrapped/cli.py" ] || die "$FROM doesn't look like a termwrapped checkout."
        build_pyz "$FROM" "$pyz" || die "Couldn't build from $FROM."
        ok
        return
    fi

    if [ -n "$VERSION" ]; then
        base="https://github.com/$REPO/releases/download/$VERSION"
        label="$VERSION"
    else
        base="https://github.com/$REPO/releases/latest/download"
        label="latest release"
    fi

    step "downloading $label"
    if download "$base/termwrapped.pyz" "$pyz" 2>/dev/null; then
        ok
        step "verifying checksum"
        if download "$base/termwrapped.pyz.sha256" "$TMP/sum" 2>/dev/null; then
            read -r want _ <"$TMP/sum"
            got="$(sha256_of "$pyz")"
            [ "$want" = "$got" ] || die "Checksum mismatch, refusing to install." "expected $want" "got      $got"
            ok
        else
            warn "no checksum published for this release, skipping"
        fi
        return
    fi

    if [ -n "$VERSION" ]; then
        printf '%sno release asset, building %s from source%s\n' "$D" "$VERSION" "$R"
        src="https://github.com/$REPO/archive/refs/tags/$VERSION.tar.gz"
    else
        printf '%sno release yet, using the latest code%s\n' "$D" "$R"
        src="https://github.com/$REPO/archive/refs/heads/main.tar.gz"
    fi
    step "downloading source"
    if ! download "$src" "$TMP/src.tar.gz" 2>/dev/null; then
        if [ -n "$VERSION" ]; then
            die "There's no termwrapped $VERSION." "See the versions at https://github.com/$REPO/releases"
        fi
        die "Couldn't download $src" "Check your internet connection and try again."
    fi
    ok
    step "building"
    build_pyz "$TMP/src.tar.gz" "$pyz" || die "Couldn't build termwrapped from source."
    ok
}

# --- versions -----------------------------------------------------------------

installed_version() {
    if [ -x "$BIN_DIR/termwrapped" ]; then
        v="$("$BIN_DIR/termwrapped" --version 2>/dev/null)" || return 0
        printf '%s' "${v#termwrapped }"
    fi
}

# The newest version: the latest release if there is one, otherwise the main branch.
latest_version() {
    if [ -n "$FROM" ]; then
        init="$FROM/termwrapped/__init__.py"
    else
        if [ -z "$VERSION" ] && download "https://api.github.com/repos/$REPO/releases/latest" "$TMP/release.json" 2>/dev/null; then
            tag="$("$PY" -c 'import json, sys; print(json.load(open(sys.argv[1])).get("tag_name", ""))' "$TMP/release.json" 2>/dev/null)"
            if [ -n "$tag" ]; then printf '%s' "${tag#v}"; return 0; fi
        fi
        ref="main"
        [ -n "$VERSION" ] && ref="$VERSION"
        init="$TMP/init.py"
        download "https://raw.githubusercontent.com/$REPO/$ref/termwrapped/__init__.py" "$init" 2>/dev/null || return 1
    fi
    "$PY" -c 'import re, sys
m = re.search(r"__version__ = \"([^\"]+)\"", open(sys.argv[1]).read())
print(m.group(1) if m else "")' "$init" 2>/dev/null
}

# Succeeds if version $1 is older than $2.
older() {
    "$PY" -c 'import sys
f = lambda v: tuple(int(p) for p in v.lstrip("v").split(".") if p.isdigit())
sys.exit(0 if f(sys.argv[1]) < f(sys.argv[2]) else 1)' "$1" "$2"
}

# --- install / uninstall ----------------------------------------------------

install_files() {
    target="$BIN_DIR/termwrapped"
    if ! mkdir -p "$BIN_DIR" 2>/dev/null || [ ! -w "$BIN_DIR" ]; then
        die "Can't write to $BIN_DIR." "Pick another place with --bin-dir, e.g.:" \
            "curl -fsSL https://raw.githubusercontent.com/$REPO/main/install.sh | sh -s -- --bin-dir ~/bin"
    fi

    previous=""
    if [ -x "$target" ]; then
        previous="$("$target" --version 2>/dev/null)" || previous=""
        previous="${previous#termwrapped }"
    fi

    step "installing to $(tilde "$target")"
    if [ "$PY" = "python3" ]; then
        # The .pyz is directly executable thanks to its #!/usr/bin/env python3 line.
        cp "$TMP/termwrapped.pyz" "$target.tmp.$$"
        chmod 755 "$target.tmp.$$"
        mv -f "$target.tmp.$$" "$target"
        rm -f "$DATA_DIR/termwrapped.pyz"  # left over from a launcher-style install
        rmdir "$DATA_DIR" 2>/dev/null || true
    else
        # No plain `python3` on PATH: keep the app in DATA_DIR and point a launcher at our Python.
        mkdir -p "$DATA_DIR"
        cp "$TMP/termwrapped.pyz" "$DATA_DIR/termwrapped.pyz"
        py_path="$(command -v "$PY")"
        printf '#!/bin/sh\n# termwrapped launcher, written by install.sh\nexec "%s" "%s/termwrapped.pyz" "$@"\n' \
            "$py_path" "$DATA_DIR" >"$target.tmp.$$"
        chmod 755 "$target.tmp.$$"
        mv -f "$target.tmp.$$" "$target"
    fi
    ok

    step "checking it runs"
    INSTALLED="$("$target" --version 2>/dev/null)" || INSTALLED=""
    INSTALLED="${INSTALLED#termwrapped }"
    [ -n "$INSTALLED" ] || die "Installed, but $(tilde "$target") --version failed." \
        "Please open an issue: https://github.com/$REPO/issues"
    if [ -n "$previous" ] && [ "$previous" != "$INSTALLED" ]; then
        ok "updated $previous → $INSTALLED"
    else
        ok "termwrapped $INSTALLED"
    fi
}

uninstall() {
    removed=0
    for f in "$BIN_DIR/termwrapped" "$DATA_DIR/termwrapped.pyz"; do
        if [ -e "$f" ]; then
            rm -f "$f"
            printf '  %s✓%s removed %s\n' "$GRN" "$R" "$(tilde "$f")"
            removed=1
        fi
    done
    rmdir "$DATA_DIR" 2>/dev/null || true
    if [ "$removed" = 0 ]; then
        printf '  Nothing to remove in %s.\n' "$(tilde "$BIN_DIR")"
    else
        printf '\n  Your share cards in ~/Pictures were left alone. Bye!\n'
    fi
}

path_advice() {
    case ":$PATH:" in
        *":$BIN_DIR:"*) return 0 ;;
    esac
    printf '\n  %s%s isn'"'"'t on your PATH yet.%s To fix that:\n' "$YEL" "$(tilde "$BIN_DIR")" "$R"
    case "$(basename "${SHELL:-sh}")" in
        fish) printf '    fish_add_path %s\n' "$BIN_DIR" ;;
        zsh) printf '    echo '"'"'export PATH="%s:$PATH"'"'"' >> ~/.zshrc && exec zsh\n' "$BIN_DIR" ;;
        bash) printf '    echo '"'"'export PATH="%s:$PATH"'"'"' >> ~/.bashrc && exec bash\n' "$BIN_DIR" ;;
        *) printf '    add %s to PATH in your shell'"'"'s startup file\n' "$BIN_DIR" ;;
    esac
    return 1
}

# --- the menu ---------------------------------------------------------------

# Can we ask the person a question? (Works even when this script is piped from curl.)
interactive() {
    [ -t 1 ] && ( : </dev/tty ) 2>/dev/null
}

ask() { # prompt -> $answer, read from the keyboard
    printf '%s' "$1"
    read -r answer </dev/tty || answer=""
}

menu() { # sets ACTION from the person's choice
    printf '\n'
    if [ -z "$current" ]; then
        printf '  Terminal Wrapped is not installed yet.\n\n'
        printf '    %s[i]%s Install Terminal Wrapped%s\n' "$B" "$R" "${latest:+ $latest}"
        printf '    %s[q]%s Quit\n\n' "$B" "$R"
        default="i"
    else
        if [ -n "$latest" ] && older "$current" "$latest"; then
            printf '  You have Terminal Wrapped %s. Version %s%s%s is available.\n\n' "$current" "$B" "$latest" "$R"
            printf '    %s[u]%s Update to %s\n' "$B" "$R" "$latest"
            default="u"
        else
            printf '  You have Terminal Wrapped %s%s.\n\n' "$current" "${latest:+, the latest version}"
            default="q"
        fi
        printf '    %s[i]%s Reinstall\n' "$B" "$R"
        printf '    %s[d]%s Delete Terminal Wrapped\n' "$B" "$R"
        printf '    %s[q]%s Quit\n\n' "$B" "$R"
    fi
    while :; do
        ask "  Choose [$default]: "
        case "${answer:-$default}" in
            i | I | install | reinstall) ACTION="install"; break ;;
            u | U | update) if [ -n "$current" ]; then ACTION="update"; break; fi ;;
            d | D | delete | uninstall | remove) if [ -n "$current" ]; then ACTION="uninstall"; break; fi ;;
            q | Q | quit | exit | n | N) ACTION="quit"; break ;;
        esac
        printf '  Please type one of the letters in brackets.\n'
    done
    printf '\n'
}

# --- main -------------------------------------------------------------------

main() {
    ACTION=""
    RUN=0
    VERSION="${TERMWRAPPED_VERSION:-}"
    BIN_DIR="${TERMWRAPPED_BIN_DIR:-}"
    FROM=""

    while [ $# -gt 0 ]; do
        case "$1" in
            --run) RUN=1 ;;
            --install) ACTION="install" ;;
            --uninstall) ACTION="uninstall" ;;
            --check) ACTION="check" ;;
            --update) ACTION="update" ;;
            --version | --bin-dir | --from)
                [ $# -ge 2 ] || die "$1 needs a value."
                case "$1" in
                    --version) VERSION="$2" ;;
                    --bin-dir) BIN_DIR="$2" ;;
                    --from) FROM="$2" ;;
                esac
                shift
                ;;
            --version=*) VERSION="${1#*=}" ;;
            --bin-dir=*) BIN_DIR="${1#*=}" ;;
            --from=*) FROM="${1#*=}" ;;
            -h | --help) usage; exit 0 ;;
            *) die "Unknown option: $1" "Run with --help to see the options." ;;
        esac
        shift
    done

    case "$VERSION" in
        "" | v*) ;;
        *) VERSION="v$VERSION" ;;
    esac

    : "${HOME:?HOME is not set}"
    if [ -z "$BIN_DIR" ]; then
        if [ "$(id -u)" = 0 ]; then BIN_DIR="/usr/local/bin"; else BIN_DIR="$HOME/.local/bin"; fi
    fi
    if [ "$(id -u)" = 0 ] && [ "$BIN_DIR" = "/usr/local/bin" ]; then
        DATA_DIR="/usr/local/share/termwrapped"
    else
        DATA_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/termwrapped"
    fi

    printf '\n  %s%sTerminal Wrapped%s %sinstaller%s\n\n' "$B" "$MAG" "$R" "$D" "$R"

    if [ "$ACTION" = "uninstall" ]; then
        uninstall
        return
    fi

    step "checking your system"
    [ "$(uname -s)" = "Linux" ] || die "Terminal Wrapped is made for Linux (this is $(uname -s))."
    find_python || die "Python 3.9 or newer is needed, and it isn't installed." \
        "Install it with:  $(python_install_hint)" "then run this installer again."
    if [ -z "$FROM" ] && ! has curl && ! has wget; then
        die "Neither curl nor wget is installed." "Install one of them and run this again."
    fi
    distro="$(os_field PRETTY_NAME)"
    ok "${distro:-Linux}, $("$PY" -c 'import platform; print("Python " + platform.python_version())')"

    TMP="$(mktemp -d 2>/dev/null || mktemp -d -t termwrapped.XXXXXX)"
    trap 'rm -rf "$TMP"' EXIT
    trap 'exit 130' INT TERM

    one_liner="curl -fsSL https://raw.githubusercontent.com/$REPO/main/install.sh | sh"
    current="$(installed_version)"
    latest=""
    if [ "$ACTION" != "install" ]; then
        step "checking for updates"
        latest="$(latest_version)" || latest=""
        if [ -n "$latest" ]; then
            ok "latest is $latest"
        else
            printf '%s!%s couldn'"'"'t check\n' "$YEL" "$R"
            STEP_OPEN=0
        fi
    fi

    if [ -z "$ACTION" ]; then
        if interactive; then menu; else ACTION="install"; fi
    fi

    case "$ACTION" in
        quit)
            printf '  Nothing changed.\n\n'
            return ;;
        uninstall)
            uninstall
            return ;;
        check)
            [ -n "$latest" ] || die "Couldn't find the latest version." "Check your internet connection and try again."
            if [ -z "$current" ]; then
                printf '\n  Terminal Wrapped is not installed yet. Install it with:\n    %s\n\n' "$one_liner"
            elif older "$current" "$latest"; then
                printf '\n  %s%sUpdate available:%s %s → %s%s%s. Run the installer again to update:\n    %s\n\n' \
                    "$B" "$YEL" "$R" "$current" "$B" "$latest" "$R" "$one_liner"
            else
                printf '\n  %s%sUp to date.%s You have Terminal Wrapped %s.\n\n' "$B" "$GRN" "$R" "$current"
            fi
            return ;;
        update)
            [ -n "$latest" ] || die "Couldn't find the latest version." "Check your internet connection and try again."
            if [ -n "$current" ] && ! older "$current" "$latest"; then
                printf '  %s%sAlready up to date%s (Terminal Wrapped %s). Nothing to do.\n\n' "$B" "$GRN" "$R" "$current"
                return
            fi ;;
    esac

    fetch
    install_files

    target="$BIN_DIR/termwrapped"
    printf '\n  %s%sDone!%s Terminal Wrapped %s is installed.\n' "$B" "$GRN" "$R" "$INSTALLED"
    if path_advice; then
        command_name="termwrapped"
    else
        command_name="$(tilde "$target")"
    fi

    if [ "$RUN" = 1 ]; then
        rm -rf "$TMP"
        trap - EXIT
        printf '\n'
        if [ -r /dev/tty ]; then exec "$target" </dev/tty; else exec "$target"; fi
    fi
    printf '\n  Unwrap your year:  %s%s%s\n' "$B" "$command_name" "$R"
    printf '  %sTo update or remove it later, run the same command again.%s\n\n' "$D" "$R"
}

main "$@"
