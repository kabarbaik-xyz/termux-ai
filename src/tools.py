# ══ termux_ai.tools ══ (fragment; merged by build.py)
class Tools:
    SAFE_TOOLS = {"read_file", "list_files", "search_files", "fetch_url", "web_search", "graphify"}
    # Dirs ignored by recursive list_files and by search_files, so dependency/VCS/
    # build noise (node_modules, .git, __pycache__, dist, ...) doesn't flood the
    # AI's context when it scans a local codebase. (AI can still read_file a
    # specific file inside one of these if it really needs to.)
    IGNORE_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", ".tox",
                   "dist", "build", ".next", ".nuxt", "target", ".pytest_cache",
                   ".mypy_cache", ".ruff_cache", ".idea", ".vscode", "coverage",
                   ".gradle", ".cache", ".terraform", ".eggs", ".sass-cache", "Pods"}

    TOOLS = [
        {"type": "function", "function": {"name": "read_file", "description": "Read file contents. Optional start/end are 1-based LINE numbers (inclusive) for reading a specific span of a large file; without them the first part of the file is returned.", "parameters": {"type": "object", "properties": {"path": {"type": "string"}, "start": {"type": "integer", "description": "1-based line to start reading from"}, "end": {"type": "integer", "description": "1-based line to read up to (inclusive)"}}, "required": ["path"]}}},
        {"type": "function", "function": {"name": "write_file", "description": "Write content to a file. Set append=true to ADD to an existing file instead of overwriting - use this to build LARGE files in sections so no single call exceeds the output token limit.", "parameters": {"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}, "append": {"type": "boolean", "default": False}}, "required": ["path", "content"]}}},
        {"type": "function", "function": {"name": "list_files", "description": "List files in a directory. Set recursive=true to map the whole tree (auto-skips dependency/VCS/build dirs like node_modules, .git, __pycache__, dist).", "parameters": {"type": "object", "properties": {"path": {"type": "string"}, "recursive": {"type": "boolean", "default": False}}, "required": ["path"]}}},
        {"type": "function", "function": {"name": "run_command", "description": "Run a shell command and return stdout/stderr. (The exact Plan-mode allowlist is provided at call time.)", "parameters": {"type": "object", "properties": {"command": {"type": "string"}, "timeout": {"type": "integer", "description": "Seconds to wait before killing the command (default 30, max 600). Set HIGHER for slow commands (npm install, builds, test suites) so they finish in ONE call instead of polling with sleep — each call is one agentic iteration, and polling wastes your step budget."}}, "required": ["command"]}}},
        {"type": "function", "function": {"name": "search_files", "description": "Search text in files (uses grep)", "parameters": {"type": "object", "properties": {"query": {"type": "string"}, "path": {"type": "string"}}, "required": ["query"]}}},
        {"type": "function", "function": {"name": "fetch_url", "description": "Fetch a web page via HTTP GET and return its text content (HTML is stripped to readable text; ~500 KB cap). Use this to READ or RESEARCH a website/URL -- prefer it over curl or run_command for any http(s) URL.", "parameters": {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]}}},
        {"type": "function", "function": {"name": "web_search", "description": "Search the web for up-to-date information (current events, weather, people, places, definitions, recent facts) and return the top results with titles, URLs, and snippets. Use this INSTEAD of guessing a URL for fetch_url when you don't know the exact page. Results come from Bing; Wikipedia is used as a fallback when Bing is unreachable.", "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}}},
        {"type": "function", "function": {"name": "clone_repo", "description": "Clone a public git repo (HTTPS only) into an isolated temp dir and return the local path, so you can read/list/search/edit its files locally. BUILD MODE only. depth defaults to 1 (shallow, fast); set 0 for full history.", "parameters": {"type": "object", "properties": {"url": {"type": "string"}, "depth": {"type": "integer", "default": 1}}, "required": ["url"]}}},
        {"type": "function", "function": {"name": "graphify", "description": "Scan a codebase directory and return a structured code graph: dependency graph (Mermaid), all function/class definitions, API endpoints, and data models. Call this FIRST to map the codebase structure before deep-diving into files. Zero dependencies, runs locally.", "parameters": {"type": "object", "properties": {"path": {"type": "string", "description": "Directory to scan (default: current dir)"}, "mode": {"type": "string", "enum": ["all", "deps", "calls", "api", "models"], "description": "all=everything, deps=import graph, calls=definitions, api=endpoints, models=data schemas"}}, "required": ["path"]}}},
    ]
    PLAN_TOOLS = [t for t in TOOLS if t["function"]["name"] not in ("write_file", "clone_repo")]
    
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
    def _run_command_desc(build_mode: bool, compact=False):
        """Description sent to the model so it knows the EXACT Plan-mode rules up
        front and never proposes a command that would be blocked (avoids wasted
        turns thrashing on blocked commands). Built from the live allowlist."""
        if build_mode:
            return ("Run a shell command and return stdout/stderr. BUILD MODE: any command "
                    "may run after the user approves. Say what you intend, then call. "
                    "For slow commands (npm install, builds, tests) set `timeout` (seconds, "
                    "max 600) so they finish in ONE call — do NOT background-and-poll with "
                    "sleep, each call is an iteration and polling wastes your step budget.")
        allowed = ", ".join(sorted(Tools.PLAN_READONLY_CMDS - {"git"}))
        git_ro = ", ".join(sorted(Tools.PLAN_GIT_RO))
        if compact:
            return ("Run a shell command (Plan mode: read-only, no shell). "
                    "ALLOWED: " + allowed + "; git: " + git_ro + ". Pipes (|) work. "
                    "REJECTED: interpreters (python/node/...), redirects > >>, $() backticks, "
                    "&& ; ||, globs * ?, mutating cmds (rm/cp/mkdir/chmod/...). "
                    "Enable Build mode (/tools) to run anything else.")
        return ("Run a shell command and return stdout/stderr.\n"
                "PLAN MODE is read-only and runs WITHOUT a shell. ONLY these programs are "
                "permitted: " + allowed + "; git is limited to: " + git_ro + ". Pipes (|) work.\n"
                "These are REJECTED before running \u2014 do NOT propose them, reformulate instead: "
                "every interpreter (python/python3/node/perl/ruby/php/java/go/lua/awk/sed/sh/bash), "
                "redirects (> >>), command substitution ($() `backticks`), && ; ||, globs (* ? []), "
                "and any mutating command (rm mv cp touch mkdir chmod tee dd pip npm apt ...). "
                "If a task truly needs them, stop and ask the user to enable Build mode (/tools on).")

    _COMPACT_DESC = {
        "read_file": "Read a file. start/end = 1-based line range (for paging large files).",
        "write_file": "Write a file. append=true to add to an existing file (build large files in parts).",
        "list_files": "List a directory. recursive=true for the full tree (skips node_modules/.git/build dirs).",
        "search_files": "Search text in files (grep).",
        "fetch_url": "Fetch a URL, return readable text (~500KB cap). Prefer over curl for URLs.",
        "web_search": "Search the web, return top results (titles, URLs, snippets). For up-to-date facts/news/weather.",
        "clone_repo": "Clone a public git repo to a temp dir. depth=0 for full history.",
        "graphify": "Code graph (deps, defs, API, models). Call first to map a codebase.",
        # run_command keeps its full description: the Plan-mode allowlist it
        # carries is security-relevant and must reach the model verbatim.
    }

    @staticmethod
    def get_schemas(build_mode, compact=False, micro=False):
        """Tool schemas for the request. Three levels:
        full     — long descriptions + parameter docs (cloud defaults)
        compact  — short per-tool descriptions, no parameter docs
        micro    — ONLY names + parameters (drop descriptions; keep the
                   run_command security allowlist). For slow LOCAL non-thinking
                   models the schema is re-tokenized every call, so cutting it
                   from ~614 -> ~300 tokens shrinks cold prefill seconds.
        Micro implies compact (no parameter descriptions)."""
        schemas = json.loads(json.dumps(Tools.TOOLS if build_mode else Tools.PLAN_TOOLS))
        desc = Tools._run_command_desc(build_mode, compact=True)
        for t in schemas:
            fn = t["function"]
            if fn["name"] == "run_command":
                fn["description"] = desc
            elif micro:
                fn.pop("description", None)
            elif compact and fn["name"] in Tools._COMPACT_DESC:
                fn["description"] = Tools._COMPACT_DESC[fn["name"]]
            if compact or micro:
                # Drop per-parameter descriptions: the names are self-
                # explanatory and they bloat every request's prompt (887 -> ~430
                # tokens), which a small local model re-evaluates each call.
                for p in (fn.get("parameters", {}).get("properties") or {}).values():
                    p.pop("description", None)
            if micro:
                prm = fn.get("parameters") or {}
                prm.pop("additionalProperties", None)
                if not (prm.get("required") or []):
                    prm.pop("required", None)
                if not prm.get("properties"):
                    fn.pop("parameters", None)
        return schemas

    @staticmethod
    def to_anthropic_schema(build_mode: bool):
        return [{"name": t["function"]["name"], "description": t["function"]["description"], "input_schema": t["function"]["parameters"]} for t in Tools.get_schemas(build_mode)]

    @staticmethod
    def _allow_private():
        return os.environ.get("AI_FETCH_ALLOW_PRIVATE", "").lower() in ("1", "true", "yes")

    @staticmethod
    def _ip_private(ip):
        """True if an IP address is private/loopback/etc. Honors NAT64
        (64:ff9b::/96, RFC 6052 well-known prefix): a NAT64-mapped address
        embeds the real IPv4 in its low 32 bits, so we classify THAT instead
        of the translation prefix (which Python flags as reserved) — otherwise
        legitimate public hosts are blocked on NAT64-only networks (common on
        Android without IPv6)."""
        try:
            ip = ipaddress.ip_address(ip)
        except ValueError:
            return False
        if ip.version == 6 and (int(ip) >> 96) == 0x64FF9B:
            return Tools._ip_private(ipaddress.ip_address(int(ip) & 0xFFFFFFFF))
        return (ip.is_private or ip.is_loopback or ip.is_link_local
                or ip.is_reserved or ip.is_multicast or ip.is_unspecified)

    @staticmethod
    def _is_private_host(host):
        """True for private/loopback/etc IPs or localhost. Also resolves DNS
        hostnames and checks resolved IPs to close the DNS-rebinding gap (V-01)."""
        host = (host or "").lower().strip()
        if not host:
            return False
        if host == "localhost" or host.endswith(".localhost"):
            return True
        if Tools._ip_private(host):
            return True
        try:
            import socket
            for _f, _t, _p, _c, sa in socket.getaddrinfo(host, None):
                if Tools._ip_private(sa[0]):
                    return True
        except Exception:
            pass
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
        headers = {"User-Agent": "termux-ai/%s (+CLI)" % __version__}
        if host == "api.github.com":
            tok = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
            if tok:
                headers["Authorization"] = "token " + tok
                headers["Accept"] = "application/vnd.github+json"
        req = urllib.request.Request(url, headers=headers)
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
            # Wikipedia pages carry ~500KB of sidebar/nav/footer junk around a
            # small article body; slice out the main content so the model gets
            # the article, not the menu (a 64s prefill on a phone otherwise).
            if "wikipedia.org" in host:
                text = Tools._wikipedia_main(text)
                text = Tools._html_to_text(text)
                text = Tools._wikipedia_clean(text)
            else:
                text = Tools._html_to_text(text)
        notes = []
        if truncated:
            notes.append("truncated at %d KB" % (max_bytes // 1000))
        text = text.strip()
        text_cap = 120000
        if len(text) > text_cap:
            text = text[:text_cap]
            notes.append("excerpt (first %d KB)" % (text_cap // 1000))
        note = " (%s)" % ", ".join(notes) if notes else ""
        return "Fetched %s%s\n\n%s" % (final_url, note, text)

    @staticmethod
    def _wikipedia_main(s):
        """Slice the article body out of a raw Wikipedia page: everything the
        reader cares about lives in the #mw-content-text div (the sidebar,
        'Jump to content', footer and interwiki columns are all outside it)."""
        m = re.search(r'(?is)<div[^>]*id=["\']mw-content-text["\'][^>]*>', s)
        if not m:
            return s
        rest = s[m.start():]
        e = re.search(r'(?is)<div[^>]*id=["\']catlinks["\']', rest)
        if e:
            rest = rest[:e.start()]
        return rest

    @staticmethod
    def _wikipedia_clean(s):
        """Drop the leftover template noise that survives tag-stripping on
        Wikipedia pages: unrendered wikitext ({{...}}) and Parsoid infobox
        JSON blobs ("wt": "..."), both of which are useless to the model."""
        s = re.sub(r"(?m)^.*\{\{.*$", "", s)          # unrendered wikitext templates
        s = re.sub(r"(?m)^.*\"wt\":\s*\".*$", "", s)  # Parsoid JSON blobs
        s = re.sub(r"\n{3,}", "\n\n", s)
        return s.strip()

    @staticmethod
    def _web_search(query, timeout=12, max_results=5):
        """Search the web and return the top results. Primary source: Bing's
        HTML results (no API key; result links are base64-wrapped and decoded).
        Fallback: Wikipedia's search API when Bing is unreachable."""
        q = (query or "").strip()
        if not q:
            return "Error: query is empty"
        qq = urllib.parse.quote(q)
        results = []
        try:
            req = urllib.request.Request(
                "https://www.bing.com/search?q=" + qq,
                headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                         "(KHTML, like Gecko) Chrome/120.0 Safari/537.36",
                         "Accept-Language": "en-US,en;q=0.9"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                body = r.read(1500000).decode("utf-8", "replace")
            for b in re.findall(r'(?is)<li class="b_algo[^"]*".*?</li>', body):
                m = re.search(r'(?is)<h2[^>]*>\s*<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>', b)
                if not m:
                    continue
                url = m.group(1)
                u = re.search(r'(?:[?&]|&amp;)u=a1([A-Za-z0-9+/=]+)', url)
                if u:
                    try:
                        real = base64.b64decode(u.group(1) + "=" * (-len(u.group(1)) % 4)) \
                            .decode("utf-8", "replace")
                        if real.startswith("http"):
                            url = real
                    except Exception:
                        pass
                title = re.sub(r"<[^>]+>", "", m.group(2)).strip()
                sn = re.search(r'(?is)<p[^>]*>(.*?)</p>', b)
                snippet = re.sub(r"<[^>]+>", "", sn.group(1)).strip() if sn else ""
                if url and title:
                    results.append((title, url, snippet))
                if len(results) >= max_results:
                    break
        except Exception:
            pass
        if not results:
            try:
                req = urllib.request.Request(
                    "https://en.wikipedia.org/w/api.php?action=query&list=search&srsearch="
                    + qq + "&format=json&srlimit=%d" % max_results,
                    headers={"User-Agent": "termux-ai/%s (+CLI)" % __version__})
                with urllib.request.urlopen(req, timeout=timeout) as r:
                    d = json.loads(r.read().decode("utf-8", "replace"))
                for it in (d.get("query") or {}).get("search") or []:
                    title = it.get("title", "")
                    url = "https://en.wikipedia.org/wiki/" + \
                        urllib.parse.quote(title.replace(" ", "_"))
                    snippet = re.sub(r"<[^>]+>", "", it.get("snippet", ""))
                    results.append((title, url, snippet))
            except Exception:
                pass
        if not results:
            return ("No web search results for '%s' (Bing/Wikipedia unreachable from here). "
                    "Try fetch_url with a known URL." % q)
        lines = ["Web search results for '%s':" % q]
        for i, (title, url, snippet) in enumerate(results, 1):
            lines.append("%d. %s\n   URL: %s" % (i, title, url))
            if snippet:
                lines.append("   %s" % snippet[:240])
        return "\n".join(lines)

    # ---- graphify: native code-graph scanner (zero deps, stdlib only) ----
    _G_EXTS = {".py", ".js", ".jsx", ".ts", ".tsx", ".go", ".rs", ".java", ".kt", ".sql"}
    _G_PAT = {
        ".py": {"defs": [(r"\bdef\s+(\w+)", "fn"), (r"\bclass\s+(\w+)", "class")],
                "imports": [r"from\s+([\w.]+)\s+import", r"\bimport\s+([\w.]+)"],
                "routes": [r"@(?:app|router|bp)\.(get|post|put|delete|patch)\(\s*['\"]([^'\"]+)", r"@(?:app|router|bp)\.route\(\s*['\"]([^'\"]+)"],
                "models": [r"class\s+(\w+).*?(?:Model|Schema|Base|Serializer)\b"]},
        ".js": {"defs": [(r"\bfunction\s+(\w+)", "fn"), (r"\bclass\s+(\w+)", "class"), (r"(?:const|let)\s+(\w+)\s*=\s*(?:async\s*)?\(", "arrow")],
                 "imports": [r"from\s+['\"]([^'\"]+)", r"require\(\s*['\"]([^'\"]+)"],
                 "routes": [r"\b(?:app|router)\.(get|post|put|delete|patch)\(\s*['\"]([^'\"]+)"],
                 "models": [r"(?:mongoose|sequelize)\.(?:model|Schema|define)\s*\(\s*['\"](\w+)"]},
        ".go": {"defs": [(r"\bfunc\s+(?:\([^)]+\)\s+)?(\w+)", "fn"), (r"\btype\s+(\w+)\s+struct", "struct")],
                "imports": [r'^\s*"([^"]+)"\s*$'],
                "routes": [r"\.(?:GET|POST|PUT|DELETE|PATCH|HandleFunc)\(\s*['\"]([^'\"]+)"],
                "models": [r"\btype\s+(\w+)\s+struct"]},
        ".rs": {"defs": [(r"\bfn\s+(\w+)", "fn"), (r"\bstruct\s+(\w+)", "struct"), (r"\benum\s+(\w+)", "enum"), (r"\btrait\s+(\w+)", "trait")],
                "imports": [r"\buse\s+(\S+)"],
                "routes": [r"\.route\(\s*['\"]([^'\"]+)"],
                "models": [r"\bstruct\s+(\w+)"]},
        ".java": {"defs": [(r"\b(?:public|private|protected)?\s*(?:static\s+)?(?:final\s+)?(?:class|interface|enum)\s+(\w+)", "class")],
                  "imports": [r"\bimport\s+(?:static\s+)?([\w.]+);"],
                  "routes": [r"@(?:Get|Post|Put|Delete|Patch)Mapping\(\s*(?:value\s*=\s*)?['\"]([^'\"]+)"],
                  "models": [r"@Entity\s+(?:public\s+)?class\s+(\w+)"]},
        ".kt": {"defs": [(r"\bfun\s+(\w+)", "fn"), (r"\b(?:data\s+)?class\s+(\w+)", "class")],
                "imports": [r"\bimport\s+([\w.]+)"],
                "routes": [], "models": []},
        ".sql": {"defs": [], "imports": [], "routes": [],
                 "models": [r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?[`\"]?(\w+)"]},
    }
    _G_PAT[".jsx"] = _G_PAT[".js"]
    _G_PAT[".tsx"] = {**_G_PAT[".js"], "defs": _G_PAT[".js"]["defs"] + [(r"\b(?:interface|type)\s+(\w+)", "type")]}
    _G_PAT[".ts"] = _G_PAT[".tsx"]

    @staticmethod
    def _graphify(path, mode="all"):
        """Scan a directory and return a structured code graph (Mermaid + tables).
        Zero external dependencies — pure os.walk + regex."""
        p = os.path.expanduser(path or ".")
        if not os.path.isdir(p): return f"Error: '{p}' is not a directory."
        defs, imports, routes, models = [], {}, [], []
        local_names = set()
        for root, dirs, fnames in os.walk(p):
            dirs[:] = sorted(d for d in dirs if d not in Tools.IGNORE_DIRS and not d.startswith("."))
            for fn in sorted(fnames):
                ext = os.path.splitext(fn)[1].lower()
                if ext in Tools._G_EXTS:
                    rel = os.path.relpath(os.path.join(root, fn), p)
                    local_names.add(os.path.splitext(fn)[0])
                    pat = Tools._G_PAT.get(ext)
                    if not pat: continue
                    try:
                        with open(os.path.join(root, fn), encoding="utf-8", errors="ignore") as fh:
                            for i, line in enumerate(fh, 1):
                                for rp, dt in pat.get("defs", []):
                                    for m in re.finditer(rp, line):
                                        defs.append((m.group(1), dt, rel, i))
                                for rp in pat.get("imports", []):
                                    for m in re.finditer(rp, line):
                                        imports.setdefault(rel, []).append(m.group(1))
                                for rp in pat.get("routes", []):
                                    for m in re.finditer(rp, line):
                                        g = m.groups()
                                        routes.append((g[0].upper() if len(g) > 1 else "?", g[-1], rel, i))
                                for rp in pat.get("models", []):
                                    for m in re.finditer(rp, line):
                                        models.append((m.group(1), rel))
                    except Exception:
                        continue
        out = [f"## Code Graph: {p}  ({len(defs)} defs, {len(routes)} routes, {len(models)} models)\n"]
        if mode in ("deps", "all"):
            edges = set()
            for src, mods in sorted(imports.items()):
                sb = os.path.splitext(os.path.basename(src))[0]
                for mod in mods:
                    mb = re.split(r"[./]", mod)[-1].strip("'\"")
                    if mb and mb in local_names and mb != sb:
                        edges.add((sb, mb))
            out.append(f"### Dependency Graph ({len(edges)} edges)")
            if edges:
                m = "```mermaid\ngraph TD\n"
                for a, b in sorted(edges)[:60]:
                    m += f"    {a} --> {b}\n"
                if len(edges) > 60: m += f"    %% ... {len(edges)-60} more\n"
                out.append(m + "```\n")
            else: out.append("(no local dependencies detected)\n")
        if mode in ("calls", "all") and defs:
            out.append(f"### Definitions ({len(defs)})\n| Name | Type | File:Line |\n|------|------|-----------|")
            for n, t, f, l in defs[:100]:
                out.append(f"| `{n}` | {t} | {f}:{l} |")
            if len(defs) > 100: out.append(f"| ... | *{len(defs)-100} more* | |")
            out.append("")
        if mode in ("api", "all") and routes:
            out.append(f"### API Endpoints ({len(routes)})\n| Method | Path | File:Line |\n|--------|------|-----------|")
            for method, path_, f, l in sorted(set(routes)):
                out.append(f"| {method} | `{path_}` | {f}:{l} |")
            out.append("")
        if mode in ("models", "all") and models:
            seen = set(); uniq = [(n, f) for n, f in models if n not in seen and not seen.add(n)]
            out.append(f"### Data Models ({len(uniq)})\n| Name | File |\n|------|------|")
            for n, f in uniq[:50]:
                out.append(f"| `{n}` | {f} |")
            out.append("")
        return "\n".join(out) if len(out) > 1 else "No source files found."

    @staticmethod
    def _clone_repo(url, depth=1, build_mode=False, timeout=120):
        """git clone a public HTTPS repo into an isolated temp dir and return
        the path. Build-mode only (writes to disk + runs git). Shallow by
        default (depth 1); depth 0 = full history."""
        if not build_mode:
            return "Error: clone_repo requires Build mode (/tools on)."
        url = (url or "").strip()
        if not url:
            return "Error: url is missing."
        # HTTPS only: blocks ssh://, git@host:, file:// (info leak / code exec).
        if not re.match(r"^https://", url, re.I):
            return "Error: clone_repo only supports https:// URLs (ssh/git@/file are blocked)."
        try:
            depth = int(depth)
        except (TypeError, ValueError):
            depth = 1
        argv = ["git", "clone"]
        if depth and depth > 0:
            argv += ["--depth", str(depth)]
        target = tempfile.mkdtemp(prefix="ai_clone_")
        import atexit; atexit.register(lambda t=target: shutil.rmtree(t, ignore_errors=True))  # V-06
        argv += [url, target]
        try:
            p = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                 text=True, start_new_session=True)
            try:
                out, err = p.communicate(timeout=timeout)
            except subprocess.TimeoutExpired:
                try: os.killpg(os.getpgid(p.pid), signal.SIGKILL)
                except OSError: pass
                p.communicate()
                shutil.rmtree(target, ignore_errors=True)
                return "Error: git clone timed out after %ds (repo too large?)." % timeout
            if p.returncode != 0:
                shutil.rmtree(target, ignore_errors=True)
                return "Error cloning: " + (err or out or "unknown error").strip()[:500]
        except Exception as e:
            shutil.rmtree(target, ignore_errors=True)
            return "Error: %s" % e
        try:
            files = sorted(os.listdir(target))
        except Exception:
            files = []
        shown = files[:30]
        return ("Cloned %s to:\n  %s\n%d top-level entries (showing %d):\n  %s"
                % (url, target, len(files), len(shown), "\n  ".join(shown)))

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
                # V-03: deny known sensitive paths to prevent credential exfiltration
                rp = os.path.realpath(p).lower()
                _sensitive = (".ssh/", ".aws/", ".env", ".git/credentials", ".netrc",
                              ".gnupg/", "id_rsa", "id_ecdsa", "id_ed25519",
                              ".docker/config", ".kube/config", ".npmrc")
                if any(s in rp for s in _sensitive):
                    return "Error: Access denied — this path may contain secrets (SSH keys, credentials, config). Use run_command if you genuinely need it and have user approval."
                if not os.path.exists(p): return f"Error: Not found at {p}"
                if os.path.isdir(p): return "Error: Is a directory"
                return FileReader.read(p, start_line=args.get("start"), end_line=args.get("end"))
            elif name == "write_file":
                if not build_mode: return "Error: Write access is disabled in Plan mode."
                p = os.path.expanduser(args.get("path", ""))
                if not p: return "Error: Path is missing."
                content = args.get("content", "")
                append = bool(args.get("append", False))

                cwd = os.getcwd()
                # Resolve symlinks so a link inside cwd cannot escape it.
                try:
                    inside_cwd = os.path.commonpath([os.path.realpath(p), os.path.realpath(cwd)]) == os.path.realpath(cwd)
                except ValueError:
                    inside_cwd = False
                if not inside_cwd:
                    return f"Error: Cannot write files outside current working directory ({cwd})."

                Path(p).parent.mkdir(parents=True, exist_ok=True)
                if append:
                    with open(p, "a", encoding="utf-8") as _f: _f.write(content)
                    return f"Appended {len(content)} chars to {p}"
                Path(p).write_text(content)
                return f"Written to {p}"
            elif name == "list_files":
                p = os.path.expanduser(args.get("path", "."))
                if not args.get("recursive", False):
                    return "\n".join(sorted(e for e in os.listdir(p) if not e.startswith(".")))
                entries = []
                for root, dirs, files in os.walk(p):
                    dirs[:] = sorted(d for d in dirs if d not in Tools.IGNORE_DIRS and not d.startswith("."))
                    for f in sorted(files):
                        if f.startswith("."): continue
                        entries.append(os.path.relpath(os.path.join(root, f), p))
                        if len(entries) >= 500:
                            return "\n".join(entries) + "\n...[tree truncated at 500 entries]"
                return "\n".join(entries) or "(empty)"
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
                    return Tools._run_plan(cmd_str, timeout=min(int(args.get("timeout") or 30), 120))
                # Build mode: full shell, always user-approved first. The model can
                # raise the per-call timeout for slow commands (npm install, builds,
                # tests) so they finish in ONE call instead of polling with sleep
                # (each poll burns an agentic iteration -> runaway-loop stop).
                timeout = max(1, min(int(args.get("timeout") or 30), 600))
                try:
                    p = subprocess.Popen(cmd_str, shell=True, stdout=subprocess.PIPE,
                                         stderr=subprocess.PIPE, text=True, start_new_session=True)
                    try:
                        out, err = p.communicate(timeout=timeout)
                    except subprocess.TimeoutExpired:
                        # Graceful SIGTERM first, then SIGKILL: a hard kill
                        # mid-write corrupts state (e.g. npm reify leaves a
                        # half-installed node_modules).
                        for sig, wait in ((signal.SIGTERM, 5), (signal.SIGKILL, 3)):
                            try: os.killpg(p.pid, sig)
                            except OSError: pass
                            try:
                                p.wait(timeout=wait); break
                            except subprocess.TimeoutExpired:
                                continue
                        out, err = p.communicate()
                        return (out or "") + (err or "") + f"\n…[command timed out after {timeout}s]"
                    return (out or "") + (err or "")
                except Exception as e:
                    return f"Error executing command: {e}"
            elif name == "search_files":
                path = args.get("path", ".")
                cmd = ["grep", "-rn"]
                for d in Tools.IGNORE_DIRS:
                    cmd += ["--exclude-dir", d]
                cmd += ["--", args.get("query", ""), path]
                r = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
                return "\n".join(r.stdout.splitlines()[:20]) or "No matches"
            elif name == "fetch_url":
                return Tools._fetch_url(args.get("url", ""))
            elif name == "web_search":
                return Tools._web_search(args.get("query", ""))
            elif name == "clone_repo":
                return Tools._clone_repo(args.get("url", ""), args.get("depth", 1), build_mode)
            elif name == "graphify":
                return Tools._graphify(args.get("path", "."), args.get("mode", "all"))
            return "Unknown tool"
        except Exception as e: return f"Error: {e}"

