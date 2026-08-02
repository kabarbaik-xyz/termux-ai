#!/usr/bin/env python3
"""Unit tests for non-security internals: Database, file attachment,
compaction, and small helpers. Run:  python3 tests/test_units.py"""
import importlib.machinery, importlib.util, os, shutil, sys, tempfile, unittest
import io
import unittest.mock as um
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


class TestSkills(_TmpHome):
    def _skills(self):
        return m.Skills(Path(self._home) / "skills")

    def test_valid_name(self):
        for ok in ["a", "review", "code-review", "python3", "a-b-c"]:
            self.assertTrue(m.Skills.valid_name(ok), ok)
        for bad in ["", "Bad", "with space", "-lead", "trail-", "double--hyphen", "x"*65, "under_score"]:
            self.assertFalse(m.Skills.valid_name(bad), bad)

    def test_parse_frontmatter(self):
        p = Path(self._home) / "s.md"
        p.write_text("---\nname: myskill\ndescription: Does X.\nmode: session\n---\nBody here.\n")
        meta, body = m.Skills.parse(p)
        self.assertEqual(meta["name"], "myskill")
        self.assertEqual(meta["mode"], "session")
        self.assertEqual(meta["description"], "Does X.")
        self.assertEqual(body, "Body here.")

    def test_parse_no_frontmatter_defaults(self):
        p = Path(self._home) / "plain.md"
        p.write_text("Just instructions.\n")
        meta, body = m.Skills.parse(p)
        self.assertEqual(meta["name"], "plain")
        self.assertEqual(meta["mode"], "once")
        self.assertIn("Just instructions", body)

    def test_parse_description_with_colon(self):
        p = Path(self._home) / "c.md"
        p.write_text("---\ndescription: time: 5pm\n---\nbody\n")
        meta, body = m.Skills.parse(p)
        self.assertEqual(meta["description"], "time: 5pm")

    def test_seed_and_load(self):
        sk = self._skills()
        self.assertEqual(sorted(sk.seed()), ["commit", "python", "reverse-engineer", "review"])
        self.assertEqual(sk.seed(), [])  # doesn't overwrite
        self.assertEqual(sorted(n for n, _ in sk.list()), ["commit", "python", "reverse-engineer", "review"])
        meta, body = sk.load("review")
        self.assertEqual(meta["mode"], "once")
        self.assertIn("senior code reviewer", body)
        self.assertEqual(sk.load("nope"), (None, None))

    def test_dir_skill(self):
        sk = self._skills(); sk.ensure_dir()
        (sk.dir / "pack").mkdir()
        (sk.dir / "pack" / "SKILL.md").write_text("---\nname: pack\ndescription: d\n---\nb\n")
        self.assertIn("pack", [n for n, _ in sk.list()])

    def test_catalog_lists_paths_and_respects_hidden(self):
        sk = self._skills()
        sk.seed()
        # a hidden skill (disable-model-invocation) should be excluded
        (sk.dir / "secret.md").write_text("---\nname: secret\ndescription: shh\ndisable-model-invocation: true\n---\nb\n")
        cat = sk.catalog()
        self.assertIn("<available-skills>", cat)
        self.assertIn('name="review"', cat)
        self.assertIn('path="', cat)                 # real path for read_file
        self.assertIn("read_file", cat)               # the load instruction
        self.assertNotIn("secret", cat)               # hidden skill excluded


class TestServerManager(_TmpHome):
    def test_pull_missing_binary_hints_install(self):
        with um.patch.object(m.shutil, "which", return_value=None):
            out = m.ServerManager.pull("qwen2.5:3b")
        self.assertIsNone(out)

    def test_pull_runs_ollama_pull(self):
        calls = []
        def fake_run(argv, **kw):
            calls.append(argv); return type("R", (), {"returncode": 0})()
        m.PID_FILE.write_text(f"{os.getpid()},ollama")  # server already "running"
        with um.patch.object(m.shutil, "which", return_value="/usr/bin/ollama"), \
             um.patch.object(m.subprocess, "run", side_effect=fake_run):
            out = m.ServerManager.pull("qwen2.5:3b")
        self.assertEqual(out, "qwen2.5:3b")
        self.assertIn(["ollama", "pull", "qwen2.5:3b"], calls)
        self.assertIn(["ollama", "list"], calls)  # refreshed after pull

    def test_models_auto_starts_server(self):
        calls = []
        def fake_run(argv, **kw):
            calls.append(argv); return type("R", (), {"returncode": 0})()
        class FakeProc: pid = 12345
        def fake_popen(argv, **kw):
            calls.append(argv); return FakeProc()
        with um.patch.object(m.shutil, "which", return_value="/usr/bin/ollama"), \
             um.patch.object(m.subprocess, "run", side_effect=fake_run), \
             um.patch.object(m.subprocess, "Popen", side_effect=fake_popen):
            m.ServerManager.models()
        self.assertIn(["ollama", "serve"], calls)  # auto-started
        self.assertIn(["ollama", "list"], calls)

    def test_cmd_server_dispatch(self):
        app = m.App(); app.quiet = True
        with um.patch.object(m.shutil, "which", return_value=None):
            app._execute_command("/server pull qwen2.5:3b")  # missing binary -> hint, no crash
        app._execute_command("/server")     # usage
        app._execute_command("/server bogus")  # unknown action


class TestConfirmStopsSpinner(_TmpHome):
    """Regression: when the backend asks for tool approval, the spinner thread is
    still running (the callback fires before the event that stops it). The
    prompt must stop it first or the \r spin overwrites the prompt + input."""
    def test_confirm_batch_stops_active_spinner(self):
        app = m.App(); app.quiet = False
        with um.patch.object(m, "IS_TTY", True), \
             um.patch("builtins.input", return_value="n"):
            buf = io.StringIO(); old = sys.stdout; sys.stdout = buf
            try:
                app.spinner = m.Spinner("thinking"); app.spinner.start()
                result = app._confirm_batch([{"name": "run_command", "args": {}}])
            finally:
                if app.spinner: app.spinner.stop()
                sys.stdout = old
        self.assertFalse(result)               # 'n' -> declined
        self.assertIsNone(app.spinner)         # spinner stopped before the prompt

    def test_continue_fn_stops_active_spinner(self):
        app = m.App(); app.quiet = False
        with um.patch.object(m, "IS_TTY", True), \
             um.patch("builtins.input", return_value="y"):
            buf = io.StringIO(); old = sys.stdout; sys.stdout = buf
            try:
                app.spinner = m.Spinner("thinking"); app.spinner.start()
                result = app._continue_fn(12, 24)
            finally:
                if app.spinner: app.spinner.stop()
                sys.stdout = old
        self.assertTrue(result)                 # 'y' -> continue
        self.assertIsNone(app.spinner)

    def test_stream_chat_stops_spinner_on_empty_reply(self):
        # The reported bug: an empty/broken reply streams no events, so the
        # spinner was never stopped and stacked with the next prompt.
        app = m.App(); app.quiet = False
        def empty_cwt(msgs, confirm, cont):
            return
            yield  # makes chat_with_tools a generator that yields nothing
        app.backend = type("B", (), {"profile": {"model": "x"}, "chat_with_tools": empty_cwt})()
        with um.patch.object(m, "IS_TTY", True):
            buf = io.StringIO(); old = sys.stdout; sys.stdout = buf
            try:
                app._stream_tool_chat([{"role": "system", "content": "s"}, {"role": "user", "content": "hi"}])
            finally:
                sys.stdout = old
        self.assertIsNone(app.spinner)   # finally must have stopped it


class TestFetchUrl(_TmpHome):
    def test_html_to_text(self):
        html_in = ("<html><head><title>T</title><style>x{}</style></head>"
                   "<body><h1>Title</h1><p>Hello &amp; <b>welcome</b></p>"
                   "<script>bad()</script></body></html>")
        out = m.Tools._html_to_text(html_in)
        self.assertIn("Title", out)
        self.assertIn("Hello & welcome", out)   # entity unescaped, tags stripped
        self.assertNotIn("bad()", out)          # script removed
        self.assertNotIn("<b>", out)

    def test_rejects_non_http(self):
        self.assertIn("must start with http", m.Tools._fetch_url("ftp://x.com"))
        self.assertIn("must start with http", m.Tools._fetch_url("example.com"))

    def test_blocks_private_addresses(self):
        self.assertIn("SSRF", m.Tools._fetch_url("http://127.0.0.1:8080/"))
        self.assertIn("SSRF", m.Tools._fetch_url("http://localhost/"))
        self.assertIn("SSRF", m.Tools._fetch_url("http://10.0.0.1/"))

    def test_private_allowed_with_env(self):
        os.environ["AI_FETCH_ALLOW_PRIVATE"] = "1"
        try:
            class FakeResp:
                headers = {}
                _data = b"ok from local"
                def read(self, n=-1): return self._data
                def geturl(self): return "http://127.0.0.1/"
                def __enter__(self): return self
                def __exit__(self, *a): return False
            with um.patch.object(m.urllib.request, "urlopen", return_value=FakeResp()):
                out = m.Tools._fetch_url("http://127.0.0.1/")
        finally:
            os.environ.pop("AI_FETCH_ALLOW_PRIVATE", None)
        self.assertIn("ok from local", out)

    def test_fetch_happy_path_html(self):
        class FakeResp:
            headers = {"Content-Type": "text/html; charset=utf-8"}
            _data = b"<html><body><h1>Hello World</h1><p>Body text</p></body></html>"
            def read(self, n=-1): return self._data
            def geturl(self): return "https://example.com/page"
            def __enter__(self): return self
            def __exit__(self, *a): return False
        with um.patch.object(m.urllib.request, "urlopen", return_value=FakeResp()):
            out = m.Tools._fetch_url("https://example.com/page")
        self.assertIn("Fetched https://example.com/page", out)
        self.assertIn("Hello World", out)
        self.assertIn("Body text", out)
        self.assertNotIn("<html>", out)         # HTML stripped

    def test_github_token_attached_for_api(self):
        os.environ["GITHUB_TOKEN"] = "ghp_test123"
        captured = {}
        class FakeResp:
            headers = {}
            _data = b"{}"
            def read(self, n=-1): return self._data
            def geturl(self): return "https://api.github.com/repos/x/y"
            def __enter__(self): return self
            def __exit__(self, *a): return False
        def fake_urlopen(req, timeout=10):
            captured["auth"] = req.headers.get("Authorization")
            return FakeResp()
        try:
            with um.patch.object(m.urllib.request, "urlopen", side_effect=fake_urlopen):
                m.Tools._fetch_url("https://api.github.com/repos/x/y")
        finally:
            os.environ.pop("GITHUB_TOKEN", None)
        self.assertEqual(captured.get("auth"), "token ghp_test123")

    def test_no_token_for_other_hosts(self):
        os.environ["GITHUB_TOKEN"] = "ghp_test123"
        captured = {}
        class FakeResp:
            headers = {}
            _data = b"plain"
            def read(self, n=-1): return self._data
            def geturl(self): return "https://example.com/"
            def __enter__(self): return self
            def __exit__(self, *a): return False
        def fake_urlopen(req, timeout=10):
            captured["auth"] = req.headers.get("Authorization")
            return FakeResp()
        try:
            with um.patch.object(m.urllib.request, "urlopen", side_effect=fake_urlopen):
                m.Tools._fetch_url("https://example.com/")
        finally:
            os.environ.pop("GITHUB_TOKEN", None)
        self.assertIsNone(captured.get("auth"))


class TestCloneRepo(_TmpHome):
    def test_requires_build_mode(self):
        out = m.Tools.run("clone_repo", {"url": "https://github.com/x/y"}, build_mode=False)
        self.assertIn("Build mode", out)

    def test_rejects_non_https(self):
        out = m.Tools.run("clone_repo", {"url": "git@github.com:x/y.git"}, build_mode=True)
        self.assertIn("https", out)
        out2 = m.Tools.run("clone_repo", {"url": "file:///etc"}, build_mode=True)
        self.assertIn("https", out2)

    def test_excluded_from_plan_tools(self):
        names = [t["function"]["name"] for t in m.Tools.PLAN_TOOLS]
        self.assertIn("fetch_url", names)      # read-only -> plan OK
        self.assertNotIn("clone_repo", names)  # writes -> build only
        self.assertNotIn("write_file", names)

    def test_happy_path(self):
        class FakeProc:
            returncode = 0
            def communicate(self, timeout=None): return ("Cloning into...", "")
        with um.patch.object(m.subprocess, "Popen", return_value=FakeProc()):
            out = m.Tools.run("clone_repo", {"url": "https://github.com/octocat/Hello-World.git"}, build_mode=True)
        self.assertIn("Cloned", out)
        import re as _re
        mm = _re.search(r"to:\s+(\S+)", out)
        if mm:
            shutil.rmtree(mm.group(1), ignore_errors=True)  # clean up the temp dir


class TestLocalScan(_TmpHome):
    def _tree(self):
        # app/main.py, app/utils/helpers.py + junk: node_modules, .git, dist
        base = Path(os.getcwd()) / "app"
        (base / "utils").mkdir(parents=True)
        (base / "main.py").write_text("print('main')")
        (base / "utils" / "helpers.py").write_text("def foo(): pass")
        (base / "node_modules").mkdir()
        (base / "node_modules" / "dep.js").write_text("var searchme = 1")
        (base / "dist").mkdir()
        (base / "dist" / "bundle.js").write_text("var searchme = 2")
        (base / ".git").mkdir()
        (base / ".git" / "config").write_text("searchme")
        return base

    def test_list_files_nonrecursive(self):
        app_dir = self._tree()
        out = m.Tools.run("list_files", {"path": str(app_dir)})
        self.assertIn("main.py", out)
        self.assertIn("utils", out)

    def test_list_files_recursive_ignores_junk(self):
        app_dir = self._tree()
        out = m.Tools.run("list_files", {"path": str(app_dir), "recursive": True})
        self.assertIn("main.py", out)
        self.assertIn(os.path.join("utils", "helpers.py"), out)
        self.assertNotIn("node_modules", out)
        self.assertNotIn(".git", out)
        self.assertNotIn("dist", out)

    def test_search_files_ignores_junk(self):
        app_dir = self._tree()
        # 'searchme' only exists inside node_modules/dist/.git -> all ignored
        out = m.Tools.run("search_files", {"query": "searchme", "path": str(app_dir)})
        self.assertEqual(out, "No matches")

    def test_search_files_finds_real(self):
        app_dir = self._tree()
        out = m.Tools.run("search_files", {"query": "print", "path": str(app_dir)})
        self.assertIn("main.py", out)


class TestTrimHistory(_TmpHome):
    def _msg(self, role, content, **kw):
        d = {"role": role, "content": content}; d.update(kw); return d
    def _tc(self, mid, name="read_file", args='{"path":"x"}'):
        return [{"id": mid, "type": "function", "function": {"name": name, "arguments": args}}]

    def test_latest_tool_result_is_protected(self):
        msgs = [
            self._msg("system", "sys"),
            self._msg("user", "go"),
            self._msg("assistant", "reading", tool_calls=self._tc("1")),
            self._msg("tool", "X" * 5000, tool_call_id="1"),  # the only/latest result
        ]
        m.Backend._trim_iteration_history(msgs, budget=400)  # tiny budget -> would trim
        self.assertEqual(msgs[3]["content"], "X" * 5000)    # but latest is protected

    def test_older_results_snippet_trimmed_latest_kept(self):
        old_big = "IMPORTANT-HEAD" + ("Y" * 5000)
        msgs = [
            self._msg("system", "sys"),
            self._msg("user", "go"),
            self._msg("assistant", "r1", tool_calls=self._tc("1")),
            self._msg("tool", old_big, tool_call_id="1"),       # OLDER big result
            self._msg("assistant", "r2", tool_calls=self._tc("2")),
            self._msg("tool", "Z" * 5000, tool_call_id="2"),    # LATEST big result
        ]
        m.Backend._trim_iteration_history(msgs, budget=400)
        self.assertIn("IMPORTANT-HEAD", msgs[3]["content"])   # head snippet survives
        self.assertIn("trimmed", msgs[3]["content"].lower())
        self.assertLess(len(msgs[3]["content"]), 700)
        self.assertEqual(msgs[5]["content"], "Z" * 5000)      # latest untouched


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
