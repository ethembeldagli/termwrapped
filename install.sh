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
    ui_stop
    if [ "$STEP_OPEN" = 1 ]; then printf '\n' >&2; fi
    printf '\n  %s✗ %s%s\n' "$RED$B" "$1" "$R" >&2
    shift
    for line in "$@"; do printf '    %s\n' "$line" >&2; done
    printf '\n' >&2
    exit 1
}
has() { command -v "$1" >/dev/null 2>&1; }

# >>> fullscreen ui >>>
# A full-screen, full-colour, animated menu in the style of Terminal Wrapped's
# slides, shared by the ethembeldagli installers. When the terminal can't show
# it (too small, no colour, not interactive) the plain text menu is used
# instead. INSTALLER_NO_ANIMATION=1 keeps the colours but skips the motion.
# UI_THEME is "TOP|BOTTOM|ACCENT|ACCENT2", each colour as "R G B".

UI_ESC=$(printf '\033')
UI_CR=$(printf '\r')
UI_NL='
'
UI_ACTIVE=0 UI_ANIM=0 UI_TRUE=0 UI_SHOWN=0
UI_CLEANUP="" UI_LOG="" UI_STTY="" UI_PREPARED="" UI_KEY="" UI_CHOICE=""
UI_SEL=1 UI_TICK=0 UI_FADE=0 UI_SLIDE=0 UI_BARFADE=100 UI_SHINE=-99 UI_BG_LEVEL=100
UI_TITLE="" UI_RIGHT="" UI_SUB="" UI_LINES="" UI_OPTS="" UI_FOOT="" UI_BRAND="" UI_SPARKS=""

# ui_supported: can this terminal show the full-screen menu?
ui_supported() {
    [ -z "${NO_COLOR:-}" ] || return 1
    [ -z "${PLAIN_INSTALLER:-}" ] || return 1
    case "${TERM:-dumb}" in dumb | linux | vt*) return 1 ;; esac
    case "${COLORTERM:-}" in
        truecolor | 24bit) UI_TRUE=1 ;;
        *) case "${TERM:-}" in *256col* | xterm-kitty | alacritty | wezterm | foot*) UI_TRUE=0 ;; *) return 1 ;; esac ;;
    esac
    [ -t 1 ] || return 1
    ( : </dev/tty ) 2>/dev/null || return 1
    command -v stty >/dev/null 2>&1 && command -v dd >/dev/null 2>&1 || return 1
    ui_size || return 1
    [ "$UI_COLS" -ge 60 ] && [ "$UI_ROWS" -ge 20 ] || return 1
    # Motion needs a sleep that takes fractions of a second.
    if [ -z "${INSTALLER_NO_ANIMATION:-}" ] && sleep 0.01 2>/dev/null; then UI_ANIM=1; fi
    return 0
}

ui_size() {
    _ui_size=$(stty size </dev/tty 2>/dev/null) || return 1
    UI_ROWS=${_ui_size% *} UI_COLS=${_ui_size#* }
    case "$UI_ROWS$UI_COLS" in '' | *[!0-9]*) return 1 ;; esac
    [ "$UI_ROWS" -gt 0 ]
}

ui_nap() {
    [ "$UI_ANIM" = 1 ] && sleep "$1" 2>/dev/null
    return 0
}

# ui_sgr 38|48 R G B -> UI_C, the escape for that foreground/background colour
ui_sgr() {
    if [ "$UI_TRUE" = 1 ]; then
        UI_C="${UI_ESC}[$1;2;$2;$3;$4m"
    else
        UI_C="${UI_ESC}[$1;5;$((16 + 36 * (($2 * 5 + 127) / 255) + 6 * (($3 * 5 + 127) / 255) + ($4 * 5 + 127) / 255))m"
    fi
}

# ui_mix "R G B" "R G B" STEP STEPS -> _ui_r _ui_g _ui_b and _ui_rgb
ui_mix() {
    # shellcheck disable=SC2086 # split the colours into their parts
    set -- $1 $2 "$3" "$4"
    _ui_r=$(($1 + ($4 - $1) * $7 / $8))
    _ui_g=$(($2 + ($5 - $2) * $7 / $8))
    _ui_b=$(($3 + ($6 - $3) * $7 / $8))
    _ui_rgb="$_ui_r $_ui_g $_ui_b"
}

# ui_spaces N -> _ui_sp, N spaces
ui_spaces() {
    _ui_sp=""
    _ui_sn=$1
    while [ "$_ui_sn" -gt 0 ]; do _ui_sp="$_ui_sp "; _ui_sn=$((_ui_sn - 1)); done
    return 0
}

# ui_lines TEXT -> _ui_cnt, its number of lines
ui_lines() {
    _ui_cnt=0
    _ui_rest=$1
    [ -n "$_ui_rest" ] || return 0
    _ui_cnt=1
    while :; do
        case "$_ui_rest" in
            *"$UI_NL"*) _ui_rest=${_ui_rest#*"$UI_NL"} && _ui_cnt=$((_ui_cnt + 1)) ;;
            *) return 0 ;;
        esac
    done
}

# ui_prepare: geometry and colours for this theme and terminal size.
ui_prepare() {
    _ui_old_ifs=$IFS
    IFS='|'
    # shellcheck disable=SC2086 # split the theme into its four colours
    set -- $UI_THEME
    IFS=$_ui_old_ifs
    UI_TOP=$1 UI_BOTTOM=$2 UI_ACC=$3 UI_ACC2=$4
    ui_mix "$UI_TOP" "$UI_BOTTOM" 1 2 && UI_MID=$_ui_rgb
    ui_mix "240 240 255" "$UI_TOP" 45 100 && UI_DIM_RGB=$_ui_rgb
    ui_spaces "$UI_COLS" && UI_BLANK=$_ui_sp
    UI_W=$((UI_COLS - 8))
    [ "$UI_W" -gt 66 ] && UI_W=66
    UI_X=$(((UI_COLS - UI_W) / 2 + 1))
    UI_PREPARED="$UI_ROWS:$UI_COLS"
    ui_bg_level "$UI_BG_LEVEL"
    ui_fade "$UI_FADE"
    return 0
}

# ui_bg_level PERCENT: the gradient, faded in from black by PERCENT.
ui_bg_level() {
    UI_BG_LEVEL=$1
    _ui_y=1
    while [ "$_ui_y" -le "$UI_ROWS" ]; do
        ui_mix "$UI_TOP" "$UI_BOTTOM" "$((_ui_y - 1))" "$((UI_ROWS > 1 ? UI_ROWS - 1 : 1))"
        ui_mix "0 0 0" "$_ui_rgb" "$1" 100
        ui_sgr 48 "$_ui_r" "$_ui_g" "$_ui_b"
        eval "UI_BG_$_ui_y=\$UI_C"
        _ui_y=$((_ui_y + 1))
    done
    return 0
}

# ui_colour NAME "R G B": set NAME to that text colour, faded in by UI_FADE.
ui_colour() {
    ui_mix "$UI_MID" "$2" "$UI_FADE" 100
    ui_sgr 38 "$_ui_r" "$_ui_g" "$_ui_b"
    eval "$1=\$UI_C"
}

# ui_fade PERCENT: text colours, faded in from the background by PERCENT.
ui_fade() {
    UI_FADE=$1
    ui_colour UI_FG_C "240 240 255"
    ui_colour UI_DIM_C "$UI_DIM_RGB"
    ui_colour UI_ACC_C "$UI_ACC"
    ui_colour UI_ACC2_C "$UI_ACC2"
    ui_colour UI_GOOD_C "124 255 178"
    ui_colour UI_WARN_C "255 206 92"
    ui_colour UI_BAD_C "255 112 120"
    ui_bar "$UI_BARFADE"
    return 0
}

# ui_bar PERCENT: the colour of the selection bar, faded in by PERCENT.
ui_bar() {
    UI_BARFADE=$1
    ui_mix "$UI_MID" "$UI_ACC" "$((UI_FADE * $1 / 100))" 100
    ui_sgr 48 "$_ui_r" "$_ui_g" "$_ui_b" && UI_BAR_BG=$UI_C
    ui_mix "240 240 255" "$UI_BOTTOM" "$1" 100
    ui_sgr 38 "$_ui_r" "$_ui_g" "$_ui_b" && UI_BAR_FG=$UI_C
    return 0
}

ui_start() {
    [ "$UI_ACTIVE" = 1 ] && return 0
    UI_STTY=$(stty -g </dev/tty)
    stty -echo -icanon min 0 time 1 </dev/tty
    printf '%s[?1049h%s[?25l%s[?7l' "$UI_ESC" "$UI_ESC" "$UI_ESC"
    UI_ACTIVE=1 UI_SHOWN=0 UI_PREPARED="" UI_FADE=0
    if [ "$UI_ANIM" = 1 ]; then UI_BG_LEVEL=0; else UI_BG_LEVEL=100; fi
    trap 'ui_stop; eval "${UI_CLEANUP:-:}"' EXIT
    trap 'ui_stop; exit 130' INT TERM HUP
    return 0
}

ui_stop() {
    [ "$UI_ACTIVE" = 1 ] || return 0
    printf '%s[0m%s[?7h%s[?25h%s[?1049l' "$UI_ESC" "$UI_ESC" "$UI_ESC" "$UI_ESC"
    stty "$UI_STTY" </dev/tty 2>/dev/null || true
    UI_ACTIVE=0
    return 0
}

# ui_put ROW COL TEXT: add TEXT at ROW, COL on top of that row's background.
ui_put() {
    [ "$1" -ge 1 ] && [ "$1" -le "$UI_ROWS" ] || return 0
    _ui_bg=""
    eval "_ui_bg=\$UI_BG_$1"
    UI_FRAME="$UI_FRAME${UI_ESC}[$1;$2H$_ui_bg$3"
}

# The gradient rule under the title. It draws itself in as the text fades in,
# and a light sweeps along it at UI_SHINE.
ui_rule() {
    _ui_rule=""
    _ui_len=$((UI_W * UI_FADE / 100))
    _ui_i=0
    while [ "$_ui_i" -lt "$_ui_len" ]; do
        ui_mix "$UI_ACC" "$UI_ACC2" "$_ui_i" "$UI_W"
        _ui_d=$((_ui_i - UI_SHINE))
        [ "$_ui_d" -lt 0 ] && _ui_d=$((-_ui_d))
        if [ "$_ui_d" -lt 8 ]; then ui_mix "$_ui_rgb" "255 255 255" "$((8 - _ui_d))" 11; fi
        ui_mix "$UI_MID" "$_ui_rgb" "$UI_FADE" 100
        ui_sgr 38 "$_ui_r" "$_ui_g" "$_ui_b"
        _ui_rule="$_ui_rule$UI_C━"
        _ui_i=$((_ui_i + 1))
    done
    return 0
}

# A loading bar with a bright stripe gliding back and forth.
ui_loader() {
    _ui_seg=14
    _ui_span=$((UI_W - _ui_seg))
    _ui_pos=$((UI_TICK * 2 % (2 * _ui_span)))
    [ "$_ui_pos" -gt "$_ui_span" ] && _ui_pos=$((2 * _ui_span - _ui_pos))
    ui_mix "$UI_MID" "$UI_DIM_RGB" "$((UI_FADE * 35 / 100))" 100
    ui_sgr 38 "$_ui_r" "$_ui_g" "$_ui_b" && _ui_track=$UI_C
    _ui_load=""
    _ui_i=0
    while [ "$_ui_i" -lt "$UI_W" ]; do
        if [ "$_ui_i" -ge "$_ui_pos" ] && [ "$_ui_i" -lt "$((_ui_pos + _ui_seg))" ]; then
            ui_mix "$UI_ACC" "$UI_ACC2" "$((_ui_i - _ui_pos))" "$_ui_seg"
            ui_mix "$UI_MID" "$_ui_rgb" "$UI_FADE" 100
            ui_sgr 38 "$_ui_r" "$_ui_g" "$_ui_b"
            _ui_load="$_ui_load$UI_C━"
        else
            _ui_load="$_ui_load$_ui_track─"
        fi
        _ui_i=$((_ui_i + 1))
    done
    return 0
}

# ui_draw: draw UI_TITLE, UI_SUB, UI_LINES, UI_OPTS and UI_FOOT, centred on the
# gradient, faded by UI_FADE and shifted by UI_SLIDE rows. UI_LINES holds
# "info|label|value|tone", "text|tone|text", "big|tone|text", "log|text",
# "spin|text", "load" or "blank" lines; UI_OPTS holds "key|label|hint".
ui_draw() {
    ui_size || return 0
    [ "$UI_PREPARED" = "$UI_ROWS:$UI_COLS" ] || ui_prepare
    UI_FRAME="${UI_ESC}[0m"
    _ui_y=1
    while [ "$_ui_y" -le "$UI_ROWS" ]; do
        ui_put "$_ui_y" 1 "$UI_BLANK"
        _ui_y=$((_ui_y + 1))
    done

    ui_lines "$UI_LINES" && _ui_nlines=$_ui_cnt
    ui_lines "$UI_OPTS" && _ui_nopts=$_ui_cnt
    _ui_count=4
    [ "$_ui_nlines" -gt 0 ] && _ui_count=$((_ui_count + _ui_nlines + 1))
    [ "$_ui_nopts" -gt 0 ] && _ui_count=$((_ui_count + _ui_nopts + 1))
    [ -n "$UI_FOOT" ] && _ui_count=$((_ui_count + 2))
    _ui_y=$(((UI_ROWS - _ui_count) / 2 + 1))
    [ "$_ui_y" -lt 2 ] && _ui_y=2
    UI_CARD_TOP=$_ui_y UI_CARD_BOTTOM=$((_ui_y + _ui_count))
    _ui_y=$((_ui_y + UI_SLIDE))
    _ui_x=$UI_X

    if [ "$UI_FADE" -gt 0 ]; then
        # Title, version on the right, subtitle and the gradient rule.
        ui_put "$_ui_y" "$_ui_x" "$UI_ACC_C${UI_ESC}[1m◆ $UI_FG_C$UI_TITLE${UI_ESC}[22m"
        if [ -n "$UI_RIGHT" ]; then
            ui_put "$_ui_y" "$((_ui_x + UI_W - ${#UI_RIGHT}))" "$UI_DIM_C$UI_RIGHT"
        fi
        _ui_y=$((_ui_y + 1))
        ui_put "$_ui_y" "$_ui_x" "$UI_DIM_C$UI_SUB"
        _ui_y=$((_ui_y + 1))
        UI_RULE_Y=$_ui_y
        ui_rule
        ui_put "$_ui_y" "$_ui_x" "$_ui_rule"
        _ui_y=$((_ui_y + 2))

        if [ "$_ui_nlines" -gt 0 ]; then
            while IFS='|' read -r _ui_kind _ui_a _ui_b _ui_c; do
                case "$_ui_kind" in
                    info)
                        ui_tone "$_ui_c"
                        ui_spaces "$((12 - ${#_ui_a}))"
                        ui_put "$_ui_y" "$_ui_x" "$UI_DIM_C$_ui_a$_ui_sp $_ui_tone$_ui_b"
                        ;;
                    text) ui_tone "$_ui_a" && ui_put "$_ui_y" "$_ui_x" "$_ui_tone$_ui_b" ;;
                    big) ui_tone "$_ui_a" && ui_put "$_ui_y" "$_ui_x" "$_ui_tone${UI_ESC}[1m$_ui_b${UI_ESC}[22m" ;;
                    log) ui_put "$_ui_y" "$((_ui_x + 2))" "$UI_DIM_C$_ui_a" ;;
                    spin)
                        ui_spinner
                        ui_put "$_ui_y" "$_ui_x" "$UI_ACC2_C$_ui_spin $UI_FG_C${UI_ESC}[1m$_ui_a${UI_ESC}[22m"
                        ;;
                    load) ui_loader && ui_put "$_ui_y" "$_ui_x" "$_ui_load" ;;
                esac
                _ui_y=$((_ui_y + 1))
            done <<EOF
$UI_LINES
EOF
            _ui_y=$((_ui_y + 1))
        fi

        if [ "$_ui_nopts" -gt 0 ]; then
            _ui_i=1
            while IFS='|' read -r _ui_key _ui_label _ui_hint; do
                _ui_text="$_ui_label${_ui_hint:+  $_ui_hint}"
                _ui_pad=$((UI_W - ${#_ui_text} - 7))
                [ "$_ui_pad" -lt 1 ] && _ui_pad=1
                ui_spaces "$_ui_pad"
                if [ "$_ui_i" = "$UI_SEL" ]; then
                    ui_put "$_ui_y" "$_ui_x" "$UI_BAR_BG$UI_BAR_FG${UI_ESC}[1m ▸ $_ui_label${UI_ESC}[22m${_ui_hint:+  $_ui_hint}$_ui_sp$_ui_key   "
                else
                    ui_put "$_ui_y" "$_ui_x" "   $UI_FG_C$_ui_label$UI_DIM_C${_ui_hint:+  $_ui_hint}$_ui_sp$_ui_key"
                fi
                _ui_i=$((_ui_i + 1))
                _ui_y=$((_ui_y + 1))
            done <<EOF
$UI_OPTS
EOF
            _ui_y=$((_ui_y + 1))
        fi

        if [ -n "$UI_FOOT" ]; then
            _ui_y=$((_ui_y + 1))
            ui_put "$_ui_y" "$_ui_x" "$UI_DIM_C$UI_FOOT"
        fi
    fi
    if [ -n "$UI_BRAND" ] && [ "$UI_BG_LEVEL" -ge 100 ] && [ "$UI_CARD_BOTTOM" -lt "$((UI_ROWS - 1))" ]; then
        ui_put "$UI_ROWS" "$(((UI_COLS - ${#UI_BRAND}) / 2 + 1))" "$UI_DIM_C$UI_BRAND"
    fi
    printf '%s%s' "$UI_FRAME" "$UI_SPARKS"
    return 0
}

# Redraw just the rule, for the light sweeping along it.
ui_draw_rule() {
    [ "$UI_ANIM" = 1 ] && [ "$UI_FADE" -ge 100 ] && [ -n "${UI_RULE_Y:-}" ] || return 0
    UI_FRAME=""
    ui_rule
    ui_put "$UI_RULE_Y" "$UI_X" "$_ui_rule"
    printf '%s' "$UI_FRAME"
    return 0
}

ui_tone() {
    case "$1" in
        good) _ui_tone=$UI_GOOD_C ;;
        warn) _ui_tone=$UI_WARN_C ;;
        bad) _ui_tone=$UI_BAD_C ;;
        dim) _ui_tone=$UI_DIM_C ;;
        accent) _ui_tone=$UI_ACC_C ;;
        accent2) _ui_tone=$UI_ACC2_C ;;
        *) _ui_tone=$UI_FG_C ;;
    esac
    return 0
}

ui_spinner() {
    case $((UI_TICK % 10)) in
        0) _ui_spin="⠋" ;; 1) _ui_spin="⠙" ;; 2) _ui_spin="⠹" ;; 3) _ui_spin="⠸" ;; 4) _ui_spin="⠼" ;;
        5) _ui_spin="⠴" ;; 6) _ui_spin="⠦" ;; 7) _ui_spin="⠧" ;; 8) _ui_spin="⠇" ;; *) _ui_spin="⠏" ;;
    esac
    return 0
}

# ui_show: bring the current screen in. The first one fades the gradient up
# from black; every one slides up a little while its text fades in.
ui_show() {
    ui_size || return 0
    [ "$UI_PREPARED" = "$UI_ROWS:$UI_COLS" ] || ui_prepare
    if [ "$UI_ANIM" = 1 ]; then
        if [ "$UI_SHOWN" = 0 ]; then
            ui_fade 0
            for _ui_lvl in 12 28 46 64 80 92 100; do
                ui_bg_level "$_ui_lvl" && ui_draw && ui_nap 0.03
            done
        fi
        for _ui_step in "15 3" "35 2" "55 2" "75 1" "90 1"; do
            ui_fade "${_ui_step% *}"
            UI_SLIDE=${_ui_step#* }
            ui_draw
            ui_nap 0.025
        done
    fi
    UI_SHOWN=1 UI_SLIDE=0
    [ "$UI_BG_LEVEL" = 100 ] || ui_bg_level 100
    ui_fade 100
    ui_draw
    return 0
}

# ui_hide: fade the current screen's text out, sliding it up.
ui_hide() {
    if [ "$UI_ANIM" != 1 ] || [ "$UI_FADE" = 0 ]; then
        UI_FADE=0
        return 0
    fi
    for _ui_step in "70 0" "40 -1" "15 -1" "0 -2"; do
        ui_fade "${_ui_step% *}"
        UI_SLIDE=${_ui_step#* }
        ui_draw
        ui_nap 0.025
    done
    UI_SLIDE=0
    return 0
}

# ui_key: wait a moment for a key; sets UI_KEY to up, down, enter, esc,
# char:X or "" when nothing was pressed.
ui_key() {
    _ui_k=$(dd bs=1 count=1 2>/dev/null </dev/tty; echo .)
    _ui_k=${_ui_k%.}
    case "$_ui_k" in
        "") UI_KEY="" ;;
        "$UI_ESC")
            # Read the rest of the key's sequence one byte at a time, so keys
            # typed quickly one after another aren't swallowed together.
            _ui_seq=""
            _ui_kn=0
            while [ "$_ui_kn" -lt 8 ]; do
                _ui_c=$(dd bs=1 count=1 2>/dev/null </dev/tty)
                [ -n "$_ui_c" ] || break
                _ui_seq="$_ui_seq$_ui_c"
                _ui_kn=$((_ui_kn + 1))
                [ "$_ui_kn" -gt 1 ] || continue
                case "$_ui_c" in [A-Za-z~]) break ;; esac
            done
            case "$_ui_seq" in
                "[A" | OA) UI_KEY=up ;;
                "[B" | OB) UI_KEY=down ;;
                "") UI_KEY=esc ;;
                *) UI_KEY=other ;;
            esac
            ;;
        "$UI_NL" | "$UI_CR" | " ") UI_KEY=enter ;;
        *) UI_KEY="char:$(printf '%s' "$_ui_k" | tr '[:upper:]' '[:lower:]')" ;;
    esac
    return 0
}

# ui_move N: move the selection to option N, fading the bar in.
ui_move() {
    UI_SEL=$1
    if [ "$UI_ANIM" = 1 ]; then
        ui_bar 45 && ui_draw && ui_nap 0.02
    fi
    ui_bar 100
    ui_draw
    return 0
}

# ui_choose: show the menu until something is picked; sets UI_CHOICE to the
# key of the option, or "esc".
ui_choose() {
    ui_lines "$UI_OPTS" && _ui_n=$_ui_cnt
    [ "$UI_SEL" -ge 1 ] && [ "$UI_SEL" -le "$_ui_n" ] || UI_SEL=1
    UI_FOOT="↑↓ move · enter select · or press a key"
    UI_SHINE=-99
    ui_show
    while :; do
        _ui_before="$UI_ROWS:$UI_COLS"
        ui_key
        case "$UI_KEY" in
            "")
                if ui_size && [ "$UI_ROWS:$UI_COLS" != "$_ui_before" ]; then
                    ui_draw
                elif [ "$UI_ANIM" = 1 ]; then
                    # Every few seconds a light sweeps along the rule.
                    UI_SHINE=$((UI_SHINE + 4))
                    [ "$UI_SHINE" -gt "$((UI_W + 260))" ] && UI_SHINE=-12
                    [ "$UI_SHINE" -le "$((UI_W + 12))" ] && ui_draw_rule
                fi
                ;;
            up) ui_move "$((UI_SEL > 1 ? UI_SEL - 1 : _ui_n))" ;;
            down) ui_move "$((UI_SEL < _ui_n ? UI_SEL + 1 : 1))" ;;
            enter)
                UI_CHOICE=$(printf '%s\n' "$UI_OPTS" | sed -n "${UI_SEL}p" | cut -d'|' -f1)
                break
                ;;
            esc) UI_CHOICE=esc && break ;;
            char:*)
                _ui_letter=${UI_KEY#char:}
                if printf '%s\n' "$UI_OPTS" | grep -q "^$_ui_letter|"; then
                    UI_CHOICE=$_ui_letter
                    break
                fi
                case "$_ui_letter" in
                    k) ui_move "$((UI_SEL > 1 ? UI_SEL - 1 : _ui_n))" ;;
                    j) ui_move "$((UI_SEL < _ui_n ? UI_SEL + 1 : 1))" ;;
                esac
                ;;
        esac
    done
    UI_SHINE=-99
    return 0
}

# ui_ask QUESTION DETAIL DEFAULT(y|n): a full-screen yes/no question.
ui_ask() {
    ui_hide
    _ui_saved_lines=$UI_LINES _ui_saved_opts=$UI_OPTS _ui_saved_sel=$UI_SEL
    UI_LINES="big|accent2|$1"
    [ -n "$2" ] && UI_LINES="$UI_LINES${UI_NL}text||$2"
    UI_OPTS="y|Yes|${UI_NL}n|No|"
    if [ "$3" = y ]; then UI_SEL=1; else UI_SEL=2; fi
    ui_choose
    ui_hide
    UI_LINES=$_ui_saved_lines UI_OPTS=$_ui_saved_opts UI_SEL=$_ui_saved_sel
    [ "$UI_CHOICE" = y ]
}

# ui_busy TEXT: a full-screen "please wait" while something quick runs.
ui_busy() {
    UI_LINES="spin|$1${UI_NL}load" UI_OPTS="" UI_FOOT=""
    ui_show
    return 0
}

# ui_run TITLE COMMAND...: run COMMAND with its output going to a log, showing
# the latest lines on a progress screen, then the result. Returns its status.
ui_run() {
    _ui_title=$1
    shift
    UI_LOG=$(mktemp "${TMPDIR:-/tmp}/installer.XXXXXX") || return 1
    ui_hide
    # The job can't touch the screen: it runs with the full-screen view marked
    # inactive and its questions answered by their defaults.
    # shellcheck disable=SC2030,SC2034 # UI_IN_JOB is only for the job, read by the installers' own functions
    (UI_ACTIVE=0 UI_IN_JOB=1 && "$@") </dev/null >"$UI_LOG" 2>&1 &
    _ui_pid=$!
    UI_TICK=0 UI_OPTS="" UI_FOOT=""
    _ui_log=$(ui_log_lines)
    UI_LINES="spin|$_ui_title${UI_NL}load$_ui_log"
    ui_show
    while kill -0 "$_ui_pid" 2>/dev/null; do
        if [ $((UI_TICK % 5)) = 0 ]; then _ui_log=$(ui_log_lines); fi
        UI_LINES="spin|$_ui_title${UI_NL}load$_ui_log"
        ui_draw
        UI_TICK=$((UI_TICK + 1))
        sleep 0.06 2>/dev/null || sleep 1
    done
    _ui_status=0
    wait "$_ui_pid" || _ui_status=$?
    if [ "$_ui_status" = 0 ]; then
        UI_LINES="big|good|✓ Done$(ui_log_lines)"
    else
        UI_LINES="big|bad|✗ That didn't work$(ui_log_lines)"
    fi
    UI_FOOT="Press any key to close"
    ui_draw
    if [ "$_ui_status" = 0 ]; then ui_celebrate; fi
    UI_KEY=""
    while [ -z "$UI_KEY" ]; do ui_key; done
    return "$_ui_status"
}

# A burst of sparkles across the gradient, like the end of a Wrapped slide.
ui_celebrate() {
    [ "$UI_ANIM" = 1 ] || return 0
    _ui_seed=$(($$ * 7919 % 2147483647 + 1))
    _ui_stars=""
    _ui_i=0
    _ui_tries=0
    while [ "$_ui_i" -lt 34 ] && [ "$_ui_tries" -lt 400 ]; do
        _ui_tries=$((_ui_tries + 1))
        _ui_seed=$(((_ui_seed * 1103515245 + 12345) % 2147483648))
        _ui_sy=$((_ui_seed / 7 % UI_ROWS + 1))
        _ui_seed=$(((_ui_seed * 1103515245 + 12345) % 2147483648))
        _ui_sx=$((_ui_seed / 7 % (UI_COLS - 1) + 1))
        _ui_phase=$((_ui_seed / 13 % 7))
        # Keep the card and the bottom line clear.
        [ "$_ui_sy" -lt "$((UI_ROWS - 1))" ] || continue
        if [ "$_ui_sy" -ge "$((UI_CARD_TOP - 1))" ] && [ "$_ui_sy" -le "$((UI_CARD_BOTTOM + 1))" ] \
            && [ "$_ui_sx" -ge "$((UI_X - 2))" ] && [ "$_ui_sx" -le "$((UI_X + UI_W + 1))" ]; then
            continue
        fi
        _ui_stars="$_ui_stars$_ui_sy $_ui_sx $_ui_phase$UI_NL"
        _ui_i=$((_ui_i + 1))
    done
    _ui_frame=0
    while [ "$_ui_frame" -lt 16 ]; do
        UI_SPARKS=""
        while read -r _ui_sy _ui_sx _ui_phase; do
            [ -n "$_ui_sy" ] || continue
            _ui_t=$((_ui_frame - _ui_phase))
            if [ "$_ui_t" -lt 0 ] || [ "$_ui_t" -ge 9 ]; then continue; fi
            _ui_glow=$((_ui_t < 3 ? (_ui_t + 1) * 33 : (9 - _ui_t) * 16))
            case $_ui_t in 0 | 8) _ui_star="·" ;; 1 | 7) _ui_star="⋆" ;; 2 | 6) _ui_star="✧" ;; *) _ui_star="✦" ;; esac
            if [ $(((_ui_sx + _ui_sy) % 2)) = 0 ]; then _ui_col=$UI_ACC; else _ui_col=$UI_ACC2; fi
            ui_mix "$UI_MID" "$_ui_col" "$_ui_glow" 100
            ui_sgr 38 "$_ui_r" "$_ui_g" "$_ui_b"
            _ui_bg=""
            eval "_ui_bg=\$UI_BG_$_ui_sy"
            UI_SPARKS="$UI_SPARKS${UI_ESC}[$_ui_sy;${_ui_sx}H$_ui_bg$UI_C$_ui_star"
        done <<EOF
$_ui_stars
EOF
        ui_draw
        ui_nap 0.05
        _ui_frame=$((_ui_frame + 1))
    done
    UI_SPARKS=""
    ui_draw
    return 0
}

# The last lines of the log, without colours, as "log|..." lines, padded to a
# fixed height so the card doesn't jump as lines arrive.
ui_log_lines() {
    _ui_max=$((UI_ROWS - 17))
    [ "$_ui_max" -gt 10 ] && _ui_max=10
    [ "$_ui_max" -lt 3 ] && _ui_max=3
    _ui_got=$(tail -n 40 "$UI_LOG" 2>/dev/null | tr "$UI_CR" '\n' \
        | sed -e "s/$UI_ESC\[[0-9;?]*[A-Za-z]//g" -e 's/^ *//' -e '/^$/d' -e 's/|/¦/g' \
        | fold -s -w "$((UI_W - 4))" | sed -e 's/^ *//' -e '/^$/d' \
        | tail -n "$_ui_max" | sed -e 's/^/log|/')
    ui_lines "$_ui_got"
    printf '\nblank'
    [ -n "$_ui_got" ] && printf '\n%s' "$_ui_got"
    while [ "$_ui_cnt" -lt "$_ui_max" ]; do printf '\nblank'; _ui_cnt=$((_ui_cnt + 1)); done
    return 0
}

# ui_finish: fade out, leave the full-screen view and print what the last
# ui_run did, so it stays in the terminal's scrollback.
ui_finish() {
    # shellcheck disable=SC2031 # the job's own copy of UI_ACTIVE doesn't matter here
    if [ "$UI_ACTIVE" = 1 ] && [ "$UI_ANIM" = 1 ]; then
        ui_hide
        for _ui_lvl in 75 50 25 0; do
            ui_bg_level "$_ui_lvl" && ui_draw && ui_nap 0.025
        done
    fi
    ui_stop
    if [ -n "$UI_LOG" ] && [ -f "$UI_LOG" ]; then
        printf '\n'
        cat "$UI_LOG"
        rm -f "$UI_LOG"
        UI_LOG=""
    fi
    return 0
}
# <<< fullscreen ui <<<

# Colours from Terminal Wrapped's themes.
UI_THEME="59 13 87|18 3 31|255 95 210|255 184 107"
UI_BRAND="github.com/ethembeldagli/termwrapped"

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

# The menu, full screen and in colour, when the terminal can show it. Sets
# ACTION, then runs it on a progress screen.
fullscreen_menu() {
    # shellcheck disable=SC2016 # expanded when the script exits
    UI_CLEANUP='rm -rf "$TMP"'
    ui_start
    UI_TITLE="Terminal Wrapped" UI_RIGHT="installer"
    UI_SUB="Spotify Wrapped, but for your terminal"
    if [ -z "$current" ]; then
        UI_LINES="info|Installed|not yet|dim${UI_NL}info|Latest|${latest:-unknown (offline?)}|"
        UI_OPTS="i|Install Terminal Wrapped${latest:+ $latest}|${UI_NL}q|Quit|"
        UI_SEL=1
    else
        newer=0
        if [ -n "$latest" ] && older "$current" "$latest"; then newer=1; fi
        if [ -z "$latest" ]; then
            UI_LINES="info|Installed|$current  (couldn't check for updates)|"
        elif [ "$newer" = 1 ]; then
            UI_LINES="info|Installed|$current  → $latest available|warn"
        else
            UI_LINES="info|Installed|$current  ✓ up to date|good"
        fi
        UI_LINES="$UI_LINES${UI_NL}info|Command|$(tilde "$BIN_DIR")/termwrapped|"
        UI_OPTS=""
        if [ "$newer" = 1 ]; then UI_OPTS="u|Update to $latest|$UI_NL"; fi
        UI_OPTS="${UI_OPTS}i|Reinstall|${UI_NL}d|Delete Terminal Wrapped|${UI_NL}q|Quit|"
        if [ "$newer" = 1 ]; then UI_SEL=1; else UI_SEL=$(printf '%s\n' "$UI_OPTS" | grep -c ''); fi
    fi
    ui_choose
    case "$UI_CHOICE" in
        i)
            ACTION="install"
            if [ -z "$current" ]; then title="Installing Terminal Wrapped${latest:+ $latest}"; else title="Reinstalling Terminal Wrapped"; fi
            ;;
        u) ACTION="update" title="Updating Terminal Wrapped to $latest" ;;
        d)
            if ui_ask "Delete Terminal Wrapped?" "Your share cards in ~/Pictures stay where they are." n; then
                ACTION="uninstall" title="Removing Terminal Wrapped"
            else
                ACTION="quit"
            fi
            ;;
        *) ACTION="quit" ;;
    esac
    if [ "$ACTION" = "quit" ]; then
        ui_finish
        printf '  Nothing changed.\n\n'
        return 0
    fi
    if ui_run "$title" perform; then
        ui_finish
    else
        status=$?
        ui_finish
        exit "$status"
    fi
    if [ "$RUN" = 1 ]; then
        rm -rf "$TMP"
        trap - EXIT
        if [ -r /dev/tty ]; then exec "$BIN_DIR/termwrapped" </dev/tty; else exec "$BIN_DIR/termwrapped"; fi
    fi
    return 0
}

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

    if [ -z "$ACTION" ] && interactive && ui_supported; then
        fullscreen_menu
        return
    fi
    if [ -z "$ACTION" ]; then
        if interactive; then menu; else ACTION="install"; fi
    fi
    perform
}

# Everything after the choice: install, update, check or remove.
perform() {
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

    # shellcheck disable=SC2031 # set only inside the full-screen job
    if [ "$RUN" = 1 ] && [ -z "${UI_IN_JOB:-}" ]; then
        rm -rf "$TMP"
        trap - EXIT
        printf '\n'
        if [ -r /dev/tty ]; then exec "$target" </dev/tty; else exec "$target"; fi
    fi
    printf '\n  Unwrap your year:  %s%s%s\n' "$B" "$command_name" "$R"
    printf '  %sTo update or remove it later, run the same command again.%s\n\n' "$D" "$R"
}

main "$@"
