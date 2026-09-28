import os
import shutil
import tempfile
import unittest
from pathlib import Path

from helpers import TempDir, akit, make_wiki

from agent_kit import frontmatter as fm

REPO = Path(__file__).resolve().parents[1]


def ok(res):
    code, out, err = res
    assert code == 0, f"exit {code}\nstdout:\n{out}\nstderr:\n{err}"
    return out


def setUpModule():
    global _cache
    _cache = tempfile.TemporaryDirectory()
    os.environ["XDG_CACHE_HOME"] = _cache.name
    os.environ["XDG_CONFIG_HOME"] = _cache.name


def tearDownModule():
    os.environ.pop("XDG_CACHE_HOME", None)
    os.environ.pop("XDG_CONFIG_HOME", None)
    _cache.cleanup()


class TemplateTest(unittest.TestCase):
    def setUp(self):
        self._tmp = TempDir()
        self.root = make_wiki(self._tmp.__enter__())
        shutil.copytree(REPO / "wiki/templates", self.root / "wiki/templates")
        ok(akit(self.root, "index"))

    def tearDown(self):
        self._tmp.__exit__()

    def test_help_shows_fields_and_rules(self):
        out = ok(akit(self.root, "new", "ticket", "--help"))
        self.assertIn("--status {DRAFT,READY,IN_PROGRESS,IN_REVIEW,BLOCKED,DONE,DROPPED}", out)
        self.assertIn("REQUIRED", out)
        self.assertIn("RULES (from templates/ticket)", out)
        self.assertIn("Link acceptance, don't copy it", out)

    def test_bdd_ticket_flow(self):
        out = ok(akit(self.root, "new", "bdd", "Login screen", "--ui-sources", "raw/designs/login.html"))
        self.assertTrue(out.startswith("F-01  behavior/login-screen"))
        page = self.root / "wiki/behavior/login-screen"
        self.assertEqual(fm.load(page / "_page.md").meta["status"], "DRAFT")
        self.assertIn("F-01.1", (page / "_page.md").read_text())  # {{key}} filled in the skeleton comment
        case = ok(akit(self.root, "atom", "new", "1.1 Valid login opens The Record", "--page", "wiki/behavior/login-screen",
                       "--body", "Given a registered user\nWhen they sign in\nThen The Record opens")).split()[0]

        self.assertTrue(ok(akit(self.root, "new", "ticket", "Skeleton", "--type", "enabling",
                                "--outcome", "The app boots.")).startswith("T-010"))
        out = ok(akit(self.root, "new", "ticket", "Email login", "--depends-on", "T-010",
                      "--covers", case, "--outcome", "Users can sign in with email."))
        self.assertTrue(out.startswith("T-020  tickets/t-020-email-login"))
        t = self.root / "wiki/tickets/t-020-email-login"
        meta = fm.load(t / "_page.md").meta
        self.assertEqual(meta["depends_on"], "T-010")
        self.assertEqual(meta["covers"], case)
        rendered = ok(akit(self.root, "read", "T-020"))
        self.assertIn("## Outcome", rendered)
        self.assertIn("Users can sign in with email.", rendered)
        self.assertIn("Human requirements", rendered)

        ok(akit(self.root, "set", "T-020", "status=READY"))
        code, _, err = akit(self.root, "set", "T-020", "status=SHIPPED")
        self.assertEqual(code, 1)
        self.assertIn("not one of", err)
        listing = ok(akit(self.root, "ls", "ticket", "--where", "status=READY"))
        keys = [line.split()[0] for line in listing.splitlines()[1:] if line.startswith("T-")]
        self.assertEqual(keys, ["T-020"])
        self.assertIn("T-020", ok(akit(self.root, "ls", "ticket", "--where", "depends_on=T-010")))
        ok(akit(self.root, "check"))

    def test_validation_errors(self):
        code, _, err = akit(self.root, "new", "ticket", "No outcome")
        self.assertEqual(code, 1)
        self.assertIn("--outcome is required", err)
        code, _, err = akit(self.root, "new", "ticket", "Bad dep", "--outcome", "x", "--depends-on", "T-999")
        self.assertEqual(code, 1)
        self.assertIn("--depends-on", err)
        ok(akit(self.root, "new", "ticket", "Good", "--outcome", "x"))
        page = self.root / "wiki/tickets/t-010-good/_page.md"
        page.write_text(page.read_text().replace("status: DRAFT", "status: WHATEVER"))
        code, out, _ = akit(self.root, "check")
        self.assertEqual(code, 1)
        self.assertIn("'WHATEVER' is not one of", out)

    def test_template_from_page_and_skeleton_not_scanned(self):
        ok(akit(self.root, "page", "new", "runbooks", "Runbooks", "--summary", "s"))
        ok(akit(self.root, "page", "new", "runbooks/deploy", "Deploy", "--summary", "s"))
        ok(akit(self.root, "atom", "new", "Steps", "--page", "wiki/runbooks/deploy", "--body", "1. ship"))
        ok(akit(self.root, "template", "new", "runbook", "--from", "wiki/runbooks/deploy", "--description", "How to run an operation"))
        self.assertTrue((self.root / "wiki/templates/runbook/template.json").exists())
        self.assertTrue((self.root / "wiki/templates/runbook/_skeleton/steps.md").exists())
        self.assertEqual(fm.load(self.root / "wiki/runbooks/deploy/_page.md").meta["template"], "runbook")
        out = ok(akit(self.root, "new", "runbook", "Rollback"))
        self.assertIn("runbooks/rollback", out)
        self.assertTrue((self.root / "wiki/runbooks/rollback/rollback-steps.md").exists())
        code, out, _ = akit(self.root, "check")
        self.assertNotIn("duplicate", out)  # skeleton atoms are not scanned as atoms


if __name__ == "__main__":
    unittest.main()
