# ══ termux_ai.tools ══ (fragment; merged by build.py)
class Tools:
    SAFE_TOOLS = {"read_file", "list_files", "search_files", "fetch_url"}

    TOOLS = [
        {"type": "function", "function": {"name": "read_file", "description": "Read file contents", "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}}},
        {"type": "function", "function": {"name": "write_file", "description": "Write content to file", "parameters": {"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}}, "required": ["path", "content"]}}},
        {"type": "function", "function": {"name": "list_files", "description": "List files in directory", "parameters": {"type": "object", "properties": {"path": {"type": "string"}}}}},
        {"type": "function", "function": {"name": "run_command", "description": "Run a shell command and return stdout/stderr. (The exact Plan-mode allowlist is provided at call time.)", "parameters": {"type": "object", "properties": {"command": {"type": "string"}}, "required": ["command"]}}},
        {"type": "function", "function": {"name": "search_files", "description": "Search text in files (uses grep)", "parameters": {"type": "object", "properties": {"query": {"type": "string"}, "path": {"type": "string"}}, "required": ["query"]}}},
        {"type": "function", "function": {"name": "fetch_url", "description": "Fetch a web page via HTTP GET and return its text content (HTML is stripped to readable text; ~500 KB cap). Use this to READ or RESEARCH a website/URL -- prefer it over curl or run_command for any http(s) URL.", "parameters": {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]}}},
    ]
    PLAN_TOOLS = [t for t in TOOLS if t["function"]["name"] != "write_file"]
    
    # Plan mode is enforced by a read-only ALLOWLIST, not a blocklist: only
    # the programs below may run, and commands are executed WITHOUT a shell
    # (see _run_plan), so shell metacharacters can never take effect. This is
    # the complete security boundary for Plan mode. Keep the list minimal.
    PLAN_READONLY_CMDS = {
        "ls", "cat", "head", "tail", "grep", "egrep", "fgrep", "rg", "find",
        "wc", "sort", "uniq", "cut", "tr", "diff", "cmp", "comm", "paste",
        "join", "fold", "fmt", "nl", "tac", "rev", "seq", "date", "pwd",
        "echo", "printf", "file", "stat", "du", "df", "which", "basename",
        "dirname", "realpath", "readlink", "uname", "id", "whoami", "groups",
        "nproc", "uptime", "md5sum", "sha1sum", "sha256sum", "sha512sum",
        "od", "hexdump", "xxd", "strings", "base64", "zcat", "bzcat", "xzcat",
        "git",
    }
    # Even allowlisted binaries can write/execute with the wrong flags.
    PLAN_ARGS_BLOCKED = {
        "sort": {"-o", "--output"},            # sort -o writes a file
        "date": {"-s", "--set"},               # date -s sets system time
    }
    PLAN_GIT_RO = {"status", "diff", "log", "show", "branch", "ls-files", "ls-tree", "rev-parse", "tag", "remote", "blame", "grep", "help", "version"}
    # Arguments that mutate a git repo even under an otherwise read-only subcommand.
    GIT_MUTATING_ARGS = {
        "add", "rm", "mv", "reset", "checkout", "clean", "stash", "apply",
        "cherry-pick", "merge", "rebase", "commit", "push", "pull", "fetch",
        "switch", "restore", "init", "clone", "gc", "prune", "repack",
        "filter-branch", "config", "update-ref", "update-index", "archive",
        "bundle", "submodule", "worktree", "notes", "replace", "reflog",
        "set-url", "rename", "remove", "--delete", "--hard", "--soft",
        "--mixed", "--amend", "--force", "--force-with-lease",
        "-d", "-D", "-m", "-M", "-f",
    }
    PLAN_FIND_BLOCKED = {"-delete", "-exec", "-execdir", "-ok", "-okdir", "-fprint", "-fprint0", "-fprintf", "-fls"}

    @staticmethod
    def _split_pipes(cmd_str):
        """Split on UNQUOTED pipes so `grep 'a|b' f` stays a single segment."""
        segments, cur, quote, esc = [], "", None, False
        for ch in cmd_str:
            if esc:
                cur += ch; esc = False; continue
            if ch == "\\" and quote != "'":
                cur += ch; esc = True; continue
            if quote:
                cur += ch
                if ch == quote: quote = None
                continue
            if ch in ("'", '"'):
                quote = ch; cur += ch; continue
            if ch == "|":
                segments.append(cur); cur = ""
            else:
                cur += ch
        segments.append(cur)
        return segments

    @staticmethod
    def _flag_hit(tokens, blocked):
        """True if any token matches a blocked flag, incl. the --opt=value form."""
        for t in tokens:
            for b in blocked:
                if t == b or t.startswith(b + "="):
                    return True
        return False

    @staticmethod
    def _plan_check(cmd_str):
        """Gate for Plan-mode run_command. Returns (ok, reason).
        Because _run_plan never invokes a shell, this allowlist plus the arg
        rules below ARE the security boundary."""
        if not cmd_str or not cmd_str.strip():
            return False, "empty command"
        if re.search(r"[\x00\r\n]", cmd_str):
            return False, "control characters (newline/CR/NUL) are not allowed"
        if re.search(r"\$\(|`|;|\|\||&&|>>|>|\{", cmd_str):
            return False, "shell construct not allowed in Plan mode"
        for segment in Tools._split_pipes(cmd_str):
            if not segment.strip():
                return False, "empty pipe segment"
            try:
                tokens = shlex.split(segment)
            except ValueError:
                return False, "unbalanced quotes in command"
            if not tokens:
                return False, "empty pipe segment"
            prog = os.path.basename(tokens[0])
            if prog not in Tools.PLAN_READONLY_CMDS:
                return False, "'%s' is not on the Plan-mode read-only allowlist" % prog
            if prog in Tools.PLAN_ARGS_BLOCKED and Tools._flag_hit(tokens[1:], Tools.PLAN_ARGS_BLOCKED[prog]):
                return False, "'%s' flag not allowed in Plan mode" % prog
            if prog == "git":
                idx = 1
                while idx < len(tokens) - 1 and tokens[idx] == "-C":
                    idx += 2
                if idx >= len(tokens) or tokens[idx] not in Tools.PLAN_GIT_RO:
                    return False, "git subcommand not allowed in Plan mode"
                if Tools._flag_hit(tokens[idx + 1:], Tools.GIT_MUTATING_ARGS):
                    return False, "git arguments would modify the repository"
            elif prog == "find":
                if any(t in Tools.PLAN_FIND_BLOCKED for t in tokens):
                    return False, "find flag would write files or execute commands"
        return True, ""

    @staticmethod
    def _plan_safe(cmd_str):
        return Tools._plan_check(cmd_str)[0]

    @staticmethod
    def _kill_procs(procs):
        for p in procs:
            try:
                os.killpg(p.pid, signal.SIGKILL)
            except OSError:
                try: p.kill()
                except Exception: pass

    @staticmethod
    def _run_plan(cmd_str, timeout=30, max_out=200000):
        """Execute an allowlisted read-only pipeline WITHOUT a shell.
        Caller must have passed _plan_check first. Output is read with a cap
        so e.g. `cat /dev/zero` cannot exhaust memory; each process gets its
        own session so a timeout/overflow kills the whole group."""
        try:
            segments = [[os.path.expanduser(t) for t in shlex.split(seg)]
                        for seg in Tools._split_pipes(cmd_str)]
        except ValueError:
            return "Error: invalid command syntax."

        procs, stderr_tmp, prev_out = [], None, None
        try:
            stderr_tmp = tempfile.TemporaryFile()
            for toks in segments:
                if not toks:
                    continue
                try:
                    p = subprocess.Popen(toks, stdin=prev_out, stdout=subprocess.PIPE,
                                         stderr=stderr_tmp, start_new_session=True)
                except Exception as e:
                    Tools._kill_procs(procs)
                    if prev_out is not None:
                        try: prev_out.close()
                        except Exception: pass
                    return "Error starting command %s: %s" % (toks[0], e)
                if prev_out is not None:
                    prev_out.close()
                procs.append(p)
                prev_out = p.stdout

            if not procs:
                return "Error: empty command."

            out_fd = procs[-1].stdout
            chunks, total = [], 0
            deadline, overflow, got_eof = time.monotonic() + timeout, False, False
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                r, _, _ = select.select([out_fd], [], [], min(remaining, 0.2))
                if not r:
                    continue
                try:
                    data = os.read(out_fd.fileno(), 65536)
                except OSError:
                    got_eof = True
                    break
                if not data:
                    got_eof = True
                    break
                chunks.append(data)
                total += len(data)
                if total >= max_out:
                    overflow = True
                    break

            timed_out = not got_eof and not overflow
            if overflow or timed_out:
                Tools._kill_procs(procs)
            for p in procs:
                try: p.wait(timeout=2)
                except Exception: pass

            out = b"".join(chunks).decode("utf-8", "replace")
            stderr_tmp.seek(0)
            err = stderr_tmp.read().decode("utf-8", "replace")
            if overflow:
                out += "\n…[output capped at %d chars]" % max_out
            elif timed_out:
                out += "\n…[command timed out after %ds]" % timeout
            else:
                codes = [p.returncode for p in procs if p.returncode not in (0, None)]
                if codes:
                    out += "\n[exit code: %d]" % codes[-1]
            return (out + ("\n" if out and err else "") + err).rstrip("\n")
        finally:
            for p in procs:
                try: p.stdout.close()
                except Exception: pass
            if stderr_tmp is not None:
                try: stderr_tmp.close()
                except Exception: pass

    @staticmethod
    def _run_command_desc(build_mode: bool):
        """Description sent to the model so it knows the EXACT Plan-mode rules up
        front and never proposes a command that would be blocked (avoids wasted
        turns thrashing on blocked commands). Built from the live allowlist."""
        if build_mode:
            return ("Run a shell command and return stdout/stderr. BUILD MODE: any command "
                    "may run after the user approves. Say what you intend, then call.")
        allowed = ", ".join(sorted(Tools.PLAN_READONLY_CMDS - {"git"}))
        git_ro = ", ".join(sorted(Tools.PLAN_GIT_RO))
        return ("Run a shell command and return stdout/stderr.\n"
                "PLAN MODE is read-only and runs WITHOUT a shell. ONLY these programs are "
                "permitted: " + allowed + "; git is limited to: " + git_ro + ". Pipes (|) work.\n"
                "These are REJECTED before running \u2014 do NOT propose them, reformulate instead: "
                "every interpreter (python/python3/node/perl/ruby/php/java/go/lua/awk/sed/sh/bash), "
                "redirects (> >>), command substitution ($() `backticks`), && ; ||, globs (* ? []), "
                "and any mutating command (rm mv cp touch mkdir chmod tee dd pip npm apt ...). "
                "If a task truly needs them, stop and ask the user to enable Build mode (/tools on).")

    @staticmethod
    def get_schemas(build_mode: bool):
        schemas = json.loads(json.dumps(Tools.TOOLS if build_mode else Tools.PLAN_TOOLS))
        desc = Tools._run_command_desc(build_mode)
        for t in schemas:
            if t["function"]["name"] == "run_command":
                t["function"]["description"] = desc
        return schemas

    @staticmethod
    def to_anthropic_schema(build_mode: bool):
        return [{"name": t["function"]["name"], "description": t["function"]["description"], "input_schema": t["function"]["parameters"]} for t in Tools.get_schemas(build_mode)]

    @staticmethod
    def _allow_private():
        return os.environ.get("AI_FETCH_ALLOW_PRIVATE", "").lower() in ("1", "true", "yes")

    @staticmethod
    def _is_private_host(host):
        """True for an IP literal in private/loopback/etc ranges, or localhost.
        DNS hostnames can't be fully checked cheaply (rebinding), so we only
        guard obvious literals -- the device is single-user and low-stakes."""
        host = (host or "").lower().strip()
        if not host:
            return False
        if host == "localhost" or host.endswith(".localhost"):
            return True
        try:
            ip = ipaddress.ip_address(host)
            return ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast
        except ValueError:
            return False

    @staticmethod
    def _html_to_text(s):
        """Crude HTML -> readable text: drop script/style/template, add line
        breaks for block elements, strip remaining tags, unescape entities."""
        s = re.sub(r"(?is)<(script|style|noscript|template)\b[^>]*>.*?</\1>", "", s)
        s = re.sub(r"(?i)<br\s*/?>", "\n", s)
        s = re.sub(r"(?i)<li\b[^>]*>", "\n- ", s)
        s = re.sub(r"(?i)<h[1-6]\b[^>]*>", "\n## ", s)
        s = re.sub(r"(?i)</(p|div|li|tr|td|th|h[1-6]|section|article|header|footer|ul|ol|table)>", "\n", s)
        s = re.sub(r"<[^>]+>", "", s)
        s = html.unescape(s)
        s = re.sub(r"[ \t]+", " ", s)
        s = re.sub(r"\n[ \t]+", "\n", s)
        s = re.sub(r"\n{3,}", "\n\n", s)
        return s.strip()

    @staticmethod
    def _fetch_url(url, timeout=10, max_bytes=500000):
        url = (url or "").strip()
        if not re.match(r"^https?://", url, re.I):
            return "Error: URL must start with http:// or https://"
        try:
            host = urllib.parse.urlparse(url).hostname or ""
        except Exception:
            host = ""
        if Tools._is_private_host(host) and not Tools._allow_private():
            return ("Error: refusing to fetch private/local address '%s' (SSRF guard). "
                    "Set env AI_FETCH_ALLOW_PRIVATE=1 to allow." % host)
        req = urllib.request.Request(url, headers={"User-Agent": "termux-ai/%s (+CLI)" % __version__})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                ctype = resp.headers.get("Content-Type", "").lower()
                data = resp.read(max_bytes + 1)
                final_url = resp.geturl()
        except urllib.error.HTTPError as e:
            return "HTTP %d %s for %s" % (e.code, e.reason, url)
        except urllib.error.URLError as e:
            return "Error: could not fetch %s (%s)" % (url, getattr(e, "reason", e))
        except Exception as e:
            return "Error: %s" % e
        truncated = len(data) > max_bytes
        if truncated:
            data = data[:max_bytes]
        text = data.decode("utf-8", "replace")
        looks_html = ("html" in ctype or text.lstrip()[:200].lower().startswith("<!doctype html")
                      or "<html" in text.lower()[:500])
        if looks_html:
            text = Tools._html_to_text(text)
        note = " (truncated at %d KB)" % (max_bytes // 1000) if truncated else ""
        return "Fetched %s%s\n\n%s" % (final_url, note, text.strip())

    @staticmethod
    def run(name, args, build_mode=False, max_result=10000):
        # Note: we intentionally do NOT memoize results. A previous cache caused
        # stale file contents to be served to the model within a session (C1).
        # Each call executes fresh; loop detection lives in chat_with_tools.
        result = Tools._run_impl(name, args, build_mode)
        if result is None:
            result = "Error: Tool returned no output."
        if len(result) > max_result: result = result[:max_result] + "\n…[truncated]"
        return result

    @staticmethod
    def _run_impl(name, args, build_mode=False):
        try:
            if name == "read_file":
                p = os.path.expanduser(args.get("path", ""))
                if not p: return "Error: Path is missing."
                if not os.path.exists(p): return f"Error: Not found at {p}"
                if os.path.isdir(p): return "Error: Is a directory"
                return FileReader.read(p)
            elif name == "write_file":
                if not build_mode: return "Error: Write access is disabled in Plan mode."
                p = os.path.expanduser(args.get("path", ""))
                if not p: return "Error: Path is missing."
                content = args.get("content", "")

                cwd = os.getcwd()
                # Resolve symlinks so a link inside cwd cannot escape it.
                try:
                    inside_cwd = os.path.commonpath([os.path.realpath(p), os.path.realpath(cwd)]) == os.path.realpath(cwd)
                except ValueError:
                    inside_cwd = False
                if not inside_cwd:
                    return f"Error: Cannot write files outside current working directory ({cwd})."

                Path(p).parent.mkdir(parents=True, exist_ok=True)
                Path(p).write_text(content)
                return f"Written to {p}"
            elif name == "list_files":
                p = os.path.expanduser(args.get("path", "."))
                return "\n".join(sorted(e for e in os.listdir(p) if not e.startswith(".")))
            elif name == "run_command":
                cmd_str = args.get("command", "")
                if not cmd_str: return "Error: Command is missing."
                if not build_mode:
                    ok, reason = Tools._plan_check(cmd_str)
                    if not ok:
                        allowed = ", ".join(sorted(Tools.PLAN_READONLY_CMDS - {"git"}))
                        return ("Error: Plan mode blocked this command: %s. Plan mode permits ONLY "
                                "these read-only programs (no shell): %s. Do NOT retry this or "
                                "similar (interpreters, redirects, &&/;/||, mutating commands are all "
                                "blocked). Reformulate using only the allowed list, or ask the user to "
                                "enable Build mode (/tools on)." % (reason, allowed))
                    return Tools._run_plan(cmd_str)
                # Build mode: full shell, always user-approved first.
                try:
                    p = subprocess.Popen(cmd_str, shell=True, stdout=subprocess.PIPE,
                                         stderr=subprocess.PIPE, text=True, start_new_session=True)
                    try:
                        out, err = p.communicate(timeout=30)
                    except subprocess.TimeoutExpired:
                        try: os.killpg(p.pid, signal.SIGKILL)
                        except OSError: pass
                        out, err = p.communicate()
                        return (out or "") + (err or "") + "\n…[command timed out after 30s]"
                    return (out or "") + (err or "")
                except Exception as e:
                    return f"Error executing command: {e}"
            elif name == "search_files":
                path = args.get("path", ".")
                r = subprocess.run(["grep", "-rn", "--", args.get("query", ""), path], capture_output=True, text=True, timeout=15)
                return "\n".join(r.stdout.splitlines()[:20]) or "No matches"
            elif name == "fetch_url":
                return Tools._fetch_url(args.get("url", ""))
            return "Unknown tool"
        except Exception as e: return f"Error: {e}"

