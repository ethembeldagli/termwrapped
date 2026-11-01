"""Turns raw stats into slides, a personality and a share card summary."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

# Each theme: background top, background bottom, accent, accent 2.
THEMES = {
    "violet": ("#3b0d57", "#12031f", "#ff5fd2", "#ffb86b"),
    "ocean": ("#043552", "#020c1b", "#3ee6ff", "#7cffb2"),
    "ember": ("#4d1207", "#160403", "#ffb000", "#ff4d6d"),
    "forest": ("#07402a", "#021108", "#b6ff5c", "#34e7a1"),
    "night": ("#151b5c", "#04051d", "#9d8cff", "#ff7ae0"),
    "candy": ("#4a0a3e", "#1a0418", "#ff8ad8", "#ffe66b"),
    "steel": ("#26303f", "#0b0e14", "#e6edf3", "#8ab4f8"),
    "toxic": ("#253600", "#0a0f00", "#d4ff00", "#00ffa3"),
}


@dataclass
class Slide:
    kicker: str
    theme: str
    blocks: list = field(default_factory=list)

    def text(self, s: str, style: str = "body") -> "Slide":
        self.blocks.append(("text", s, style))
        return self

    def number(self, value: float, suffix: str = "") -> "Slide":
        self.blocks.append(("number", value, suffix))
        return self

    def word(self, s: str) -> "Slide":
        self.blocks.append(("word", s))
        return self

    def bars(self, rows: list[tuple[str, float]], unit: str = "") -> "Slide":
        self.blocks.append(("bars", rows, unit))
        return self

    def rows(self, rows: list[tuple[str, str]]) -> "Slide":
        self.blocks.append(("list", rows))
        return self

    def gap(self) -> "Slide":
        self.blocks.append(("gap",))
        return self


@dataclass
class Archetype:
    key: str
    title: str
    tagline: str
    theme: str


ARCHETYPES = {
    "sudo": Archetype("sudo", "The Sudo Sorcerer", "Root is not a privilege. It's a lifestyle.", "ember"),
    "tinkerer": Archetype("tinkerer", "The Eternal Tinkerer", "If it ain't broke, rebase it anyway.", "toxic"),
    "gamer": Archetype("gamer", "The Proton Pilgrim", "Came to Linux to game. Stayed for the suffering.", "violet"),
    "owl": Archetype("owl", "The Night Owl", "Your best work happens after midnight. So do your worst bugs.", "night"),
    "vim": Archetype("vim", "The Vim Monk", "You have exited vim. Probably.", "forest"),
    "gambler": Archetype("gambler", "The Force Pusher", "History is written by those who --force.", "ember"),
    "chaos": Archetype("chaos", "The Chaos Agent", "rm -rf first, ask questions never.", "ember"),
    "container": Archetype("container", "The Container Captain", "Your apps live in boxes. So do you.", "ocean"),
    "ai": Archetype("ai", "The AI Whisperer", "Why type commands when you can ask for them?", "night"),
    "hoarder": Archetype("hoarder", "The Package Hoarder", "Gotta install 'em all.", "candy"),
    "ricer": Archetype("ricer", "The Ricer", "Fetch. Screenshot. Post. Repeat.", "candy"),
    "explorer": Archetype("explorer", "The Wanderer", "cd .. && ls. The journey is the destination.", "ocean"),
    "builder": Archetype("builder", "The Builder", "make. Fix. make. Fix. It compiles!", "forest"),
    "committer": Archetype("committer", "The Commit Machine", "git commit -m 'one more thing'", "forest"),
    "tourist": Archetype("tourist", "The Terminal Tourist", "Just visiting. Mostly clicking.", "steel"),
    "steady": Archetype("steady", "The Steady Hand", "No drama. Just commands that work.", "steel"),
}

TOP_QUIPS = {
    "ls": "You really like looking at your files.",
    "cd": "Always on the move.",
    "git": "Version control is your love language.",
    "grep": "Always searching for something.",
    "rg": "Always searching for something. Fast.",
    "cat": "Meow. You read a lot of files.",
    "flatpak": "Sandboxed and proud.",
    "systemctl": "You talk to systemd more than to most people.",
    "vim": "Of course it's vim.",
    "nvim": "Of course it's Neovim.",
    "python": "Snakes. Everywhere.",
    "python3": "Snakes. Everywhere.",
    "docker": "Everything is a container.",
    "podman": "Everything is a (rootless) container.",
    "clear": "Hiding the evidence?",
    "nano": "Simple. Honest. Judged by vim users.",
    "ssh": "You're never really here.",
    "curl": "Always downloading something.",
    "rm": "Destroyer of files.",
    "htop": "Watching. Always watching.",
    "btop": "Watching. Always watching. In style.",
    "ujust": "Why type it all when you can just ujust it.",
    "pacman": "Waka waka.",
    "yay": "Yay indeed.",
    "make": "It compiles. Ship it.",
    "cargo": "Fighting the borrow checker, and winning.",
    "npm": "node_modules is heavier than the sun.",
    "kubectl": "You speak fluent YAML.",
    "echo": "Echo... echo... echo...",
}

EDITOR_QUIPS = {
    "Vim": "You know how to exit. We think.",
    "Neovim": "Lua-configured and proud of it.",
    "nano": "Ctrl+X, Y, Enter. Muscle memory.",
    "Emacs": "A great operating system, lacking only a decent editor.",
    "VS Code": "GUI gang. No shame.",
    "VSCodium": "VS Code, but make it free.",
    "Helix": "Post-modern. Very cool.",
    "micro": "Small, sane, underrated.",
    "Kakoune": "Selection first. Respect.",
    "ed": "ed is the standard text editor.",
}


def _hour_label(h: int) -> str:
    return f"{h % 12 or 12} {'AM' if h < 12 else 'PM'}"


def _plural(n: int, word: str) -> str:
    return f"{n:,} {word}" + ("" if n == 1 else "s")


def score_archetypes(sh, git, games, pkgs) -> list[tuple[float, str]]:
    scores: dict[str, float] = {}
    if sh and sh.total:
        total = sh.total
        share = lambda n: n / total  # noqa: E731
        rollbacks = sh.combos.get("rpm-ostree rollback", 0) + sh.combos.get("bootc rollback", 0)
        scores["sudo"] = share(sh.sudo) / 0.12
        scores["tinkerer"] = share(sh.pkg_cmds + 5 * (sh.rebases + rollbacks)) / 0.12
        scores["vim"] = share(sh.editors.get("Vim", 0) + sh.editors.get("Neovim", 0)) / 0.06
        scores["chaos"] = share(sum(sh.danger.values())) / 0.04
        scores["container"] = share(sh.containers) / 0.06
        scores["ai"] = share(sum(sh.ai.values())) / 0.04
        scores["ricer"] = max(share(sh.fetches) / 0.015, sh.fetches / 25)
        scores["explorer"] = share(sh.cd_ls) / 0.35
        scores["builder"] = share(sh.builds) / 0.10
        scores["gambler"] = sh.danger.get("git push --force", 0) / 4
        night = sum(sh.hours[h] for h in range(5))
        if sum(sh.hours.values()) >= 50:
            scores["owl"] = (night / sum(sh.hours.values())) / 0.2
    if git and git.commits:
        scores["committer"] = git.commits / 400
        if git.commits >= 10:
            scores["owl"] = max(scores.get("owl", 0), (git.night_commits / git.commits) / 0.2)
    if games:
        scores["gamer"] = games.hours / 400
    installed = (pkgs.installed if pkgs else 0) + (sh.installs_requested if sh else 0)
    scores["hoarder"] = installed / 150
    if (not sh or sh.total < 120) and (not git or git.commits < 10):
        scores["tourist"] = 1.5
    return sorted(((v, k) for k, v in scores.items()), reverse=True)


@dataclass
class Wrapped:
    year: int
    name: str
    slides: list[Slide]
    archetype: Archetype
    traces: list[Archetype]
    tiles: list[tuple[str, str]]
    top_commands: list[tuple[str, int]]
    system_line: str
    share_text: str
    host: str = "linux"


def build(year: int, name: str, sh, git, games, pkgs, sysinfo) -> Wrapped:
    slides: list[Slide] = []
    tiles: list[tuple[str, str]] = []
    when = f"in {year}" if (sh and sh.filtered_to_year) else "in your shell history"

    # --- intro
    desktop = " on ".join(x for x in (sysinfo.desktop, sysinfo.session.capitalize() if sysinfo.session else "") if x)
    intro = Slide(f"TERMINAL WRAPPED {year}", "violet").word(str(year)).gap()
    intro.text(f"Hey {name}." if name else "Hey there.", "title")
    intro.text(" · ".join(x for x in (sysinfo.distro, desktop) if x), "dim")
    intro.gap().text("Let's unwrap your year in the terminal.", "quip")
    slides.append(intro)

    # --- shell
    top: list[tuple[str, int]] = []
    if sh and sh.total:
        top = sh.programs.most_common(5)
        s = Slide("COMMANDS", "ocean").text("You ran", "title").number(sh.total)
        s.text(f"commands {when}", "body")
        s.text(f"using {len(sh.programs):,} different programs", "dim").gap()
        quip = (
            "A light year. Literally." if sh.total < 500 else
            "Respectable. Your keyboard is fine." if sh.total < 2500 else
            "Your keyboard felt that." if sh.total < 10000 else
            "Touch grass? Never heard of it."
        )
        s.text(quip, "quip")
        slides.append(s)
        tiles.append(("commands run", f"{sh.total:,}"))

        if top:
            s = Slide("YOUR TOP 5", "night").text("Your most-used commands", "title").gap()
            s.bars([(c, n) for c, n in top])
            s.gap().text(TOP_QUIPS.get(top[0][0], f"`{top[0][0]}` carried your year."), "quip")
            slides.append(s)
            tiles.append(("top command", top[0][0]))

        if sh.sudo >= 5:
            pct = 100 * sh.sudo / sh.total
            s = Slide("ROOT ACCESS", "ember").text("You typed sudo", "title").number(sh.sudo)
            s.text("times", "body").text(f"That's {pct:.0f}% of everything you ran.", "dim").gap()
            s.text(
                "Who even needs user mode?" if pct > 15 else
                "Power, used mostly responsibly." if pct > 5 else
                "Respectful. Rare. Admirable.",
                "quip",
            )
            slides.append(s)
            tiles.append(("sudo", f"{sh.sudo:,}×"))

        if sum(sh.editors.values()) >= 3:
            (ed, n), *rest = sh.editors.most_common()
            s = Slide("EDITOR WARS", "forest").text("Your editor of choice", "title").gap().word(ed)
            s.gap().text(f"opened {_plural(n, 'time')}", "dim")
            if rest:
                s.text(f"(sorry, {rest[0][0]}: only {rest[0][1]})", "dim")
            s.gap().text(EDITOR_QUIPS.get(ed, "A person of taste."), "quip")
            slides.append(s)
            tiles.append(("editor", ed))

        typos = sum(sh.typos.values())
        if typos or sh.vim_quits:
            s = Slide("OOPS", "candy").text("Your fingers slipped", "title").number(typos + sh.vim_quits)
            s.text("times", "body").gap()
            if sh.typos:
                (pair, n), = sh.typos.most_common(1)
                wrong, right = pair.split(" -> ")
                s.text(f"Fan favourite: `{wrong}` instead of `{right}` ({n}×)", "dim")
            if sh.vim_quits:
                s.text(f"You typed :q into your shell {_plural(sh.vim_quits, 'time')}.", "dim")
            s.gap().text("Autocorrect can't save you here.", "quip")
            slides.append(s)
            if typos:
                tiles.append(("typos", f"{typos + sh.vim_quits:,}"))

        if sh.danger:
            s = Slide("DANGER ZONE", "ember").text("Living dangerously", "title").gap()
            s.rows([(k, f"{v}×") for k, v in sh.danger.most_common()])
            s.gap().text(
                "Piping the internet straight into your shell. Bold." if "curl | sh" in sh.danger else
                "History is written by those who --force." if "git push --force" in sh.danger else
                "rm -rf and still standing." if "rm -rf" in sh.danger else
                "You like it on the edge.",
                "quip",
            )
            slides.append(s)
            tiles.append(("risky moves", f"{sum(sh.danger.values()):,}"))

        if sum(sh.ai.values()) >= 3:
            tool, _ = sh.ai.most_common(1)[0]
            s = Slide("AI", "night").text("You asked an AI for help", "title").number(sum(sh.ai.values()))
            s.text("times", "body").text(f"mostly via `{tool}`", "dim").gap()
            s.text("We won't tell anyone. Except this card.", "quip")
            slides.append(s)

        if sh.fetches >= 3:
            s = Slide("SHOW-OFF", "candy").text(f"You ran {sh.fetch_tool}", "title").number(sh.fetches)
            s.text("times", "body").gap().text("The rice must be immaculate.", "quip")
            slides.append(s)
            tiles.append((sh.fetch_tool, f"{sh.fetches}×"))

        rollbacks = sh.combos.get("rpm-ostree rollback", 0) + sh.combos.get("bootc rollback", 0)
        surgery = [
            ("OS rebases", sh.rebases),
            ("rollbacks", rollbacks),
            ("layered packages", sh.combos.get("rpm-ostree install", 0)),
            ("ujust recipes", sh.programs.get("ujust", 0)),
            ("service restarts", sh.combos.get("systemctl restart", 0)),
            ("reboots from the terminal", sh.combos.get("systemctl reboot", 0) + sh.programs.get("reboot", 0)),
        ]
        surgery = [(k, v) for k, v in surgery if v]
        if sum(v for _, v in surgery) >= 5:
            s = Slide("SYSTEM SURGERY", "toxic").text("Your system has been through a lot", "title").gap()
            s.rows([(k, f"{v}×") for k, v in surgery])
            s.gap().text(
                "Rebase, regret, rollback. The circle of life." if rollbacks else
                "If it ain't broke, tweak it anyway.",
                "quip",
            )
            slides.append(s)

        if sh.containers >= 5:
            s = Slide("CONTAINERS", "ocean").text("You hopped into containers", "title").number(sh.containers)
            s.text("times", "body")
            if sysinfo.container:
                s.text(f"(you're inside one right now: {sysinfo.container})", "dim")
            s.gap().text("Your apps live in boxes. So do you.", "quip")
            slides.append(s)

        timed = sum(sh.hours.values())
        if timed >= 50:
            hour = sh.hours.most_common(1)[0][0]
            s = Slide("PRIME TIME", "night").text("Your terminal was busiest at", "title").gap().word(_hour_label(hour))
            s.gap().text(
                "Night owl detected." if hour < 5 else
                "Early bird. Respect." if hour < 9 else
                "Strictly business hours." if hour < 18 else
                "Evening hacker energy.",
                "quip",
            )
            slides.append(s)

    # --- packages
    logged = pkgs.installed if pkgs else 0
    # Logs miss a lot (rpm-ostree layers, other boxes), so typed installs can win.
    installed = max(logged, sh.installs_requested if sh else 0)
    if installed >= 3:
        s = Slide("PACKAGES", "candy").text("You installed", "title").number(installed).text("packages", "body")
        if logged == installed and pkgs and pkgs.managers:
            parts = [f"{m} {v['installed']}" for m, v in pkgs.managers.items() if v.get("installed")]
            if parts:
                s.text(" · ".join(parts), "dim")
        if pkgs and pkgs.flatpak_apps_now:
            s.text(f"{pkgs.flatpak_apps_now} Flatpak apps on your system right now", "dim")
        removed = pkgs.removed if pkgs else 0
        s.gap().text(
            "Install, regret, remove, repeat." if removed > installed * 0.5 else "Gotta install 'em all.",
            "quip",
        )
        slides.append(s)
        tiles.append(("packages installed", f"{installed:,}"))

    # --- git
    if git and git.commits:
        s = Slide("GIT", "forest").text("You made", "title").number(git.commits)
        s.text(f"commits across {_plural(git.repos_active, 'repo')}", "body")
        s.text(f"+{git.added:,} / -{git.deleted:,} lines", "dim")
        if git.longest_streak >= 2:
            s.text(f"Longest streak: {git.longest_streak} days in a row", "dim")
        lang = git.languages.most_common(1)
        s.gap().text(f"Mostly {lang[0][0]}. Good choice." if lang else "Ship it.", "quip")
        slides.append(s)
        tiles.append(("git commits", f"{git.commits:,}"))

        if git.commits >= 10:
            peak = git.hours.most_common(1)[0][0]
            rows = [("busiest hour", _hour_label(peak))]
            rows += [(k, f"{v:,}") for k, v in (
                ("commits between 0 and 5 AM", git.night_commits),
                ("weekend commits", git.weekend_commits),
                ("'fix' commits", git.fix_msgs),
                ("WIP commits", git.wip_msgs),
                ("one-word messages", git.lazy_msgs),
                ("swear words", git.swears),
            ) if v]
            if git.words:
                rows.append(("favourite word", git.words.most_common(1)[0][0]))
            s = Slide("COMMIT HABITS", "forest").text("How you commit", "title").gap().rows(rows).gap()
            s.text(
                "Sleep is for people without merge conflicts." if git.night_commits / git.commits > 0.2 else
                "Weekends are just unpaid sprints." if git.weekend_commits / git.commits > 0.3 else
                "Fixing things you broke. Iconic." if git.fix_msgs / git.commits > 0.3 else
                "Clean history. Suspiciously clean.",
                "quip",
            )
            slides.append(s)

    # --- games
    if games and games.games:
        named = [g for g in games.games if not g.name.startswith("Steam app ")]
        hours = int(games.hours)
        s = Slide("GAMING", "violet").text(f"You played {_plural(len(games.games), 'game')} this year", "title")
        s.number(hours, "h").text("on the clock (total playtime of those games)", "dim").gap()
        if named:
            s.bars([(g.name, round(g.minutes / 60)) for g in named[:3]], "h")
            s.gap()
        s.text(
            f"That's {hours // 24} full days. Worth it." if hours >= 24 * 20 else
            f"{named[0].name} owns your GPU." if named else "GG.",
            "quip",
        )
        slides.append(s)
        tiles.append(("hours gaming", f"{hours:,}h"))

    # --- machine
    rows = [("distro", sysinfo.distro), ("kernel", sysinfo.kernel.split("-")[0])]
    if desktop:
        rows.append(("desktop", desktop))
    if sysinfo.shell:
        rows.append(("shell", sysinfo.shell))
    if sysinfo.container:
        rows.append(("running inside", f"{sysinfo.container} ({sysinfo.container_distro})"))
    if sysinfo.boots:
        rows.append(("boots this year", f"{sysinfo.boots:,}"))
        rows.append(("longest uptime", f"{sysinfo.longest_boot_hours:.0f}h"))
    s = Slide("YOUR MACHINE", "steel").text("The machine that put up with you", "title").gap().rows(rows).gap()
    born = dt.datetime.fromtimestamp(sysinfo.home_born) if sysinfo.home_born else None
    if born and born.year == year:
        s.text(f"Fresh home folder since {born:%b} {born.day}. Welcome (back) to Linux.", "quip")
    elif born:
        s.text(f"Same home folder since {born.year}. Loyal.", "quip")
    else:
        s.text("Thanks for not distro-hopping. Probably.", "quip")
    slides.append(s)

    # --- personality
    ranked = score_archetypes(sh, git, games, pkgs)
    best = ranked[0][1] if ranked and ranked[0][0] >= 0.5 else "steady"
    arch = ARCHETYPES[best]
    traces = [ARCHETYPES[k] for v, k in ranked[1:] if v >= 0.5 and k != best][:2]
    s = Slide(f"YOUR {year} TERMINAL PERSONALITY", arch.theme).text("You are", "title").gap()
    s.word(arch.title.upper()).gap().text(arch.tagline, "body")
    if traces:
        s.text("with traces of " + " and ".join(t.title for t in traces), "dim")
    slides.append(s)

    system_line = " · ".join(x for x in (sysinfo.distro, desktop, f"kernel {sysinfo.kernel.split('-')[0]}") if x)
    bits = [f"I'm {arch.title}"]
    if sh and sh.total:
        bits.append(f"{sh.total:,} commands")
    if top:
        bits.append(f"top: {top[0][0]}")
    if sh and sh.sudo:
        bits.append(f"{sh.sudo:,} sudos")
    if games and games.games:
        bits.append(f"{int(games.hours):,}h gaming")
    share = f"My {year} Terminal Wrapped: " + ", ".join(bits) + ". #TerminalWrapped"

    host = sysinfo.distro_id or "linux"
    return Wrapped(year, name, slides, arch, traces, tiles[:6], top, system_line, share, host)


def outro(w: Wrapped, card_path: str | None) -> Slide:
    s = Slide("THAT'S A WRAP", w.archetype.theme)
    if card_path:
        s.text("Your share card is ready", "title").gap().text(card_path, "accent")
    else:
        s.text("That's your year.", "title")
    s.gap().text("Post it with #TerminalWrapped", "body")
    s.text("Everything was computed locally. Nothing left your machine.", "dim")
    return s
