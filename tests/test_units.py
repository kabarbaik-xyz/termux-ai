#!/usr/bin/env python3
"""Unit tests for non-security internals: Database, file attachment,
compaction, and small helpers. Run:  python3 tests/test_units.py"""
import importlib.machinery, importlib.util, os, shutil, sys, tempfile, unittest
import io
import json
import hashlib
import base64
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
        self.assertEqual(sorted(sk.seed()), ["brainstorm", "cloud-arch", "commit", "data-engineer", "finops", "frontend-tester", "fullstack", "pentest", "python", "qa", "reverse-engineer", "review"])
        self.assertEqual(sk.seed(), [])  # doesn't overwrite
        self.assertEqual(sorted(n for n, _ in sk.list()), ["brainstorm", "cloud-arch", "commit", "data-engineer", "finops", "frontend-tester", "fullstack", "pentest", "python", "qa", "reverse-engineer", "review"])
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

    def _bundled_fullstack(self):
        return m.EXAMPLES["fullstack.md"]

    def test_seed_second_call_is_noop(self):
        """After a fresh seed, re-seeding is a no-op (digest matches)."""
        sk = self._skills()
        self.assertNotEqual(sk.seed(), [])
        self.assertEqual(sk.seed(), [])
        # the digest sidecar is a hidden dotfile -> never shows in listings
        self.assertTrue((sk.dir / ".seed-digests.json").exists())
        self.assertNotIn(".seed-digests.json", [n for n, _ in sk.list()])

    def test_seed_upgrades_unchanged_bundled_copy(self):
        """When the bundled version changes and the installed copy is the
        untouched previous-bundled version, seed() auto-upgrades it."""
        sk = self._skills(); sk.seed()
        old = "OLD BUNDLED VERSION\n"
        (sk.dir / "fullstack.md").write_text(old)
        sk._write_digests({"fullstack": hashlib.sha256(old.encode()).hexdigest()})
        out = sk.seed()
        self.assertIn("fullstack", out)
        self.assertEqual((sk.dir / "fullstack.md").read_text(), self._bundled_fullstack())

    def test_seed_preserves_user_customized_copy(self):
        """A copy the user edited is NEVER clobbered, even when a new bundled
        version exists."""
        sk = self._skills(); sk.seed()
        custom = "MY CUSTOM FULLSTACK SKILL\n"
        (sk.dir / "fullstack.md").write_text(custom)
        # user edited after seed -> record still holds the old bundled digest
        out = sk.seed()
        self.assertNotIn("fullstack", out)
        self.assertEqual((sk.dir / "fullstack.md").read_text(), custom)

    def test_seed_first_transition_backs_up_and_upgrades(self):
        """Pre-digest installs (no record) are upgraded AND backed up to a
        .bak-<digest8> so nothing is ever lost."""
        sk = self._skills(); sk.seed()
        old = "OLD VERSION BEFORE DIGESTS\n"
        (sk.dir / "fullstack.md").write_text(old)
        (sk.dir / ".seed-digests.json").unlink()   # simulate legacy install
        out = sk.seed()
        self.assertIn("fullstack", out)
        self.assertEqual((sk.dir / "fullstack.md").read_text(), self._bundled_fullstack())
        bak = sk.dir / ("fullstack.md.bak-%s" % hashlib.sha256(self._bundled_fullstack().encode()).hexdigest()[:8])
        self.assertTrue(bak.exists())
        self.assertEqual(bak.read_text(), old)
        # backups never appear in skill listings
        self.assertNotIn(bak.name, [n for n, _ in sk.list()])


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

    def test_cmd_models_lists_models_and_ram_advice(self):
        app = m.App(); app.quiet = True
        # default profile is local Ollama (localhost:11434)
        tags = {"models": [{"name": "qwen3:1.7b", "size": int(1.4e9)},
                          {"name": "llama3.2:3b", "size": int(2.0e9)}]}
        class R:
            def __enter__(self): return self
            def __exit__(self, *a): pass
            def read(self): return json.dumps(tags).encode()
        with um.patch("urllib.request.urlopen", return_value=R()), \
             um.patch.object(m, "_free_ram_gb", return_value=3.5):
            buf = io.StringIO(); old = sys.stdout; sys.stdout = buf
            try: app._execute_command("/models")
            finally: sys.stdout = old
        out = buf.getvalue()
        self.assertIn("qwen3:1.7b", out)
        self.assertIn("llama3.2:3b", out)
        self.assertIn("Free RAM: 3.5 GB", out)
        self.assertIn("num_ctx", out)          # the RAM-based suggestion

    def test_cmd_server_dispatch(self):
        app = m.App(); app.quiet = True
        with um.patch.object(m.shutil, "which", return_value=None):
            app._execute_command("/server pull qwen2.5:3b")  # missing binary -> hint, no crash
        app._execute_command("/server")     # usage
        app._execute_command("/server bogus")  # unknown action


class TestMaxTokensMigrationHint(_TmpHome):
    """max_tokens is global (cloud + Anthropic read it). Users who lowered it
    for a local model (per the earlier /models advice) silently capped cloud.
    A one-time startup hint detects that + a cloud backend and points them at
    the local-only ollama_max_tokens -- without ever overriding their value."""

    def _cfg(self, overrides, backends):
        import json as _j
        base = {"backend": "ollama", "max_tokens": 8192, "backends": backends}
        base.update(overrides)
        m.CONFIG_FILE.write_text(_j.dumps(base))

    def _captured_validate(self):
        buf = io.StringIO(); old = sys.stdout; sys.stdout = buf
        try:
            app = m.App(); app.quiet = False
        finally:
            sys.stdout = old
        return buf.getvalue(), app

    CLOUD = {"ollama": {"base_url": "http://localhost:11434/v1", "model": "qwen3:1.7b", "api_key": "ollama"},
             "openai": {"base_url": "https://api.openai.com/v1", "model": "gpt-4o", "api_key": "sk-x"}}
    LOCAL_ONLY = {"ollama": {"base_url": "http://localhost:11434/v1", "model": "qwen3:1.7b", "api_key": "ollama"}}

    def test_hint_fires_once_for_low_max_tokens_with_cloud(self):
        self._cfg({"max_tokens": 2048}, self.CLOUD)
        out, app = self._captured_validate()
        self.assertIn("ALSO caps cloud", out)
        self.assertTrue(app.cfg.get("_hint_ollama_mt"))
        # 2nd startup with the persisted flag -> silent
        out2, _ = self._captured_validate()
        self.assertNotIn("ALSO caps cloud", out2)

    def test_no_hint_at_default_max_tokens(self):
        self._cfg({}, self.CLOUD)   # default 8192
        out, _ = self._captured_validate()
        self.assertNotIn("ALSO caps cloud", out)

    def test_no_hint_when_only_local_backends(self):
        self._cfg({"max_tokens": 2048}, self.LOCAL_ONLY)
        out, _ = self._captured_validate()
        self.assertNotIn("ALSO caps cloud", out)   # nothing to leak to


class TestCliSkillArgs(_TmpHome):
    """The --skill CLI flag activates comma-separated skills for one run.
    Missing skills warn + confirm; declining exits, non-TTY continues."""

    def _app(self):
        app = m.App(); app.quiet = True; return app

    def test_loads_real_comma_separated_skills(self):
        app = self._app()
        self.assertTrue(app._apply_skill_args("fullstack,python"))
        names = {n for n, _ in app.active_session_skills}
        self.assertEqual(names, {"fullstack", "python"})

    def test_missing_skill_warns_and_continues_non_tty(self):
        app = self._app()
        buf = io.StringIO(); old = sys.stdout; sys.stdout = buf
        try:
            ok = app._apply_skill_args("fullstack,ghostskill")
        finally:
            sys.stdout = old
        self.assertTrue(ok)                                   # non-TTY -> continue
        self.assertIn("fullstack", {n for n, _ in app.active_session_skills})
        self.assertNotIn("ghostskill", {n for n, _ in app.active_session_skills})
        self.assertIn("Skill not found: ghostskill", buf.getvalue())

    def test_missing_skill_tty_decline_returns_false(self):
        app = self._app()
        with um.patch.object(m, "IS_TTY", True), \
             um.patch.object(sys.stdin, "isatty", return_value=True), \
             um.patch("builtins.input", return_value="n"):
            self.assertFalse(app._apply_skill_args("ghostskill"))   # caller exits

    def test_missing_skill_tty_accept_continues(self):
        app = self._app()
        with um.patch.object(m, "IS_TTY", True), \
             um.patch.object(sys.stdin, "isatty", return_value=True), \
             um.patch("builtins.input", return_value="y"):
            self.assertTrue(app._apply_skill_args("fullstack"))


class TestProjectContext(_TmpHome):
    """CONTEXT.md project memory: auto-attached to the system prompt each turn,
    cached per session, refreshed on mtime change, cap-enforced, toggleable."""

    def setUp(self):
        super().setUp()
        self._old_cwd = os.getcwd()
        self.tmp = tempfile.mkdtemp(prefix="aictx_")
        os.chdir(self.tmp)

    def tearDown(self):
        os.chdir(self._old_cwd)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _app(self):
        app = m.App(); app.quiet = True; return app

    def test_attaches_and_refreshes_on_change(self):
        open("CONTEXT.md", "w").write("Stack: python, stdlib only.")
        app = self._app()
        ctx = app._project_context()
        self.assertIn("Stack: python", ctx)
        # cached: same content returned without a re-read
        self.assertEqual(app._project_context(), ctx)
        # file changed (new mtime) -> refreshed
        import time as _t; _t.sleep(0.02)
        open("CONTEXT.md", "w").write("Stack: python + rust.")
        self.assertIn("rust", app._project_context())

    def test_fallback_path_and_absent(self):
        os.makedirs(".ai", exist_ok=True)
        open(".ai/context.md", "w").write("alt path")
        app = self._app()
        self.assertIn("alt path", app._project_context())
        # absent -> empty string, no crash
        os.remove(".ai/context.md")
        self.assertEqual(app._project_context(), "")

    def test_cap_and_session_off(self):
        open("CONTEXT.md", "w").write("x" * 50000)
        app = self._app()
        app.cfg.set("max_context_md", 1000, save=False)
        self.assertLessEqual(len(app._project_context()), 1000)
        app._ctx_disabled = True
        self.assertEqual(app._project_context(), "")

    def test_warm_prefix_matches_first_real_turn(self):
        """KV-cache guarantee: the startup warm-prime sends the SAME system
        prompt (persona + CONTEXT.md + gather workflow) the first real turn
        sends. Ollama's cache only hits on a byte-identical prefix -- any drift
        (e.g. warm sending the bare persona) silently wastes the prime. This
        locks _assemble_system_prompt as the single source for BOTH."""
        # scenario: CONTEXT.md present + gather_first on (CLOUD backend -- local
        # chat models correctly skip the gather line)
        open("CONTEXT.md", "w").write("FACT-7")
        app = m.App(); app.quiet = True
        app.cfg.set("ollama_warm", True, save=False)
        app.cfg.set_path("backends.cloud", {"base_url": "https://x.test/v1", "model": "gpt-4o", "api_key": "k"}, save=False)
        app.cfg.set("backend", "cloud", save=False)
        app.backend = m.get_backend(app.cfg)
        expected = app._assemble_system_prompt()
        self.assertIn("FACT-7", expected)                 # CONTEXT.md included
        self.assertIn("WORKFLOW: gather", expected)        # gather line included
        # the first real _chat sends exactly this as msgs[0]
        captured = {}
        def fake_chat(msgs, confirm_batch_fn=None, continue_fn=None):
            captured["sysp"] = msgs[0]["content"]
            yield {"type": "text", "content": "ok"}
        with um.patch.object(app.backend, "chat_with_tools", side_effect=fake_chat):
            app._chat("hello")
        self.assertEqual(captured["sysp"], expected)       # byte-identical prefix

    def test_chat_attaches_context_to_system_prompt(self):
        open("CONTEXT.md", "w").write("UNIQUE-PROJECT-FACT-42")
        app = self._app()
        captured = {}
        def fake_chat(msgs, confirm_batch_fn=None, continue_fn=None):
            captured["sysp"] = msgs[0]["content"]
            yield {"type": "text", "content": "ok"}
            return
        with um.patch.object(app.backend, "chat_with_tools", side_effect=fake_chat):
            app._chat("hello")
        self.assertIn("UNIQUE-PROJECT-FACT-42", captured["sysp"])
        self.assertIn("Project context", captured["sysp"])


class TestSkillSuggest(_TmpHome):
    """One-line skill hints: fires on distinctive trigger words, silent for
    generic chat, never when a session skill is active, and configurable off."""

    def _app(self):
        app = m.App(); app.quiet = False; return app

    def _out(self, app, text):
        buf = io.StringIO(); old = sys.stdout; sys.stdout = buf
        try: app._suggest_skill(text)
        finally: sys.stdout = old
        return buf.getvalue()

    def test_fires_on_trigger_word(self):
        app = self._app()
        out = self._out(app, "please write playwright test scenarios for this frontend")
        self.assertIn("frontend-tester", out)
        self.assertIn("/skill frontend-tester", out)
        out2 = self._out(app, "can you do a pentest on this box")
        self.assertIn("pentest", out2)

    def test_silent_for_generic_chat(self):
        app = self._app()
        self.assertEqual(self._out(app, "fix the bug in app.py"), "")
        self.assertEqual(self._out(app, "hello there"), "")

    def test_silent_when_session_skill_active_or_config_off(self):
        app = self._app()
        app.active_session_skills.append(("fullstack", "body"))
        self.assertEqual(self._out(app, "write playwright tests"), "")
        app2 = self._app()
        app2.cfg.set("skill_suggest", False, save=False)
        self.assertEqual(self._out(app2, "write playwright tests"), "")

    def test_silent_in_quiet_mode(self):
        app = m.App(); app.quiet = True
        self.assertEqual(self._out(app, "write playwright tests"), "")


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
        self.assertIn("must start with http", m.Tools.run("fetch_url", {"url": "ftp://x.com"}))
        self.assertIn("must start with http", m.Tools.run("fetch_url", {"url": "example.com"}))

    def test_blocks_private_addresses(self):
        self.assertIn("SSRF", m.Tools.run("fetch_url", {"url": "http://127.0.0.1:8080/"}))
        self.assertIn("SSRF", m.Tools.run("fetch_url", {"url": "http://localhost/"}))
        self.assertIn("SSRF", m.Tools.run("fetch_url", {"url": "http://10.0.0.1/"}))

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
                out = m.Tools.run("fetch_url", {"url": "http://127.0.0.1/"})
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

    def test_fetch_wikipedia_extracts_main_content(self):
        """_fetch_url on a wikipedia.org host slices #mw-content-text so the
        model gets the article, not the sidebar/nav/footer (~500KB of junk)."""
        page = ('<html><body><div id="mw-panel">Main menu<br>Navigation<br>Donate</div>'
            '<div id="mw-content-text"><h1>Prabowo</h1><p>Born 1951.</p>'
            '<p>{{nobold|{{lang|id|Bapak}}}}</p>'
            '<p>"native_name":{"wt":"ngoko"}</p></div>'
            '<div id="catlinks">Categories...</div></body></html>').encode()
        class FakeResp:
            headers = {"Content-Type": "text/html"}
            _data = page
            def read(self, n=-1): return self._data
            def geturl(self): return "https://en.wikipedia.org/wiki/Prabowo_Subianto"
            def __enter__(self): return self
            def __exit__(self, *a): return False
        with um.patch.object(m.urllib.request, "urlopen", return_value=FakeResp()):
            out = m.Tools._fetch_url("https://en.wikipedia.org/wiki/Prabowo_Subianto")
        self.assertIn("Prabowo", out)
        self.assertIn("Born 1951.", out)
        self.assertNotIn("Main menu", out)      # sidebar junk removed
        self.assertNotIn("Donate", out)
        self.assertNotIn("catlinks", out)       # footer categories removed
        self.assertNotIn("{{", out)             # wikitext template cruft gone
        self.assertNotIn('"wt":', out)          # Parsoid JSON gone

    def test_web_search_parses_bing_and_decodes_base64_urls(self):
        """Bing's HTML results: 10 b_algo blocks, and result links are wrapped
        (/ck/a?...u=a1<base64>) — the base64 must be decoded to the real URL."""
        target = "https://www.accuweather.com/en/id/yogyakarta/208977/weather"
        wrapped = "https://www.bing.com/ck/a?!&&p=1&amp;u=a1" + base64.b64encode(target.encode()).decode()
        body = ('<li class="b_algo"><h2><a href="' + wrapped + '">Yogyakarta Weather</a></h2>'
                '<p>Hourly forecast for Yogyakarta.</p></li>'
                '<li class="b_algo"><h2><a href="https://weather.com/id-YO">Weather.com</a></h2>'
                '<p>10-day outlook.</p></li>').encode()
        class FakeResp:
            headers = {"Content-Type": "text/html"}
            _data = body
            def read(self, n=-1): return self._data
            def geturl(self): return "https://www.bing.com/search?q=weather"
            def __enter__(self): return self
            def __exit__(self, *a): return False
        with um.patch.object(m.urllib.request, "urlopen", return_value=FakeResp()):
            out = m.Tools._web_search("yogyakarta weather", timeout=5)
        self.assertIn("Yogyakarta Weather", out)
        self.assertIn(target, out)              # base64-wrapped URL decoded
        self.assertIn("weather.com", out)       # plain URL kept

    def test_web_search_falls_back_to_wikipedia(self):
        """When Bing is unreachable, _web_search uses Wikipedia's search API."""
        calls = {"n": 0}
        def fake_urlopen(req, timeout=10):
            calls["n"] += 1
            if calls["n"] == 1:
                raise m.urllib.error.URLError("bing unreachable")
            class FakeResp:
                headers = {"Content-Type": "application/json"}
                _data = (b'{"query":{"search":[{"title":"Yogyakarta",'
                         b'"snippet":"City on <b>Java</b> island."}]}}')
                def read(self, n=-1): return self._data
                def geturl(self): return req.full_url
                def __enter__(self): return self
                def __exit__(self, *a): return False
            return FakeResp()
        with um.patch.object(m.urllib.request, "urlopen", side_effect=fake_urlopen):
            out = m.Tools._web_search("yogyakarta", timeout=5)
        self.assertIn("Yogyakarta", out)
        self.assertIn("https://en.wikipedia.org/wiki/Yogyakarta", out)

    def test_web_search_canary_fixtures(self):
        """CANARY: each SERP parser is pinned to a frozen HTML/JSON fixture.
        If a provider changes its markup, THIS fails loudly in CI instead of
        silently degrading to the fallback chain in production."""
        fx = Path(__file__).resolve().parent / "fixtures"
        bing = m.Tools._parse_bing_html((fx / "bing_serp.html").read_text())
        self.assertEqual(len(bing), 2)
        self.assertEqual(bing[0][0], "Yogyakarta Weather Forecast")
        self.assertTrue(bing[0][1].startswith("https://www.accuweather.com/"))  # u=a1 unwrapped
        self.assertEqual(bing[1][1], "https://weather.com/id-YO")               # direct kept
        self.assertIn("10-day", bing[1][2])

        ddg = m.Tools._parse_ddg_html((fx / "ddg_serp.html").read_text())
        self.assertEqual(len(ddg), 2)
        self.assertEqual(ddg[0][0], "Yogyakarta | History, Map, & Facts | Britannica")  # entity unescaped
        self.assertEqual(ddg[0][1], "https://www.britannica.com/place/Yogyakarta")      # uddg unwrapped
        self.assertIn("island of Java", ddg[0][2])                                    # snippet paired
        self.assertEqual(ddg[1][1], "https://en.wikipedia.org/wiki/Yogyakarta")        # direct kept

        wiki = m.Tools._parse_wikipedia_json((fx / "wikipedia_search.json").read_text())
        self.assertEqual(wiki[0], ("Yogyakarta", "https://en.wikipedia.org/wiki/Yogyakarta",
                                   "City on Java island."))

    def test_web_search_ddg_fallback_when_bing_down(self):
        """Bing unreachable -> DuckDuckGo serves results (second keyless source
        so a single provider outage/markup change doesn't kill web search)."""
        fx = Path(__file__).resolve().parent / "fixtures"
        ddg_body = (fx / "ddg_serp.html").read_bytes()
        def fake_urlopen(req, timeout=10):
            if "bing.com" in req.full_url:
                raise m.urllib.error.URLError("bing down")
            class FakeResp:
                headers = {"Content-Type": "text/html"}
                _data = ddg_body
                def read(self, n=-1): return self._data
                def geturl(self): return req.full_url
                def __enter__(self): return self
                def __exit__(self, *a): return False
            return FakeResp()
        with um.patch.object(m.urllib.request, "urlopen", side_effect=fake_urlopen):
            out = m.Tools._web_search("yogyakarta", timeout=5)
        self.assertIn("Britannica", out)                                # DDG results used
        self.assertIn("https://www.britannica.com/place/Yogyakarta", out)  # uddg unwrapped

    def test_web_search_empty_query(self):
        self.assertIn("Error: query is empty", m.Tools.run("web_search", {"query": "  "}))

    def test_weather_returns_forecast(self):
        """_weather geocodes the city (call 1) then pulls current + daily
        forecast (call 2) and returns a concise readable summary."""
        calls = {"n": 0}
        def fake_urlopen(req, timeout=10):
            calls["n"] += 1
            class FakeResp:
                _data = (b'{"results":[{"name":"Yogyakarta","country":"Indonesia",'
                         b'"latitude":-7.80139,"longitude":110.36472}]}' if calls["n"] == 1 else
                         b'{"current":{"temperature_2m":24.2,"relative_humidity_2m":77,'
                         b'"apparent_temperature":27.5,"weather_code":3,"wind_speed_10m":3.6},'
                         b'"daily":{"time":["2026-08-15","2026-08-16"],'
                         b'"temperature_2m_max":[30.8,34.0],"temperature_2m_min":[21.4,21.4],'
                         b'"weather_code":[51,55],"precipitation_probability_max":[2,22]}}')
                def read(self, n=-1): return self._data
                def geturl(self): return "http://open-meteo/"
                def __enter__(self): return self
                def __exit__(self, *a): return False
            return FakeResp()
        with um.patch.object(m.urllib.request, "urlopen", side_effect=fake_urlopen):
            out = m.Tools._weather("Yogyakarta", timeout=5)
        self.assertEqual(calls["n"], 2)
        self.assertIn("Yogyakarta", out)
        self.assertIn("Overcast", out)
        self.assertIn("24.2 C", out)
        self.assertIn("77%", out)
        self.assertIn("2026-08-15", out)
        self.assertIn("rain 2%", out)

    def test_weather_empty_and_unknown(self):
        self.assertIn("Error: city is empty", m.Tools.run("weather", {"city": "  "}))
        def fake_urlopen(req, timeout=10):
            class FakeResp:
                _data = b'{"results":[]}'
                def read(self, n=-1): return self._data
                def geturl(self): return "http://open-meteo/"
                def __enter__(self): return self
                def __exit__(self, *a): return False
            return FakeResp()
        with um.patch.object(m.urllib.request, "urlopen", side_effect=fake_urlopen):
            self.assertIn("No location found", m.Tools._weather("atlantis-xyz", timeout=5))

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
    def test_attended_long_task_extends_past_iteration_limit(self):
        """A long multi-step task (install+build+test+fix) used to die at the hard
        max_iterations ceiling even when the user kept approving 'continue?'.
        Now each approved checkpoint EXTENDS the ceiling, so an attended task
        runs to completion; an unattended run (no continue_fn) still hard-stops
        (runaway protection for one-shot/piped mode)."""
        def drive(continue_fn):
            b = m.OpenAICompatible({"max_iterations": 6, "continue_every": 2}, "t",
                                   {"base_url": "http://localhost", "model": "x"})
            calls = {"n": 0}
            def fs(url, d, h, notify=None, mapper=None, ndjson=False):
                calls["n"] += 1
                if calls["n"] > 15:
                    yield {"choices": [{"delta": {}}]}; return
                # UNIQUE args each call so the stuck-loop detector doesn't fire
                yield {"choices": [{"delta": {"tool_calls": [{"index": 0, "id": f"t{calls['n']}",
                    "type": "function", "function": {"name": "list_files",
                    "arguments": '{"path":"./%d"}' % calls["n"]}}]}, "finish_reason": "tool_calls"}]}
            with um.patch.object(b, "_stream_req", side_effect=fs), \
                 um.patch.object(m.Tools, "run_checked", side_effect=lambda n, a, bm, mr: (True, "ok")):
                evts = list(b.chat_with_tools([{"role": "user", "content": "hi"}],
                                              confirm_batch_fn=lambda c: True, continue_fn=continue_fn))
            return calls["n"], any(e.get("fatal") for e in evts)
        # attended + approved: runs PAST max_iterations=6 to completion
        n_att, fatal_att = drive(lambda i, t: True)
        self.assertGreater(n_att, 6)
        self.assertFalse(fatal_att)
        # unattended (no continue_fn): hard stop at the ceiling
        n_un, fatal_un = drive(None)
        self.assertLessEqual(n_un, 6)
        self.assertTrue(fatal_un)

    def test_run_command_timeout_param_and_graceful_kill(self):
        """Long commands (npm install, builds) used to hit a hard 30s SIGKILL,
        corrupting state and forcing the model into a sleep/poll loop that
        burned the whole iteration budget. run_command now takes a `timeout`
        (clamped to [1,600]) so they finish in one call, and kills with SIGTERM
        first (SIGKILL mid-write corrupts e.g. npm reify)."""
        app = m.App(); app.quiet = True
        app.cfg.set("tools_enabled", True, save=False)   # BUILD mode
        # short-timeout kill: sleep 30 with timeout=2 -> killed at 2s
        r = m.Tools.run("run_command", {"command": "sleep 30", "timeout": 2}, build_mode=True)
        self.assertIn("timed out after 2s", r)
        # graceful: a TERM-trapping command can clean up before the SIGKILL
        r2 = m.Tools.run("run_command", {"command":
            "trap 'echo CLEANED; exit 0' TERM; sleep 30 & wait", "timeout": 2}, build_mode=True)
        self.assertIn("CLEANED", r2)   # SIGTERM was delivered, trap ran
        # default still works for a quick command
        self.assertEqual(m.Tools.run("run_command", {"command": "echo ok"}, build_mode=True).strip(), "ok")
        # timeout is in the schema so the model knows it can raise it
        rc = next(t for t in m.Tools.get_schemas(True) if t["function"]["name"] == "run_command")
        self.assertIn("timeout", rc["function"]["parameters"]["properties"])

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

    def test_req_is_single_attempt_no_double_retry(self):
        """_req must NOT retry internally -- it used to, compounding with
        _stream_req/_with_retry into up to 9 attempts on a persistent 429/503
        (the cause of slow, noisy cloud backends). Retry now lives in ONE place."""
        b = m.OpenAICompatible({"retries": 3}, "t", {"base_url": "https://x.test/v1", "model": "m", "api_key": "k"})
        calls = {"n": 0}
        class E429(m.urllib.error.HTTPError):
            def __init__(self):
                super().__init__("https://x.test/v1/chat/completions", 429, "x", {"Retry-After": "5"}, io.BytesIO(b"{}"))
        def boom(req, timeout=120):
            calls["n"] += 1; raise E429()
        with um.patch("urllib.request.urlopen", side_effect=boom):
            with self.assertRaises(m.BackendError) as cm:
                b._req("https://x.test/v1/chat/completions", {}, {})
        self.assertEqual(calls["n"], 1)             # single attempt, no internal loop
        self.assertTrue(cm.exception.transient)
        self.assertEqual(cm.exception.retry_after, 5)  # Retry-After parsed

    def test_stream_req_total_attempts_equal_retries_not_compounded(self):
        """A persistent transient error must be tried exactly `retries` times
        through _stream_req -- not retries x 3 (the old _req internal loop)."""
        b = m.OpenAICompatible({"retries": 3, "retry_delay": 1.0}, "t", {"base_url": "https://x.test/v1", "model": "m", "api_key": "k"})
        calls = {"n": 0}
        class E503(m.urllib.error.HTTPError):
            def __init__(self):
                super().__init__("https://x.test/v1/chat/completions", 503, "x", {}, io.BytesIO(b"{}"))
        def boom(req, timeout=120):
            calls["n"] += 1; raise E503()
        with um.patch("urllib.request.urlopen", side_effect=boom), um.patch("time.sleep"):
            with self.assertRaises(m.BackendError):
                list(b._stream_req("https://x.test/v1/chat/completions", {}, {}))
        self.assertEqual(calls["n"], 3)             # 3 total, NOT 9

    def test_retry_after_header_overrides_backoff_delay(self):
        """When a 429 carries Retry-After, the retry waits that long instead of
        the default exponential backoff (respects the server's rate-limit ask)."""
        b = m.OpenAICompatible({"retries": 3, "retry_delay": 1.0}, "t", {"base_url": "https://x.test/v1", "model": "m", "api_key": "k"})
        class E429(m.urllib.error.HTTPError):
            def __init__(self):
                super().__init__("https://x.test/v1/chat/completions", 429, "x", {"Retry-After": "7"}, io.BytesIO(b"{}"))
        delays = []
        with um.patch("urllib.request.urlopen", side_effect=lambda *a, **k: (_ for _ in ()).throw(E429())):
            with self.assertRaises(m.BackendError):
                list(b._stream_req("https://x.test/v1/chat/completions", {}, {}, notify=lambda a, t, d: delays.append(d)))
        self.assertEqual(delays, [7, 7])            # Retry-After used, not 1/2

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

    def test_think_filter_strips_reasoning_split_across_chunks(self):
        """Reasoning models (deepseek-r1, phi-reasoning) wrap chain-of-thought in
        <think>...</think>. ThinkFilter strips it from the stream even when the
        tag is split across chunk boundaries, so raw reasoning isn't dumped to
        the screen."""
        tf = m.ThinkFilter()
        out = []
        for c in ["Hello <th", "ink>secret reasoning", "</think>", " world <think>", "x", "</think>!"]:
            p = tf.feed(c)
            if p: out.append(p)
        p = tf.flush()
        if p: out.append(p)
        self.assertEqual("".join(out), "Hello  world !")
        # unclosed <think> at end of stream -> reasoning discarded
        tf2 = m.ThinkFilter()
        self.assertEqual(tf2.feed("hi <think>endless reasoning"), "hi ")
        self.assertEqual(tf2.flush(), "")
        # no tags -> passthrough
        self.assertEqual(m.ThinkFilter().feed("plain text"), "plain text")

    def test_split_think_routes_reasoning_into_events(self):
        """_split_think separates a complete content buffer into text/thinking
        segments; chat_with_tools uses it to yield dim 'thinking' events instead
        of mixing reasoning into the answer."""
        st = m.OpenAICompatible._split_think
        self.assertEqual(st("a<think>r</think>b<think>unclosed"),
                         [("text", "a"), ("thinking", "r"), ("text", "b"), ("thinking", "unclosed")])
        self.assertEqual(st("plain"), [("text", "plain")])
        self.assertEqual(st(""), [])

    def test_ollama_max_tokens_is_local_only_no_cloud_leak(self):
        """max_tokens is global (read by cloud + Anthropic too), so a low cap set
        for a slow phone-CPU model would cripple cloud replies. ollama_max_tokens
        overrides it on the native path ONLY -- cloud keeps its own max_tokens."""
        # local: override applies
        loc = m.OpenAICompatible({"ollama_no_think": True, "max_tokens": 8192, "ollama_max_tokens": 2048},
                                "ollama", {"base_url": "http://localhost:11434/v1", "model": "qwen3:1.7b"})
        loc._caps_cache["qwen3:1.7b"] = ["thinking"]
        d = loc._payload([{"role": "user", "content": "hi"}], True, max_tokens=None)
        self.assertEqual(d["options"]["num_predict"], 2048)
        # cloud: same config, override IGNORED
        cloud = m.OpenAICompatible({"max_tokens": 8192, "ollama_max_tokens": 2048},
                                   "openai", {"base_url": "https://api.openai.com/v1", "model": "gpt-4o", "api_key": "x"})
        d2 = cloud._payload([{"role": "user", "content": "hi"}], True, max_tokens=None)
        self.assertEqual(d2["max_tokens"], 8192)
        self.assertNotIn("options", d2)
        # local with override unset -> falls back to max_tokens
        loc2 = m.OpenAICompatible({"ollama_no_think": True, "max_tokens": 8192, "ollama_max_tokens": 0},
                                  "ollama", {"base_url": "http://localhost:11434/v1", "model": "qwen3:1.7b"})
        loc2._caps_cache["qwen3:1.7b"] = ["thinking"]
        d3 = loc2._payload([{"role": "user", "content": "hi"}], True, max_tokens=None)
        self.assertEqual(d3["options"]["num_predict"], 8192)

    def test_cloud_lock_full_tools_every_turn_in_build_mode(self):
        """CLOUD INVARIANT (Phase-1 lock): a cloud backend offers the FULL toolset
        EVERY turn in Build mode, regardless of message phrasing -- the local
        responsiveness gate must never touch cloud. Asserted via _tools_for and
        the actual schemas chat_with_tools sends."""
        c = m.OpenAICompatible({"tools_enabled": True}, "openai", {"base_url": "https://api.openai.com/v1", "model": "gpt-4o", "api_key": "x"})
        for msg in ("hi", "what can I do for you?", "build a website", "who is Prabowo?"):
            self.assertEqual(c._tools_for([{"role": "user", "content": msg}], True), "all", msg)
        # the payload actually carries the FULL schemas (write_file incl.)
        captured = {}
        def fs(url, data, headers, notify=None, mapper=None, ndjson=False):
            captured.update(data)
            yield {"choices": [{"delta": {"content": "ok"}}]}
        with um.patch.object(c, "_stream_req", side_effect=fs):
            list(c.chat_with_tools([{"role": "user", "content": "hi"}], confirm_batch_fn=lambda cc: True))
        names = {t["function"]["name"] for t in (captured.get("tools") or [])}
        self.assertIn("write_file", names)             # FULL set, not gated
        self.assertIn("run_command", names)
        self.assertNotIn("think", captured)             # no local-only fields

    def test_cloud_lock_temperature_clamp_only_with_tools(self):
        """CLOUD INVARIANT: build-mode temperature is clamped to <=0.4 exactly
        when tools are offered; the clamp may not appear in tool-less requests."""
        c = m.OpenAICompatible({"tools_enabled": True, "temperature": 0.7}, "openai", {"base_url": "https://api.openai.com/v1", "model": "gpt-4o", "api_key": "x"})
        captured = {}
        def fs(url, data, headers, notify=None, mapper=None, ndjson=False):
            captured.update(data)
            yield {"choices": [{"delta": {"content": "ok"}}]}
        with um.patch.object(c, "_stream_req", side_effect=fs):
            list(c.chat_with_tools([{"role": "user", "content": "build a website"}], confirm_batch_fn=lambda cc: True))
        self.assertLessEqual(captured["temperature"], 0.4)   # tools on -> clamp
        d = c._payload([{"role": "user", "content": "hi"}], True, temperature=c._eff("temperature"))
        self.assertEqual(d["temperature"], 0.7)              # explicit temp passes through

    def test_cloud_path_is_byte_identical_to_pre_change(self):
        """Regression guard: every local-Ollama optimization (native shim,
        think:false, keep_alive, compact schemas, ThinkFilter, NDJSON) must be
        a NO-OP for cloud backends. The remote OpenAI-compat path keeps the
        original URL, payload shape, full schemas, and plain-SSE streaming."""
        b = m.OpenAICompatible({"temperature": 0.7, "max_tokens": 4096}, "openai",
                              {"base_url": "https://api.openai.com/v1", "model": "gpt-4o-mini", "api_key": "sk-x"})
        self.assertFalse(b._native_ollama())
        self.assertEqual(b._url(), "https://api.openai.com/v1/chat/completions")
        d = b._payload([{"role": "user", "content": "hi"}], True, tools=[{"type": "function"}])
        self.assertNotIn("think", d)            # no native-only fields leak
        self.assertNotIn("options", d)
        self.assertNotIn("keep_alive", d)
        self.assertEqual(d["temperature"], 0.7)  # top-level, original position
        self.assertEqual(d["max_tokens"], 4096)
        # schemas stay full for cloud (compact is local-Ollama only)
        self.assertEqual(m.Tools.get_schemas(False, compact=b._native_ollama()),
                         m.Tools.get_schemas(False))
        # streamed content with no <think> passes through UNCHANGED, and the
        # stream uses plain SSE (mapper=None, ndjson=False), not the native shim
        seen = {}
        def fake_stream(url, data, headers, notify=None, mapper=None, ndjson=False):
            seen["mapper"] = mapper; seen["ndjson"] = ndjson
            for c in ["Hello ", "world", "! <not a think tag>"]:
                yield {"choices": [{"delta": {"content": c}}]}
        with um.patch.object(b, "_stream_req", side_effect=fake_stream):
            got = "".join(b.chat([{"role": "user", "content": "hi"}], stream=True))
        self.assertEqual(got, "Hello world! <not a think tag>")
        self.assertIsNone(seen["mapper"])
        self.assertFalse(seen["ndjson"])

    def test_compact_schemas_shrink_prompt_preserve_safety(self):
        """Local Ollama re-evaluates the tool schema every request (its prompt
        cache doesn't reliably hold the tools prefix), so compact=True trims
        verbose descriptions + per-param docs to cut ~250 tokens/call. The
        run_command Plan-mode allowlist must stay intact (security-relevant)."""
        full = m.Tools.get_schemas(False)
        comp = m.Tools.get_schemas(False, compact=True)
        self.assertLess(len(json.dumps(comp)), len(json.dumps(full)))
        # run_command keeps its full allowlist description in BOTH modes
        rc_f = next(t for t in full if t["function"]["name"] == "run_command")["function"]["description"]
        rc_c = next(t for t in comp if t["function"]["name"] == "run_command")["function"]["description"]
        self.assertGreater(len(rc_c), 100)            # still carries the allowlist
        self.assertIn("ALLOWED", rc_c)                # compact allowlist present
        # per-parameter descriptions stripped in compact mode
        rf = next(t for t in comp if t["function"]["name"] == "read_file")
        for p in rf["function"]["parameters"]["properties"].values():
            self.assertNotIn("description", p)
        # compact=False (cloud) is unchanged
        self.assertEqual(full, m.Tools.get_schemas(False))

    def test_chat_with_tools_routes_think_blocks_to_thinking_events(self):
        """A reasoning model's <think>...</think> in the streamed answer is split
        into dim 'thinking' events instead of mixing the chain-of-thought into
        the visible answer."""
        b = m.OpenAICompatible({}, "t", {"base_url": "http://localhost", "model": "x"})
        def fake_stream(url, data, headers, notify=None, mapper=None, ndjson=False):
            yield {"choices": [{"delta": {"content": "Let me think. <think>secret reasoning</think> Done."}}]}
        with um.patch.object(b, "_stream_req", side_effect=fake_stream):
            evts = list(b.chat_with_tools([{"role": "user", "content": "hi"}], confirm_batch_fn=lambda c: True))
        segs = [(e["type"], e["content"]) for e in evts if e["type"] in ("text", "thinking")]
        self.assertIn(("text", "Let me think. "), segs)
        self.assertIn(("thinking", "secret reasoning"), segs)
        self.assertIn(("text", " Done."), segs)

    def test_reasoning_content_passed_back_on_tool_turn(self):
        """Reasoning models (deepseek/o1-class via OpenAI-compat gateways) stream
        `reasoning_content` and the provider REQUIRES it on subsequent turns --
        omitting it -> HTTP 400 "The reasoning_content in the thinking mode must
        be passed back to the API." The assistant msg now carries it."""
        b = m.OpenAICompatible({}, "t", {"base_url": "https://x.test/v1", "model": "big-pickle", "api_key": "k"})
        captured = []
        def fake_stream(url, data, headers, notify=None, mapper=None, ndjson=False):
            captured.append(json.loads(json.dumps(data)))
            if len(captured) == 1:
                yield {"choices": [{"delta": {"reasoning_content": "planning..."}, "finish_reason": None}]}
                yield {"choices": [{"delta": {"tool_calls": [{"index": 0, "id": "c1", "type": "function",
                    "function": {"name": "list_files", "arguments": '{"path":"."}'}}]}, "finish_reason": "tool_calls"}]}
            else:
                yield {"choices": [{"delta": {"content": "done"}, "finish_reason": "stop"}]}
        with um.patch.object(b, "_stream_req", side_effect=fake_stream), \
             um.patch.object(m.Tools, "run_checked", side_effect=lambda n, a, bm, mr: (True, "f")):
            list(b.chat_with_tools([{"role": "user", "content": "go"}], confirm_batch_fn=lambda c: True))
        asst = [mm for mm in captured[1]["messages"] if mm.get("role") == "assistant"]
        self.assertTrue(any(mm.get("reasoning_content") == "planning..." for mm in asst))

    def test_non_reasoning_model_omits_reasoning_content(self):
        """A normal model sends no reasoning_content; the assistant message must
        NOT carry an empty reasoning_content field (keeps payloads clean)."""
        self.assertNotIn("reasoning_content", m.Backend._asst_msg("hi", [], ""))
        self.assertNotIn("reasoning_content", m.Backend._asst_msg("hi", [], None))
        self.assertEqual(m.Backend._asst_msg("hi", [], "think")["reasoning_content"], "think")

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
            run_count["n"] += 1; return (True, "ok")
        with um.patch.object(b, "_stream_req", side_effect=fake_stream), \
             um.patch.object(m.Tools, "run_checked", side_effect=fake_run):
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
             um.patch.object(m.Tools, "run_checked", side_effect=lambda name, args, bm, mr: (True, "ok")):
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
             um.patch.object(m.Tools, "run_checked", side_effect=lambda name, args, bm, mr: (True, "ok")):
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
        """A LOCAL Ollama model that reports a `thinking` capability routes
        through the native /api/chat shim with think:false (the /v1 compat
        endpoint ignores `think`, and reasoning models burn minutes of phone
        CPU). Detection is capability-based (model-agnostic), not name-based."""
        # thinking-capable local model -> native path (seed the caps cache to
        # avoid a live /api/show network call during the test)
        b = m.OpenAICompatible({"ollama_no_think": True}, "t", {"base_url": "http://localhost:11434/v1", "model": "qwen3:1.7b"})
        b._caps_cache["qwen3:1.7b"] = ["completion", "tools", "thinking"]
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
        # remote (even a thinking model) -> OpenAI path
        b2 = m.OpenAICompatible({"ollama_no_think": True}, "t", {"base_url": "https://api.openai.com/v1", "model": "qwen3:1.7b"})
        self.assertFalse(b2._native_ollama())
        self.assertEqual(b2._url(), "https://api.openai.com/v1/chat/completions")
        # local NON-thinking model -> OpenAI path (no native shim needed)
        b3 = m.OpenAICompatible({"ollama_no_think": True}, "t", {"base_url": "http://localhost:11434/v1", "model": "llama3.2"})
        b3._caps_cache["llama3.2"] = ["completion", "tools"]
        self.assertFalse(b3._native_ollama())
        # config disabled -> STILL the native path (the only way to control
        # thinking); ollama_no_think=false now means think:true, not /v1
        b4 = m.OpenAICompatible({"ollama_no_think": False}, "t", {"base_url": "http://localhost:11434/v1", "model": "qwen3:1.7b"})
        b4._caps_cache["qwen3:1.7b"] = ["thinking"]
        self.assertTrue(b4._native_ollama())
        self.assertIs(b4._payload([{"role": "user", "content": "hi"}], True, max_tokens=None)["think"], True)

    def test_ollama_caps_fallback_heuristic_and_cache(self):
        """When /api/show is unavailable (cold model / old Ollama), known
        reasoning-model families fall back to the thinking heuristic; the
        capability query is cached so it runs at most once per model."""
        b = m.OpenAICompatible({"ollama_no_think": True}, "t", {"base_url": "http://localhost:11434/v1", "model": "x"})
        with um.patch("urllib.request.urlopen", side_effect=Exception("no server")):
            # qwen3/qwq families are confirmed Ollama thinking-protocol models
            self.assertEqual(b._ollama_caps("qwen3:1.7b"), ["thinking"])
            self.assertEqual(b._ollama_caps("qwq:32b"), ["thinking"])
            # other models stay empty via the conservative heuristic (detected
            # authoritatively by /api/show when actually pulled instead)
            self.assertEqual(b._ollama_caps("deepseek-r1:1.5b"), [])
            self.assertEqual(b._ollama_caps("granite4.1:3b"), [])
            self.assertEqual(b._ollama_caps("llama3.2:3b"), [])
        # cached: a 2nd query for an already-seen model must NOT hit the network
        calls = {"n": 0}
        def boom(*a, **k):
            calls["n"] += 1; raise Exception("should not be called")
        with um.patch("urllib.request.urlopen", side_effect=boom):
            b._ollama_caps("qwen3:1.7b")   # already cached above
        self.assertEqual(calls["n"], 0)

    def test_tuning_registry_first_match_wins(self):
        """tuning_for() is first-match-wins on the lowercased model name: the
        registered reasoning/chat families get their profile, unknown models get
        an empty dict (safe no-op)."""
        self.assertTrue(m.tuning_for("qwen3:1.7b")["thinking"])
        self.assertTrue(m.tuning_for("qwen3:4b")["thinking"])
        self.assertTrue(m.tuning_for("qwen3:8b")["thinking"])
        self.assertTrue(m.tuning_for("qwen3-coder:14b")["thinking"])
        self.assertTrue(m.tuning_for("qwq:32b")["thinking"])
        self.assertTrue(m.tuning_for("deepseek-r1:1.5b")["thinking"])
        self.assertTrue(m.tuning_for("phi4-reasoning:3b")["thinking"])
        self.assertFalse(m.tuning_for("qwen2.5:3b")["thinking"])
        self.assertFalse(m.tuning_for("qwen2.5-coder:7b")["thinking"])
        self.assertFalse(m.tuning_for("llama3.2:3b")["thinking"])
        self.assertFalse(m.tuning_for("gemma3:4b")["thinking"])
        self.assertTrue(m.tuning_for("o1")["thinking"])
        self.assertTrue(m.tuning_for("o3-mini")["thinking"])
        # unknown model -> no profile, no behavior change
        self.assertEqual(m.tuning_for("gpt-4o"), {})
        self.assertEqual(m.tuning_for("granite4.1:3b"), {})
        # regexes are anchored to the start; suffixes after the family are fine
        self.assertEqual(m.tuning_for("qwen3:1.7b")["num_ctx"], 16384)

    def test_is_thinking_model_priority(self):
        """capabilities are authoritative when present; the registry decides for
        known families (even offline); everything else defaults to non-thinking."""
        # 1. /api/show caps win over the registry
        self.assertTrue(m.is_thinking_model("llama3.2", ["completion", "tools", "thinking"]))
        self.assertFalse(m.is_thinking_model("qwen3:1.7b", ["completion", "tools"]))
        # 2. registry decides when caps are absent/empty (offline Ollama)
        self.assertTrue(m.is_thinking_model("deepseek-r1:1.5b", []))
        self.assertTrue(m.is_thinking_model("phi4-reasoning:3b", []))
        self.assertTrue(m.is_thinking_model("qwen3:1.7b", None))
        self.assertFalse(m.is_thinking_model("llama3.2:3b", None))
        self.assertFalse(m.is_thinking_model("qwen2.5:3b", None))
        # 3. unknown -> not a reasoning model
        self.assertFalse(m.is_thinking_model("granite4.1:3b", None))
        self.assertFalse(m.is_thinking_model("gpt-4o", None))

    def test_registry_routes_local_reasoning_models_to_native(self):
        """deepseek-r1/phi4/qwen3 on a local Ollama route through the native
        /api/chat shim via the REGISTRY even when /api/show is unavailable;
        registry non-thinking families (llama3/gemma/qwen2.5) stay on /v1."""
        # offline server -> _ollama_caps falls back to the empty heuristic
        for model, expect_native in (("deepseek-r1:1.5b", True), ("phi4-reasoning:3b", True),
                                     ("qwen3:1.7b", True), ("llama3.2:3b", False),
                                     ("gemma3:4b", False), ("qwen2.5:3b", False)):
            b = m.OpenAICompatible({"ollama_no_think": True}, "ollama",
                                   {"base_url": "http://localhost:11434/v1", "model": model})
            with um.patch("urllib.request.urlopen", side_effect=Exception("offline")):
                b._ollama_caps(model)
            self.assertEqual(b._native_ollama(), expect_native, model)
            if expect_native:
                self.assertEqual(b._url(), "http://localhost:11434/api/chat")
            else:
                self.assertEqual(b._url(), "http://localhost:11434/v1/chat/completions")

    def test_eff_layering_and_auto_tune_both_local_and_cloud(self):
        """_eff resolves profile.settings -> model tuning -> local_defaults ->
        global, and the registry applies to CLOUD backends too (auto-tuning),
        while unknown cloud models are completely untouched."""
        # local qwen2.5: registry sets strategy_first False (fewer round-trips)
        loc = m.OpenAICompatible({"strategy_first": True}, "ollama",
                                 {"base_url": "http://localhost:11434/v1", "model": "qwen2.5:3b"})
        self.assertFalse(loc._eff("strategy_first", False))
        self.assertTrue(loc._is_compact_schemas())          # local -> compact
        # local llama3: registry temperature applies
        loc3 = m.OpenAICompatible({"temperature": 0.7}, "ollama",
                                  {"base_url": "http://localhost:11434/v1", "model": "llama3.2"})
        self.assertEqual(loc3._eff("temperature", 0.7), 0.6)
        # cloud qwen3: SAME registry applies (auto-tune both sides)
        cloud = m.OpenAICompatible({}, "openrouter",
                                   {"base_url": "https://openrouter.ai/api/v1", "model": "qwen/qwen3", "api_key": "x"})
        self.assertFalse(cloud.is_local)
        self.assertFalse(cloud.is_ollama)
        self.assertFalse(cloud._eff("strategy_first", False))
        self.assertTrue(cloud._is_compact_schemas())
        self.assertEqual(cloud._eff("temperature", 0.7), 0.6)
        # profile.settings override the registry
        pr = m.OpenAICompatible({}, "openrouter",
                                {"base_url": "https://openrouter.ai/api/v1", "model": "qwen/qwen3",
                                 "api_key": "x", "settings": {"strategy_first": True}})
        self.assertTrue(pr._eff("strategy_first", False))
        # unknown cloud model: no tuning, no compact schemas, no behavior change
        gpt = m.OpenAICompatible({"temperature": 0.7, "strategy_first": False}, "openai",
                                 {"base_url": "https://api.openai.com/v1", "model": "gpt-4o", "api_key": "x"})
        self.assertFalse(gpt._is_compact_schemas())
        self.assertEqual(gpt._eff("temperature", 0.7), 0.7)
        self.assertEqual(gpt._eff("strategy_first", False), False)
        # local_defaults safety net applies only to local backends
        net = m.OpenAICompatible({"max_tool_result": 30000, "local_defaults": {"max_tool_result": 8000}}, "ollama",
                                 {"base_url": "http://localhost:11434/v1", "model": "llama3.2"})
        self.assertEqual(net._eff("max_tool_result", 10000), 8000)
        cloud_net = m.OpenAICompatible({"max_tool_result": 30000, "local_defaults": {"max_tool_result": 8000}}, "openai",
                                       {"base_url": "https://api.openai.com/v1", "model": "gpt-4o", "api_key": "x"})
        self.assertEqual(cloud_net._eff("max_tool_result", 10000), 30000)

    def test_model_tuning_user_override_beats_registry(self):
        """config `model_tuning.<model>.<key>` is merged over the registry for
        that model only (the rare manual escape hatch)."""
        b = m.OpenAICompatible({"model_tuning": {"qwen2.5:3b": {"strategy_first": True, "temperature": 0.9}},
                                "temperature": 0.7}, "ollama",
                               {"base_url": "http://localhost:11434/v1", "model": "qwen2.5:3b"})
        self.assertTrue(b._eff("strategy_first", False))
        self.assertEqual(b._eff("temperature", 0.7), 0.9)
        # other models are unaffected
        b2 = m.OpenAICompatible({"model_tuning": {"qwen2.5:3b": {"strategy_first": True}}}, "ollama",
                                {"base_url": "http://localhost:11434/v1", "model": "llama3.2"})
        self.assertFalse(b2._eff("strategy_first", False))

    def test_micro_schemas_are_smallest_and_still_valid(self):
        """micro mode (local non-thinking models) is strictly smaller than
        compact, drops per-tool descriptions, and keeps the run_command
        security allowlist so Plan-mode rules still reach the model."""
        full = json.dumps(m.Tools.get_schemas(True, compact=False), separators=(",", ":"))
        comp = json.dumps(m.Tools.get_schemas(True, compact=True), separators=(",", ":"))
        mic = json.dumps(m.Tools.get_schemas(True, micro=True), separators=(",", ":"))
        self.assertLess(len(mic), len(comp))
        self.assertLess(len(comp), len(full))
        # description dropped on normal tools, kept on run_command (security)
        for t in m.Tools.get_schemas(True, micro=True):
            fn = t["function"]
            if fn["name"] == "run_command":
                self.assertTrue(fn.get("description"))
            else:
                self.assertNotIn("description", fn)
        # parameters still carry name+type for the model to fill correctly
        read = next(t["function"] for t in m.Tools.get_schemas(True, micro=True) if t["function"]["name"] == "read_file")
        self.assertIn("path", read["parameters"]["properties"])

    def test_schema_mode_and_local_chat_tuning(self):
        """local NON-thinking models get micro schemas + tuned num_ctx/
        ollama_max_tokens/keep_alive; local thinking models compact+native;
        unknown cloud stays full with no tuning."""
        b = m.OpenAICompatible({"ollama_no_think": True}, "ollama",
                               {"base_url": "http://localhost:11434/v1", "model": "qwen2.5:3b"})
        with um.patch("urllib.request.urlopen", side_effect=Exception("offline")):
            b._ollama_caps("qwen2.5:3b")
        self.assertEqual(b._schema_mode(), "micro")
        self.assertTrue(b._local_chat_model())
        self.assertEqual(b._eff("temperature", 0.7), 0.6)
        self.assertEqual(b._eff("num_ctx", 0), 8192)
        self.assertEqual(b._eff("ollama_max_tokens", 0), 2048)
        self.assertEqual(b._eff("ollama_keep_alive", "2h"), "2h")
        # the tuning applies into the request payload on the native path
        b._caps_cache["qwen2.5:3b"] = ["thinking"]
        d = b._payload([{"role": "user", "content": "hi"}], True, max_tokens=None)
        self.assertEqual(d["options"]["num_ctx"], 8192)
        self.assertEqual(d["options"]["num_predict"], 2048)
        # local thinking model -> compact schemas (native has num_ctx room)
        b2 = m.OpenAICompatible({}, "ollama", {"base_url": "http://localhost:11434/v1", "model": "qwen3:1.7b"})
        with um.patch("urllib.request.urlopen", side_effect=Exception("offline")):
            b2._ollama_caps("qwen3:1.7b")
        self.assertEqual(b2._schema_mode(), "compact")
        self.assertTrue(b2._native_ollama())
        self.assertFalse(b2._local_chat_model())
        # unknown cloud -> full schemas, no tuning leakage
        c = m.OpenAICompatible({}, "openai", {"base_url": "https://api.openai.com/v1", "model": "gpt-4o", "api_key": "x"})
        self.assertEqual(c._schema_mode(), "full")
        self.assertEqual(c._eff("ollama_max_tokens", 0), 0)
        self.assertFalse(c._local_chat_model())

    def test_chat_kind_heuristic(self):
        """_chat_kind() splits messages into chat (no tools) / knowledge (web
        tools) / task (full tools) so a small local model stops looping file
        tools on trivial chat but can still look up facts on the web."""
        for chat in ("what can I do for you?", "hi", "how are you?", "",
                     "thanks!", "what should I call you?", "can I call you donAI?"):
            self.assertEqual(m._chat_kind(chat), "chat", chat)
        for know in ("who is Prabowo Subianto?",
                     "tell me the weather today",
                     "tell me the weather today, I'm in yogyakarta",
                     "what is the capital of France?",
                     "explain photosynthesis",
                     "latest news about AI chips"):
            self.assertEqual(m._chat_kind(know), "knowledge", know)
        for task in ("create app/main.py that prints hello",
                     "install the deps and run the tests",
                     "fix the bug in the server",
                     "read src/deep/file.py",
                     "list files in ./project",
                     "run pytest",
                     "can you help me create a website",
                     "show me the config in app/settings.py"):
            self.assertEqual(m._chat_kind(task), "task", task)
        # long ambiguous messages keep tools (safe default)
        self.assertEqual(m._chat_kind("hey I was wondering if you could help me with a "
                                      "small thing I've been thinking about for a while "
                                      "and I'd really appreciate some guidance on it today"), "task")

    def test_tools_for_gate(self):
        """Local non-thinking chat models get NO tools for casual chat (kills
        the ~200s tool loop), web-only tools for knowledge questions, and the
        full/read-only toolset for tasks (per build mode). CLOUD is never gated:
        full in Build, read-only in Plan, every turn. Plan mode is restored
        (read-only tools offered, not zero tools)."""
        b = m.OpenAICompatible({}, "ollama", {"base_url": "http://localhost:11434/v1", "model": "qwen2.5:3b"})
        self.assertTrue(b._local_chat_model())
        self.assertIsNone(b._tools_for(
            [{"role": "system", "content": "s"}, {"role": "user", "content": "what can I do for you?"}], True))
        self.assertIsNone(b._tools_for([{"role": "user", "content": "hi"}], True))
        self.assertEqual(b._tools_for(
            [{"role": "user", "content": "who is Prabowo Subianto?"}], True), "web")
        self.assertEqual(b._tools_for(
            [{"role": "user", "content": "tell me the weather today"}], True), "web")
        self.assertEqual(b._tools_for(
            [{"role": "user", "content": "create app/main.py that prints hello"}], True), "all")
        # PLAN MODE restored: task message -> read-only toolset, not None
        self.assertEqual(b._tools_for(
            [{"role": "user", "content": "create app/main.py"}], False), "plan")
        self.assertEqual(b._tools_for(
            [{"role": "user", "content": "who is Prabowo?"}], False), "web")   # web tools are read-only anyway
        self.assertIsNone(b._tools_for(
            [{"role": "user", "content": "hi"}], False))                        # casual chat stays tool-less
        # cloud backend: NEVER gated, every turn, either mode
        c = m.OpenAICompatible({}, "openai", {"base_url": "https://api.openai.com/v1", "model": "gpt-4o", "api_key": "x"})
        self.assertFalse(c._local_chat_model())
        self.assertEqual(c._tools_for([{"role": "user", "content": "what can I do for you?"}], True), "all")
        self.assertEqual(c._tools_for([{"role": "user", "content": "hi"}], False), "plan")

    def test_process_default_migration_auto_to_on(self):
        """One-time _process_v1 migration: installs that still carry the OLD
        default ("auto") are moved to compact "on"; an explicit "off" or "on"
        choice is never touched; the flag prevents re-migration."""
        import json as _j
        # old install with "auto" saved -> migrated to "on", flag set, persisted
        m.CONFIG_FILE.write_text(_j.dumps({"compact_process": "auto"}))
        cfg = m.Config()
        self.assertEqual(cfg.get("compact_process"), "on")
        self.assertTrue(cfg.get("_process_v1"))
        # explicit "off" survives untouched
        m.CONFIG_FILE.write_text(_j.dumps({"compact_process": "off", "_process_v1": False}))
        cfg2 = m.Config()
        self.assertEqual(cfg2.get("compact_process"), "off")
        self.assertTrue(cfg2.get("_process_v1"))
        # explicit "on" unchanged; second boot no-op
        m.CONFIG_FILE.write_text(_j.dumps({"compact_process": "on"}))
        cfg3 = m.Config()
        self.assertEqual(cfg3.get("compact_process"), "on")

    def test_ollama_no_think_false_enables_real_thinking(self):
        """ollama_no_think=false must actually THINK: previously it fell back to
        /v1 where thinking is uncontrolled (the flag promised something the code
        never delivered). Now the native path is used either way and the flag
        only flips think true/false."""
        b = m.OpenAICompatible({"ollama_no_think": False}, "ollama",
                               {"base_url": "http://localhost:11434/v1", "model": "qwen3:1.7b"})
        b._caps_cache["qwen3:1.7b"] = ["thinking"]
        self.assertTrue(b._native_ollama())              # still native (control!)
        d = b._payload([{"role": "user", "content": "hi"}], True, max_tokens=None)
        self.assertIs(d["think"], True)                  # ...but thinking ON
        # default: native + think False (the responsive fast path)
        b2 = m.OpenAICompatible({}, "ollama", {"base_url": "http://localhost:11434/v1", "model": "qwen3:1.7b"})
        b2._caps_cache["qwen3:1.7b"] = ["thinking"]
        self.assertTrue(b2._native_ollama())
        self.assertIs(b2._payload([{"role": "user", "content": "hi"}], True, max_tokens=None)["think"], False)
        # cloud is never native regardless
        c = m.OpenAICompatible({"ollama_no_think": False}, "openai",
                               {"base_url": "https://api.openai.com/v1", "model": "gpt-4o", "api_key": "x"})
        self.assertFalse(c._native_ollama())

    def test_native_thinking_maps_to_reasoning_and_displays(self):
        """Native Ollama think:true streams message.thinking; the mapper converts
        it to reasoning_content (passback convention) and chat_with_tools shows
        it live as dim 'thinking' events on the LOCAL path only."""
        evt = m.OpenAICompatible._native_to_openai(
            {"message": {"role": "assistant", "thinking": "planning the build...", "content": "done"}})
        delta = evt["choices"][0]["delta"]
        self.assertEqual(delta["reasoning_content"], "planning the build...")
        self.assertEqual(delta["content"], "done")
        # live display on the native path only (cloud reasoning stays buffered)
        b = m.OpenAICompatible({"tools_enabled": True}, "ollama",
                               {"base_url": "http://localhost:11434/v1", "model": "qwen3:1.7b"})
        b._caps_cache["qwen3:1.7b"] = ["thinking"]
        seen = []
        def fs(url, data, headers, notify=None, mapper=None, ndjson=False):
            assert mapper is not None and ndjson, "native path must be used"
            yield mapper({"message": {"thinking": "let me plan"}, "done": False})
            yield mapper({"message": {"content": "answer"}, "done": True, "done_reason": "stop"})
        with um.patch.object(b, "_stream_req", side_effect=fs):
            for e in b.chat_with_tools([{"role": "user", "content": "buat rencana"}], confirm_batch_fn=lambda cc: True):
                if e["type"] in ("thinking", "text"):
                    seen.append((e["type"], e["content"]))
        self.assertIn(("thinking", "let me plan"), seen)
        self.assertIn(("text", "answer"), seen)

    def test_o_series_official_api_uses_max_completion_tokens(self):
        """o1/o3 on api.openai.com require max_completion_tokens (max_tokens 400s)
        and only accept temperature=1. Via OTHER gateways (opencode/OpenRouter)
        max_tokens still applies -- cloud behavior stays untouched there."""
        o = m.OpenAICompatible({"temperature": 0.7, "max_tokens": 4096}, "openai",
                               {"base_url": "https://api.openai.com/v1", "model": "o3-mini", "api_key": "x"})
        d = o._payload([{"role": "user", "content": "hi"}], True, max_tokens=None)
        self.assertEqual(d["max_completion_tokens"], 4096)
        self.assertNotIn("max_tokens", d)
        self.assertNotIn("temperature", d)
        og = m.OpenAICompatible({"temperature": 0.7, "max_tokens": 8192}, "opencode",
                                {"base_url": "https://opencode.ai/zen/v1", "model": "o3-mini", "api_key": "x"})
        d2 = og._payload([{"role": "user", "content": "hi"}], True, max_tokens=None)
        self.assertEqual(d2["max_tokens"], 8192)
        self.assertNotIn("max_completion_tokens", d2)
        self.assertEqual(d2["temperature"], 0.7)

    def test_openai_delta_accumulator_merge_rules(self):
        """One place owns the streamed-delta merge rules: fragment concatenation
        for name/arguments, overwrite for id/type, reasoning fallback field,
        index-ordered calls, finish_reason retention, live-thinking callback."""
        a = m.OpenAIDeltaAccumulator()
        seen_thinking = []
        a.feed({"choices": [{"delta": {"content": "he"}, "finish_reason": None}]}, live_thinking=seen_thinking.append)
        a.feed({"choices": [{"delta": {"content": "llo"}, "finish_reason": None}]})
        a.feed({"choices": [{"delta": {"reasoning": "think1"}, "finish_reason": None}]}, live_thinking=seen_thinking.append)
        a.feed({"choices": [{"delta": {"tool_calls": [
            {"index": 0, "id": "c1", "type": "function", "function": {"name": "read_", "arguments": '{"pa'}}]}}]})
        a.feed({"choices": [{"delta": {"tool_calls": [
            {"index": 0, "function": {"name": "file", "arguments": 'th":"a"}'}}]}}]})
        a.feed({"choices": [{"delta": {"tool_calls": [
            {"index": 1, "id": "c2", "type": "function", "function": {"name": "list_files", "arguments": '{}'}}]}}]})
        a.feed({"choices": [{"delta": {}, "finish_reason": "tool_calls"}]})
        self.assertEqual(a.content, "hello")
        self.assertEqual(a.reasoning, "think1")
        self.assertEqual(seen_thinking, ["think1"])          # live callback fired
        self.assertEqual(a.finish_reason, "tool_calls")
        cs = a.calls
        self.assertEqual([c["id"] for c in cs], ["c1", "c2"])  # index order
        self.assertEqual(cs[0]["function"]["name"], "read_file")  # fragments joined
        self.assertEqual(json.loads(cs[0]["function"]["arguments"]), {"path": "a"})

    def test_gate_self_heal_reoffers_tools_once(self):
        """A mis-gated turn (gate read the message as chat -> no tools) whose
        answer says it WANTED tools ("maaf, saya tidak bisa mengakses file") is
        retried ONCE with the toolset forced on; a second tool-less answer
        stands (never loops). Cloud is unaffected (never gated)."""
        b = m.OpenAICompatible({"tools_enabled": True}, "ollama",
                               {"base_url": "http://localhost:11434/v1", "model": "qwen2.5:3b"})
        self.assertIsNone(b._tools_for([{"role": "user", "content": "coba cek file saya dong"}], True))
        n, healed_payloads = [], []
        def fs(url, data, headers, notify=None, mapper=None, ndjson=False):
            n.append(1)
            if len(n) == 1:
                yield {"choices": [{"delta": {"content": "Maaf, saya tidak bisa mengakses file di perangkat Anda."}}]}
            elif len(n) == 2:
                healed_payloads.append(data)
                yield {"choices": [{"delta": {"tool_calls": [{"index": 0, "id": "c1", "type": "function",
                    "function": {"name": "list_files", "arguments": '{"path":"."}'}}]}, "finish_reason": "tool_calls"}]}
            else:
                yield {"choices": [{"delta": {"content": "ini isinya"}, "finish_reason": "stop"}]}
        with um.patch.object(b, "_stream_req", side_effect=fs), \
             um.patch.object(m.Tools, "run_checked", side_effect=lambda n_, a, bm, mr: (True, "f1\nf2")):
            evts = list(b.chat_with_tools([{"role": "user", "content": "coba cek file saya dong"}],
                                          confirm_batch_fn=lambda c: True))
        self.assertEqual(len(n), 3)                       # heal retry + tool round + final
        self.assertTrue(healed_payloads[0].get("tools")) # tools re-offered
        self.assertTrue(any(e["type"] == "tool_progress" for e in evts))
        # one-shot: an always-refusing model heals exactly once then stands
        n2 = []
        def fs2(url, data, headers, notify=None, mapper=None, ndjson=False):
            n2.append(1)
            yield {"choices": [{"delta": {"content": "Maaf, saya tidak bisa mengakses file."}}]}
        with um.patch.object(b, "_stream_req", side_effect=fs2):
            list(b.chat_with_tools([{"role": "user", "content": "coba cek file saya dong"}],
                                   confirm_batch_fn=lambda c: True))
        self.assertEqual(len(n2), 2)

    def test_web_cache_ttl_dedupes_and_bypassable(self):
        """Web tools (fetch/search/weather) share a short-TTL cache keyed on the
        lowercased arg -- repeated lookups in a turn don't re-fetch; TTL 0 via
        AI_WEB_CACHE_TTL disables; errors are never cached."""
        m.Tools._web_cache.clear()
        calls = []
        def fake(url, timeout=10, max_bytes=500000):
            calls.append(url); return "content " + url
        with um.patch.object(m.Tools, "_fetch_url", side_effect=fake):
            a = m.Tools.run("fetch_url", {"url": "https://x.test/a"})
            b = m.Tools.run("fetch_url", {"url": "https://X.test/A"})   # same key case-insensitively
            self.assertEqual(len(calls), 1)
            self.assertEqual(a, b)
        # TTL 0 disables (always fresh)
        os.environ["AI_WEB_CACHE_TTL"] = "0"
        try:
            m.Tools._web_cache.clear()
            with um.patch.object(m.Tools, "_fetch_url", side_effect=fake):
                m.Tools.run("fetch_url", {"url": "https://x.test/a"})
                m.Tools.run("fetch_url", {"url": "https://x.test/a"})
            self.assertEqual(len(calls), 3)   # 1 + 2 fresh
        finally:
            os.environ.pop("AI_WEB_CACHE_TTL", None)
        # errors are not cached
        m.Tools._web_cache.clear()
        n = []
        def err_fetch(url, timeout=10, max_bytes=500000):
            n.append(url); raise m.urllib.error.URLError("down")
        with um.patch.object(m.Tools, "_fetch_url", side_effect=err_fetch):
            r1 = m.Tools.run("fetch_url", {"url": "https://x.test/e"})
            r2 = m.Tools.run("fetch_url", {"url": "https://x.test/e"})
        self.assertEqual(len(n), 2)           # both attempted (nothing cached)
        self.assertIn("Error", r1)

    def test_run_checked_structured_flags(self):
        """Tools.run_checked is the structured boundary: genuine failures raise
        ToolError inside _run_impl and come back as (False, 'Error: ...') with
        the SAME message text the string API always produced; successes are
        (True, out). Loop guards key off the flag -- no string sniffing."""
        ok, out = m.Tools.run_checked("read_file", {"path": "/definitely/not/here"})
        self.assertFalse(ok)
        self.assertTrue(out.startswith("Error:"))
        # string API renders the identical text (model-facing, unchanged)
        self.assertEqual(m.Tools.run("read_file", {"path": "/definitely/not/here"}), out)
        # plan-mode block is a failure too
        ok2, out2 = m.Tools.run_checked("write_file", {"path": "x", "content": "y"}, build_mode=False)
        self.assertFalse(ok2); self.assertIn("Plan mode", out2)
        # success path
        ok3, out3 = m.Tools.run_checked("web_search", {"query": "  "})
        self.assertFalse(ok3)                     # empty query is a tool error
        ok4, out4 = m.Tools.run_checked("run_command", {"command": "echo hi"}, build_mode=True)
        self.assertTrue(ok4); self.assertIn("hi", out4)
        # guards consume the structured flag via _run_batch outcomes
        b = m.Backend({})
        with um.patch.object(m.Tools, "run_checked", side_effect=lambda n, a, bm, mr: (False, "Error: boom")):
            outcomes = b._run_batch([("write_file", {"path": "w", "content": ""})], True, 10000, set(), {})
        self.assertEqual(outcomes[0][3], False)   # ok flag rides the tuple

    def test_run_batch_parallel_reads_order_preserved(self):
        """Read-only batched calls run CONCURRENTLY (wall-clock ~= the slowest
        call, not the sum) while results stay in the original order for the API
        contract; mutating calls run sequentially AFTER the reads (a batch's
        reads must see pre-write state, like the old sequential loop)."""
        import threading, time as _t
        b = m.Backend({})
        threads = set()
        events = []
        def fake_run(name, args, bm, mr):
            threads.add(threading.current_thread().name)
            _t.sleep(0.3 if name != "write_file" else 0.05)
            events.append(name)
            return True, f"r:{name}"
        with um.patch.object(m.Tools, "run_checked", side_effect=fake_run):
            t0 = _t.time()
            out = b._run_batch([("read_file", {"path": "a"}), ("search_files", {"query": "x"}),
                                ("list_files", {"path": "."}), ("write_file", {"path": "w", "content": ""})],
                               True, 10000, set(), {})
            dt = _t.time() - t0
        self.assertEqual([o[0] for o in out], ["read_file", "search_files", "list_files", "write_file"])  # order
        self.assertEqual([o[1] for o in out], ["r:read_file", "r:search_files", "r:list_files", "r:write_file"])
        self.assertTrue(all(o[2] for o in out))
        self.assertGreaterEqual(len(threads), 2)          # actually ran on multiple threads
        self.assertLess(dt, 0.3 + 0.3 + 0.3)              # NOT the serial sum (~0.95s)

    def test_run_batch_mutators_after_reads_and_config_off(self):
        import time as _t
        order = []
        def fake_run(name, args, bm, mr):
            order.append((name, _t.perf_counter()))
            _t.sleep(0.15)
            return True, "ok"
        # reads-before-writes within one batch
        b = m.Backend({})
        with um.patch.object(m.Tools, "run_checked", side_effect=fake_run):
            b._run_batch([("write_file", {"path": "w", "content": ""}), ("read_file", {"path": "a"})], True, 10000, set(), {})
        w = next(t for n, t in order if n == "write_file")
        r = next(t for n, t in order if n == "read_file")
        # read (parallel pool) finishes before the mutator starts
        self.assertLessEqual(r, w)
        # parallel_tools off -> everything sequential (single thread is fine;
        # behavior identical, just not concurrent)
        b2 = m.Backend({"parallel_tools": False})
        with um.patch.object(m.Tools, "run_checked", side_effect=lambda n, a, bm, mr: (True, f"r:{n}")):
            out = b2._run_batch([("read_file", {"path": "a"}), ("list_files", {"path": "."})], True, 10000, set(), {})
        self.assertEqual([o[1] for o in out], ["r:read_file", "r:list_files"])

    def test_run_batch_shortcircuits_preserved(self):
        """Already-done and redundant-read short-circuits keep working through
        the batch executor (claimed sequentially, no re-execution)."""
        b = m.Backend({})
        done = {("read_file", json.dumps({"path": "a"}, sort_keys=True))}
        calls = []
        def fake_run(name, args, bm, mr):
            calls.append(name); return (True, "executed")
        with um.patch.object(m.Tools, "run_checked", side_effect=fake_run):
            out = b._run_batch([("read_file", {"path": "a"}), ("list_files", {"path": "."})], True, 10000, done, {})
        self.assertIn("ALREADY DONE", out[0][1])
        self.assertFalse(out[0][2])
        self.assertEqual(calls, ["list_files"])          # read short-circuited

    def test_loop_guard_stuck_and_failure_backstops(self):
        """LoopGuard is the single implementation of the loop backstops shared by
        both backends: stuck repeats (zero new work x5) and 3 consecutive failed
        rounds stop fatally; a successful round resets both streaks."""
        g = m.LoopGuard({}, None)
        # ceiling: begin_iteration passes up to max_iterations (default 50)
        for _ in range(50):
            self.assertIsNone(g.begin_iteration())
        self.assertIn("iteration limit", g.begin_iteration() or "")
        # stuck: 4 repeats tolerate, the 5th stops
        g2 = m.LoopGuard({}, None)
        for i in range(4):
            stop, reflect = g2.note_results(any_productive=False, failed_names=[])
            self.assertIsNone(stop)
        stop, reflect = g2.note_results(any_productive=False, failed_names=[])
        self.assertIn("no new progress", stop)
        # failure streak: 2 reflects, the 3rd stops; success resets
        g3 = m.LoopGuard({}, None)
        stop, reflect = g3.note_results(True, ["write_file"])
        self.assertIsNone(stop); self.assertIn("REFLECT", reflect)
        stop, reflect = g3.note_results(True, ["write_file"])
        self.assertIsNone(stop)
        stop, reflect = g3.note_results(True, ["write_file"])
        self.assertIn("consecutive failed", stop)
        g4 = m.LoopGuard({}, None)
        g4.note_results(True, ["run_command"])      # one failure...
        g4.note_results(True, [])                    # ...then success resets
        stop, reflect = g4.note_results(True, ["run_command"])
        self.assertIsNone(stop)                      # so this is failure #1, not #3
        # checkpoint: approved extends the ceiling, declined stops, None skips
        g5 = m.LoopGuard({"max_iterations": 6, "continue_every": 2}, lambda i, t: True)
        g5.note_calls(2)
        self.assertIsNone(g5.checkpoint())
        self.assertEqual(g5.iteration_cap, 8)
        g6 = m.LoopGuard({"max_iterations": 6, "continue_every": 2}, lambda i, t: False)
        g6.note_calls(2)
        self.assertEqual(g6.checkpoint(), "stop")
        g7 = m.LoopGuard({"max_iterations": 6, "continue_every": 2}, None)
        g7.note_calls(2)
        self.assertIsNone(g7.checkpoint())           # unattended: no prompt, no extension
        self.assertEqual(g7.iteration_cap, 6)

    def test_gate_task_stickiness_mid_task_and_continuation(self):
        """A chat-like "ok"/"lanjutkan" must NOT drop the toolset when a task is
        in flight (tool rounds after the last user msg) or was just requested
        (continuation turn right after a task turn). A fresh casual "hi" with no
        task context still gets no tools."""
        b = m.OpenAICompatible({}, "ollama", {"base_url": "http://localhost:11434/v1", "model": "qwen2.5:3b"})
        # mid-loop: tool rounds accumulated after the last user message
        msgs = [{"role": "user", "content": "buat file app.py"},
                {"role": "assistant", "content": "", "tool_calls": [{"id": "c1", "type": "function",
                    "function": {"name": "write_file", "arguments": "{}"}}]},
                {"role": "tool", "tool_call_id": "c1", "content": "ok"}]
        self.assertEqual(b._tools_for(msgs, True), "all")
        # continuation turn: previous user msg was a task, current is "ok lanjutkan"
        msgs2 = [{"role": "user", "content": "tolong buatkan simple website"},
                 {"role": "assistant", "content": "selesai"},
                 {"role": "user", "content": "ok lanjutkan bagian kedua"}]
        self.assertEqual(b._tools_for(msgs2, True), "all")
        # plain "ya" with no task history -> chat (no tools)
        self.assertIsNone(b._tools_for(
            [{"role": "user", "content": "halo"}, {"role": "assistant", "content": "hai"},
             {"role": "user", "content": "ya"}], True))
        # long non-continuation chat stays chat
        self.assertIsNone(b._tools_for(
            [{"role": "user", "content": "ceritakan pendapatmu tentang kopi hari ini saja singkat"}], True))

    def test_chat_kind_indonesian(self):
        """The gate's task/knowledge/chat split understands Indonesian phrasing
        so local models don't lose tools ("tolong buatkan website" was chat!)."""
        for task in ("tolong buatkan simple website",
                     "bikin file test.py",
                     "perbaiki bug di server",
                     "hapus file lama",
                     "jalankan tesnya",
                     "cari file config",
                     "bisakah kamu buatkan laporan"):
            self.assertEqual(m._chat_kind(task), "task", task)
        for know in ("apa itu fotosintesis",
                     "siapa presiden amerika",
                     "cuaca hari ini di yogyakarta",
                     "bagaimana cara kerja mesin diesel",
                     "kenapa langit biru"):
            self.assertEqual(m._chat_kind(know), "knowledge", know)
        for chat in ("siapa kamu",
                     "apa yang bisa kamu bantu",
                     "halo apa kabar",
                     "terima kasih banyak"):
            self.assertEqual(m._chat_kind(chat), "chat", chat)

    def test_plan_mode_offers_readonly_schemas_not_write(self):
        """End-to-end: in Plan mode the request carries read_file but NOT
        write_file/clone_repo; in Build mode write_file returns. (H1 fix.)"""
        c = m.OpenAICompatible({"tools_enabled": False}, "openai",
                               {"base_url": "https://api.openai.com/v1", "model": "gpt-4o", "api_key": "x"})
        captured = {}
        def fs(url, data, headers, notify=None, mapper=None, ndjson=False):
            captured.update(data)
            yield {"choices": [{"delta": {"content": "ok"}}]}
        with um.patch.object(c, "_stream_req", side_effect=fs):
            list(c.chat_with_tools([{"role": "user", "content": "analyze the files"}], confirm_batch_fn=lambda cc: True))
        names = {t["function"]["name"] for t in (captured.get("tools") or [])}
        self.assertIn("read_file", names)
        self.assertIn("run_command", names)          # plan-mode allowlisted executor
        self.assertNotIn("write_file", names)
        self.assertNotIn("clone_repo", names)
        # Build mode restores the full set
        c2 = m.OpenAICompatible({"tools_enabled": True}, "openai",
                                {"base_url": "https://api.openai.com/v1", "model": "gpt-4o", "api_key": "x"})
        captured2 = {}
        def fs2(url, data, headers, notify=None, mapper=None, ndjson=False):
            captured2.update(data)
            yield {"choices": [{"delta": {"content": "ok"}}]}
        with um.patch.object(c2, "_stream_req", side_effect=fs2):
            list(c2.chat_with_tools([{"role": "user", "content": "analyze"}], confirm_batch_fn=lambda cc: True))
        names2 = {t["function"]["name"] for t in (captured2.get("tools") or [])}
        self.assertIn("write_file", names2)

    def test_phase_nudge_web_vs_file(self):
        """The gather nudge stays file-focused for file-read loops but tells a
        web-only research loop (fetch/search/weather) to stop probing and answer."""
        b = m.OpenAICompatible({}, "ollama", {"base_url": "http://localhost:11434/v1", "model": "qwen2.5:3b"})
        # file-only loop -> file-oriented "Context phase" message
        streak, nudged, msg = b._phase_nudge(["read_file"], 4, False, 5)
        self.assertEqual((streak, nudged), (5, True))
        self.assertIn("Context phase", msg)
        self.assertIn("read_file", msg)
        # web-only loop -> web-oriented "Research phase" message
        streak, nudged, msg = b._phase_nudge(["fetch_url"], 4, False, 5)
        self.assertEqual((streak, nudged), (5, True))
        self.assertIn("Research phase", msg)
        self.assertNotIn("read_file", msg)
        # mixed web+file -> file message wins (still a context loop)
        streak, nudged, msg = b._phase_nudge(["read_file", "web_search"], 4, False, 5)
        self.assertIn("Context phase", msg)
        # an execution call resets the streak and clears the nudge latch
        streak, nudged, msg = b._phase_nudge(["write_file"], 5, True, 5)
        self.assertEqual(streak, 0)

    def test_warm_is_ollama_only_and_never_raises(self):
        """_warm() pre-loads the local model; remote backends are a no-op and
        failures are swallowed (startup must never block or crash)."""
        b = m.OpenAICompatible({}, "ollama", {"base_url": "http://localhost:11434/v1", "model": "qwen2.5:3b"})
        calls = {"n": 0}
        def fake_open(req, timeout):
            calls["n"] += 1
            raise Exception("boom")   # swallowed
        with um.patch("urllib.request.urlopen", side_effect=fake_open):
            b._warm()                 # must not raise
        self.assertEqual(calls["n"], 1)
        c = m.OpenAICompatible({}, "openai", {"base_url": "https://api.openai.com/v1", "model": "gpt-4o", "api_key": "x"})
        c._warm()                     # no-op for remote
        self.assertEqual(calls["n"], 1)

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
            run_count["n"] += 1; return (True, "line content here\n" * 10)
        with um.patch.object(b, "_stream_req", side_effect=fake_stream), \
             um.patch.object(m.Tools, "run_checked", side_effect=fake_run):
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
            return True, "ok"
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
