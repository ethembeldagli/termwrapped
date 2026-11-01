"""Stdlib-only tests. Run with:  python3 -m unittest discover -s tests -v"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests"))

import fixtures  # noqa: E402
from termwrapped import games, shell  # noqa: E402


def run_cli(home: str, *args: str) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if k not in ("HISTFILE", "XDG_DATA_HOME", "ZDOTDIR")}
    env.update(HOME=home, TZ="UTC", COLUMNS="100", LINES="30")
    return subprocess.run(
        [sys.executable, "-m", "termwrapped", "--year", str(fixtures.YEAR), *args],
        cwd=ROOT, env=env, capture_output=True, text=True, timeout=120,
    )


class EndToEnd(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.home = cls.tmp.name
        fixtures.small_home(cls.home)
        out = run_cli(cls.home, "--json", "--email", fixtures.EMAIL)
        assert out.returncode == 0, out.stderr
        cls.data = json.loads(out.stdout)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_shell_counts(self):
        sh = self.data["shell"]
        self.assertTrue(sh["filtered_to_year"])
        self.assertEqual(sh["total"], 12)  # 13 commands, one from last year
        self.assertNotIn("bogusword", sh["programs"])  # heredoc body is not a command
        self.assertEqual(sh["programs"]["git"], 3)
        self.assertEqual(sh["sudo"], 2)
        self.assertEqual(sh["vim_quits"], 1)
        self.assertEqual(sh["typos"], {"gti -> git": 1})
        self.assertNotIn("gti", sh["programs"])
        self.assertEqual(sh["installs_requested"], 2)
        self.assertEqual(sh["fetches"], 1)
        self.assertEqual(sh["editors"], {"Vim": 1})
        for k in ("rm -rf", "curl | sh", "git push --force"):
            self.assertEqual(sh["danger"][k], 1, k)
        self.assertEqual(sh["hours"].get("2") or sh["hours"].get(2), 2)

    def test_git(self):
        git = self.data["git"]
        self.assertEqual(git["commits"], 3)  # other author and last year excluded
        self.assertEqual(git["night_commits"], 1)
        self.assertEqual(git["longest_streak"], 3)
        self.assertEqual(git["fix_msgs"], 3)
        self.assertEqual(git["languages"], {"Python": 3})
        self.assertEqual(git["added"], 2 + 3 + 4)

    def test_games(self):
        g = self.data["games"]
        self.assertEqual([x["name"] for x in g["games"]], ["Space Goose Simulator"])
        self.assertEqual(g["hours"], 10.0)

    def test_plain_output_and_card(self):
        card = os.path.join(self.home, "card.svg")
        out = run_cli(self.home, "--plain", "--card", card, "--email", fixtures.EMAIL, "--name", "tester")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("TERMINAL WRAPPED 2025", out.stdout)
        self.assertIn("TERMINAL PERSONALITY", out.stdout)
        self.assertIn("#TerminalWrapped", out.stdout)
        root = ET.parse(card).getroot()
        self.assertTrue(root.tag.endswith("svg"))
        with open(card) as f:
            self.assertIn("tester@", f.read())

    def test_empty_home_does_not_crash(self):
        with tempfile.TemporaryDirectory() as empty:
            out = run_cli(empty, "--plain", "--no-card")
            self.assertEqual(out.returncode, 0, out.stderr)
            self.assertIn("TERMINAL PERSONALITY", out.stdout)


class Parsers(unittest.TestCase):
    def test_zsh_extended_and_metafied(self):
        with tempfile.NamedTemporaryFile("wb", delete=False) as f:
            # "é" is 0xC3 0xA9; zsh metafies 0xA9 as 0x83 0x89
            f.write(b": 1736000000:0;ls\n: 1736000001:0;echo caf\xc3\x83\x89\n: 1736000002:0;for x in 1 2; do\\\necho $x\\\ndone\n")
        try:
            entries = shell.read_zsh(f.name)
        finally:
            os.unlink(f.name)
        self.assertEqual([e.cmd for e in entries][:2], ["ls", "echo café"])
        self.assertEqual(len(entries), 3)
        self.assertEqual(entries[0].ts, 1736000000.0)

    def test_fish(self):
        with tempfile.NamedTemporaryFile("w", delete=False) as f:
            f.write("- cmd: git status\n  when: 1736000000\n- cmd: echo a\\nb\n  when: 1736000001\n  paths:\n    - x\n")
        try:
            entries = shell.read_fish(f.name)
        finally:
            os.unlink(f.name)
        self.assertEqual([e.cmd for e in entries], ["git status", "echo a\nb"])
        self.assertEqual(entries[1].ts, 1736000001.0)

    def test_segments_strip_wrappers(self):
        segs = shell.segments(shell.tokenize("FOO=1 sudo -u root apt install x | grep y && ls; time make"))
        firsts = [shell._strip_prefix(s)[0][0] for s in segs]
        self.assertEqual(firsts, ["apt", "grep", "ls", "make"])

    def test_osa_distance(self):
        self.assertEqual(shell.osa_distance("gti", "git"), 1)
        self.assertEqual(shell.osa_distance("claer", "clear"), 1)
        self.assertEqual(shell.osa_distance("ls", "cd"), 2)

    def test_vdf(self):
        d = games.parse_vdf('"A" { "B" { "c" "1" // comment\n "Quote" "say \\"hi\\"" } }')
        self.assertEqual(d["a"]["b"]["c"], "1")
        self.assertEqual(d["a"]["b"]["quote"], 'say "hi"')


if __name__ == "__main__":
    unittest.main()
