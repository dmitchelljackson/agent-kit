import os
import re
import tempfile
import unittest
from pathlib import Path

from helpers import TempDir, akit, make_wiki

from agent_kit import frontmatter as fm
from agent_kit.wiki import UUID_RE, Wiki


def ok(res):
    code, out, err = res
    assert code == 0, f"exit {code}\nstdout:\n{out}\nstderr:\n{err}"
    return out


class FrontmatterTest(unittest.TestCase):
    def test_round_trip_quotes_risky_values(self):
        meta = {"title": "Use: colons # and quotes \"x\"", "id": "abc"}
        text = fm.dump(meta, "body")
        parsed, body = fm.parse(text)
        self.assertEqual(parsed, meta)
        self.assertEqual(body.strip(), "body")

    def test_no_frontmatter(self):
        self.assertEqual(fm.parse("# hi\n"), ({}, "# hi\n"))


class AtomTest(unittest.TestCase):
    def test_new_atom_generates_uuid_file_and_embed(self):
        with TempDir() as root:
            make_wiki(root)
            ok(akit(root, "page", "new", "android", "Android", "--summary", "Android rules"))
            out = ok(akit(root, "atom", "new", "Prefer fakes over mocks", "--page", "wiki/android", "--body", "Use fakes."))
            atom_id, rel = out.split()
            self.assertRegex(atom_id, UUID_RE)
            self.assertEqual(rel, "android/prefer-fakes-over-mocks.md")
            self.assertIn("![[prefer-fakes-over-mocks]]", (root / "wiki/android/_page.md").read_text())
            self.assertIn("[Android](android/_page.md) — Android rules", (root / "wiki/index.md").read_text())

    def test_names_are_unique_across_wiki(self):
        with TempDir() as root:
            make_wiki(root)
            ok(akit(root, "page", "new", "a", "A"))
            ok(akit(root, "page", "new", "b", "B"))
            ok(akit(root, "atom", "new", "Fixed time", "--page", "wiki/a"))
            out = ok(akit(root, "atom", "new", "Fixed time", "--page", "wiki/b"))
            self.assertTrue(out.strip().endswith("b/fixed-time-2.md"))

    def test_read_inlines_atoms_with_nested_heading_levels(self):
        with TempDir() as root:
            make_wiki(root)
            ok(akit(root, "page", "new", "t", "Testing"))
            (root / "wiki/t/_page.md").write_text("---\ntitle: Testing\n---\n\n## Doubles\n")
            ok(akit(root, "atom", "new", "Fakes", "--page", "wiki/t", "--body", "Use fakes.\nWhy: mocks lie."))
            out = ok(akit(root, "read", "wiki/t"))
            self.assertIn("# Testing", out)
            self.assertIn("### Fakes", out)  # one below the ## heading it sits under
            self.assertIn("Why: mocks lie.", out)
            self.assertRegex(out, r"<!-- atom: [0-9a-f-]{36} · t/fakes\.md -->")

    def test_read_fails_loudly_on_missing_atom(self):
        with TempDir() as root:
            make_wiki(root)
            ok(akit(root, "page", "new", "t", "T"))
            (root / "wiki/t/_page.md").write_text("---\ntitle: T\n---\n\n![[nope]]\n")
            code, out, err = akit(root, "read", "wiki/t")
            self.assertEqual(code, 1)
            self.assertIn("MISSING ATOM", out)
            self.assertIn("missing: nope", err)

    def test_rename_rewrites_embeds_and_alias_everywhere(self):
        with TempDir() as root:
            make_wiki(root)
            ok(akit(root, "page", "new", "a", "A"))
            ok(akit(root, "page", "new", "b", "B"))
            atom_id = ok(akit(root, "atom", "new", "Old name", "--page", "wiki/a")).split()[0]
            (root / "wiki/b/_page.md").write_text("---\ntitle: B\n---\n\n![[a/old-name|Old name]]\nSee [[old-name]].\n")
            ok(akit(root, "atom", "rename", atom_id, "New name"))
            self.assertTrue((root / "wiki/a/new-name.md").exists())
            self.assertIn("![[new-name]]", (root / "wiki/a/_page.md").read_text())
            b = (root / "wiki/b/_page.md").read_text()
            self.assertIn("![[a/new-name|New name]]", b)
            self.assertIn("[[new-name]]", b)
            self.assertEqual(fm.load(root / "wiki/a/new-name.md").id, atom_id)

    def test_move_and_rm(self):
        with TempDir() as root:
            make_wiki(root)
            ok(akit(root, "page", "new", "a", "A"))
            ok(akit(root, "page", "new", "b", "B"))
            atom_id = ok(akit(root, "atom", "new", "Thing", "--page", "wiki/a")).split()[0]
            ok(akit(root, "atom", "move", atom_id, "--page", "wiki/b"))
            self.assertNotIn("thing", (root / "wiki/a/_page.md").read_text())
            self.assertIn("![[thing]]", (root / "wiki/b/_page.md").read_text())
            ok(akit(root, "atom", "rm", atom_id))
            self.assertFalse((root / "wiki/b/thing.md").exists())
            self.assertNotIn("thing", (root / "wiki/b/_page.md").read_text())

    def test_check_finds_problems(self):
        with TempDir() as root:
            make_wiki(root)
            ok(akit(root, "page", "new", "a", "A", "--summary", "s"))
            ok(akit(root, "atom", "new", "One", "--page", "wiki/a"))
            (root / "wiki/a/hand-made.md").write_text("---\ntitle: Hand made\nid: not-a-uuid\n---\nx\n")
            code, out, _ = akit(root, "check")
            self.assertEqual(code, 1)
            self.assertIn("id is not a lowercase UUID", out)
            self.assertIn("orphan atom", out)


class BookmarkTest(unittest.TestCase):
    def test_owner_bookmark_generates_mirrored_skills(self):
        with TempDir() as root:
            make_wiki(root, agents=("claude", "opencode"))
            ok(akit(root, "page", "new", "t", "Testing", "--summary", "s"))
            ok(akit(root, "bookmark", "add", "wiki/t", "--when", "Use before writing tests", "--owner"))
            for d in (".agents/skills", ".claude/skills", ".opencode/skills"):
                skill = (root / d / "t" / "SKILL.md").read_text()
                self.assertIn("description: Use before writing tests. The project wiki has pages you must read first.", skill)
                self.assertIn("akit read wiki/t", skill)
            self.assertEqual(fm.load(root / "wiki/t/_page.md").meta["bookmark_approval"], "owner")
            ok(akit(root, "check"))
            ok(akit(root, "bookmark", "rm", "wiki/t"))
            self.assertFalse((root / ".claude/skills/t").exists())

    def test_trigger_must_be_a_moment(self):
        with TempDir() as root:
            make_wiki(root)
            ok(akit(root, "page", "new", "t", "T"))
            code, _, err = akit(root, "bookmark", "add", "wiki/t", "--when", "Android stuff", "--owner")
            self.assertEqual(code, 1)
            self.assertIn('must start with "Use "', err)

    def test_without_judge_writes_packet_and_accepts_verdict(self):
        import os
        with TempDir() as root:
            make_wiki(root, agents=())
            ok(akit(root, "page", "new", "t", "T", "--summary", "s"))
            (root / "wiki/agent-kit/judges/bookmark").mkdir(parents=True)
            (root / "wiki/agent-kit/_page.md").write_text("---\ntitle: K\n---\n")
            (root / "wiki/agent-kit/judges/_page.md").write_text("---\ntitle: J\n---\n")
            (root / "wiki/agent-kit/judges/bookmark/_page.md").write_text("---\ntitle: Bookmark judge\n---\nBe strict.\n")
            os.environ.pop("AKIT_JUDGE", None)
            code, _, err = akit(root, "bookmark", "add", "wiki/t", "--when", "Use before x")
            self.assertEqual(code, 3)
            packet = re.search(r"^\s+(\S+judge-bookmark-\S+\.md)$", err, re.M).group(1)
            self.assertIn("Be strict.", Path(packet).read_text())
            code, _, err = akit(root, "bookmark", "add", "wiki/t", "--when", "Use before x", "--verdict", "reject: background only")
            self.assertEqual(code, 1)
            ok(akit(root, "bookmark", "add", "wiki/t", "--when", "Use before x", "--verdict", "VERDICT: approve: real mistake"))
            self.assertEqual(fm.load(root / "wiki/t/_page.md").meta["bookmark_approval"], "judge: approve: real mistake")

    def test_judge_command_via_env(self):
        import os
        with TempDir() as root:
            make_wiki(root, agents=())
            ok(akit(root, "page", "new", "t", "T", "--summary", "s"))
            for rel in ["agent-kit", "agent-kit/judges", "agent-kit/judges/bookmark"]:
                (root / "wiki" / rel).mkdir(parents=True, exist_ok=True)
                (root / "wiki" / rel / "_page.md").write_text("---\ntitle: x\n---\n")
            os.environ["AKIT_JUDGE"] = "cat >/dev/null; echo 'criteria ok'; echo 'VERDICT: approve: fine'"
            try:
                ok(akit(root, "bookmark", "add", "wiki/t", "--when", "Use before x"))
            finally:
                os.environ.pop("AKIT_JUDGE")
            self.assertEqual(fm.load(root / "wiki/t/_page.md").meta["bookmark_approval"], "judge: approve: fine")


def setUpModule():
    global _cache
    _cache = tempfile.TemporaryDirectory()
    os.environ["XDG_CACHE_HOME"] = _cache.name
    os.environ["XDG_CONFIG_HOME"] = _cache.name


def tearDownModule():
    os.environ.pop("XDG_CACHE_HOME", None)
    os.environ.pop("XDG_CONFIG_HOME", None)
    _cache.cleanup()


if __name__ == "__main__":
    unittest.main()
