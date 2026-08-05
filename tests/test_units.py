#!/usr/bin/env python3
"""Unit tests for non-security internals: Database, file attachment,
compaction, and small helpers. Run:  python3 tests/test_units.py"""
import importlib.machinery, importlib.util, os, shutil, sys, tempfile, unittest
import io
import json
import unittest.mock as um

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
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
        self.assertEqual(sorted(sk.seed()), ["brainstorm", "cloud-arch", "commit", "data-engineer", "finops", "fullstack", "pentest", "python", "qa", "reverse-engineer", "review"])
        self.assertEqual(sk.seed(), [])  # doesn't overwrite
        self.assertEqual(sorted(n for n, _ in sk.list()), ["brainstorm", "cloud-arch", "commit", "data-engineer", "finops", "fullstack", "pentest", "python", "qa", "reverse-engineer", "review"])
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

    def test_continue_auto_option_skips_future_prompts(self):
        app = m.App(); app.quiet = False
        app._auto_continue = False
        with um.patch("builtins.input", return_value="a"):
            r1 = app._continue_fn(12, 24)
        self.assertTrue(r1)
        self.assertTrue(app._auto_continue)     # 'a' sets the flag
        # subsequent calls must NOT prompt (flag set) and just continue
        with um.patch("builtins.input", side_effect=AssertionError("should not prompt")):
            r2 = app._continue_fn(40, 80)
        self.assertTrue(r2)

    def test_continue_no_stops(self):
        app = m.App(); app.quiet = False
        with um.patch("builtins.input", return_value="n"):
            self.assertFalse(app._continue_fn(12, 24))

    def test_plaintext_api_key_warns_in_profile(self):
        """H-5/V-04: storing a real API key in config.json must warn and
        suggest the env var; local placeholders must not warn."""
        app = m.App(); app.quiet = True
        buf = io.StringIO(); old = sys.stdout; sys.stdout = buf
        try:
            app._cmd_profile(["set", "openai.api_key", "sk-real-12345"])
        finally:
            sys.stdout = old
        out = buf.getvalue()
        self.assertIn("TERMUX_AI_API_KEY", out)          # env var suggested
        self.assertIn("plaintext", out)
        # local placeholder key must NOT warn
        buf = io.StringIO(); old = sys.stdout; sys.stdout = buf
        try:
            app._cmd_profile(["set", "ollama.api_key", "ollama"])
        finally:
            sys.stdout = old
        self.assertNotIn("plaintext", buf.getvalue())

    def test_plaintext_api_key_warns_in_setup_wizard(self):
        app = m.App(); app.quiet = True
        buf = io.StringIO(); old = sys.stdout; sys.stdout = buf
        try:
            app._warn_plaintext_key("anthropic", "sk-ant-real")
        finally:
            sys.stdout = old
        self.assertIn("ANTHROPIC_API_KEY", buf.getvalue())
        buf = io.StringIO(); old = sys.stdout; sys.stdout = buf
        try:
            app._warn_plaintext_key("ollama", "ollama")
        finally:
            sys.stdout = old
        self.assertEqual(buf.getvalue(), "")

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

    def test_nat64_mapping_not_flagged_private(self):
        """A NAT64-mapped address (64:ff9b::/96, common on Android without
        IPv6) embeds the real IPv4 in its low 32 bits — a PUBLIC embedded IPv4
        must not be blocked, but one mapping to a private IPv4 (e.g.
        64:ff9b::7f00:1 = 127.0.0.1) must still be blocked."""
        self.assertFalse(m.Tools._ip_private("64:ff9b::14cd:f3a8"))   # -> 20.205.243.168 public
        self.assertTrue(m.Tools._ip_private("64:ff9b::7f00:1"))       # -> 127.0.0.1 loopback
        self.assertTrue(m.Tools._ip_private("64:ff9b::a00:1"))        # -> 10.0.0.1 private
        self.assertTrue(m.Tools._ip_private("127.0.0.1"))

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
            # Deterministic: this test checks the token header, not SSRF —
            # don't depend on live DNS (which may return NAT64/reserved addrs).
            with um.patch.object(m.Tools, "_is_private_host", staticmethod(lambda h: False)), \
                 um.patch.object(m.urllib.request, "urlopen", side_effect=fake_urlopen):
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

    def test_compact_summarizes_old_rounds(self):
        """When context exceeds budget, old tool rounds are LLM-summarized into
        a single message; recent rounds are kept intact."""
        b = m.OpenAICompatible({"iteration_history_budget": 500, "compact_keep_recent": 100}, "t", {"base_url": "http://localhost", "model": "x"})
        with um.patch.object(b, "chat", return_value=iter(["SUMMARY OF FILES READ"])):
            msgs = [
                self._msg("system", "sys"),
                self._msg("user", "do task"),
                self._msg("assistant", "reading", tool_calls=self._tc("1")),
                self._msg("tool", "X" * 5000, tool_call_id="1"),   # old, big
                self._msg("assistant", "more", tool_calls=self._tc("2")),
                self._msg("tool", "Y" * 200, tool_call_id="2"),    # recent, small
            ]
            n = b._compact_iteration_history(msgs)
        self.assertGreater(n, 0)                                       # something compacted
        summaries = [m for m in msgs if m["role"] == "user" and "Summary" in m.get("content", "")]
        self.assertTrue(summaries)                                     # summary message exists
        self.assertIn("SUMMARY OF FILES READ", summaries[0]["content"])
        recent_tools = [m for m in msgs if m.get("role") == "tool"]
        self.assertEqual(len(recent_tools), 1)                         # only recent kept

    def test_compact_falls_back_to_trim_on_failure(self):
        """If the summarization LLM call fails, fall back to crude trim."""
        b = m.OpenAICompatible({"iteration_history_budget": 500, "compact_keep_recent": 100}, "t", {"base_url": "http://localhost", "model": "x"})
        with um.patch.object(b, "chat", side_effect=Exception("network error")):
            msgs = [
                self._msg("system", "sys"),
                self._msg("user", "do task"),
                self._msg("assistant", "r1", tool_calls=self._tc("1")),
                self._msg("tool", "X" * 5000, tool_call_id="1"),
                self._msg("assistant", "r2", tool_calls=self._tc("2")),
                self._msg("tool", "Y" * 200, tool_call_id="2"),
            ]
            n = b._compact_iteration_history(msgs)
        self.assertGreater(n, 0)  # fell back to trim, still compacted something

    def test_compact_never_orphans_final_round_tool_results(self):
        """Regression: when the budget boundary falls inside the final round's
        tool results (a big file read at the end of a long task), compaction
        must NOT strip the assistant tool_calls while leaving its tool results
        behind — that makes the API reject with 'Messages with role tool must
        be a response to a preceding message with tool_calls' (HTTP 400)."""
        b = m.OpenAICompatible({"iteration_history_budget": 20000, "compact_keep_recent": 8000}, "t", {"base_url": "http://localhost", "model": "x"})
        with um.patch.object(b, "chat", return_value=iter(["SUMMARY" * 10])):
            msgs = [
                self._msg("system", "sys"),
                self._msg("user", "do task"),
                self._msg("assistant", "r0", tool_calls=self._tc("a0")),
                self._msg("tool", "X" * 5000, tool_call_id="a0"),
                self._msg("assistant", "r1", tool_calls=self._tc("b0")),
                self._msg("tool", "X" * 5000, tool_call_id="b0"),
                # final round: two huge results that alone exceed keep_recent
                self._msg("assistant", "final round", tool_calls=self._tc("c0") + self._tc("c1")),
                self._msg("tool", "A" * 50000, tool_call_id="c0"),
                self._msg("tool", "B" * 50000, tool_call_id="c1"),
            ]
            n = b._compact_iteration_history(msgs)
        self.assertGreater(n, 0)  # compaction still happened
        self.assertTrue(m.Backend._history_rounds_valid(msgs))  # and stayed valid
        # the final round's assistant + both tool results are all still present
        roles = [mm["role"] for mm in msgs]
        self.assertIn("assistant", roles)
        tools = [mm for mm in msgs if mm.get("role") == "tool"]
        self.assertEqual(len(tools), 2)

    def test_history_rounds_valid_flags_orphans(self):
        msgs = [
            self._msg("system", "sys"),
            self._msg("tool", "orphaned result", tool_call_id="zzz"),
        ]
        self.assertFalse(m.Backend._history_rounds_valid(msgs))
        msgs = [
            self._msg("system", "sys"),
            self._msg("assistant", "go", tool_calls=self._tc("1")),
            self._msg("tool", "result", tool_call_id="1"),
        ]
        self.assertTrue(m.Backend._history_rounds_valid(msgs))

    def test_graphify_finds_definitions_and_routes(self):
        d = os.path.join(tempfile.gettempdir(), "_graphify_test")
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "app.py"), "w") as f:
            f.write("from auth import check\n")
            f.write("class Order(Model):\n")
            f.write("    pass\n")
            f.write("def get_orders():\n")
            f.write("    pass\n")
            f.write("@app.route('/api/orders', methods=['GET'])\n")
            f.write("def orders():\n")
            f.write("    pass\n")
        with open(os.path.join(d, "auth.py"), "w") as f:
            f.write("def check():\n")
            f.write("    return True\n")
        result = m.Tools.run("graphify", {"path": d, "mode": "all"}, False)
        self.assertIn("get_orders", result)
        self.assertIn("Order", result)
        self.assertIn("check", result)
        self.assertIn("/api/orders", result)
        self.assertIn("auth", result)  # dependency or definition
        self.assertIn("graph TD", result)  # Mermaid
        shutil.rmtree(d)

    def test_low_value_trimmed_before_read_file(self):
        rf = "read-content-here " * 300   # high-value (read_file)
        lf = "listing-content " * 300    # low-value  (list_files)
        lf_head = m.est_tok(lf[:2500] + "\n...[older tool result trimmed]")
        # Budget where trimming ONLY the low-value result suffices.
        budget = m.est_tok(rf) + lf_head + 10
        msgs = [
            self._msg("system", "s"),
            self._msg("user", "go"),
            self._msg("assistant", "r1", tool_calls=self._tc("1", name="read_file")),
            self._msg("tool", rf, tool_call_id="1"),
            self._msg("assistant", "r2", tool_calls=self._tc("2", name="list_files")),
            self._msg("tool", lf, tool_call_id="2"),
            self._msg("assistant", "r3", tool_calls=self._tc("3", name="read_file")),
            self._msg("tool", "latest small", tool_call_id="3"),
        ]
        m.Backend._trim_iteration_history(msgs, budget=budget)
        self.assertNotIn("trimmed", msgs[3]["content"].lower())   # read_file kept intact
        self.assertIn("trimmed", msgs[5]["content"].lower())      # list_files trimmed first

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
        self.assertLess(len(msgs[3]["content"]), 2700)
        self.assertEqual(msgs[5]["content"], "Z" * 5000)      # latest untouched


class TestXlsxReader(_TmpHome):
    def _build_xlsx(self, shared, sheet_rows):
        """Build a minimal xlsx the parser can read. sheet_rows: list of rows,
        each a list of cell tuples (type, value): 's'=shared-string idx,
        'n'=number string, 'gap'=skip (sparse)."""
        import zipfile, io
        SS = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
        shared_xml = '<?xml version="1.0"?><sst %s>' % SS + "".join("<si><t>%s</t></si>" % s for s in shared) + "</sst>"
        sheet_xml = '<?xml version="1.0"?><worksheet %s><sheetData>' % SS
        for ri, row in enumerate(sheet_rows, 1):
            sheet_xml += '<row r="%d">' % ri
            for ci, cell in enumerate(row):
                col = chr(65 + ci)
                t, val = cell
                if t == "s": sheet_xml += '<c r="%s%d" t="s"><v>%s</v></c>' % (col, ri, val)
                elif t == "n": sheet_xml += '<c r="%s%d"><v>%s</v></c>' % (col, ri, val)
                # 'gap' -> omit the cell entirely (sparse)
            sheet_xml += '</row>'
        sheet_xml += '</sheetData></worksheet>'
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("xl/sharedStrings.xml", shared_xml)
            z.writestr("xl/worksheets/sheet1.xml", sheet_xml)
        return buf.getvalue()

    def test_xlsx_reconstructs_table(self):
        data = self._build_xlsx(["Name", "Age", "Alice", "Bob"], [
            [("s", 0), ("s", 1)],      # Name | Age
            [("s", 2), ("n", "30")],   # Alice | 30
            [("s", 3), ("n", "25")],   # Bob | 25
        ])
        p = os.path.join(os.getcwd(), "t.xlsx"); open(p, "wb").write(data)
        out = m.Tools.run("read_file", {"path": p})
        self.assertIn("Name | Age", out)
        self.assertIn("Alice | 30", out)
        self.assertIn("Bob | 25", out)

    def test_xlsx_aligns_sparse_columns(self):
        # row2: A=Bob, C=Engineer (B skipped) -> must keep 3 columns
        data = self._build_xlsx(["Name", "Age", "Bob", "Engineer"], [
            [("s", 0), ("s", 1)],
            [("s", 2), ("gap", None), ("s", 3)],
        ])
        p = os.path.join(os.getcwd(), "s.xlsx"); open(p, "wb").write(data)
        out = m.Tools.run("read_file", {"path": p})
        bob = [ln for ln in out.splitlines() if "Bob" in ln][0]
        parts = bob.split(" | ")
        self.assertEqual(len(parts), 3)        # gap-filled to 3 columns
        self.assertEqual(parts[0], "Bob")
        self.assertEqual(parts[1], "")         # the skipped column B
        self.assertEqual(parts[2], "Engineer")


class TestWriteFileAppend(_TmpHome):
    def test_append_adds_without_overwriting(self):
        app = m.App(); app.quiet = True
        # build_mode ON so write_file is allowed
        app.cfg.set("tools_enabled", True, save=False)
        p = os.path.join(os.getcwd(), "chunk.html")
        r1 = m.Tools.run("write_file", {"path": p, "content": "<html>\n<head></head>\n"}, build_mode=True)
        r2 = m.Tools.run("write_file", {"path": p, "content": "<body>chart</body>\n", "append": True}, build_mode=True)
        r3 = m.Tools.run("write_file", {"path": p, "content": "</html>\n", "append": True}, build_mode=True)
        self.assertIn("Written", r1)
        self.assertIn("Appended", r2)
        self.assertIn("Appended", r3)
        body = open(p).read()
        self.assertEqual(body, "<html>\n<head></head>\n<body>chart</body>\n</html>\n")


class TestFold(_TmpHome):
    def _feed(self, fmt, text):
        buf = io.StringIO(); old = sys.stdout; sys.stdout = buf
        try:
            fmt.feed(text); fmt.flush()
        finally:
            sys.stdout = old
        return buf.getvalue()

    def test_long_list_folds(self):
        f = m.MarkdownFormatter(fold=True, fold_head=8)
        out = self._feed(f, "\n".join("- item %d" % i for i in range(1, 16)) + "\n")
        self.assertIn("item 1", out); self.assertIn("item 8", out)   # head shown
        self.assertNotIn("item 9", out)                              # tail hidden
        self.assertIn("7 more", out)                                 # 15 - 8
        self.assertIn("/expand", out)

    def test_short_list_not_folded(self):
        f = m.MarkdownFormatter(fold=True, fold_head=8)
        out = self._feed(f, "\n".join("- item %d" % i for i in range(1, 6)) + "\n")
        self.assertIn("item 5", out)
        self.assertNotIn("more", out)

    def test_fold_disabled_shows_all(self):
        f = m.MarkdownFormatter(fold=False, fold_head=8)
        out = self._feed(f, "\n".join("- item %d" % i for i in range(1, 16)) + "\n")
        self.assertIn("item 15", out)
        self.assertNotIn("more", out)

    def test_long_table_folds(self):
        rows = "| Col |\n|---|\n" + "\n".join("| r%d |" % i for i in range(1, 13)) + "\n"
        f = m.MarkdownFormatter(fold=True, fold_head=8)
        out = self._feed(f, rows)
        self.assertIn("more", out)
        self.assertNotIn("r12", out)

    def test_fold_command_toggles(self):
        app = m.App(); app.quiet = True
        app._execute_command("/fold off")
        self.assertFalse(app.cfg.get("fold_long_blocks"))
        app._execute_command("/fold on")
        self.assertTrue(app.cfg.get("fold_long_blocks"))

    def test_expand_no_reply_warns(self):
        app = m.App(); app.quiet = True; app.last_reply = ""
        app._execute_command("/expand")   # warns, no crash

    def test_expand_inline_when_no_less(self):
        app = m.App(); app.quiet = False; app.last_reply = "FULL REPLY BODY"
        with um.patch.object(m.shutil, "which", return_value=None):
            buf = io.StringIO(); old = sys.stdout; sys.stdout = buf
            try: app._execute_command("/expand")
            finally: sys.stdout = old
        self.assertIn("FULL REPLY BODY", buf.getvalue())


class TestBackendResilience(_TmpHome):
    def setUp(self):
        super().setUp()
        self.b = m.Backend({})

    def test_stream_req_retries_transient_then_succeeds(self):
        calls = {"n": 0}
        def fake_req(url, data, headers):
            calls["n"] += 1
            if calls["n"] == 1:
                raise m.BackendError("Stream idle for too long. Aborting.", transient=True)
            return object()
        def fake_sse(resp, ndjson=False):
            yield {"type": "text", "content": "hi"}
        with um.patch.object(self.b, "_req", side_effect=fake_req), \
             um.patch.object(self.b, "_sse_lines", side_effect=fake_sse), \
             um.patch("time.sleep"):
            evts = list(self.b._stream_req("u", {}, {}, notify=lambda *a: None))
        self.assertEqual(calls["n"], 2)
        self.assertEqual(evts, [{"type": "text", "content": "hi"}])

    def test_stream_req_never_retries_mid_stream(self):
        calls = {"n": 0}
        def fake_req(url, data, headers):
            calls["n"] += 1
            return object()
        def fake_sse(resp, ndjson=False):
            yield {"type": "text", "content": "partial"}
            raise m.BackendError("Stream idle for too long. Aborting.", transient=True)
        with um.patch.object(self.b, "_req", side_effect=fake_req), \
             um.patch.object(self.b, "_sse_lines", side_effect=fake_sse):
            with self.assertRaises(m.BackendError):
                list(self.b._stream_req("u", {}, {}, notify=lambda *a: None))
        self.assertEqual(calls["n"], 1)   # mid-stream drop: never retried

    def test_stream_req_never_retries_permanent_error(self):
        calls = {"n": 0}
        def fake_req(url, data, headers):
            calls["n"] += 1
            raise m.BackendError("HTTP 401: bad key", transient=False)
        with um.patch.object(self.b, "_req", side_effect=fake_req):
            with self.assertRaises(m.BackendError):
                list(self.b._stream_req("u", {}, {}, notify=lambda *a: None))
        self.assertEqual(calls["n"], 1)

    def test_stream_req_retries_on_empty_body(self):
        calls = {"n": 0}
        def fake_req(url, data, headers):
            calls["n"] += 1
            return object()
        def fake_sse(resp, ndjson=False):
            if calls["n"] >= 2:
                yield {"choices": [{"delta": {"content": "hello"}}]}
                return
            return   # first attempt: empty body, no events
        with um.patch.object(self.b, "_req", side_effect=fake_req), \
             um.patch.object(self.b, "_sse_lines", side_effect=fake_sse), \
             um.patch("time.sleep"):
            evts = list(self.b._stream_req("u", {}, {}, notify=lambda *a: None))
        self.assertEqual(calls["n"], 2)
        self.assertEqual(evts, [{"choices": [{"delta": {"content": "hello"}}]}])

    def test_stream_req_retries_when_only_whitespace_before_drop(self):
        calls = {"n": 0}
        def fake_req(url, data, headers):
            calls["n"] += 1
            return object()
        def fake_sse(resp, ndjson=False):
            if calls["n"] == 1:
                yield {"choices": [{"delta": {"content": "\n"}}]}
                raise m.BackendError("Stream idle for too long. Aborting.", transient=True)
            yield {"choices": [{"delta": {"content": "real"}}]}
        with um.patch.object(self.b, "_req", side_effect=fake_req), \
             um.patch.object(self.b, "_sse_lines", side_effect=fake_sse), \
             um.patch("time.sleep"):
            evts = list(self.b._stream_req("u", {}, {}, notify=lambda *a: None))
        self.assertEqual(calls["n"], 2)
        self.assertEqual(evts[-1], {"choices": [{"delta": {"content": "real"}}]})

    def test_has_payload(self):
        self.assertTrue(m.Backend._has_payload({"choices": [{"delta": {"content": "hi"}}]}))
        self.assertFalse(m.Backend._has_payload({"choices": [{"delta": {"content": "   "}}]}))
        self.assertFalse(m.Backend._has_payload({"choices": [{"delta": {}}]}))
        self.assertTrue(m.Backend._has_payload({"type": "content_block_delta", "delta": {"text": "x"}}))
        self.assertFalse(m.Backend._has_payload({"type": "content_block_delta", "delta": {}}))
        self.assertTrue(m.Backend._has_payload({"type": "message_start"}))

    def test_identical_call_short_circuits_not_stops(self):
        """Repeating the exact same call returns 'already done' and keeps the
        model working -- it does NOT kill the task."""
        b = m.OpenAICompatible({}, "t", {"base_url": "http://localhost", "model": "x"})
        calls = {"n": 0}; run_count = {"n": 0}
        def fake_stream(url, data, headers, notify=None, mapper=None, ndjson=False):
            calls["n"] += 1
            if calls["n"] <= 3:
                yield {"choices": [{"delta": {"tool_calls": [{"index": 0, "id": "t1", "type": "function", "function": {"name": "read_file", "arguments": '{"path":"app.js","start":600}'}}]}, "finish_reason": "tool_calls"}]}
            else:
                yield {"choices": [{"delta": {}}]}
        def fake_run(name, args, bm, mr):
            run_count["n"] += 1; return "ok"
        with um.patch.object(b, "_stream_req", side_effect=fake_stream), \
             um.patch.object(m.Tools, "run", side_effect=fake_run):
            evts = list(b.chat_with_tools([{"role": "user", "content": "hi"}], confirm_batch_fn=lambda c: True))
        results = [e["result"] for e in evts if e["type"] == "tool_result"]
        self.assertEqual(run_count["n"], 1)                          # executed ONCE
        self.assertTrue(any("ALREADY DONE" in r for r in results[1:]))  # 2nd+ redirected
        self.assertFalse(any(e.get("fatal") for e in evts))           # no hard stop

    def test_read_file_offset_paging(self):
        p = os.path.join(tempfile.gettempdir(), "_f_tool_paging.txt")
        with open(p, "w") as f:
            f.write("\n".join(f"line {i}" for i in range(1, 21)))
        res = m.Tools.run("read_file", {"path": p, "start": 3, "end": 5}, False)
        self.assertIn(f"[lines 3\u20135 of 20]", res)
        self.assertIn("line 3", res)
        self.assertIn("line 5", res)
        self.assertNotIn("line 6", res)
        self.assertIn("continue", res)
        full = m.Tools.run("read_file", {"path": p}, False)   # no offsets
        self.assertNotIn("[lines", full)                       # backward compatible
        self.assertIn("line 1", full)

    def test_phase_nudge_injected_after_read_streak(self):
        b = m.OpenAICompatible({"gather_threshold": 3}, "t", {"base_url": "http://localhost", "model": "x"})
        calls = {"n": 0}; seen = []
        def fake_stream(url, data, headers, notify=None, mapper=None, ndjson=False):
            n = calls["n"]; calls["n"] += 1
            seen.append((n, data.get("messages", [])))
            if n == 0:
                yield {"choices": [{"delta": {"tool_calls": [{"index": 0, "id": "t1", "type": "function", "function": {"name": "read_file", "arguments": '{"path":"a"}'}}]}, "finish_reason": "tool_calls"}]}
            elif n == 1:
                yield {"choices": [{"delta": {"tool_calls": [{"index": 0, "id": "t2", "type": "function", "function": {"name": "read_file", "arguments": '{"path":"b"}'}}]}, "finish_reason": "tool_calls"}]}
            elif n == 2:
                yield {"choices": [{"delta": {"tool_calls": [{"index": 0, "id": "t3", "type": "function", "function": {"name": "read_file", "arguments": '{"path":"c"}'}}]}, "finish_reason": "tool_calls"}]}
            elif n == 3:
                yield {"choices": [{"delta": {"tool_calls": [{"index": 0, "id": "t4", "type": "function", "function": {"name": "write_file", "arguments": '{"path":"d","content":"x"}'}}]}, "finish_reason": "tool_calls"}]}
            else:
                yield {"choices": [{"delta": {}}, {"delta": {}}, {"delta": {}}, {"delta": {}}, {"delta": {}}]}
        with um.patch.object(b, "_stream_req", side_effect=fake_stream), \
             um.patch.object(m.Tools, "run", side_effect=lambda name, args, bm, mr: "ok"):
            evts = list(b.chat_with_tools([{"role": "user", "content": "hi"}], confirm_batch_fn=lambda c: True))
        notices = [e for e in evts if e["type"] == "notice"]
        self.assertTrue(any("Context phase" in e["content"] for e in notices))
        # the nudge is visible to the model in the WRITE request (4th request)
        write_req_msgs = [mm for n, mm in seen if n == 3][0]
        self.assertTrue(any(mm.get("role") == "system" and "Context phase" in mm["content"] for mm in write_req_msgs))

    def test_phase_nudge_honors_threshold(self):
        b = m.OpenAICompatible({"gather_threshold": 5}, "t", {"base_url": "http://localhost", "model": "x"})
        calls = {"n": 0}
        def fake_stream(url, data, headers, notify=None, mapper=None, ndjson=False):
            n = calls["n"]; calls["n"] += 1
            if n == 0:
                yield {"choices": [{"delta": {"tool_calls": [{"index": 0, "id": "t1", "type": "function", "function": {"name": "read_file", "arguments": '{"path":"a"}'}}]}, "finish_reason": "tool_calls"}]}
            elif n == 1:
                yield {"choices": [{"delta": {"tool_calls": [{"index": 0, "id": "t2", "type": "function", "function": {"name": "read_file", "arguments": '{"path":"b"}'}}]}, "finish_reason": "tool_calls"}]}
            elif n == 2:
                yield {"choices": [{"delta": {"tool_calls": [{"index": 0, "id": "t3", "type": "function", "function": {"name": "read_file", "arguments": '{"path":"c"}'}}]}, "finish_reason": "tool_calls"}]}
            elif n == 3:
                yield {"choices": [{"delta": {"tool_calls": [{"index": 0, "id": "t4", "type": "function", "function": {"name": "write_file", "arguments": '{"path":"d","content":"x"}'}}]}, "finish_reason": "tool_calls"}]}
            else:
                yield {"choices": [{"delta": {} }]}
        with um.patch.object(b, "_stream_req", side_effect=fake_stream), \
             um.patch.object(m.Tools, "run", side_effect=lambda name, args, bm, mr: "ok"):
            evts = list(b.chat_with_tools([{"role": "user", "content": "hi"}], confirm_batch_fn=lambda c: True))
        self.assertFalse(any("Context phase" in e.get("content", "") for e in evts if e["type"] == "notice"))

    def test_ver_tuple(self):
        self.assertEqual(m.App._ver_tuple("7.0.0"), (7, 0, 0))
        self.assertEqual(m.App._ver_tuple("6.9"), (6, 9, 0))
        self.assertTrue(m.App._ver_tuple("7.0.0") > m.App._ver_tuple("6.8.0"))
        self.assertFalse(m.App._ver_tuple("6.8.0") > m.App._ver_tuple("7.0.0"))

    def test_self_update_refuses_downgrade(self):
        app = m.App(); app.quiet = True
        body = b'__version__ = "6.8.0"\n' + b"x" * 10000
        class _Resp:
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def read(self): return body
        buf = io.StringIO(); old = sys.stdout; sys.stdout = buf
        try:
            with um.patch("urllib.request.urlopen", return_value=_Resp()):
                app._self_update()
        finally:
            sys.stdout = old
        out = buf.getvalue()
        self.assertIn("OLDER", out)
        self.assertIn("not downgrading", out)

    def test_self_update_reports_up_to_date_with_version(self):
        app = m.App(); app.quiet = True
        os.chdir(_REPO)   # Path(__file__).resolve() must point at the real repo ai
        body = open(os.path.join(_REPO, "ai"), "rb").read()
        class _Resp:
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def read(self): return body
        buf = io.StringIO(); old = sys.stdout; sys.stdout = buf
        try:
            with um.patch("urllib.request.urlopen", return_value=_Resp()):
                app._self_update()
        finally:
            sys.stdout = old
        out = buf.getvalue()
        self.assertIn(f"local v{m.__version__}", out)
        self.assertIn("Already up to date", out)

    def test_native_ollama_shim_detection_and_mapping(self):
        """Local qwen3 on Ollama routes through the native /api/chat shim with
        think:false (the /v1 compat endpoint ignores `think`, and qwen3's
        thinking mode burns minutes of phone CPU). Remote/non-qwen3/disabled
        stay on the OpenAI path."""
        b = m.OpenAICompatible({"ollama_no_think": True}, "t", {"base_url": "http://localhost:11434/v1", "model": "qwen3:1.7b"})
        self.assertTrue(b._native_ollama())
        self.assertEqual(b._url(), "http://localhost:11434/api/chat")
        d = b._payload([{"role": "user", "content": "hi"}], True, tools=[{"type": "function"}], temperature=0.3, max_tokens=512)
        self.assertIs(d["think"], False)
        self.assertEqual(d["options"]["num_predict"], 512)
        self.assertNotIn("max_tokens", d)
        # mapper: dict arguments -> JSON string, done_reason -> finish_reason
        evt = b._native_to_openai({"message": {"role": "assistant", "content": "x",
            "tool_calls": [{"id": "c1", "function": {"name": "list_files", "arguments": {"path": "."}}}]},
            "done_reason": "stop"})
        ch = evt["choices"][0]
        self.assertEqual(ch["delta"]["content"], "x")
        self.assertEqual(ch["delta"]["tool_calls"][0]["function"]["arguments"], '{"path": "."}')
        self.assertEqual(ch["finish_reason"], "stop")
        # remote -> OpenAI path
        b2 = m.OpenAICompatible({"ollama_no_think": True}, "t", {"base_url": "https://api.openai.com/v1", "model": "qwen3:1.7b"})
        self.assertFalse(b2._native_ollama())
        self.assertEqual(b2._url(), "https://api.openai.com/v1/chat/completions")
        # non-qwen3 local -> OpenAI path
        b3 = m.OpenAICompatible({"ollama_no_think": True}, "t", {"base_url": "http://localhost:11434/v1", "model": "llama3.2"})
        self.assertFalse(b3._native_ollama())
        # config disabled -> OpenAI path
        b4 = m.OpenAICompatible({"ollama_no_think": False}, "t", {"base_url": "http://localhost:11434/v1", "model": "qwen3:1.7b"})
        self.assertFalse(b4._native_ollama())

    def test_native_ollama_normalizes_tool_call_arguments(self):
        """Assistant tool_calls accumulated by the streaming tool loop carry
        `arguments` as a JSON STRING (OpenAI shape). Ollama's native /api/chat
        rejects the round-trip ("can't find closing '}' symbol") unless they're
        an OBJECT — _native_messages converts str->dict before sending."""
        msgs = [
            {"role": "system", "content": "x"},
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "", "tool_calls": [
                {"id": "call_1", "type": "function", "function": {"name": "list_files", "arguments": '{"path": "."}'}},
                {"id": "call_2", "type": "function", "function": {"name": "read_file", "arguments": ""}},
            ]},
            {"role": "tool", "tool_call_id": "call_1", "content": "LICENSE"},
        ]
        norm = m.OpenAICompatible._native_messages(msgs)
        asst = norm[2]
        self.assertEqual(asst["tool_calls"][0]["function"]["arguments"], {"path": "."})
        self.assertEqual(asst["tool_calls"][1]["function"]["arguments"], {})
        # non-assistant messages pass through untouched
        self.assertEqual(norm[3], msgs[3])

    def test_redundant_read_short_circuits_not_stops(self):
        """Reading lines already fetched returns 'already read' and continues --
        does NOT kill the task."""
        b = m.OpenAICompatible({}, "t", {"base_url": "http://localhost", "model": "x"})
        calls = {"n": 0}; run_count = {"n": 0}
        ranges = [(100, 500), (200, 400), (250, 350)]
        def fake_stream(url, data, headers, notify=None, mapper=None, ndjson=False):
            calls["n"] += 1
            if calls["n"] <= 3:
                lo, hi = ranges[calls["n"] - 1]
                yield {"choices": [{"delta": {"tool_calls": [{"index": 0, "id": "t%d" % calls["n"], "type": "function", "function": {"name": "read_file", "arguments": json.dumps({"path": "a", "start": lo, "end": hi})}}]}, "finish_reason": "tool_calls"}]}
            else:
                yield {"choices": [{"delta": {}}]}
        def fake_run(name, args, bm, mr):
            run_count["n"] += 1; return "line content here\n" * 10
        with um.patch.object(b, "_stream_req", side_effect=fake_stream), \
             um.patch.object(m.Tools, "run", side_effect=fake_run):
            evts = list(b.chat_with_tools([{"role": "user", "content": "hi"}], confirm_batch_fn=lambda c: True))
        results = [e["result"] for e in evts if e["type"] == "tool_result"]
        self.assertEqual(run_count["n"], 1)                          # only first (fresh) executed
        self.assertTrue(any("ALREADY READ" in r for r in results[1:]))  # 2nd+ redirected
        self.assertFalse(any(e.get("fatal") for e in evts))           # no hard stop

    def test_transient_classification(self):
        self.assertTrue(m.Backend._transient(m.BackendError("x", transient=True)))
        self.assertFalse(m.Backend._transient(m.BackendError("x", transient=False)))
        self.assertTrue(m.Backend._transient(TimeoutError("t")))
        self.assertFalse(m.Backend._transient(ValueError("boom")))

    def test_with_retry_succeeds_after_transient(self):
        calls = {"n": 0}
        def fn():
            calls["n"] += 1
            if calls["n"] == 1:
                raise m.BackendError("Request timed out.", transient=True)
            return "ok"
        with um.patch("time.sleep"):
            self.assertEqual(self.b._with_retry(fn), "ok")
        self.assertEqual(calls["n"], 2)

    def test_model_switch_preserves_session_context(self):
        app = m.App(); app.quiet = True
        app.cid = app.db.new_conv("ctx", "old-model", "openai")
        app.db.save_msg(app.cid, "user", "first question")
        app.db.save_msg(app.cid, "assistant", "first answer")
        app._execute_command("/model new-model-xyz")
        msgs = app.db.get_msgs(app.cid)
        self.assertEqual([x["content"] for x in msgs], ["first question", "first answer"])
        self.assertIsNotNone(app.cid)


class TestSessionResume(_TmpHome):
    def test_continue_resumes_last_session(self):
        app = m.App(); app.quiet = True
        cid = app.db.new_conv("t", "m", "openai")
        app.db.save_msg(cid, "user", "hello")
        app._set_last_cid(cid); app._resume_mode = "continue"
        app._maybe_resume()
        self.assertEqual(app.cid, cid)

    def test_auto_resume_respects_config(self):
        app = m.App(); app.quiet = True
        cid = app.db.new_conv("t", "m", "openai")
        app._set_last_cid(cid); app._resume_mode = "auto"
        app._maybe_resume()
        self.assertEqual(app.cid, cid)

        app2 = m.App(); app2.quiet = True
        app2.cfg.set("auto_resume", False)
        cid2 = app2.db.new_conv("t2", "m", "openai")
        app2._set_last_cid(cid2); app2._resume_mode = "auto"
        app2._maybe_resume()
        self.assertIsNone(app2.cid)

    def test_continue_with_no_session_does_nothing(self):
        app = m.App(); app.quiet = True
        app._resume_mode = "continue"
        app._maybe_resume()
        self.assertIsNone(app.cid)

    def test_stale_pointer_is_cleared(self):
        app = m.App(); app.quiet = True
        app._set_last_cid(999999); app._resume_mode = "auto"
        app._maybe_resume()
        self.assertIsNone(app._get_last_cid())
        self.assertIsNone(app.cid)

    def test_new_clears_pointer(self):
        app = m.App(); app.quiet = True
        cid = app.db.new_conv("t", "m", "openai")
        app.cid = cid; app._set_last_cid(cid)
        app._execute_command("/new")
        self.assertIsNone(app.cid)
        self.assertIsNone(app._get_last_cid())

    def test_load_persists_pointer(self):
        app = m.App(); app.quiet = True
        cid = app.db.new_conv("t", "m", "openai")
        app._execute_command("/load %d" % cid)
        self.assertEqual(app.cid, cid)
        self.assertEqual(app._get_last_cid(), cid)

    def test_delete_clears_pointer(self):
        app = m.App(); app.quiet = True
        cid = app.db.new_conv("t", "m", "openai")
        app.cid = cid; app._set_last_cid(cid)
        app._execute_command("/delete %d" % cid)
        self.assertIsNone(app.cid)
        self.assertIsNone(app._get_last_cid())


class TestNamedSessions(_TmpHome):
    def _conv(self, app, title="default"):
        cid = app.db.new_conv(title, "m", "openai")
        app.db.save_msg(cid, "user", "hello")
        return cid

    def test_save_pins_and_renames(self):
        app = m.App(); app.quiet = True
        cid = self._conv(app, "old")
        app.cid = cid
        app._execute_command("/save refactor-plan")
        conv = app.db.get_conv(cid)
        self.assertEqual(conv["title"], "refactor-plan")
        self.assertEqual(conv["pinned"], 1)

    def test_save_no_name_keeps_title_and_pins(self):
        app = m.App(); app.quiet = True
        cid = self._conv(app, "keep me")
        app.cid = cid
        app._execute_command("/save")
        conv = app.db.get_conv(cid)
        self.assertEqual(conv["title"], "keep me")
        self.assertEqual(conv["pinned"], 1)

    def test_unsave_unpins_keeps_chat(self):
        app = m.App(); app.quiet = True
        cid = self._conv(app)
        app.cid = cid
        app.db.set_pinned(cid, 1)
        app._execute_command("/unsave")
        self.assertEqual(app.db.get_conv(cid)["pinned"], 0)
        self.assertIsNotNone(app.db.get_conv(cid))  # chat kept

    def test_sessions_lists_pinned_first(self):
        app = m.App(); app.quiet = True
        a = self._conv(app, "aaa"); b = self._conv(app, "bbb")
        app.db.set_pinned(b, 1)
        rows = app.db.list_sessions(limit=50)
        ids = [r["id"] for r in rows]
        # b pinned should appear before a
        self.assertLess(ids.index(b), ids.index(a))
        self.assertTrue(rows[ids.index(b)]["pinned"])

    def test_load_by_name(self):
        app = m.App(); app.quiet = True
        cid = self._conv(app, "deploy-checklist")
        app._execute_command("/load deploy")
        self.assertEqual(app.cid, cid)
        self.assertEqual(app._get_last_cid(), cid)

    def test_load_by_name_not_found(self):
        app = m.App(); app.quiet = True
        self._conv(app, "other-task")
        app._execute_command("/load nope-xyz")
        self.assertIsNone(app.cid)

    def test_pinned_column_present_and_usable(self):
        # Fresh DB has the pinned column; the setter exercises the migration path
        app = m.App(); app.quiet = True
        cid = self._conv(app)
        self.assertIn("pinned", {c[1] for c in app.db.conn.execute("PRAGMA table_info(conversations)")})
        app.db.set_pinned(cid, 1)
        self.assertEqual(app.db.get_conv(cid)["pinned"], 1)


class TestResumeQuality(_TmpHome):
    def _capture(self, fn):
        buf = io.StringIO(); old = sys.stdout; sys.stdout = buf
        try: fn()
        finally: sys.stdout = old
        return buf.getvalue()

    def test_resume_banner_notes_model_change(self):
        app = m.App(); app.quiet = False
        cid = app.db.new_conv("mytask", "m", "openai")
        app.db.save_msg(cid, "user", "hi", "oldmodel")
        if app.backend and isinstance(getattr(app.backend, "profile", None), dict):
            app.backend.profile["model"] = "current-model"
        out = self._capture(lambda: app._activate(cid, banner=True))
        self.assertIn("mytask", out)
        self.assertIn("now on current-model", out)
        self.assertIn("/retry", out)

    def test_resume_banner_same_model_shows_session_model(self):
        app = m.App(); app.quiet = False
        cid = app.db.new_conv("easy", "m", "openai")
        app.db.save_msg(cid, "user", "hi", "deepseek-chat")
        if app.backend and isinstance(getattr(app.backend, "profile", None), dict):
            app.backend.profile["model"] = "deepseek-chat"
        out = self._capture(lambda: app._activate(cid, banner=True))
        self.assertIn("easy", out)
        self.assertIn("was deepseek-chat", out)

    def test_compact_summary_reattaches_on_resume(self):
        app = m.App(); app.quiet = True
        cid = app.db.new_conv("task", "m", "openai")
        app.db.save_msg(cid, "user", "How do we ship?")
        app.db.save_msg(cid, "assistant", "Step one: ...")
        app.db.save_msg(cid, "user", "[Summary of the earlier conversation]\nKey facts: db scheme, files")
        app.db.save_msg(cid, "user", "continue")
        app.db.save_msg(cid, "assistant", "Step two done.")
        app._set_last_cid(cid); app._resume_mode = "continue"
        app._maybe_resume()
        self.assertEqual(app.cid, cid)
        msgs = app.db.get_msgs(cid)
        contents = [x["content"] for x in msgs]
        self.assertIn("[Summary of the earlier conversation]\nKey facts: db scheme, files", contents)
        self.assertEqual(contents[-1], "Step two done.")

    def test_show_on_resumed_session_prints_history(self):
        app = m.App(); app.quiet = True
        cid = app.db.new_conv("t", "m", "openai")
        app.db.save_msg(cid, "user", "question-one")
        app.db.save_msg(cid, "assistant", "answer-one")
        app._set_last_cid(cid); app._resume_mode = "continue"
        app._maybe_resume()
        self.assertEqual(app.cid, cid)
        out = self._capture(lambda: app._execute_command("/show"))
        self.assertIn("question-one", out)
        self.assertIn("answer-one", out)


class TestHygiene(_TmpHome):
    def _age(self, app, cid, days):
        app.db.conn.execute("UPDATE conversations SET updated_at = datetime('now', ?) WHERE id = ?", (f"-{days} days", cid))
        app.db.conn.commit()

    def test_prune_deletes_old_unpinned_keeps_pinned_and_recent(self):
        app = m.App(); app.quiet = True
        old = app.db.new_conv("old", "m", "openai"); app.db.save_msg(old, "user", "hi")
        old_pin = app.db.new_conv("old-pin", "m", "openai"); app.db.save_msg(old_pin, "user", "hi"); app.db.set_pinned(old_pin, 1)
        recent = app.db.new_conv("recent", "m", "openai"); app.db.save_msg(recent, "user", "hi")
        self._age(app, old, 30); self._age(app, old_pin, 30)
        self.assertEqual(app.db.prune_old(7), 1)
        self.assertIsNone(app.db.get_conv(old))                 # pruned
        self.assertIsNotNone(app.db.get_conv(old_pin))          # pinned kept
        self.assertIsNotNone(app.db.get_conv(recent))           # recent kept

    def test_prune_zero_is_noop(self):
        app = m.App(); app.quiet = True
        cid = app.db.new_conv("x", "m", "openai")
        self._age(app, cid, 100)
        self.assertEqual(app.db.prune_old(0), 0)
        self.assertIsNotNone(app.db.get_conv(cid))

    def test_import_restores_session(self):
        app = m.App(); app.quiet = True
        path = os.path.join(self._home, "backup.md")
        with open(path, "w", encoding="utf-8") as f:
            f.write("# My Imported Chat\n\n**User:** hello there\nsecond line\n\n**Assistant:** hi!\n")
        app._execute_command("/import %s" % path)
        self.assertIsNotNone(app.cid)
        self.assertEqual(app.db.get_conv(app.cid)["title"], "My Imported Chat")
        self.assertEqual([(x["role"], x["content"]) for x in app.db.get_msgs(app.cid)],
                         [("user", "hello there\nsecond line"), ("assistant", "hi!")])
        self.assertEqual(app._get_last_cid(), app.cid)  # resume pointer set

    def test_import_missing_file_warns(self):
        app = m.App(); app.quiet = True
        app._execute_command("/import /nonexistent/nope.md")  # no crash
        self.assertIsNone(app.cid)

    def test_roundtrip_export_import(self):
        app = m.App(); app.quiet = True
        cid = app.db.new_conv("roundtrip", "m", "openai")
        app.db.save_msg(cid, "user", "q1"); app.db.save_msg(cid, "assistant", "a1")
        app.cid = cid
        path = os.path.join(self._home, "rt.md")
        app._execute_command("/export %s" % path)
        app2 = m.App(); app2.quiet = True
        app2._execute_command("/import %s" % path)
        self.assertEqual([(x["role"], x["content"]) for x in app2.db.get_msgs(app2.cid)],
                         [("user", "q1"), ("assistant", "a1")])
        self.assertEqual(app2.db.get_conv(app2.cid)["title"], "roundtrip")


class TestInterruptContinue(_TmpHome):
    def test_handle_interruption_auto_continues_and_saves(self):
        app = m.App(); app.quiet = True
        cid = app.db.new_conv("t", "m", "openai"); app.cid = cid
        ck = [{"role": "system", "content": "sys"},
              {"role": "user", "content": "build thing"},
              {"role": "assistant", "content": "", "tool_calls": [{"id": "c1", "type": "function", "function": {"name": "read_file", "arguments": "{}"}}]},
              {"role": "tool", "tool_call_id": "c1", "content": "file contents"}]
        calls = {"n": 0}
        def fake(msgs):
            calls["n"] += 1
            if calls["n"] == 1:
                app._pending_checkpoint = [dict(k) for k in msgs]
                return ""
            return "final answer"
        with um.patch.object(app, "_stream_tool_chat", side_effect=fake), um.patch("time.sleep"):
            app._handle_interruption(ck, "gemma")
        self.assertEqual(calls["n"], 2)
        self.assertEqual(app.db.get_msgs(cid)[-1]["content"], "final answer")
        self.assertIsNone(app.db.get_resume_state(cid))

    def test_auto_continue_off_keeps_checkpoint_and_saves_nothing(self):
        app = m.App(); app.quiet = True
        cid = app.db.new_conv("t", "m", "openai"); app.cid = cid
        app.cfg.set("auto_continue", False)
        ck = [{"role": "user", "content": "x"}, {"role": "tool", "tool_call_id": "c", "content": "r"}]
        with um.patch.object(app, "_stream_tool_chat") as st:
            app._handle_interruption(ck, "m")
        st.assert_not_called()
        self.assertIsNotNone(app.db.get_resume_state(cid))
        self.assertEqual(len(app.db.get_msgs(cid)), 0)

    def test_auto_continue_gives_up_after_max_and_keeps_checkpoint(self):
        app = m.App(); app.quiet = True
        cid = app.db.new_conv("t", "m", "openai"); app.cid = cid
        ck = [{"role": "user", "content": "x"}, {"role": "tool", "tool_call_id": "c", "content": "r"}]
        def fake(msgs):
            app._pending_checkpoint = [dict(k) for k in msgs]
            return ""   # keeps failing
        with um.patch.object(app, "_stream_tool_chat", side_effect=fake), um.patch("time.sleep") as sl:
            app._handle_interruption(ck, "m")
        self.assertIsNotNone(app.db.get_resume_state(cid))
        self.assertEqual(len(app.db.get_msgs(cid)), 0)

    def test_retry_continues_from_checkpoint(self):
        app = m.App(); app.quiet = True
        cid = app.db.new_conv("t", "m", "openai"); app.cid = cid; app.last_user_msg = "x"
        ck = [{"role": "user", "content": "x"}, {"role": "tool", "tool_call_id": "c", "content": "r"}]
        app.db.set_resume_state(cid, json.dumps(ck))
        with um.patch.object(app, "_stream_tool_chat", return_value="recovered"), um.patch("time.sleep"):
            app._cmd_regen([])
        self.assertEqual(app.db.get_msgs(cid)[-1]["content"], "recovered")
        self.assertIsNone(app.db.get_resume_state(cid))

    def test_count_tool_steps(self):
        msgs = [{"role": "tool", "content": "a"}, {"role": "tool", "content": "b"},
                {"role": "user", "content": [{"type": "tool_result", "content": "c"}]},
                {"content": "plain"}]
        self.assertEqual(m.App._count_tool_steps(msgs), 3)

    def test_resume_shows_pending_notice(self):
        app = m.App(); app.quiet = False
        cid = app.db.new_conv("t", "m", "openai")
        app.db.set_resume_state(cid, json.dumps([{"role": "tool", "tool_call_id": "c", "content": "r"}]))
        buf = io.StringIO(); old = sys.stdout; sys.stdout = buf
        try: app._activate(cid, banner=True)
        finally: sys.stdout = old
        self.assertIn("Interrupted turn pending", buf.getvalue())


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
