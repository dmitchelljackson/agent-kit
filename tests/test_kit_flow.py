"""End to end against a throwaway local kit repo: init → install → upstream change → sync → share prepare."""

import os
import shutil
import subprocess
import unittest
from pathlib import Path

from helpers import TempDir, akit

from agent_kit import frontmatter as fm

REPO = Path(__file__).resolve().parents[1]


def ok(res):
    code, out, err = res
    assert code == 0, f"exit {code}\nstdout:\n{out}\nstderr:\n{err}"
    return out


def git(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


class KitFlowTest(unittest.TestCase):
    def setUp(self):
        self._tmp = TempDir()
        self.tmp = self._tmp.__enter__()
        self.cache = self.tmp / "cache"
        os.environ["XDG_CACHE_HOME"] = str(self.cache)
        os.environ["XDG_CONFIG_HOME"] = str(self.tmp / "config")
        os.environ.pop("AKIT_JUDGE", None)
        # a kit repo: this repo's wiki + PR template, plus an android page
        self.kit = self.tmp / "kit"
        self.kit.mkdir()
        shutil.copytree(REPO / "wiki", self.kit / "wiki")
        shutil.copytree(REPO / ".github", self.kit / ".github")
        shutil.copy(REPO / ".agent-kit.json", self.kit / ".agent-kit.json")
        git(self.kit, "init", "-q", "-b", "main")
        git(self.kit, "config", "user.email", "t@example.com")
        git(self.kit, "config", "user.name", "t")
        ok(akit(self.kit, "page", "new", "android", "Android", "--summary", "Android rules"))
        self.fakes = ok(akit(self.kit, "atom", "new", "Prefer fakes", "--page", "wiki/android", "--body", "Use fakes.")).split()[0]
        (self.kit / "wiki/android/_page.md").write_text(
            "---\ntitle: Android\nsummary: Android rules\nbookmark: Use before writing Android tests\nbookmark_approval: owner\n---\n\n![[prefer-fakes]]\n")
        ok(akit(self.kit, "index"))
        git(self.kit, "add", "-A")
        git(self.kit, "commit", "-q", "-m", "kit")
        os.environ["AKIT_KIT_DIR"] = str(self.kit)
        self.proj = self.tmp / "proj"
        self.proj.mkdir()
        git(self.proj, "init", "-q", "-b", "main")

    def tearDown(self):
        for k in ("AKIT_KIT_DIR", "XDG_CACHE_HOME", "XDG_CONFIG_HOME"):
            os.environ.pop(k, None)
        self._tmp.__exit__()

    def commit_kit(self, msg):
        git(self.kit, "add", "-A")
        git(self.kit, "commit", "-q", "-m", msg)

    def test_full_flow(self):
        out = ok(akit(self.proj, "init", "--name", "Demo", "--summary", "A demo app.", "--agents", "claude,codex"))
        self.assertIn("wrote AGENTS.md", out)
        self.assertEqual((self.proj / "CLAUDE.md").read_text(), "@AGENTS.md\n")
        agents = (self.proj / "AGENTS.md").read_text()
        self.assertIn("# Demo", agents)
        self.assertIn("<!-- akit:begin", agents)
        self.assertTrue((self.proj / "wiki/agent-kit/atoms/_page.md").exists())
        self.assertTrue((self.proj / ".claude/skills/agent-kit-wiki/SKILL.md").exists())
        self.assertIn("wiki/log.md merge=union", (self.proj / ".gitattributes").read_text())

        ok(akit(self.proj, "install", "android"))
        self.assertTrue((self.proj / ".agents/skills/android/SKILL.md").exists())
        self.assertIn("✓ android", ok(akit(self.proj, "kit", "ls")))
        ok(akit(self.proj, "check"))

        # project diverges on one atom; kit changes that atom and adds another
        local_fakes = self.proj / "wiki/android/prefer-fakes.md"
        kit_fakes = self.kit / "wiki/android/prefer-fakes.md"
        ok(akit(self.kit, "atom", "new", "Fixed time", "--page", "wiki/android", "--body", "Use a fixed clock."))
        self.commit_kit("add fixed time")
        report = ok(akit(self.proj, "sync"))
        self.assertIn("New atoms on pages you have (1)", report)
        self.assertIn("Page layouts updated upstream", report)

        d = fm.load(kit_fakes)
        d.body = "Use fakes. Updated upstream."
        fm.save(d)
        self.commit_kit("update fakes")
        report = ok(akit(self.proj, "sync"))
        self.assertIn("Updated upstream, untouched here", report)
        self.assertIn(self.fakes, report)

        local_text = local_fakes.read_text().replace("Use fakes.", "Use fakes, except Retrofit.")
        local_fakes.write_text(local_text)
        report = ok(akit(self.proj, "sync"))
        self.assertIn("Conflicts", report)

        ok(akit(self.proj, "sync", "--take-safe"))
        self.assertIn("except Retrofit", local_fakes.read_text())  # conflict not taken silently
        self.assertTrue((self.proj / "wiki/android/fixed-time.md").exists())
        self.assertIn("![[fixed-time]]", (self.proj / "wiki/android/_page.md").read_text())
        ok(akit(self.proj, "sync", "--done"))
        self.assertIn("already up to date", ok(akit(self.proj, "sync")))

        # share a new project atom back (owner-approved), stopping before submit
        ok(akit(self.proj, "atom", "new", "Test the real class", "--page", "wiki/android",
                "--body", "Construct the production class with fakes.\nWhy: test copies drift."))
        # the scan blocks project-specific terms even when the owner approved
        leak = ok(akit(self.proj, "atom", "new", "Leaky", "--page", "wiki/android", "--body", "Demo uses sk-abcdefghijklmnopqrstuvwxyz.")).split()[0]
        code, _, err = akit(self.proj, "share", "wiki/android", "--owner")
        self.assertEqual(code, 1)
        self.assertIn("project-specific term 'Demo'", err)
        self.assertIn("possible API key", err)
        ok(akit(self.proj, "atom", "rm", leak))

        out = ok(akit(self.proj, "share", "wiki/android", "--owner"))
        self.assertIn("Prepared branch share/android-", out)
        body_path = out.split("fill every TODO(akit) in the PR body:\n  ")[1].split("\n")[0]
        body = Path(body_path).read_text()
        self.assertIn("Owner-approved in session", body)
        self.assertIn("Test the real class", body)
        self.assertIn("TODO(akit)", body)
        code, _, err = akit(self.proj, "share", "submit", "--title", "x")
        self.assertEqual(code, 1)
        self.assertIn("Fill in every TODO(akit)", err)


if __name__ == "__main__":
    unittest.main()
