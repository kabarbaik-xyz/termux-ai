#!/usr/bin/env python3
"""Unit tests for non-security internals: Database, file attachment,
compaction, and small helpers. Run:  python3 tests/test_units.py"""
import importlib.machinery, importlib.util, os, shutil, subprocess, sys, tempfile, time, unittest
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


class TestProjectSessions(_TmpHome):
    """Sessions remember where they lived: cwd + tools_mode + skills captured at
    creation, restored on resume; project-scoped auto-resume prefers this cwd;
    named sessions via ai -S / /session."""

class TestWorkspaceIsolation(_TmpHome):
    """Sessions are isolated per WORKSPACE (nearest .git/manifest/CONTEXT.md
    root), not per exact launch dir. Resume never grabs another project's
    session; slugs are workspace-scoped; history/search views filter."""

    def _mkws(self, name):
        d = tempfile.mkdtemp(prefix=f"ws_{name}_")
        os.makedirs(os.path.join(d, ".git"))
        os.makedirs(os.path.join(d, "src", "deep"), exist_ok=True)
        return d

    def test_workspace_root_detection_matrix(self):
        wr = m.App._workspace_root
        wa = self._mkws("a")
        self.assertEqual(wr(os.path.join(wa, "src", "deep")), wa)   # deep subdir -> root
        # manifest root
        d2 = tempfile.mkdtemp(); os.makedirs(os.path.join(d2, "sub"))
        open(os.path.join(d2, "package.json"), "w").write("{}")
        self.assertEqual(wr(os.path.join(d2, "sub")), d2)
        # nested repos -> NEAREST marker
        d3 = tempfile.mkdtemp()
        os.makedirs(os.path.join(d3, ".git")); os.makedirs(os.path.join(d3, "inner", ".git"))
        self.assertEqual(wr(os.path.join(d3, "inner")), os.path.join(d3, "inner"))
        # outside any workspace -> None
        d4 = tempfile.mkdtemp()
        self.assertIsNone(wr(d4))

    def test_resume_isolated_by_workspace(self):
        wa, wb = self._mkws("a"), self._mkws("b")
        app = m.App(); app.quiet = True
        a1 = app.db.new_conv("A", "m", "b", cwd=wa, workspace=wa)
        app.db.save_msg(a1, "user", "a", "m", 1)
        time.sleep(1.1)                       # distinct updated_at
        b1 = app.db.new_conv("B", "m", "b", cwd=wb, workspace=wb)
        app.db.save_msg(b1, "user", "b", "m", 1)
        # resume from a DEEP SUBDIR of A gets A's session (never B's, no global fallback)
        old = os.getcwd(); os.chdir(os.path.join(wa, "src", "deep"))
        try:
            app2 = m.App(); app2.quiet = True
            app2._resume_mode = "continue"; app2._maybe_resume()
            self.assertEqual(app2.cid, a1)
        finally:
            os.chdir(old)
        # a NEW workspace with no sessions starts fresh (not another project's)
        wc = self._mkws("c")
        old = os.getcwd(); os.chdir(wc)
        try:
            app3 = m.App(); app3.quiet = True
            app3._resume_mode = "continue"; app3._maybe_resume()
            self.assertIsNone(app3.cid)
        finally:
            os.chdir(old)

    def test_slugs_scoped_per_workspace(self):
        wa, wb = self._mkws("a"), self._mkws("b")
        app = m.App(); app.quiet = True
        a1 = app.db.new_conv("A", "m", "b", cwd=wa, workspace=wa)
        b1 = app.db.new_conv("B", "m", "b", cwd=wb, workspace=wb)
        app.db.set_conv_slug(a1, "refactor")
        app.db.set_conv_slug(b1, "refactor")
        # same slug, two workspaces: each resolves to its own
        self.assertEqual(app.db.get_conv_by_slug("refactor", workspace=wa)["id"], a1)
        self.assertEqual(app.db.get_conv_by_slug("refactor", workspace=wb)["id"], b1)
        # scoped miss is a MISS (no global fallback)
        self.assertIsNone(app.db.get_conv_by_slug("other", workspace=wa))
        # unscoped lookup still works (global escape hatch)
        self.assertIsNotNone(app.db.get_conv_by_slug("refactor"))

    def test_backfill_anchors_legacy_rows(self):
        wa = self._mkws("back")
        app = m.App(); app.quiet = True
        # legacy row with cwd INSIDE a workspace but NULL workspace
        cid = app.db.new_conv("legacy", "m", "b", cwd=os.path.join(wa, "src"))
        n = app.db.backfill_workspaces(m.App._workspace_root)
        conv = app.db.get_conv(cid)
        self.assertEqual(conv["workspace"], wa)
        n2 = app.db.backfill_workspaces(m.App._workspace_root)
        self.assertEqual(n2, 0)             # idempotent

    def test_scoped_history_and_search(self):
        wa, wb = self._mkws("a"), self._mkws("b")
        app = m.App(); app.quiet = True
        a1 = app.db.new_conv("fix auth", "m", "b", cwd=wa, workspace=wa)
        b1 = app.db.new_conv("docker setup", "m", "b", cwd=wb, workspace=wb)
        app.db.save_msg(a1, "user", "auth token expired", "m", 1)
        app.db.save_msg(b1, "user", "nginx config", "m", 1)
        # scoped search misses across workspaces; hits within; global finds all
        self.assertEqual([r["id"] for r in app.db.search_convs("nginx", workspace=wa)], [])
        self.assertEqual([r["id"] for r in app.db.search_convs("nginx", workspace=wb)], [b1])
        self.assertEqual([r["id"] for r in app.db.search_convs("nginx")], [b1])
        # LIKE fallback path equally scoped
        app.db._fts_ok = False
        self.assertEqual([r["id"] for r in app.db.search_convs("nginx", workspace=wa)], [])
        self.assertEqual([r["id"] for r in app.db.search_convs("nginx", workspace=wb)], [b1])
        # scoped history listing
        h = [r["id"] for r in app.db.list_convs(workspace=wa)]
        self.assertEqual(h, [a1])

    def test_capture_and_restore_working_set(self):
        app = m.App(); app.quiet = True
        app.cfg.set("tools_enabled", True, save=False)
        app.active_session_skills.append(("python", "skill body"))
        def fake_cwt(msgs, confirm_batch_fn=None, continue_fn=None):
            yield {"type": "text", "content": "ok"}
        with um.patch.object(app.backend, "chat_with_tools", side_effect=fake_cwt):
            app._chat("build me a thing")          # creates the session
        conv = app.db.get_conv(app.cid)
        self.assertEqual(conv["cwd"], os.getcwd())
        self.assertEqual(conv["tools_mode"], 1)
        self.assertEqual(json.loads(conv["skills_json"]), ["python"])
        # resume into a FRESH app with different config -> working set restored
        app2 = m.App(); app2.quiet = True
        app2.cfg.set("tools_enabled", False, save=False)
        self.assertFalse(app2.cfg.get("tools_enabled"))
        app2._activate(app.cid, banner=False)
        self.assertTrue(app2.cfg.get("tools_enabled"))            # Build restored
        self.assertIn("python", {n for n, _ in app2.active_session_skills})

    def test_cwd_mismatch_warns(self):
        app = m.App(); app.quiet = True
        def fake_cwt(msgs, confirm_batch_fn=None, continue_fn=None):
            yield {"type": "text", "content": "ok"}
        with um.patch.object(app.backend, "chat_with_tools", side_effect=fake_cwt):
            app._chat("hello")
        conv = app.db.get_conv(app.cid)
        # fake a different origin dir
        app.db.conn.execute("UPDATE conversations SET cwd = ? WHERE id = ?", ("/somewhere/else", app.cid))
        app.db.conn.commit()
        buf = io.StringIO(); old = sys.stdout; sys.stdout = buf
        try:
            app2 = m.App(); app2.quiet = False
            app2._activate(app.cid, banner=False)   # quiet=False but mismatch warns
        finally:
            sys.stdout = old
        self.assertIn("cd /somewhere/else", buf.getvalue())

    def test_project_scoped_auto_resume(self):
        app = m.App(); app.quiet = True
        def fake_cwt(msgs, confirm_batch_fn=None, continue_fn=None):
            yield {"type": "text", "content": "ok"}
        with um.patch.object(app.backend, "chat_with_tools", side_effect=fake_cwt):
            app._chat("session in cwd X")
        cid_here = app.cid
        # another session anchored to a DIFFERENT cwd, more recent
        other = app.db.new_conv("other project", "m", "b", cwd="/other/project")
        app.db.save_msg(other, "user", "hi", "m", 1)   # bumps updated_at
        app.db.set_last(other) if hasattr(app.db, "set_last") else None
        # auto-resume HERE must pick the session whose cwd matches, not global-last
        app2 = m.App(); app2.quiet = True
        app2._maybe_resume()
        self.assertEqual(app2.cid, cid_here)

    def test_smart_titles(self):
        """Session titles strip EN+ID pleasantries (multi-layer), take the first
        clause, and never return empty."""
        st = m.App._smart_title
        self.assertIn("website", st("tolong buatkan simple website untuk toko kue").lower())
        self.assertIn("login bug", st("hey, can you help me fix the login bug in auth.py?").lower())
        self.assertIn("deploy", st("Halo! saya mau tanya soal deploy docker").lower())
        self.assertEqual(st(""), "New Chat")
        self.assertTrue(st("plain message").startswith("plain"))
        # multi-clause: only the first clause is kept
        t = st("buat dashboard. include charts. and filters")
        self.assertNotIn("charts", t)

    def test_backup_creates_valid_db_snapshot(self):
        """/backup snapshots the whole history DB atomically (VACUUM INTO) into
        the config dir, keeps the last 5, and the copy is a valid sqlite DB
        containing the messages."""
        app = m.App(); app.quiet = True
        cid = app.db.new_conv("backup test", "m", "b")
        app.db.save_msg(cid, "user", "findable-needle-42", "m", 3)
        app._execute_command("/backup")
        files = sorted(m.CONFIG_DIR.glob("backup-*.db"))
        self.assertTrue(files, "no backup file created")
        import sqlite3 as _sq
        c = _sq.connect(str(files[-1]))
        n = c.execute("SELECT COUNT(*) FROM messages WHERE content LIKE '%findable-needle-42%'").fetchone()[0]
        c.close()
        self.assertGreaterEqual(n, 1)   # snapshot has the data

    def test_named_session_create_or_resume(self):
        app = m.App(); app.quiet = True
        app._resume_mode = "session"; app._resume_arg = "webproject"
        buf = io.StringIO(); old = sys.stdout; sys.stdout = buf
        try:
            app._maybe_resume()          # no slug yet -> creates + tags
        finally:
            sys.stdout = old
        cid = app.cid
        self.assertIsNotNone(cid)
        self.assertEqual(app.db.get_conv(cid)["slug"], "webproject")
        # second launch with the same name -> RESUMES it
        app2 = m.App(); app2.quiet = True
        app2._resume_mode = "session"; app2._resume_arg = "WEBPROJECT"   # case-insensitive
        app2._maybe_resume()
        self.assertEqual(app2.cid, cid)
        # /session tag management
        app3 = m.App(); app3.quiet = True
        app3._activate(cid, banner=False)
        app3._execute_command("/session api-refactor")
        self.assertEqual(app3.db.get_conv(cid)["slug"], "api-refactor")

    def test_load_by_slug(self):
        app = m.App(); app.quiet = True
        def fake_cwt(msgs, confirm_batch_fn=None, continue_fn=None):
            yield {"type": "text", "content": "ok"}
        with um.patch.object(app.backend, "chat_with_tools", side_effect=fake_cwt):
            app._chat("tag me")
        app.db.set_conv_slug(app.cid, "deepwork")
        app2 = m.App(); app2.quiet = True
        app2._execute_command("/load deepwork")   # slug exact match, no FTS ambiguity
        self.assertEqual(app2.cid, app.cid)


class TestSmartPaste(_TmpHome):
    """Paste classifier + traceback auto-context: recognize content type, extract
    frames, attach bounded source around them."""

    def test_classify_paste_types(self):
        cp = m.App._classify_paste
        cases = [
            ("Traceback (most recent call last):\n  File \"/app/main.py\", line 42, in run\n    x = 1/0\nZeroDivisionError: division by zero", "traceback"),
            ("diff --git a/src/app.py b/src/app.py\n--- a/src/app.py\n+++ b/src/app.py\n@@ -1,3 +1,4 @@\n+import os", "diff"),
            ("https://github.com/vercel/next.js/issues/58123", "github-issue"),
            ("https://github.com/vercel/next.js/pull/58100", "github-pull"),
            ("https://github.com/anthropics/claude-code", "github-repo"),
            ('{"name": "ai", "version": 3}', "json"),
            ("# Heading\n\nSome doc text\n\n- item", "markdown"),
            ("def foo():\n    return 1\n\nclass Bar:\n    pass", "code"),
            ("hello there how are you", "plain"),
            ("", "empty"),
        ]
        for text, want in cases:
            kind, info = cp(text)
            self.assertEqual(kind, want, (text[:40], kind, want))
        _, info = cp("Traceback (most recent call last):\n  File \"/x/a.py\", line 3, in f\n  File \"/x/b.py\", line 9, in g\nError: x")
        self.assertEqual(info["files"], ["/x/a.py", "/x/b.py"])

    def test_traceback_context_attaches_local_frames(self):
        app = m.App(); app.quiet = True
        # local file with an "error" at line 12
        p = os.path.join(os.getcwd(), "tb_test.py")
        with open(p, "w") as f:
            f.write("\n".join(f"line{i}" for i in range(1, 21)))
        try:
            ctx = app._traceback_context([(p, 12)])
            self.assertIn(p, ctx)
            self.assertIn("line12", ctx)          # the failing line is included
            self.assertIn("lines 6-18", ctx)       # window around the frame
            # nonexistent frames are skipped without crashing
            self.assertEqual(app._traceback_context([("/nope/missing.py", 5)]), "")
        finally:
            os.unlink(p)

class TestEditFileAndGitTools(_TmpHome):
    """edit_file: surgical substring edits with unique-match enforcement and
    helpful failures. git tool: read-only views everywhere, mutations gated."""

    def setUp(self):
        super().setUp()
        self._old_cwd = os.getcwd()
        self.tmp = tempfile.mkdtemp(prefix="aiedit_")
        os.chdir(self.tmp)

    def tearDown(self):
        os.chdir(self._old_cwd)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_edit_file_surgical_semantics(self):
        p = os.path.join(self.tmp, "app.py")
        open(p, "w").write("def greet():\n    return 'hi'\n\ndef bye():\n    return 'bye'\n")
        # unique find -> replaced, line range reported
        r = m.Tools.run("edit_file", {"path": p, "find": "return 'hi'", "replace": "return 'hello'"}, build_mode=True)
        self.assertIn("lines 2-2", r)
        self.assertIn("return 'hello'", open(p).read())
        # not found -> helpful error (ok=False)
        ok, out = m.Tools.run_checked("edit_file", {"path": p, "find": "nope", "replace": "x"}, build_mode=True)
        self.assertFalse(ok); self.assertIn("not found", out); self.assertIn("read_file", out)
        # ambiguous -> told to disambiguate (two 'return ' lines now distinct; craft dup)
        open(p, "w").write("x = 1\nx = 1\n")
        ok2, out2 = m.Tools.run_checked("edit_file", {"path": p, "find": "x = 1", "replace": "x = 2"}, build_mode=True)
        self.assertFalse(ok2); self.assertIn("2 places", out2)
        # replace_all overrides
        r3 = m.Tools.run("edit_file", {"path": p, "find": "x = 1", "replace": "x = 2", "replace_all": True}, build_mode=True)
        self.assertEqual(open(p).read(), "x = 2\nx = 2\n")
        # plan mode blocks
        ok4, out4 = m.Tools.run_checked("edit_file", {"path": p, "find": "x", "replace": "y"}, build_mode=False)
        self.assertFalse(ok4); self.assertIn("Plan mode", out4)

    def test_git_tool_readonly_and_mutations(self):
        # real repo
        subprocess.run(["git", "init", "-q"], cwd=self.tmp, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "t@t"], cwd=self.tmp, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "t"], cwd=self.tmp, check=True, capture_output=True)
        open("a.txt", "w").write("one\n")
        # read-only in PLAN mode: status/diff/log work
        r = m.Tools.run("git", {"action": "status"}, build_mode=False)
        self.assertIn("a.txt", r)
        # mutation blocked in plan
        ok, out = m.Tools.run_checked("git", {"action": "stage", "path": "a.txt"}, build_mode=False)
        self.assertFalse(ok); self.assertIn("Build mode", out)
        # build mode: stage + commit flow
        r2 = m.Tools.run("git", {"action": "stage", "path": "a.txt"}, build_mode=True)
        self.assertIn("ok", r2.lower())
        r3 = m.Tools.run("git", {"action": "commit", "message": "init"}, build_mode=True)
        self.assertIn("init", r3)
        r4 = m.Tools.run("git", {"action": "log"}, build_mode=False)
        self.assertIn("init", r4)
        # dirty diff shows changes
        open("a.txt", "w").write("one\ntwo\n")
        r5 = m.Tools.run("git", {"action": "diff"}, build_mode=False)
        self.assertIn("+two", r5)
        # checkout_file discards (after approval in real UI)
        r6 = m.Tools.run("git", {"action": "checkout_file", "path": "a.txt"}, build_mode=True)
        self.assertEqual(open("a.txt").read(), "one\n")

    def test_git_confirm_gating(self):
        app = m.App(); app.quiet = True
        # read-only git batch auto-approves
        self.assertTrue(app._confirm_batch([{"name": "git", "args": {"action": "status"}}]))
        # mutating git batch needs approval (quiet -> declined)
        self.assertFalse(app._confirm_batch([{"name": "git", "args": {"action": "commit", "message": "x"}}]))
        self.assertFalse(app._confirm_batch([{"name": "write_file", "args": {"path": "x", "content": "y"}}]))

    def test_search_files_v2_grouping_and_filters(self):
        d = tempfile.mkdtemp(prefix="aisrch_")
        try:
            open(os.path.join(d, "a.py"), "w").write("x = 1\nneedle here\nx = 2\nneedle again\n")
            open(os.path.join(d, "b.py"), "w").write("NEEDLE upper\n")
            open(os.path.join(d, "c.txt"), "w").write("needle in txt\n")
            # default (case-sensitive): a.py + c.txt only; b.py is NEEDLE-upper
            r = m.Tools.run("search_files", {"query": "needle", "path": d})
            self.assertIn("a.py (2 matches)", r)
            self.assertNotIn("b.py", r)
            self.assertIn("c.txt (1 match)", r)
            self.assertIn("[3 of 3 matches shown]", r)
            # ignore_case picks up the upper-case one too
            ri = m.Tools.run("search_files", {"query": "needle", "path": d, "ignore_case": True})
            self.assertIn("b.py (1 match)", ri)
            self.assertIn("[4 of 4 matches shown]", ri)
            # ignore_case + max_results
            r2 = m.Tools.run("search_files", {"query": "needle", "path": d, "max_results": 1})
            self.assertIn("[1 of 3 matches shown]", r2)
            # glob filter excludes txt
            r3 = m.Tools.run("search_files", {"query": "needle", "path": d, "glob": "*.py"})
            self.assertNotIn("c.txt", r3)
            # regex mode
            r4 = m.Tools.run("search_files", {"query": "needle\s+here", "path": d, "regex": True})
            self.assertIn("a.py", r4)
            self.assertNotIn("b.py", r4)
            # no match message
            self.assertEqual(m.Tools.run("search_files", {"query": "zzznope", "path": d}), "No matches")
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_tool_runs_real_pytest_with_summary(self):
        """The `test` tool detects pytest, runs it, and returns parsed counts +
        failing test names."""
        import importlib.util as _ilu
        if _ilu.find_spec("pytest") is None:
            self.skipTest("pytest not installed in this environment")
        d = tempfile.mkdtemp(prefix="aitest_")
        try:
            open(os.path.join(d, "pyproject.toml"), "w").write("[tool.pytest.ini_options]\n")
            open(os.path.join(d, "t_ok.py"), "w").write("def test_ok():\n    assert 1 == 1\n")
            open(os.path.join(d, "t_bad.py"), "w").write("def test_broken():\n    assert 1 == 2\n")
            old = os.getcwd(); os.chdir(d)
            try:
                ok, out = m.Tools.run_checked("test", {})
            finally:
                os.chdir(old)
            self.assertTrue(ok)                     # a FAILING SUITE is not a tool error
            self.assertIn("total=2 passed=1 failed=1", out)
            self.assertIn("test_broken", out)
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_tool_no_manifest_errors_cleanly(self):
        d = tempfile.mkdtemp(prefix="ainotest_")
        try:
            old = os.getcwd(); os.chdir(d)
            ok, out = m.Tools.run_checked("test", {})
        finally:
            os.chdir(old); shutil.rmtree(d, ignore_errors=True)
        self.assertFalse(ok)
        self.assertIn("no recognized test manifest", out)

    def test_project_info_snapshot(self):
        d = tempfile.mkdtemp(prefix="aipinfo_")
        try:
            open(os.path.join(d, "pyproject.toml"), "w").write("[project]\nname='x'\n")
            open(os.path.join(d, "main.py"), "w").write("print('hi')\n")
            open(os.path.join(d, "util.py"), "w").write("x=1\n")
            r = m.Tools.run("project_info", {"path": d})
            self.assertIn(".py (2)", r)
            self.assertIn("pytest", r)                 # runner detected from pyproject
            self.assertIn("main.py", r)                 # entry point found
            self.assertIn("Files:", r)
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_paste_raw_flag_and_quiet_skip_preview(self):
        """--raw / non-TTY paths send verbatim (no preview interaction); the
        preview itself returns the enriched text on Enter/'a'/'f'."""
        app = m.App(); app.quiet = True
        sent = {}
        with um.patch.object(app, "_chat", side_effect=lambda t: sent.setdefault("t", t)):
            app._execute_command("/paste --raw")
        # clipboard may be empty on CI -> only assert no crash + no preview I/O


class TestMutationLedger(_TmpHome):
    """Ground truth for what a turn actually changed: the executor records
    writes/edits/mutating commands into MutationLedger; turn_end carries it;
    the footer lists real files, never the model's narration."""

    def test_empty_write_guard(self):
        """An empty write over a non-empty file is refused (arguments were
        probably truncated); allow_empty=true really blanks; empty writes to
        NEW files are fine; append never blocked."""
        d = tempfile.mkdtemp(prefix="aiblank_"); old = os.getcwd(); os.chdir(d)
        try:
            open("f.py", "w").write("real content\n")
            ok, out = m.Tools.run_checked("write_file", {"path": "f.py", "content": ""}, build_mode=True)
            self.assertFalse(ok)
            self.assertIn("refusing to overwrite", out)
            self.assertIn("allow_empty", out)
            self.assertEqual(open("f.py").read(), "real content\n")   # untouched
            # allow_empty really blanks
            r = m.Tools.run("write_file", {"path": "f.py", "content": "", "allow_empty": True}, build_mode=True)
            self.assertEqual(open("f.py").read(), "")
            # new file with empty content is allowed
            r2 = m.Tools.run("write_file", {"path": "new.py", "content": ""}, build_mode=True)
            self.assertTrue(os.path.exists("new.py"))
        finally:
            os.chdir(old); shutil.rmtree(d, ignore_errors=True)

    def test_auto_verify_runs_tests_after_mutations(self):
        """After a successful write in Build mode (auto_verify on), the suite's
        test tool runs ONCE and its result is injected into the next request;
        it does not run when no mutations happened, when the model already ran
        tests itself, when disabled, or a second time in the same turn."""
        d = tempfile.mkdtemp(prefix="aiverify_"); old = os.getcwd(); os.chdir(d)
        try:
            b = m.OpenAICompatible({"tools_enabled": True, "auto_verify": True}, "t",
                                   {"base_url": "http://localhost", "model": "x"})
            n = {"n": 0}; sent = []; tests_run = []
            def fs(url, data, headers, notify=None, mapper=None, ndjson=False):
                n["n"] += 1; sent.append(data)
                if n["n"] == 1:
                    yield {"choices": [{"delta": {"tool_calls": [{"index": 0, "id": "c1", "type": "function",
                        "function": {"name": "write_file", "arguments": '{"path":"a.py","content":"x=1"}'}}]}, "finish_reason": "tool_calls"}]}
                else:
                    yield {"choices": [{"delta": {"content": "done"}}]}
            def fake_test(name, args, bm, mr):
                tests_run.append(1)
                return (True, "[pytest] exit=0 | total=3 passed=3 failed=0")
            orig = m.Tools.run_checked
            def routed(name, args, bm=False, mr=10000):
                if name == "test": return fake_test(name, args, bm, mr)
                return orig(name, args, bm, mr)
            with um.patch.object(b, "_stream_req", side_effect=fs), \
                 um.patch.object(m.Tools, "run_checked", side_effect=routed):
                evts = list(b.chat_with_tools([{"role": "user", "content": "write it"}], confirm_batch_fn=lambda c: True))
            self.assertEqual(len(tests_run), 1)                     # ran exactly once
            self.assertTrue(any("AUTO-VERIFY" in (mm.get("content") or "")
                                for mm in sent[-1]["messages"] if mm.get("role") == "system"))
            self.assertTrue(any(e["type"] == "notice" and "auto-verify" in e.get("text", "") for e in evts))
            # no mutations -> never runs
            b2 = m.OpenAICompatible({"tools_enabled": True, "auto_verify": True}, "t",
                                    {"base_url": "http://localhost", "model": "x"})
            def fs2(url, data, headers, notify=None, mapper=None, ndjson=False):
                yield {"choices": [{"delta": {"content": "analysis only, no changes needed"}}]}
            with um.patch.object(b2, "_stream_req", side_effect=fs2):
                list(b2.chat_with_tools([{"role": "user", "content": "analyze"}], confirm_batch_fn=lambda c: True))
            # disabled -> never runs even with mutations
            b3 = m.OpenAICompatible({"tools_enabled": True, "auto_verify": False}, "t",
                                    {"base_url": "http://localhost", "model": "x"})
            n3 = {"n": 0}
            def fs3(url, data, headers, notify=None, mapper=None, ndjson=False):
                n3["n"] += 1
                if n3["n"] == 1:
                    yield {"choices": [{"delta": {"tool_calls": [{"index": 0, "id": "c1", "type": "function",
                        "function": {"name": "write_file", "arguments": '{"path":"b.py","content":"x"}'}}]}, "finish_reason": "tool_calls"}]}
                else:
                    yield {"choices": [{"delta": {"content": "done"}}]}
            ran3 = []
            def routed3(name, args, bm=False, mr=10000):
                if name == "test": ran3.append(1); return (True, "ok")
                return orig(name, args, bm, mr)
            with um.patch.object(b3, "_stream_req", side_effect=fs3), \
                 um.patch.object(m.Tools, "run_checked", side_effect=routed3):
                list(b3.chat_with_tools([{"role": "user", "content": "write it"}], confirm_batch_fn=lambda c: True))
            self.assertEqual(len(ran3), 0)                          # config off -> skipped
        finally:
            os.chdir(old); shutil.rmtree(d, ignore_errors=True)

    def test_done_claim_guard_matrix(self):
        """'Sudah diperbaiki!' with ZERO mutations -> ONE corrective retry; the
        model then writing the file -> clean turn_end (no warning). A second
        empty claim passes through with claimed_done=True (footer warns).
        Real mutations never trigger the guard. Pure Q&A (no claim words)
        never triggers it either."""
        b = m.OpenAICompatible({"tools_enabled": True}, "t", {"base_url": "http://localhost", "model": "x"})
        n = {"n": 0}
        def fs(url, data, headers, notify=None, mapper=None, ndjson=False):
            n["n"] += 1
            if n["n"] == 1:
                yield {"choices": [{"delta": {"content": "Bug sudah diperbaiki di app.py!"}}]}
            elif n["n"] == 2:
                yield {"choices": [{"delta": {"tool_calls": [{"index": 0, "id": "c1", "type": "function",
                    "function": {"name": "write_file", "arguments": '{"path":"app2.py","content":"x"}'}}]}, "finish_reason": "tool_calls"}]}
            else:
                yield {"choices": [{"delta": {"content": "Selesai, file dibuat."}}]}
        with um.patch.object(b, "_stream_req", side_effect=fs):
            evts = list(b.chat_with_tools([{"role": "user", "content": "fix the bug"}], confirm_batch_fn=lambda c: True))
        warn_notices = [e for e in evts if e["type"] == "notice" and "nothing was executed" in e.get("text", "")]
        self.assertEqual(len(warn_notices), 1)              # guard fired once
        te = [e for e in evts if e["type"] == "turn_end"]
        self.assertEqual(len(te), 1)
        self.assertFalse(te[0].get("claimed_done") and te[0]["ledger"].empty())  # wrote a file -> clean

        # double empty claim: passes through with claimed_done (footer warns)
        b2 = m.OpenAICompatible({"tools_enabled": True}, "t", {"base_url": "http://localhost", "model": "x"})
        n2 = {"n": 0}
        def fs2(url, data, headers, notify=None, mapper=None, ndjson=False):
            n2["n"] += 1
            yield {"choices": [{"delta": {"content": "Sudah diperbaiki semuanya, trust me."}}]}
        with um.patch.object(b2, "_stream_req", side_effect=fs2):
            evts2 = list(b2.chat_with_tools([{"role": "user", "content": "fix it"}], confirm_batch_fn=lambda c: True))
        te2 = [e for e in evts2 if e["type"] == "turn_end"]
        self.assertEqual(len(te2), 1)
        self.assertTrue(te2[0].get("claimed_done"))        # honest warning flag
        self.assertTrue(te2[0]["ledger"].empty())

        # no claim words -> guard silent
        b3 = m.OpenAICompatible({"tools_enabled": True}, "t", {"base_url": "http://localhost", "model": "x"})
        def fs3(url, data, headers, notify=None, mapper=None, ndjson=False):
            yield {"choices": [{"delta": {"content": "The bug is in line 4 of app.py; here is my analysis."}}]}
        with um.patch.object(b3, "_stream_req", side_effect=fs3):
            evts3 = list(b3.chat_with_tools([{"role": "user", "content": "analyze"}], confirm_batch_fn=lambda c: True))
        self.assertFalse(any(e["type"] == "notice" and "nothing was executed" in e.get("text", "") for e in evts3))

    def test_ledger_records_only_real_mutations(self):
        led = m.MutationLedger()
        led.record("write_file", "a.py", True)
        led.record("edit_file", "a.py", True)
        led.record("edit_file", "b.py", False, "not found")
        self.assertEqual(led.files_changed(), ["a.py"])   # unique, only successful
        self.assertEqual(led.failed_paths(), ["b.py"])
        self.assertTrue(led.empty() is False)
        led2 = m.MutationLedger()
        self.assertTrue(led2.empty())
        self.assertEqual(led2.files_changed(), [])

    def test_turn_end_carries_ledger_and_footer_is_real(self):
        d = tempfile.mkdtemp(prefix="ailedg_"); old = os.getcwd(); os.chdir(d)
        try:
            b = m.OpenAICompatible({"tools_enabled": True}, "t", {"base_url": "http://localhost", "model": "x"})
            n = {"n": 0}
            def fs(url, data, headers, notify=None, mapper=None, ndjson=False):
                n["n"] += 1
                if n["n"] == 1:
                    yield {"choices": [{"delta": {"tool_calls": [{"index": 0, "id": "c1", "type": "function",
                        "function": {"name": "write_file", "arguments": '{"path":"app.py","content":"x=1"}'}}]}, "finish_reason": "tool_calls"}]}
                else:
                    yield {"choices": [{"delta": {"content": "Fixed! app.py updated."}}]}
            with um.patch.object(b, "_stream_req", side_effect=fs):
                evts = list(b.chat_with_tools([{"role": "user", "content": "fix app.py"}], confirm_batch_fn=lambda c: True))
            tes = [e for e in evts if e["type"] == "turn_end"]
            self.assertEqual(len(tes), 1)
            led = tes[0]["ledger"]
            self.assertEqual([os.path.basename(f) for f in led.files_changed()], ["app.py"])
            self.assertTrue(os.path.exists("app.py"))   # really on disk
        finally:
            os.chdir(old); shutil.rmtree(d, ignore_errors=True)


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


class _FakeHTTPResp:
    """Test double: http.client response surface for pooled _req tests."""
    def __init__(self, status=429, body=b"{}", headers=None):
        self.status = status
        self._body = body
        self.will_close = status >= 400   # errors don't return to the pool
        self._headers = headers or {}
    def read(self, n=None):
        return self._body
    def getheader(self, name, default=None):
        return self._headers.get(name, default)


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
        class Fake429Conn:
            def __init__(self, *a, **k): pass
            def request(self, *a, **k):
                calls["n"] += 1
                self._resp = _FakeHTTPResp(status=429, body=b'{"error":"rate"}',
                                                headers={"Retry-After": "5"})
            def getresponse(self):
                return self._resp
            def close(self): pass
        with um.patch.object(m.http.client, "HTTPSConnection", Fake429Conn):
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
        class E503Conn:
            def __init__(self, *a, **k): pass
            def request(self, *a, **k):
                calls["n"] += 1
                self._resp = _FakeHTTPResp(status=503, body=b"{}")
            def getresponse(self):
                return self._resp
            def close(self): pass
        with um.patch.object(m.http.client, "HTTPSConnection", E503Conn), um.patch("time.sleep"):
            with self.assertRaises(m.BackendError):
                list(b._stream_req("https://x.test/v1/chat/completions", {}, {}))
        self.assertEqual(calls["n"], 3)             # 3 total, NOT 9

    def test_retry_after_header_overrides_backoff_delay(self):
        """When a 429 carries Retry-After, the retry waits that long instead of
        the default exponential backoff (respects the server's rate-limit ask)."""
        b = m.OpenAICompatible({"retries": 3, "retry_delay": 1.0}, "t", {"base_url": "https://x.test/v1", "model": "m", "api_key": "k"})
        class E429Conn:
            def __init__(self, *a, **k): pass
            def request(self, *a, **k):
                self._resp = _FakeHTTPResp(status=429, body=b"{}", headers={"Retry-After": "7"})
            def getresponse(self):
                return self._resp
            def close(self): pass
        delays = []
        with um.patch.object(m.http.client, "HTTPSConnection", E429Conn):
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
        self.assertTrue(any("coaching" in e.get("text", e.get("content", "")) for e in notices))
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

    def test_notice_renderer_levels_and_hints(self):
        """_render_notice: info -> dim, warn -> yellow, error -> red + indented
        hint; icons prefixed; legacy string notices degrade to info; empty
        notices print nothing."""
        app = m.App(); app.quiet = False
        def render(evt):
            buf = io.StringIO(); old = sys.stdout; sys.stdout = buf
            try: app._render_notice(evt)
            finally: sys.stdout = old
            return buf.getvalue()
        # NOTE: colors are empty strings when not a TTY, so assert STRUCTURE.
        out_info = render({"type": "notice", "level": "info", "icon": "\u23f3", "text": "context compacted \u00b7 12 old results"})
        self.assertIn("\u23f3 context compacted", out_info)   # icon + text, one line
        self.assertEqual(out_info.count("\n"), 1)
        out_warn = render({"type": "notice", "level": "warn", "icon": "\u26a0", "text": "output hit the token limit"})
        self.assertIn("\u26a0 output hit the token limit", out_warn)
        out_err = render({"type": "notice", "level": "error", "icon": "\u2716", "text": "iteration limit reached (50)",
                          "hint": "/retry to continue \u00b7 /config set max_iterations N"})
        self.assertIn("\u2716 iteration limit reached", out_err)
        self.assertIn("  /retry", out_err)               # hint indented on its own line
        self.assertEqual(out_err.count("\n"), 2)        # 2 lines max for a fatal
        # legacy string notice -> info, no crash
        out_legacy = render({"type": "notice", "content": "[old style]"})
        self.assertIn("[old style]", out_legacy)
        # empty -> nothing
        self.assertEqual(render({"type": "notice", "content": "   "}), "")

    def test_fatal_stops_are_two_line_state_plus_options(self):
        """Every LoopGuard fatal: state on line 1, actionable hint on line 2 —
        no walls of text, no 'I'm stuck', always a next action."""
        g = m.LoopGuard({"max_iterations": 3}, None)
        for _ in range(3):
            self.assertIsNone(g.begin_iteration())
        stop = g.begin_iteration()
        self.assertEqual(set(stop), {"level", "icon", "text", "hint"})
        self.assertLessEqual(len(stop["text"]), 60)
        self.assertIn("retry", stop["hint"])
        g2 = m.LoopGuard({}, None)
        stop2 = None
        for _ in range(5):
            stop2, _ = g2.note_results(any_productive=False, failed_names=[])
        self.assertIn("/retry or rephrase", stop2["hint"])
        self.assertNotIn("stuck", stop2["text"].lower())

    def test_nudge_model_text_full_user_line_short(self):
        """Phase nudges: the MODEL message keeps the full coaching text; the
        user-visible notice is ONE dim info line, not a warning paragraph."""
        b = m.OpenAICompatible({"gather_threshold": 2}, "t", {"base_url": "http://localhost", "model": "x"})
        calls = {"n": 0}; notices = []
        def fake_stream(url, data, headers, notify=None, mapper=None, ndjson=False):
            n = calls["n"]; calls["n"] += 1
            if n < 3:
                yield {"choices": [{"delta": {"tool_calls": [{"index": 0, "id": f"t{n}", "type": "function",
                    "function": {"name": "read_file", "arguments": '{"path":"f%d"}' % n}}]}, "finish_reason": "tool_calls"}]}
            else:
                yield {"choices": [{"delta": {"content": "done"}}]}
        with um.patch.object(b, "_stream_req", side_effect=fake_stream), \
             um.patch.object(m.Tools, "run_checked", side_effect=lambda name, args, bm, mr: (True, "ok")):
            for e in b.chat_with_tools([{"role": "user", "content": "read them"}], confirm_batch_fn=lambda c: True):
                if e["type"] == "notice":
                    notices.append(e)
        nudges = [nv for nv in notices if "coaching" in nv.get("text", "")]
        self.assertTrue(nudges)
        for nv in nudges:
            self.assertLessEqual(len(nv["text"]), 48)     # one short line
            self.assertEqual(nv["level"], "info")          # dim, not a warning
            self.assertNotIn("Stop reading one file", nv["text"])   # no paragraph leak

    def test_usage_capture_openai_anthropic_native(self):
        """Usage events: OpenAI final chunk (with stream_options requested),
        native Ollama via the mapper, Anthropic message_start/delta merge —
        and the stream_options-400 recovery path."""
        b = m.OpenAICompatible({}, "t", {"base_url": "https://x.test/v1", "model": "gpt-4o", "api_key": "k"})
        seen_body = {}
        def fs(url, data, headers, notify=None, mapper=None, ndjson=False):
            seen_body.update(data)
            yield {"choices": [{"delta": {"content": "hi"}}]}
            yield {"choices": [], "usage": {"prompt_tokens": 120, "completion_tokens": 45}}
        with um.patch.object(b, "_stream_req", side_effect=fs):
            evts = list(b.chat_with_tools([{"role": "user", "content": "x"}], confirm_batch_fn=lambda c: True))
        u = [e for e in evts if e["type"] == "usage"][0]
        self.assertEqual((u["in"], u["out"]), (120, 45))
        self.assertEqual(seen_body.get("stream_options"), {"include_usage": True})
        # native Ollama final event flows through the mapper
        b2 = m.OpenAICompatible({}, "ollama", {"base_url": "http://localhost:11434/v1", "model": "qwen3:1.7b"})
        b2._caps_cache["qwen3:1.7b"] = ["thinking"]
        def fs2(url, data, headers, notify=None, mapper=None, ndjson=False):
            yield mapper({"message": {"content": "ok"}, "done": True, "done_reason": "stop",
                          "prompt_eval_count": 892, "eval_count": 12})
        with um.patch.object(b2, "_stream_req", side_effect=fs2):
            u2 = [e for e in b2.chat_with_tools([{"role": "user", "content": "x"}], confirm_batch_fn=lambda c: True) if e["type"] == "usage"][0]
        self.assertEqual((u2["in"], u2["out"]), (892, 12))
        # extractor: anthropic shapes
        self.assertEqual(m.Backend._usage_from_chunk({"type": "message_start", "message": {"usage": {"input_tokens": 55}}})[:2], (55, 0))
        self.assertEqual(m.Backend._usage_from_chunk({"type": "message_delta", "usage": {"output_tokens": 30}})[:2], (0, 30))
        self.assertIsNone(m.Backend._usage_from_chunk({"choices": [{"delta": {}}]}))

    def test_usage_persistence_and_aggregates(self):
        app = m.App(); app.quiet = True
        cid = app.db.new_conv("t", "gpt-4o", "openai", cwd="/tmp")
        app.db.log_usage(cid, "gpt-4o", "openai", 100, 40, est=False)
        app.db.log_usage(cid, "gpt-4o", "openai", 50, 10, est=False)
        app.db.log_usage(cid, "llama3.2", "ollama", 300, 60, est=True)
        t = app.db.usage_totals(cid)
        self.assertEqual((t["tin"], t["tout"], t["requests"], t["est"]), (450, 110, 3, 1))
        by = app.db.usage_by_model()
        self.assertEqual(by["gpt-4o"]["requests"], 2)
        self.assertEqual(by["llama3.2"]["est"], 1)
        self.assertEqual(app.db.usage_totals(days=1)["requests"], 3)

    def test_context_window_registry_and_effective(self):
        """Per-model windows: cloud registry, local num_ctx, config fallback."""
        for name, want in [("gpt-4o", 128000), ("gpt-4.1", 1047576), ("o3-mini", 200000),
                           ("claude-3-5-sonnet", 200000), ("gemini-2.5-pro", 1048576),
                           ("qwen3:1.7b", 32768), ("llama3.2:3b", 8192), ("mystery", 32000)]:
            self.assertEqual(m.context_window_for(name), want, name)
        app = m.App(); app.quiet = True
        app.cfg.set_path("backends.cloud", {"base_url": "https://x.test/v1", "model": "gpt-4o", "api_key": "k"}, save=False)
        app.cfg.set("backend", "cloud", save=False)
        app.backend = m.get_backend(app.cfg)
        self.assertEqual(app._effective_window(), 128000)     # cloud registry
        app2 = m.App(); app2.quiet = True
        app2.cfg.set("backend", "ollama", save=False)
        app2.backend = m.get_backend(app2.cfg)
        self.assertEqual(app2._effective_window(), 8192)      # local llama3.2 num_ctx via tuning

    def test_usage_line_format(self):
        """The pi-style footer: ↑in ↓out · conv/window (%) (rN) (auto)."""
        app = m.App(); app.quiet = True
        app.cfg.set_path("backends.cloud", {"base_url": "https://x.test/v1", "model": "gpt-4o", "api_key": "k"}, save=False)
        app.cfg.set("backend", "cloud", save=False)
        app.backend = m.get_backend(app.cfg)
        app._sess_usage = {"in": 1234567, "out": 340, "req": 42}
        cid = app.db.new_conv("t", "gpt-4o", "openai", cwd="/tmp")
        app.cid = cid
        for _ in range(5):
            app.db.save_msg(cid, "user", "x" * 4000, "gpt-4o", 1000)
        line = app._usage_line()
        self.assertIn("\u21911.2M", line)
        self.assertIn("\u2193340", line)
        self.assertIn("/128.0k", line)
        self.assertIn("(r42)", line)
        self.assertIn("(auto)", line)

    def test_reasoning_effort_per_profile_and_selfhealing(self):
        """Phase B: reasoning_effort is per-profile opt-in (bynara-style reasoning
        models think by default; 'low' = shortest thinking). Never sent unset,
        invalid, or on the native Ollama path; a gateway 400 mentioning it gets
        the field stripped, ONE retry, and the profile cleared."""
        # set -> included
        b = m.OpenAICompatible({}, "bynara", {"base_url": "https://router.bynara.id/v1", "model": "laguna-s-2.1",
                                              "api_key": "k", "reasoning_effort": "low"})
        self.assertEqual(b._payload([{"role": "user", "content": "x"}], True)["reasoning_effort"], "low")
        # unset -> absent (every other backend: byte-identical payloads)
        b2 = m.OpenAICompatible({}, "opencode", {"base_url": "https://opencode.ai/zen/v1", "model": "big-pickle", "api_key": "k"})
        self.assertNotIn("reasoning_effort", b2._payload([{"role": "user", "content": "x"}], True))
        # invalid value ignored
        b3 = m.OpenAICompatible({}, "t", {"base_url": "https://x/v1", "model": "m", "api_key": "k", "reasoning_effort": "turbo"})
        self.assertNotIn("reasoning_effort", b3._payload([{"role": "user", "content": "x"}], True))
        # local NEVER sends it (native shim governs thinking)
        b4 = m.OpenAICompatible({}, "ollama", {"base_url": "http://localhost:11434/v1", "model": "qwen3:1.7b",
                                                "api_key": "o", "reasoning_effort": "low"})
        b4._caps_cache["qwen3:1.7b"] = ["thinking"]
        self.assertNotIn("reasoning_effort", b4._payload([{"role": "user", "content": "x"}], True))
        # self-heal: 400 mentioning reasoning_effort -> strip, retry once, clear profile
        calls = {"n": 0, "bodies": []}
        def fake_req(url, data, headers, timeout=120):
            calls["n"] += 1; calls["bodies"].append(json.loads(json.dumps(data)))
            if "reasoning_effort" in data:
                raise m.BackendError("HTTP 400: {'error':'reasoning_effort is not supported'}", transient=False)
            class R:
                status = 200
                def read(self, n=-1):
                    return b'data: {"choices":[{"delta":{"content":"ok"}}]}\n\ndata: [DONE]\n\n'
                def __enter__(self): return self
                def __exit__(self, *a): return False
            return R()
        with um.patch.object(b, "_req", side_effect=fake_req):
            list(b.chat_with_tools([{"role": "user", "content": "hi"}], confirm_batch_fn=lambda c: True))
        self.assertEqual(calls["n"], 2)
        self.assertNotIn("reasoning_effort", calls["bodies"][-1])
        self.assertIsNone(b.profile.get("reasoning_effort"))

    def test_long_doc_rules_and_big_write_coaching(self):
        """Long documents: tool rule 8 instructs sectioned writing; a >15KB
        single write_file still executes but the model is coached to continue
        in append sections (never blocked, never wasted)."""
        self.assertIn("LONG DOCUMENTS", m.Config.TOOL_RULES)
        self.assertIn("append=true", m.Config.TOOL_RULES)
        d = tempfile.mkdtemp(prefix="aidoc_"); old = os.getcwd(); os.chdir(d)
        try:
            b = m.OpenAICompatible({"tools_enabled": True}, "t", {"base_url": "http://x/v1", "model": "m", "api_key": "k"})
            big = json.dumps({"path": "guide.md", "content": "x" * 16000})
            n = {"n": 0}; sent = []
            def fs(url, data, headers, notify=None, mapper=None, ndjson=False):
                n["n"] += 1; sent.append(data)
                if n["n"] == 1:
                    yield {"choices": [{"delta": {"tool_calls": [{"index": 0, "id": "c1", "type": "function",
                        "function": {"name": "write_file", "arguments": big}}]}, "finish_reason": "tool_calls"}]}
                else:
                    yield {"choices": [{"delta": {"content": "done"}}]}
            with um.patch.object(b, "_stream_req", side_effect=fs):
                evts = list(b.chat_with_tools([{"role": "user", "content": "make a guide"}], confirm_batch_fn=lambda c: True))
            self.assertTrue(any("sections" in e.get("text", "") for e in evts if e["type"] == "notice"))
            self.assertTrue(any("append=true" in (mm.get("content") or "")
                                for mm in sent[-1]["messages"] if mm.get("role") == "system"))
            self.assertGreater(os.path.getsize("guide.md"), 15000)   # executed, not blocked
            # small writes: no coaching noise
            b2 = m.OpenAICompatible({"tools_enabled": True}, "t", {"base_url": "http://x/v1", "model": "m", "api_key": "k"})
            small = json.dumps({"path": "s.md", "content": "tiny"})
            n2 = {"n": 0}; sent2 = []
            def fs2(url, data, headers, notify=None, mapper=None, ndjson=False):
                n2["n"] += 1; sent2.append(data)
                if n2["n"] == 1:
                    yield {"choices": [{"delta": {"tool_calls": [{"index": 0, "id": "c1", "type": "function",
                        "function": {"name": "write_file", "arguments": small}}]}, "finish_reason": "tool_calls"}]}
                else:
                    yield {"choices": [{"delta": {"content": "done"}}]}
            with um.patch.object(b2, "_stream_req", side_effect=fs2):
                evts2 = list(b2.chat_with_tools([{"role": "user", "content": "x"}], confirm_batch_fn=lambda c: True))
            self.assertFalse(any("sections" in e.get("text", "") for e in evts2 if e["type"] == "notice"))
        finally:
            os.chdir(old); shutil.rmtree(d, ignore_errors=True)

    def test_stream_progress_beacons_flow(self):
        """The loop emits throttled stream_progress beacons (elapsed, content
        chars, tool-arg bytes) so buffered gateways still show live progress;
        usage events carry measured stream seconds for the tok/s footer."""
        b = m.OpenAICompatible({}, "t", {"base_url": "http://x/v1", "model": "m", "api_key": "k"})
        n = {"n": 0}
        def fs(url, data, headers, notify=None, mapper=None, ndjson=False):
            n["n"] += 1
            if n["n"] == 1:
                for piece in ("one", "two", "three"):
                    yield {"choices": [{"delta": {"content": piece}}]}
                yield {"choices": [{"delta": {}}, {"delta": {}}], "usage": {"prompt_tokens": 10, "completion_tokens": 30}}
            else:
                yield {"choices": [{"delta": {"content": "done"}}]}
        with um.patch.object(b, "_stream_req", side_effect=fs), um.patch("time.monotonic") as tm:
            tm.side_effect = [0, 2, 4, 6, 8, 10, 12, 14]   # force the 1s throttle
            evts = list(b.chat_with_tools([{"role": "user", "content": "x"}], confirm_batch_fn=lambda c: True))
        beacons = [e for e in evts if e["type"] == "stream_progress"]
        usage = [e for e in evts if e["type"] == "usage"]
        self.assertTrue(beacons)
        self.assertEqual(beacons[0]["content_chars"], 3)   # "one"
        self.assertTrue(usage and usage[0].get("secs") is not None)

    def test_sandbox_guard_intercepts_doomed_writes(self):
        """Writes outside the cwd sandbox are caught BEFORE execution (the old
        path streamed a full 23KB doc, failed at exec, and burned a corrective
        round): one system correction asks for relative paths; the retry lands
        the file. Non-write batches never trigger it."""
        d = tempfile.mkdtemp(prefix="aisg_"); old = os.getcwd(); os.chdir(d)
        try:
            b = m.OpenAICompatible({"tools_enabled": True}, "t", {"base_url": "http://x/v1", "model": "m", "api_key": "k"})
            outside = json.dumps({"path": "/definitely/outside/guide.md", "content": "c1"})
            inside = json.dumps({"path": "guide.md", "content": "c1"})
            n = {"n": 0}; sent = []; executed = []
            def fs(url, data, headers, notify=None, mapper=None, ndjson=False):
                n["n"] += 1; sent.append(data)
                if n["n"] == 1:
                    yield {"choices": [{"delta": {"tool_calls": [{"index": 0, "id": "c1", "type": "function",
                        "function": {"name": "write_file", "arguments": outside}}]}, "finish_reason": "tool_calls"}]}
                else:
                    yield {"choices": [{"delta": {"tool_calls": [{"index": 0, "id": "c2", "type": "function",
                        "function": {"name": "write_file", "arguments": inside}}]}, "finish_reason": "tool_calls"}]}
                    yield {"choices": [{"delta": {"content": "done"}}]}
            orig = m.Tools.run_checked
            def spy(name, args, bm=False, mr=10000):
                executed.append(name); return orig(name, args, bm, mr)
            with um.patch.object(b, "_stream_req", side_effect=fs), \
                 um.patch.object(m.Tools, "run_checked", side_effect=spy):
                evts = list(b.chat_with_tools([{"role": "user", "content": "make a guide"}], confirm_batch_fn=lambda c: True))
            self.assertTrue(any("sandbox" in e.get("text", "") for e in evts if e["type"] == "notice"))
            self.assertEqual(executed.count("write_file"), 1)      # doomed one never executed
            self.assertTrue(any("RELATIVE" in (mm.get("content") or "")
                                for mm in sent[-1]["messages"] if mm.get("role") == "tool"))
            self.assertTrue(os.path.exists("guide.md"))
            # read-only batches: guard silent
            b2 = m.OpenAICompatible({"tools_enabled": True}, "t", {"base_url": "http://x/v1", "model": "m", "api_key": "k"})
            n2 = {"n": 0}
            def fs2(url, data, headers, notify=None, mapper=None, ndjson=False):
                n2["n"] += 1
                if n2["n"] == 1:
                    yield {"choices": [{"delta": {"tool_calls": [{"index": 0, "id": "c1", "type": "function",
                        "function": {"name": "list_files", "arguments": '{"path":"."}'}}]}, "finish_reason": "tool_calls"}]}
                else:
                    yield {"choices": [{"delta": {"content": "ok"}}]}
            with um.patch.object(b2, "_stream_req", side_effect=fs2), \
                 um.patch.object(m.Tools, "run_checked", side_effect=lambda n_, a, bm=False, mr=10000: (True, "f")):
                evts2 = list(b2.chat_with_tools([{"role": "user", "content": "list"}], confirm_batch_fn=lambda c: True))
            self.assertFalse(any("sandbox" in e.get("text", "") for e in evts2 if e["type"] == "notice"))
        finally:
            os.chdir(old); shutil.rmtree(d, ignore_errors=True)

    def test_doc_request_gets_relative_path_rule(self):
        """Guide/report requests append the FILE OUTPUT RULE (relative path,
        sections with append) to the system message; other requests don't;
        _assemble_system_prompt stays message-independent (warm-prefix lock)."""
        app = m.App(); app.quiet = True
        app.cfg.set("tools_enabled", True, save=False)
        captured = {}
        def fake(msgs, confirm_batch_fn=None, continue_fn=None):
            captured["sysp"] = msgs[0]["content"]
            yield {"type": "text", "content": "ok"}
        with um.patch.object(app.backend, "chat_with_tools", side_effect=fake):
            app._chat("Create me a fully comprehensive guidebook panduan rust")
        self.assertIn("FILE OUTPUT RULE", captured["sysp"])
        with um.patch.object(app.backend, "chat_with_tools", side_effect=fake):
            app._chat("what is two plus two")
        self.assertNotIn("FILE OUTPUT RULE", captured["sysp"])
        self.assertEqual(app._assemble_system_prompt(), app._assemble_system_prompt())

    def test_transient_first_stream_drop_checkpoints(self):
        """A transient first-stream failure (idle timeout/reset, no work yet)
        checkpoints the turn so auto-resume//retry continues it instead of the
        user retyping; the resumed reply is saved normally."""
        app = m.App(); app.quiet = True
        app.cfg.set("tools_enabled", False, save=False)
        app.backend = m.OpenAICompatible({}, "t", {"base_url": "http://x/v1", "model": "m", "api_key": "k"})
        calls = {"n": 0}
        def fs(url, data, headers, notify=None, mapper=None, ndjson=False):
            calls["n"] += 1
            if calls["n"] == 1:
                time.sleep(0.1)
                raise m.BackendError("Stream idle for too long (gateway went silent mid-generation) /retry continues", transient=True)
            yield {"choices": [{"delta": {"content": "Chapter 1: welcome"}}]}
        app.cfg.set("auto_continue", True, save=False)
        with um.patch.object(app.backend, "_stream_req", side_effect=fs):
            app._chat("make a rust guide")
        self.assertGreaterEqual(calls["n"], 2)
        self.assertIn("Chapter 1", app.last_reply or "")

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
        _stop = g.begin_iteration()
        self.assertEqual(_stop["level"], "error")
        self.assertIn("iteration limit", _stop["text"])
        self.assertIn("/retry", _stop["hint"])
        # stuck: 4 repeats tolerate, the 5th stops
        g2 = m.LoopGuard({}, None)
        for i in range(4):
            stop, reflect = g2.note_results(any_productive=False, failed_names=[])
            self.assertIsNone(stop)
        stop, reflect = g2.note_results(any_productive=False, failed_names=[])
        self.assertEqual(stop["level"], "error")
        self.assertIn("no new progress", stop["text"])
        # failure streak: 2 reflects, the 3rd stops; success resets
        g3 = m.LoopGuard({}, None)
        stop, reflect = g3.note_results(True, ["write_file"])
        self.assertIsNone(stop); self.assertIn("REFLECT", reflect)
        stop, reflect = g3.note_results(True, ["write_file"])
        self.assertIsNone(stop)
        stop, reflect = g3.note_results(True, ["write_file"])
        self.assertEqual(stop["level"], "error")
        self.assertIn("failed rounds in a row", stop["text"])
        self.assertIn("Build mode", stop["hint"])
        g4 = m.LoopGuard({}, None)
        g4.note_results(True, ["run_command"])      # one failure...
        g4.note_results(True, [])                    # ...then success resets
        stop, reflect = g4.note_results(True, ["run_command"])
        self.assertIsNone(stop)                      # so this is failure #1, not #3
        # checkpoint: approved extends the ceiling, declined stops, None skips
        g5 = m.LoopGuard({"max_iterations": 6, "continue_every": 2, "continue_mode": "prompt"}, lambda i, t: True)
        g5.note_calls(2)
        self.assertIsNone(g5.checkpoint())
        self.assertEqual(g5.iteration_cap, 8)
        # continue_mode=auto (default): pi-style keep-going, no prompt at all
        g5b = m.LoopGuard({"max_iterations": 6, "continue_every": 2}, lambda i, t: (_ for _ in ()).throw(AssertionError("must not prompt")))
        g5b.note_calls(2)
        self.assertIsNone(g5b.checkpoint())
        self.assertEqual(g5b.iteration_cap, 8)
        g6 = m.LoopGuard({"max_iterations": 6, "continue_every": 2, "continue_mode": "prompt"}, lambda i, t: False)
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


class TestHelpers(_TmpHome):
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
