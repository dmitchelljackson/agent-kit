"""`akit land` against a real bare remote."""

import json
import os
import subprocess
import unittest
from pathlib import Path

from helpers import TempDir, akit


def ok(res):
    code, out, err = res
    assert code == 0, f"exit {code}\nstdout:\n{out}\nstderr:\n{err}"
    return out


def git(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


class LandTest(unittest.TestCase):
    landing = "scoped"

    def setUp(self):
        self._tmp = TempDir()
        self.tmp = self._tmp.__enter__()
        os.environ["XDG_CACHE_HOME"] = str(self.tmp / "cache")
        os.environ["XDG_CONFIG_HOME"] = str(self.tmp / "config")
        self.origin = self.tmp / "origin.git"
        git(self.tmp, "init", "-q", "--bare", "-b", "main", str(self.origin))
        self.proj = self.tmp / "proj"
        git(self.tmp, "clone", "-q", str(self.origin), str(self.proj))
        for k, v in (("user.email", "t@example.com"), ("user.name", "t"), ("commit.gpgsign", "false")):
            git(self.proj, "config", k, v)
        ok(akit(self.proj, "init", "--agents", "claude", "--share", "off", "--landing", self.landing, "--no-install"))
        ok(akit(self.proj, "page", "new", "tickets", "Tickets", "--summary", "work"))
        (self.proj / "wiki/tickets/.akit-scope").write_text("main\n")
        ok(akit(self.proj, "page", "new", "behavior", "Behavior", "--summary", "features"))
        (self.proj / "src.txt").write_text("code v1\n")
        git(self.proj, "add", "-A")
        git(self.proj, "commit", "-q", "-m", "setup")
        git(self.proj, "push", "-q", "-u", "origin", "main")

    def tearDown(self):
        os.environ.pop("XDG_CACHE_HOME", None)
        os.environ.pop("XDG_CONFIG_HOME", None)
        self._tmp.__exit__()

    def origin_files(self):
        return set(git(self.origin, "ls-tree", "-r", "--name-only", "main").splitlines())

    def origin_show(self, path):
        return git(self.origin, "show", f"main:{path}")


class ScopedLandTest(LandTest):
    def test_feature_branch_lands_only_main_scoped(self):
        git(self.proj, "checkout", "-q", "-b", "feature")
        branch_head = git(self.proj, "rev-parse", "HEAD")
        ok(akit(self.proj, "atom", "new", "T-010 status", "--page", "wiki/tickets", "--body", "IN_PROGRESS"))
        ok(akit(self.proj, "atom", "new", "Login works", "--page", "wiki/behavior", "--body", "Given...\nWhen...\nThen..."))
        (self.proj / "src.txt").write_text("code v2\n")  # code change: must never be touched
        (self.proj / "wiki/behavior/.akit-scope").write_text("main\n")  # scope change: always stays

        plan = ok(akit(self.proj, "land", "--dry-run"))
        land_part, stay_part = plan.split("Stays with your branch")
        self.assertIn("wiki/tickets/t-010-status.md", land_part)
        self.assertIn("wiki/tickets/_page.md", land_part)  # the embed was added there
        self.assertNotIn("behavior", land_part)
        self.assertIn("wiki/behavior/login-works.md", stay_part)
        self.assertIn("wiki/behavior/login-works.md", stay_part)  # even though its scope file now says main
        self.assertIn("scope file changes ride with the branch", stay_part)
        self.assertNotIn("src.txt", plan)
        (self.proj / "wiki/behavior/.akit-scope").unlink()

        out = ok(akit(self.proj, "land"))
        self.assertIn("Landed", out)
        files = self.origin_files()
        self.assertIn("wiki/tickets/t-010-status.md", files)
        self.assertNotIn("wiki/behavior/login-works.md", files)
        self.assertNotIn("wiki/behavior/.akit-scope", files)
        self.assertEqual(self.origin_show("src.txt"), "code v1")
        self.assertIn("land | 2 file(s)", self.origin_show("wiki/log.md"))
        # the branch and working tree are untouched
        self.assertEqual(git(self.proj, "rev-parse", "HEAD"), branch_head)
        self.assertEqual(git(self.proj, "branch", "--show-current"), "feature")
        self.assertEqual((self.proj / "src.txt").read_text(), "code v2\n")
        self.assertTrue((self.proj / "wiki/behavior/login-works.md").exists())
        # tickets now match main (modulo derived files), so nothing more of main scope differs
        self.assertIn("Already on main", ok(akit(self.proj, "land")))

    def test_naming_a_branch_scoped_path_fails(self):
        ok(akit(self.proj, "atom", "new", "Login works", "--page", "wiki/behavior", "--body", "x"))
        code, _, err = akit(self.proj, "land", "wiki/behavior")
        self.assertEqual(code, 1)
        self.assertIn("branch-scoped, so they can't be landed", err)
        self.assertIn("branch (from main's wiki/.akit-scope)", err)
        self.assertEqual(self.origin_files(), set(git(self.proj, "ls-tree", "-r", "--name-only", "HEAD").splitlines()))

    def test_on_main_with_unpushed_code_commits_locally_but_never_pushes(self):
        (self.proj / "src.txt").write_text("code v2\n")
        git(self.proj, "commit", "-q", "-am", "my code")
        origin_before = git(self.origin, "rev-parse", "main")
        ok(akit(self.proj, "atom", "new", "T-020", "--page", "wiki/tickets", "--body", "READY"))
        out = ok(akit(self.proj, "land"))
        self.assertIn("never pushes your commits", out)
        self.assertEqual(git(self.origin, "rev-parse", "main"), origin_before)
        self.assertEqual(git(self.proj, "log", "-1", "--format=%s"), "wiki: land tickets")
        self.assertEqual(git(self.proj, "log", "-1", "--format=%s", "HEAD^"), "my code")
        self.assertEqual(git(self.proj, "status", "--porcelain", "wiki/tickets"), "")

    def test_main_moved_underneath(self):
        other = self.tmp / "other"
        git(self.tmp, "clone", "-q", str(self.origin), str(other))
        for k, v in (("user.email", "o@example.com"), ("user.name", "o")):
            git(other, "config", k, v)
        (other / "README.md").write_text("someone else\n")
        git(other, "add", "-A"); git(other, "commit", "-q", "-m", "other"); git(other, "push", "-q")
        git(self.proj, "checkout", "-q", "-b", "feature")
        ok(akit(self.proj, "atom", "new", "T-030", "--page", "wiki/tickets", "--body", "DRAFT"))
        ok(akit(self.proj, "land"))
        files = self.origin_files()
        self.assertIn("README.md", files)
        self.assertIn("wiki/tickets/t-030.md", files)


class OpenLandTest(LandTest):
    landing = "open"

    def test_open_mode_on_main_lands_everything_and_leaves_tree_clean(self):
        ok(akit(self.proj, "atom", "new", "Login works", "--page", "wiki/behavior", "--body", "x"))
        (self.proj / "src.txt").write_text("code v2\n")
        out = ok(akit(self.proj, "land"))
        self.assertIn("landing: open", out)
        self.assertIn("wiki/behavior/login-works.md", self.origin_files())
        self.assertEqual(git(self.proj, "rev-parse", "main"), git(self.origin, "rev-parse", "main"))
        self.assertEqual(git(self.proj, "status", "--porcelain", "wiki"), "")
        self.assertEqual(git(self.proj, "status", "--porcelain", "src.txt"), "M src.txt")  # code untouched
        self.assertEqual(self.origin_show("src.txt"), "code v1")


class ConfigTest(LandTest):
    def test_config_shows_both_settings(self):
        out = ok(akit(self.proj, "config"))
        self.assertIn("share:   off", out)
        self.assertIn("landing: scoped", out)
        data = json.loads((self.proj / ".agent-kit-owner.json").read_text())
        self.assertEqual((data["share"], data["landing"]), ("off", "scoped"))

    def test_scope_command(self):
        out = ok(akit(self.proj, "scope"))
        self.assertIn("main    tickets/", out)
        self.assertIn("branch  ./", out)
        self.assertIn("main (from wiki/tickets/.akit-scope)", ok(akit(self.proj, "scope", "wiki/tickets")))

    def test_scope_shows_when_main_disagrees(self):
        (self.proj / "wiki/behavior/.akit-scope").write_text("main\n")
        out = ok(akit(self.proj, "scope", "wiki/behavior"))
        self.assertIn("here: main", out)
        self.assertIn("for landing (main's scope files): branch", out)

    def test_new_main_scoped_directory_lands_with_its_scope_file(self):
        git(self.proj, "checkout", "-q", "-b", "feature")
        ok(akit(self.proj, "page", "new", "decisions", "Decisions", "--summary", "d"))
        (self.proj / "wiki/decisions/.akit-scope").write_text("main\n")
        ok(akit(self.proj, "atom", "new", "Use Postgres", "--page", "wiki/decisions", "--body", "Why: boring."))
        ok(akit(self.proj, "land"))
        files = self.origin_files()
        self.assertIn("wiki/decisions/.akit-scope", files)
        self.assertIn("wiki/decisions/use-postgres.md", files)


del LandTest

if __name__ == "__main__":
    unittest.main()
