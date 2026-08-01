#!/usr/bin/env python3
"""Unit tests for non-security internals: Database, file attachment,
compaction, and small helpers. Run:  python3 tests/test_units.py"""
import importlib.machinery, importlib.util, os, shutil, sys, tempfile, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ARTIFACT = ROOT / "ai"   # the generated single-file artifact


def load():
    loader = importlib.machinery.SourceFileLoader("ai_units", str(ARTIFACT))
    spec = importlib.util.spec_from_loader("ai_units", loader)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


m = load()


class _TmpHome(unittest.TestCase):
    def setUp(self):
        self._home = tempfile.mkdtemp(prefix="aihome_")
        self._old_home = os.environ.get("HOME")
        os.environ["HOME"] = self._home
        # The artifact computes CONFIG_DIR/DB_FILE at import time, so just setting
        # HOME isn't enough -- re-point the module globals at a fresh, isolated
        # config dir so tests never share state or read stale rows/config.
        cfgdir = Path(self._home) / ".config" / "termux-ai"
        m.CONFIG_DIR = cfgdir
        m.CONFIG_FILE = cfgdir / "config.json"
        m.DB_FILE = cfgdir / "ai_history.db"
        m.HIST_FILE = cfgdir / "history"
        m.PID_FILE = cfgdir / "server.pid"
        cfgdir.mkdir(parents=True, exist_ok=True)
        self._old_cwd = os.getcwd()
        os.chdir(tempfile.mkdtemp(prefix="aiwd_"))

    def tearDown(self):
        os.chdir(self._old_cwd)
        if self._old_home is None: os.environ.pop("HOME", None)
        else: os.environ["HOME"] = self._old_home
        shutil.rmtree(self._home, ignore_errors=True)


class TestDatabase(_TmpHome):
    def test_undo_normal_pair(self):
        db = m.Database(); cid = db.new_conv("t", "m", "b")
        db.save_msg(cid, "user", "hi"); db.save_msg(cid, "assistant", "yo")
        n = db.undo_last_msg_pair(cid)
        self.assertEqual(n, 2)
        self.assertEqual(db.get_msgs(cid), [])

    def test_undo_orphan_user_prompt(self):
        # last msg is an unanswered user prompt -> remove only it
        db = m.Database(); cid = db.new_conv("t", "m", "b")
        db.save_msg(cid, "user", "q1"); db.save_msg(cid, "assistant", "a1"); db.save_msg(cid, "user", "q2")
        n = db.undo_last_msg_pair(cid)
        self.assertEqual(n, 1)
        roles = [x["role"] for x in db.get_msgs(cid)]
        self.assertEqual(roles, ["user", "assistant"])

    def test_undo_solo_user(self):
        db = m.Database(); cid = db.new_conv("t", "m", "b")
        db.save_msg(cid, "user", "solo")
        self.assertEqual(db.undo_last_msg_pair(cid), 1)
        self.assertEqual(db.get_msgs(cid), [])

    def test_undo_empty(self):
        db = m.Database(); cid = db.new_conv("t", "m", "b")
        self.assertEqual(db.undo_last_msg_pair(cid), 0)

    def test_tokens_by_model(self):
        db = m.Database(); cid = db.new_conv("t", "m", "b")
        db.save_msg(cid, "user", "hi", "gpt-4o-mini", 5)
        db.save_msg(cid, "assistant", "yo", "gpt-4o-mini", 7)
        db.save_msg(cid, "user", "more", "llama3.2", 3)
        self.assertEqual(db.get_tokens_by_model(), {"gpt-4o-mini": 12, "llama3.2": 3})
        self.assertEqual(db.get_conv_tokens(cid), 15)
        self.assertEqual(db.get_total_tokens(), 15)

    def test_rename_and_clear(self):
        db = m.Database(); cid = db.new_conv("old", "m", "b")
        db.save_msg(cid, "user", "x")
        db.rename_conv(cid, "new title")
        self.assertEqual(db.get_conv(cid)["title"], "new title")
        db.clear_conv_msgs(cid)
        self.assertEqual(db.get_msgs(cid), [])

    def test_get_msgs_order_and_limit(self):
        db = m.Database(); cid = db.new_conv("t", "m", "b")
        for i in range(5): db.save_msg(cid, "user", str(i))
        msgs = db.get_msgs(cid)              # ascending order
        self.assertEqual([x["content"] for x in msgs], ["0", "1", "2", "3", "4"])
        self.assertEqual(len(db.get_msgs(cid, limit=2)), 2)


class TestAttachFiles(_TmpHome):
    def _app(self):
        app = m.App(); app.quiet = True
        return app

    def test_at_path_and_dot_slash_and_tilde(self):
        app = self._app()
        Path("a.py").write_text("x=1\n")
        Path("b.txt").write_text("hello\n")
        out = app._attach_files("see @a.py and ./b.txt")
        self.assertIn("File:", out)              # at least one attached
        self.assertIn("x=1", out)                # a.py content
        self.assertIn("hello", out)              # b.txt content

    def test_tilde_expansion(self):
        app = self._app()
        (Path(os.environ["HOME"]) / "tildefile.md").write_text("tilde-content\n")
        out = app._attach_files("read ~/tildefile.md")
        self.assertIn("tilde-content", out)

    def test_nonexistent_left_untouched(self):
        app = self._app()
        out = app._attach_files("see @/no/such/file.py and ./missing.txt")
        self.assertNotIn("File:", out)           # nothing attached

    def test_directory_scan(self):
        app = self._app()
        os.mkdir("pkg"); os.mkdir("pkg/.git"); os.mkdir("pkg/node_modules")
        Path("pkg/main.py").write_text("print(1)\n")
        Path("pkg/util.py").write_text("y=2\n")
        Path("pkg/.git/hidden.py").write_text("SHOULD_NOT_APPEAR\n")
        Path("pkg/node_modules/junk.js").write_text("SHOULD_NOT_APPEAR\n")
        Path("pkg/notes.md").write_text("notes\n")
        out = app._attach_files("review ./pkg")
        self.assertIn("Directory:", out)
        self.assertIn("main.py", out) and self.assertIn("util.py", out)
        self.assertNotIn("SHOULD_NOT_APPEAR", out)   # .git / node_modules skipped

    def test_attach_disabled(self):
        app = self._app()
        app.cfg.set("attach_files", False)
        Path("a.py").write_text("x=1\n")
        self.assertEqual(app._attach_files("see @a.py"), "see @a.py")


class TestCompact(_TmpHome):
    def test_compact_replaces_history_with_summary(self):
        app = m.App(); app.quiet = True
        # mock backend.chat (used by _ask -> _compact_conversation) to return a summary
        app.backend = type("B", (), {
            "profile": {"model": "x"},
            "chat": lambda self, msgs, stream=True: iter(["SUMMARY: did X and Y."]),
        })()
        app.cid = app.db.new_conv("t", "x", "b")
        for i in range(5): app.db.save_msg(app.cid, "user" if i % 2 == 0 else "assistant", f"msg {i}")
        before = len(app.db.get_msgs(app.cid))
        ok, msg = app._compact_conversation(app.cid)
        after = app.db.get_msgs(app.cid)
        self.assertTrue(ok)
        self.assertLess(len(after), before)          # shrank
        self.assertIn("SUMMARY", after[0]["content"]) # summary kept as first msg
        # last two original messages retained
        self.assertEqual(after[-1]["content"], "msg 4")

    def test_compact_needs_more_messages(self):
        app = m.App(); app.quiet = True
        app.cid = app.db.new_conv("t", "x", "b")
        app.db.save_msg(app.cid, "user", "only one")
        ok, msg = app._compact_conversation(app.cid)
        self.assertFalse(ok)


class TestHelpers(unittest.TestCase):
    def test_parse_value(self):
        from_types = lambda v: type(m.parse_value(v)).__name__
        self.assertEqual(m.parse_value("true"), True)
        self.assertEqual(m.parse_value("OFF"), False)
        self.assertEqual(m.parse_value("42"), 42)
        self.assertEqual(m.parse_value("3.14"), 3.14)
        self.assertEqual(m.parse_value('"a b"'), "a b")
        self.assertEqual(m.parse_value("plain"), "plain")

    def test_match_price(self):
        app = m.App()
        self.assertGreater(app._match_price("gpt-4o-mini-2024-07-18"), 0)  # substring match
        self.assertEqual(app._match_price("llama3.2"), 0.0)                # local/free
        self.assertEqual(app._match_price("some-unknown-model"), 0.0)

    def test_strip_code_fence(self):
        self.assertEqual(m.App._strip_code_fence("```bash\nls -la\n```"), "ls -la")
        self.assertEqual(m.App._strip_code_fence("plain cmd"), "plain cmd")


if __name__ == "__main__":
    unittest.main(verbosity=2)
