#!/usr/bin/env python3
"""Security & Plan-mode regression tests for the aiv1 script.

Covers the Phase 1 hardening:
  S1  Plan-mode newline/control-char injection bypass
  S2  Missing interpreter blocklist (node/go/java/lua/...) -> allowlist
  S3  write_file sandbox bypass via symlinks (realpath fix)
  S4  find/git/sort/date flag abuse in Plan mode
plus the no-shell executor, output cap, timeout, and pipe handling.

Run:  python3 tests/test_security.py
"""
import importlib.machinery, importlib.util, os, shutil, sys, tempfile, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
AIV1 = ROOT / "ai"   # the generated single-file artifact (built by build.py from src/)


def load_aiv1():
    loader = importlib.machinery.SourceFileLoader("aiv1_security_test", str(AIV1))
    spec = importlib.util.spec_from_loader("aiv1_security_test", loader)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


m = load_aiv1()
Tools = m.Tools


class TestPlanAllowlist(unittest.TestCase):
    def _allow(self, cmd):  self.assertTrue(Tools._plan_safe(cmd), "expected ALLOWED:  %r" % cmd)
    def _block(self, cmd):  self.assertFalse(Tools._plan_safe(cmd), "expected BLOCKED: %r" % cmd)

    # --- S1: control-char / shell-construct injection ---
    def test_newline_injection_blocked(self):           # S1
        self._block("ls\nrm -rf ~/x")
    def test_cr_injection_blocked(self):                # S1
        self._block("ls\rrm -rf ~/x")
    def test_nul_injection_blocked(self):               # S1
        self._block("ls\x00rm -rf ~/x")
    def test_semicolon_blocked(self):
        self._block("ls; rm -rf ~/x")
    def test_redirect_blocked(self):
        self._block("echo hi > /tmp/f")
        self._block("echo hi >> /tmp/f")
    def test_and_and_or_blocked(self):
        self._block("ls && rm -rf ~")
        self._block("ls || rm -rf ~")
    def test_command_subst_blocked(self):
        self._block("cat $(rm -rf ~)")
        self._block("cat `rm -rf ~`")

    # --- S2: interpreters excluded from the allowlist entirely ---
    def test_interpreters_blocked(self):                # S2
        for c in [
            "python3 -c 'import os; os.system(\"rm -rf x\")'",
            "python -c '1'",
            "node -e 'require(\"child_process\").execSync(\"rm -rf x\")'",
            "go run x.go",
            "java -version",
            "lua -e 'os.execute(\"rm -rf x\")'",
            "deno eval '1'",
            "ruby -e 'system(\"rm -rf x\")'",
            "php -r '1'",
            "perl -e 'system(\"rm -rf x\")'",
            "awk 'BEGIN{system(\"rm -rf x\")}'",
            "sed 's/x/y/e'",
            "sh -c 'rm -rf x'",
            "bash -c 'rm -rf x'",
        ]:
            self._block(c)

    def test_wrappers_blocked(self):
        for c in ["sudo ls", "doas ls", "su -c ls", "env ls", "xargs ls",
                  "timeout 5 ls", "busybox ls", "toybox ls", "command ls"]:
            self._block(c)

    def test_mutating_binaries_blocked(self):
        for c in ["rm -rf ~", "touch x", "mkdir x", "cp a b", "mv a b",
                  "chmod 777 x", "chown u x", "dd if=/dev/zero of=x", "tee x",
                  "ln -s a b", "mkfs /dev/sda", "mount /dev/sda /mnt",
                  "pkg install x", "apt install x", "pip install x",
                  "npm install x", "kill 1", "reboot", "shutdown"]:
            self._block(c)

    # --- S4: allowlisted binaries with mutating flags ---
    def test_find_mutation_blocked(self):               # S4
        self._block("find . -delete")
        self._block("find . -exec rm {} \\;")
        self._block("find . -execdir rm {} \\;")
        self._block("find . -ok rm {} \\;")
        self._block("find . -okdir rm {} \\;")
        self._block("find . -fprint out.txt")
        self._block("find . -fprint0 out.txt")
        self._block("find . -fprintf out.txt '%p'")
        self._block("find . -fls out.txt")

    def test_sort_date_mutation_blocked(self):          # S4
        self._block("sort -o out.txt f.txt")
        self._block("sort --output=out.txt f.txt")
        self._block("date -s tomorrow")
        self._block("date --set 'tomorrow'")

    def test_git_mutation_blocked(self):                # S4
        for c in ["git reset --hard", "git clean -fd", "git rm x",
                  "git checkout -- x", "git stash", "git commit -m x",
                  "git push", "git branch -d x", "git branch -D x",
                  "git tag -d v1", "git tag --delete v1",
                  "git remote add o url", "git remote remove o",
                  "git remote set-url o url", "git config user.name x",
                  "git -C /tmp reset --hard"]:
            self._block(c)

    def test_pipe_segment_checked(self):
        # a mutating binary anywhere in the pipe must be rejected
        self._block("git status | rm -rf ~")
        self._block("ls | xargs rm")

    # --- legitimate read-only commands stay allowed ---
    def test_readonly_commands_allowed(self):
        for c in [
            "ls", "ls -la", "ls ~", "ls /sdcard",
            "cat a.txt", "cat 'a b.txt'",
            "head -n 5 x", "tail -n 10 x",
            "grep -rn foo .", "grep 'a|b' f",
            "wc -l x", "sort x", "uniq x", "cut -d, -f1 x",
            "diff a b", "cmp a b", "comm a b",
            "find . -name '*.py'", "find src -type f -print",
            "find . -mtime -7 -print",
            "git status", "git diff", "git log --oneline -5",
            "git show HEAD", "git -C /tmp status",
            "git status --porcelain", "git branch -a", "git remote -v",
            "file x", "stat x", "du -sh .", "df -h", "which python",
            "date", "echo hello", "realpath x", "readlink x", "uname -a",
            "id", "whoami", "uptime", "md5sum x", "strings x", "base64 x",
            "ls | wc -l", "grep foo a.txt | sort | uniq",
            "find . -name '*.log' | head -n 3",
        ]:
            self._allow(c)

    def test_split_pipes_respects_quotes(self):
        self.assertEqual(Tools._split_pipes("grep 'a|b' f | wc -l"),
                         ["grep 'a|b' f ", " wc -l"])
        self.assertEqual(Tools._split_pipes('echo "x|y"'), ['echo "x|y"'])


class TestPlanExecutor(unittest.TestCase):
    def setUp(self):
        self._old_cwd = os.getcwd()
        self._tmp = tempfile.mkdtemp()
        os.chdir(self._tmp)
        Path("f.txt").write_text("alpha|beta\ngamma\n")
        Path("d.txt").write_text("one\ntwo\nthree\n")

    def tearDown(self):
        try: os.chdir(self._old_cwd)
        except OSError: pass
        shutil.rmtree(self._tmp, ignore_errors=True)

    def _cmd(self, cmd, build=False):
        return Tools.run("run_command", {"command": cmd}, build_mode=build)

    def test_pipes_and_quoted_patterns_work(self):
        self.assertIn("alpha", self._cmd("grep alpha f.txt"))
        self.assertIn("2", self._cmd("cat f.txt | wc -l"))
        self.assertIn("alpha|beta", self._cmd("grep 'a|b' f.txt"))
        self.assertIn("f.txt", self._cmd("find . -name '*.txt' | sort"))

    def test_tilde_expansion_works(self):
        out = self._cmd("ls ~ | wc -l")
        # home dir is non-empty on any real system
        self.assertNotIn("Error", out)

    # --- the actual S1/S2/S4 exploitation must be inert in Plan mode ---
    def test_newline_injection_blocked_and_inert(self):  # S1
        out = self._cmd("cat f.txt\ntouch injected.txt")
        self.assertIn("blocked", out.lower())
        self.assertFalse(os.path.exists("injected.txt"))

    def test_interpreter_execution_blocked(self):        # S2
        out = self._cmd("python3 -c 'open(\"pwn.txt\",\"w\").write(\"x\")'")
        self.assertIn("blocked", out.lower())
        self.assertFalse(os.path.exists("pwn.txt"))
        out = self._cmd("node -e 'require(\"fs\").writeFileSync(\"pwn2.txt\",\"x\")'")
        self.assertIn("blocked", out.lower())
        self.assertFalse(os.path.exists("pwn2.txt"))

    def test_redirect_blocked_and_inert(self):           # S1
        out = self._cmd("echo hi > escaped.txt")
        self.assertIn("blocked", out.lower())
        self.assertFalse(os.path.exists("escaped.txt"))

    def test_find_exec_blocked_and_inert(self):          # S4
        out = self._cmd("find . -exec touch {} \\;")
        self.assertIn("blocked", out.lower())
        self.assertFalse(os.path.exists("f.txt.exec"))  # sanity, nothing created

    # --- robustness of the executor ---
    def test_output_cap(self):
        out = Tools._run_plan("cat /dev/zero", max_out=4096)
        self.assertIn("output capped", out)

    def test_timeout(self):
        out = Tools._run_plan("sleep 5", timeout=1)
        self.assertIn("timed out", out)

    def test_nonexistent_command_reports_error(self):
        out = self._cmd("doesnotexist123")
        # allowlist blocks it first
        self.assertIn("blocked", out.lower())

    def test_stderr_returned(self):
        out = self._cmd("cat missing-file-xyz.txt")
        self.assertIn("No such file", out)

    # --- Build mode still runs a real shell (with confirmation elsewhere) ---
    def test_build_mode_still_shell(self):
        out = self._cmd("echo build-mode-ok; touch build.txt", build=True)
        self.assertIn("build-mode-ok", out)
        self.assertTrue(os.path.exists("build.txt"))
        os.remove("build.txt")

    def test_build_mode_timeout_kills_group(self):
        # a runaway shell pipeline must be killed, not orphaned
        out = self._cmd("yes | head -c 1", build=True)  # exits fast anyway
        # run something that would hang without a timeout/kill
        out = self._cmd("sleep 60", build=True)
        self.assertIn("timed out", out)


class TestWriteFileSandbox(unittest.TestCase):
    def setUp(self):
        self._old_cwd = os.getcwd()
        self._tmp = tempfile.mkdtemp()
        os.chdir(self._tmp)

    def tearDown(self):
        try: os.chdir(self._old_cwd)
        except OSError: pass
        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_inside_cwd_allowed(self):
        res = Tools.run("write_file", {"path": "ok.txt", "content": "hi"}, build_mode=True)
        self.assertIn("Written", res)
        self.assertTrue(os.path.exists("ok.txt"))

    def test_symlink_escape_blocked(self):               # S3
        outside = tempfile.mkdtemp()
        try:
            os.symlink(outside, os.path.join(self._tmp, "escape"))
            res = Tools.run("write_file", {"path": "escape/pwn.txt", "content": "hi"}, build_mode=True)
            self.assertIn("Error", res)
            self.assertFalse(os.path.exists(os.path.join(outside, "pwn.txt")))
        finally:
            shutil.rmtree(outside, ignore_errors=True)

    def test_parent_dotdot_escape_blocked(self):
        res = Tools.run("write_file", {"path": "../pwn.txt", "content": "hi"}, build_mode=True)
        self.assertIn("Error", res)
        self.assertFalse(os.path.exists(os.path.join(self._tmp, "..", "pwn.txt")))


if __name__ == "__main__":
    unittest.main(verbosity=2)
