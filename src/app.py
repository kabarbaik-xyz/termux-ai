# ══ termux_ai.app ══ (fragment; merged by build.py)
def _dbg_exc(e):
    """Print a full traceback when AI_DEBUG is set; otherwise stay quiet (the
    caller still shows a one-line error). Set AI_DEBUG=1 to debug crashes."""
    if os.environ.get("AI_DEBUG"):
        import traceback
        traceback.print_exc()


class App:
    COMMANDS = ["/new", "/continue", "/show", "/history", "/load", "/rename", "/delete", "/save", "/sessions", "/session", "/unsave", "/backup", "/regen", "/retry", "/export", "/import", "/prune", "/compact", "/search", "/undo", "/diff", "/cost", "/setup", "/update", "/backends", "/backend", "/model", "/models", "/profile", "/system", "/config", "/tools", "/strategy", "/think", "/skill", "/multi", "/tokens", "/status", "/copy", "/paste", "/speak", "/share", "/server", "/expand", "/fold", "/graphify", "/process", "/context", "/bench", "/clear", "/help", "/exit"]

    def __init__(self):
        self.cfg = Config()
        self.db = Database()
        atexit.register(self.db.close)
        try: self.backend = get_backend(self.cfg)
        except Exception as e: print(f"{C.RED}Backend error: {e}{C.RESET}"); self.backend = None
        self.cid = None
        self.last_reply = ""
        self.last_user_msg = ""
        self.multi_line = self.cfg.get("multi_line", False)
        self.skills = Skills(CONFIG_DIR / "skills")
        self.active_session_skills = []  # [(name, body)] toggled on via /skill <session>
        # Auto-seed: silently copy any bundled example skills missing from the
        # user's dir, so new skills from an /update appear after restart with
        # zero manual steps (no /skill seed needed).
        self.skills.ensure_dir()
        self._seeded = self.skills.seed()
        self._validate_config()
        self.setup_rl()
        self.spinner = None
        self._auto_approve_all = False
        self._auto_continue = False
        self.quiet = not IS_TTY  # suppress UI when stdout is piped (one-shot mode)
        self._errored = False  # set when a request fails (for one-shot exit codes)
        self._pending_checkpoint = None  # in-flight msgs snapshot when a turn is interrupted mid-stream
        self.last_process = []           # step-by-step log of the last turn (for /process)
        self._step_count = 0             # tool steps in the current turn
        self._ctx_cache = None           # ((path, mtime), body) for CONTEXT.md project memory
        self._ws_backfilled = False     # one-time legacy workspace backfill
        self._sess_usage = {"in": 0, "out": 0, "req": 0}   # live process counters (status line)
        self._resume_mode = "auto"   # auto|continue|new|load (set by CLI flags)
        self._resume_arg = None
        # Pre-load the local model in the background at startup so the first
        # real prompt doesn't pay a ~30s cold load+prefill (config: ollama_warm).
        if (self.backend and not self.quiet and self.cfg.get("ollama_warm", True)
                and getattr(self.backend, "is_ollama", False)):
            try:
                # SAME system prompt the first real turn will send (persona +
                # CONTEXT.md + gather workflow) so the KV-cache prime actually
                # hits -- an identical prefix is required or the prime is wasted.
                _sysp = self._assemble_system_prompt()
                _tools = None
                if self.cfg.get("tools_enabled", False):
                    _mode = self.backend._schema_mode()
                    _tools = Tools.get_schemas(True, compact=_mode != "full", micro=_mode == "micro")
                threading.Thread(target=self.backend._warm, args=(_sysp, _tools), daemon=True).start()
            except Exception:
                pass

    def _validate_config(self):
        name, prof = self.cfg.active_profile()
        if not prof:
            if IS_TTY and sys.stdin.isatty():
                self.warn(f"Backend '{name}' is not configured.")
                self._run_setup("")
            else:
                self.warn(f"Backend '{name}' is not configured. Run 'ai' interactively to set up.")
            return
        base = prof.get("base_url", "")
        if not base.startswith("http"): self.warn(f"Backend '{name}' URL looks invalid: {base}")
        if "localhost" not in base and "127.0.0.1" not in base and not prof.get("api_key"):
            self.warn(f"Backend '{name}' is remote but has no API key. Run /setup")
        # Low-RAM heads-up for local Ollama: a big model + small context budget
        # is the #1 cause of the Android OOM killer silently killing Ollama.
        if ("localhost" in base or "127.0.0.1" in base) and not getattr(self, "quiet", False):
            free = _free_ram_gb()
            if free is not None and free < 2.0:
                if IS_TERMUX:
                    self.warn(f"Only {free:.1f} GB RAM free. A large local model may get killed by Android."
                              f" Try a smaller model or /config set num_ctx 2048.")
                else:
                    self.warn(f"Only {free:.1f} GB RAM free. A large local model may get swapped or killed."
                              f" Try a smaller model or /config set num_ctx 2048.")
        # One-time migration hint: max_tokens is GLOBAL (cloud + Anthropic read
        # it too). Earlier /models advice suggested lowering it for slow local
        # models -- which silently capped cloud replies. If a user did that and
        # has a cloud backend, point them at the local-only ollama_max_tokens.
        # (Shown once via a config flag; non-destructive -- we never override a
        # user-set value, since it's indistinguishable from an intentional one.)
        if not self.cfg.get("_hint_ollama_mt") and self.cfg.get("max_tokens", 8192) < 8192 \
                and not getattr(self, "quiet", False):
            has_cloud = any("localhost" not in (b.get("base_url") or "") and
                            "127.0.0.1" not in (b.get("base_url") or "")
                            for b in self.cfg.get("backends", {}).values())
            if has_cloud:
                self.warn(f"max_tokens is {self.cfg.get('max_tokens')} \u2014 this ALSO caps cloud backends "
                          f"(GPT/Claude). If you lowered it for a local model, restore cloud with "
                          f"{C.CYAN}/config set max_tokens 8192{C.RESET} and cap local separately with "
                          f"{C.CYAN}/config set ollama_max_tokens 2048{C.RESET}.")
            self.cfg.set("_hint_ollama_mt", True)

    def _get_ollama_models(self):
        try:
            r = urllib.request.urlopen("http://localhost:11434/api/tags", timeout=2)
            data = json.loads(r.read().decode("utf-8"))
            return [m["name"] for m in data.get("models", [])]
        except Exception: return []

    def _warn_plaintext_key(self, name, key):
        """H-5 / V-04: warn when a real API key is persisted to config.json
        (0o600 but plaintext) instead of an environment variable."""
        if not key or not isinstance(key, str):
            return
        if key.strip().lower() in ("ollama", "placeholder", "none"):
            return  # local placeholder, not a secret
        env = "ANTHROPIC_API_KEY" if "anthropic" in (name or "").lower() else "TERMUX_AI_API_KEY"
        self.warn(f"Storing API key for '{name}' in config.json (plaintext, 0o600). "
                  f"Consider setting the {env} environment variable instead and leaving the profile key empty.")

    def _run_setup(self, arg):
        print(f"\n{C.BOLD}{C.CYAN}=== Termux AI Setup Wizard ==={C.RESET}")
        print("Choose a backend to configure:")
        print("  1) Ollama (Local)")
        print("  2) OpenAI / Custom (OpenAI-compatible)")
        print("  3) Anthropic (Claude)")
        choice = input("Enter choice [1]: ").strip() or "1"

        if choice == "1":
            models = self._get_ollama_models()
            if models:
                print(f"\n{C.GREEN}Detected installed Ollama models:{C.RESET}")
                for i, m in enumerate(models, 1): print(f"  {i}) {m}")
                m_idx = input(f"Choose model [1]: ").strip() or "1"
                try: model = models[int(m_idx)-1]
                except Exception: model = "llama3.2"
            else:
                model = input("Enter model name (e.g., llama3.2): ").strip() or "llama3.2"
            self.cfg.set_path("backends.ollama", {"base_url": "http://localhost:11434/v1", "model": model, "api_key": "ollama"})
            self.cfg.set("backend", "ollama")
            self.info("Ollama configured!")

        elif choice == "2":
            name = input("Enter profile name [openai]: ").strip() or "openai"
            base = input("Enter Base URL [https://api.openai.com/v1]: ").strip() or "https://api.openai.com/v1"
            model = input("Enter Model ID [gpt-4o-mini]: ").strip() or "gpt-4o-mini"
            key = input("Enter API Key: ").strip()
            self.cfg.set_path(f"backends.{name}", {"base_url": base, "model": model, "api_key": key})
            self.cfg.set("backend", name)
            self._warn_plaintext_key(name, key)
            self.info(f"Profile '{name}' configured!")

        elif choice == "3":
            key = input("Enter Anthropic API Key: ").strip()
            model = input("Enter Model ID [claude-3-5-sonnet-20241022]: ").strip() or "claude-3-5-sonnet-20241022"
            self.cfg.set_path("backends.anthropic", {"base_url": "https://api.anthropic.com/v1", "model": model, "api_key": key})
            self.cfg.set("backend", "anthropic")
            self._warn_plaintext_key("anthropic", key)
            self.info("Anthropic configured!")
        else:
            self.warn(f"Invalid choice '{choice}'. Setup cancelled.")
            return

        try: self.backend = get_backend(self.cfg)
        except Exception as e: self.err(str(e))

    @staticmethod
    def _ver_tuple(v):
        parts = []
        for seg in (v or "").split("."):
            try: parts.append(int(seg))
            except ValueError:
                parts.append(sum(int(c) for c in seg if c.isdigit()) or 0)
        return tuple(parts + [0, 0, 0])[:3]

    def _self_update(self):
        import urllib.request
        url = "https://raw.githubusercontent.com/kabarbaik-xyz/termux-ai/main/ai"
        self.info("Checking for updates...")
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=10) as r:
                new_code = r.read().decode('utf-8')

            m = re.search(r'__version__\s*=\s*"([^"]+)"', new_code)
            if not m or len(new_code) < 10000:
                self.err("Downloaded file looks invalid; update aborted.")
                return
            remote = m.group(1)

            current_file = Path(__file__).resolve()
            try:
                old_code = current_file.read_text(encoding='utf-8')
            except OSError:
                old_code = ""
            local = __version__
            self.info(f"local v{local} \u2192 remote v{remote}")

            if new_code == old_code:
                self.info(f"Already up to date (v{local}).")
                self.info("Run /status to see what\u2019s installed and configured.")
                return

            # Never silently downgrade: if the remote is an older version,
            # something is out of sync -- warn instead of regressing this build.
            if self._ver_tuple(local) > self._ver_tuple(remote):
                self.warn(f"Remote v{remote} is OLDER than this build (v{local}); not downgrading.")
                self.warn("Your local build is newer than GitHub. Push your commits (git push) if you intended to publish them.")
                return

            backup = current_file.with_suffix('.bak')
            shutil.copy2(current_file, backup)
            try:
                current_file.write_text(new_code, encoding='utf-8')
                os.chmod(current_file, 0o755)
            except PermissionError:
                self.err(f"Can't write {current_file} (installed system-wide). "
                         "Get the latest version via install.sh or your package manager.")
                return
            self.success(f"Updated to v{remote}! Backup saved to {backup.name}. Please restart.")
        except Exception as e:
            self.err(f"Update failed: {e}")

    def _completion_vocab(self, cmd):
        """Second-level completion vocabulary for a command's argument."""
        if cmd in self.TOGGLES or cmd in ("/process",):
            if cmd == "/process":
                return ["on", "off", "auto"]
            return ["on", "off"]
        if cmd in ("/skill", "/context"):
            try:
                return [n for n, _ in self.skills.list()][:30]
            except Exception:
                return []
        if cmd == "/model":
            models = self._get_ollama_models()
            return models[:20] if models else []
        if cmd in ("/backend", "/backends"):
            return list((self.cfg.get("backends") or {}).keys())
        if cmd == "/load":
            try:
                return [str(r["id"]) for r in self.db.list_convs(limit=15)]
            except Exception:
                return []
        if cmd == "/session":
            return ["off"]
        return []

    def setup_rl(self):
        if HAVE_READLINE:
            try:
                HIST_FILE.touch(exist_ok=True)
                readline.read_history_file(str(HIST_FILE))
                readline.set_history_length(1000)
                
                def completer(text, state):
                    line = readline.get_line_buffer()
                    stripped = line.lstrip()
                    # Second-level completion: after a command word, complete
                    # its argument vocabulary instead of more commands.
                    if stripped.startswith("/") and " " in stripped:
                        cmd, _, arg = stripped.partition(" ")
                        cmd = cmd.lower().rstrip(".,;:!?")
                        vocab = self._completion_vocab(cmd)
                        if vocab:
                            cands = [c for c in vocab if c.startswith(arg)]
                            cands = [c + " " for c in cands]
                            if state < len(cands):
                                return cands[state]
                            return None
                    cmds = [c for c in self.COMMANDS if c.startswith(text)]
                    if state < len(cmds):
                        return cmds[state]
                    return None
                readline.set_completer(completer)
                readline.set_completer_delims(' \t\n')
                readline.parse_and_bind("tab: complete")
                # Ctrl+T flips Build/Plan instantly (VolDown+T on Termux).
                # Default transpose-chars is dead weight in a chat prompt; the
                # mode is visible in the prompt (Phase A) so the flip is obvious.
                readline.parse_and_bind('"\\C-t": "\\C-a/tools\\C-m"')
            except Exception: pass
            # V-07: secure history file permissions after readline writes
            import atexit
            atexit.register(lambda: _secure_file(HIST_FILE))

    def info(self, msg): print(f"{C.CYAN}[i] {msg}{C.RESET}")
    def warn(self, msg): print(f"{C.YELLOW}[!] {msg}{C.RESET}")
    def err(self, msg): print(f"{C.RED}[x] {msg}{C.RESET}")
    def success(self, msg): print(f"{C.GREEN}[✓] {msg}{C.RESET}")

    def print_startup_status(self):
        print(f"{C.BOLD}{C.CYAN}Termux AI v{__version__}{C.RESET}")
        if not self.backend:
            self.warn("Run /setup to configure a backend.")
            return
            
        name, prof = self.cfg.active_profile()
        model = prof.get("model", "N/A") if prof else "N/A"
        tools = "Build" if self.cfg.get("tools_enabled") else "Plan"
        total_toks = self.db.get_total_tokens()
        conv_toks = self.db.get_conv_tokens(self.cid) if self.cid else 0
        
        print(f"{C.DIM}----------------------------------------------------------{C.RESET}")
        print(f" {C.BOLD}Backend{C.RESET} : {C.GREEN}{name}{C.RESET}")
        print(f" {C.BOLD}Model{C.RESET}   : {C.GREEN}{model}{C.RESET}")
        print(f" {C.BOLD}Tools{C.RESET}   : {tools} Mode")
        print(f" {C.BOLD}Tokens{C.RESET}  : {conv_toks} (current) / {total_toks} (total)")
        ctx_win = int(self.cfg.get("context_window", 32000))
        print(f" {C.BOLD}Window{C.RESET} : {ctx_win // 1000}k context (trim tool results at {int(self.cfg.get('iteration_history_budget', 30000)) // 1000}k)")
        if not IS_TTY: self.warn("Output is piped, UI disabled.")
        if getattr(self, "_seeded", None):
            print(f" {C.DIM}New skills: {', '.join(self._seeded)} \u2014 /skill to list, /skill <name> to activate{C.RESET}")
        print(f"{C.DIM}----------------------------------------------------------{C.RESET}")

    def print_help(self):
        print(f"\n{C.BOLD}{C.CYAN}Termux AI Help{C.RESET}")
        print(f"{C.DIM}Version: {__version__} · Ctrl+T flip Build/Plan · Tab complete · ↑ history{C.RESET}\n")

        daily = [
            ("/n /new", "New chat"), ("/h /history", "List chats"), ("/l /load <id|name>", "Load chat"),
            ("/p /paste", "Smart paste+send"), ("/t /tools", "Flip Build/Plan (on|off)"),
            ("/sk /skill", "Run a skill (Tab lists)"), ("/m /model <n>", "Switch model"),
            ("/b /backend <n>", "Switch backend"), ("/r /retry", "Retry last answer"), ("/d /diff", "Git changes made"),
        ]
        manage = [
            ("/sessions /session", "List / tag sessions (ai -S <n>)"), ("/rename <t>", "Rename (auto = AI title)"),
            ("/search <q>", "Search chats"), ("/context", "Project memory (CONTEXT.md)"),
            ("/status", "Engine + backend status"), ("/bench", "Time the active backend"), ("/config", "View/set config"),
            ("/setup /update", "Configure / self-update"), ("/models /profile", "Models & profiles"),
        ]
        more = [
            ("/save /unsave /delete /prune /export /import /backup", "Session admin"),
            ("/undo /regen /compact /tokens /cost", "Chat admin"),
            ("/process [on|off|auto]", "Tool-step display"), ("/strategy /think /multi /fold", "Toggles (on|off)"),
            ("/copy /speak /share", "Mobile: clipboard/TTS/share"), ("/expand", "Long replies in less"),
            ("/graphify /server /system", "Code graph · ollama server · prompt"), ("/clear /exit", "Clear · quit"),
        ]
        for title, rows, hint in (("Daily (aliases included)", daily, None),
                                  ("Manage", manage, None),
                                  ("More", more, "every command still works; /last and /quit are undocumented aliases")):
            print(f"{C.BOLD}{C.MAGENTA}{title}{C.RESET}")
            for cmd, desc in rows:
                print(f"  {C.CYAN}{cmd.ljust(38)}{C.RESET} {desc}")
            if hint:
                print(f"  {C.DIM}{hint}{C.RESET}")
            print()

    def _attach_files(self, text):
        if not self.cfg.get("attach_files", True): return text
        # Match explicit path references: @path, ./path, ../path, ~/path
        pattern = re.compile(r'(@[^\s@]+|\.\./[^\s]+|\./[^\s]+|~/[^\s]+)')
        def replacer(match):
            token = match.group(1)
            raw = token[1:] if token.startswith("@") else token
            path = os.path.expanduser(raw.rstrip(".,;:)]"))
            if not path or not os.path.exists(path):
                return token
            if os.path.isdir(path):
                att = self._scan_directory(path)
                return att if att else token
            content = FileReader.read(path, self.cfg.get("max_file_chars", 20000))
            if content and not content.startswith("[Error"):
                ext = os.path.splitext(path)[1].lstrip('.')
                return f"\n\n--- File: {path} ---\n```{ext}\n{content}\n```\n--- End File ---\n"
            return token
        return pattern.sub(replacer, text)

    def _scan_directory(self, path):
        """Attach all source files under a directory (bounded)."""
        max_files = self.cfg.get("max_attach_files", 20)
        budget = self.cfg.get("max_file_chars", 20000)
        skip_dirs = {".git", "node_modules", "__pycache__", "venv", ".venv", ".idea", "dist", "build"}
        chunks, n, total = [], 0, 0
        for root, dirs, files in os.walk(path):
            dirs[:] = sorted(d for d in dirs if d not in skip_dirs and not d.startswith("."))
            for f in sorted(files):
                ext = os.path.splitext(f)[1].lower()
                if ext not in FileReader.TEXT_EXTS:
                    continue
                fp = os.path.join(root, f)
                if not os.path.isfile(fp):
                    continue
                content = FileReader.read(fp, min(4000, budget))
                if not content or content.startswith("[Error"):
                    continue
                rel = os.path.relpath(fp, path)
                chunks.append(f"--- File: {rel} ---\n```{ext.lstrip('.')}\n{content}\n```\n--- End File ---\n")
                n += 1
                total += len(content)
                if n >= max_files or total >= budget:
                    break
            if n >= max_files or total >= budget:
                break
        if not chunks:
            return None
        return f"\n\n--- Directory: {path} ({n} file(s)) ---\n" + "\n".join(chunks) + "--- End Directory ---\n"

    def _confirm_batch(self, calls):
        # git read-only views are auto-approved; its mutations (stage/commit/
        # unstage/checkout_file) go through the normal approval like write_file.
        def _safe(c):
            if c["name"] in Tools.SAFE_TOOLS:
                if c["name"] == "git":
                    return c.get("args", {}).get("action") in ("status", "diff", "log", "show")
                return True
            return False
        if all(_safe(c) for c in calls):
            return True

        if self.quiet:
            # Non-interactive (piped output): cannot prompt, so decline any
            # mutating action. Read-only tools above already auto-approve.
            return False
        if self._auto_approve_all:
            return True
        
        if self.spinner: self.spinner.stop(); self.spinner = None  # backend calls this before the event that stops the spinner
        print(f"\n{C.YELLOW}Approval needed for {len(calls)} action(s):{C.RESET}")
        for c in calls:
            args_str = json.dumps(c['args'])
            if len(args_str) > 100: args_str = args_str[:100] + "..."
            print(f"  • {C.BOLD}{c['name']}{C.RESET}: {args_str}")
        
        print(f"\n{C.DIM}[y] Yes  [a] Yes to all remaining  [n] No{C.RESET}")
        choice = input("> ").strip().lower()
        if choice == 'a':
            self._auto_approve_all = True
            return True
        return choice in ('y', '')

    def _continue_fn(self, iters, calls):
        if self.quiet:
            return True  # non-interactive one-shot: keep going (bounded by max_iterations)
        if self._auto_continue:
            return True  # user already chose "don't ask again" for this task
        if self.spinner: self.spinner.stop(); self.spinner = None  # stop before prompting
        print(f"\n{C.YELLOW}\u23f1 long task \u00b7 {iters} iterations, {calls} tool calls{C.RESET}")
        print(f"{C.DIM}[y] keep going  [a] keep going, don't ask again this task  [n] stop{C.RESET}")
        try:
            choice = input("> ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            return False
        if choice == "a":
            self._auto_continue = True
            return True
        return choice in ("y", "")

    def _spinner_msg(self):
        """Label the wait spinner honestly. 'prefilling' = the model is still
        chewing the prompt (the real "stuck" wait on slow local hardware);
        'generating' = it started emitting tokens. Falls back to 'working'."""
        if self.cfg.get("extended_thinking", False):
            return "thinking"
        return "prefilling context…"

    def _start_spinner(self):
        if self.quiet:
            self.spinner = None
            return
        self.spinner = Spinner(self._spinner_msg())
        self.spinner.start()

    def _render_notice(self, event):
        """One quiet place for loop-status rendering (pi-style):
          info  -> dim one-liner (routine: compaction, retry, self-heal, resume)
          warn  -> yellow (truncation, declined)
          error -> red + indented hint line (fatal stops)
        Legacy string notices render as info. Never blank-line splatters."""
        text = (event.get("text") or event.get("content") or "").strip()
        if not text:
            return
        level = event.get("level") or ("error" if event.get("fatal") else "info")
        icon = event.get("icon")
        line = f"{icon} {text}" if icon else text
        if level == "error":
            print(f"{C.RED}{line}{C.RESET}")
            hint = event.get("hint")
            if hint:
                print(f"{C.DIM}  {hint}{C.RESET}")
        elif level == "warn":
            print(f"{C.YELLOW}{line}{C.RESET}")
        else:
            print(f"{C.DIM}{line}{C.RESET}")

    def _stream_tool_chat(self, msgs):
        self.spinner = None
        self._auto_continue = False  # reset per task: re-confirm long-task continuation each turn
        self._start_spinner()
        fmt = None if self.quiet else MarkdownFormatter(fold=self.cfg.get("fold_long_blocks", True), fold_head=self.cfg.get("fold_head", 8))
        current_block = ""  # current text run; resets on each tool -> only the LAST run (the answer) is returned
        did_tools = False   # once any tool runs, later text is inter-step reasoning
        buf = []            # text buffered after the first tool, awaiting dim/normal render

        # Compact process mode: suppress tool-call chatter, show clean summary.
        mode = self.cfg.get("compact_process", "on") if not self.quiet else "off"
        threshold = max(1, int(self.cfg.get("compact_threshold", 4)))
        self._step_count = 0
        self.last_process = []

        def _tool_summary(name, args):
            """One-line summary of a tool call for compact display."""
            a = args or {}
            if name == "read_file":
                return f"read {os.path.basename(a.get('path', '?'))}"
            if name == "write_file":
                return f"write {os.path.basename(a.get('path', '?'))}"
            if name == "list_files":
                return f"list {a.get('path', '.')}"
            if name == "search_files":
                return f"search \"{(a.get('query', ''))[:30]}\""
            if name == "run_command":
                return f"run: {(a.get('command', ''))[:40]}"
            if name == "fetch_url":
                return f"fetch {a.get('url', '?')[:40]}"
            if name == "weather":
                return f"weather {a.get('city', '?')}"
            if name == "graphify":
                return f"graphify {a.get('path', '.')}"
            if name == "clone_repo":
                return f"clone {a.get('url', '?')[:40]}"
            return name

        def _is_compact():
            """In auto mode, switch to compact after threshold steps."""
            if mode == "on": return True
            if mode == "off": return False
            return self._step_count > threshold  # auto

        def flush(thinking):
            # Render buffered text. `thinking`=True -> dim "reflecting" styling
            # (or discarded in quiet mode); False -> the final answer (normal).
            nonlocal buf
            if not buf: return
            joined = "".join(buf); buf = []
            if self.quiet:
                if not thinking: print(joined, end="", flush=True)
            elif thinking:
                print(f"\n{C.DIM}{C.ITALIC}{joined}{C.RESET}", end="", flush=True)
            else:
                fmt.first_line = True   # final answer starts at column 0, not as a continuation
                fmt.feed(joined)

        try:
            for event in self.backend.chat_with_tools(msgs, self._confirm_batch, self._continue_fn):
                et = event["type"]
                if et == "text":
                    if self.spinner: self.spinner.stop(); self.spinner = None
                    current_block += event["content"]
                    if did_tools or self.quiet:
                        buf.append(event["content"])          # reasoning or final (post-tool)
                    else:
                        fmt.feed(event["content"])             # live-stream opening / no-tool answer
                elif et == "thinking":
                    # Claude extended-thinking blocks: stream dim, never saved to history.
                    if self.spinner: self.spinner.stop(); self.spinner = None
                    if not self.quiet:
                        print(f"{C.DIM}{event['content']}{C.RESET}", end="", flush=True)
                elif et == "tool_progress":
                    if fmt: fmt.flush()
                    flush(thinking=True)
                    current_block = ""
                    did_tools = True
                    self._step_count += 1
                    # Always accumulate for /process
                    self.last_process.append({"step": self._step_count, "name": event["name"],
                                              "args": event.get("args", {}), "result": "", "status": "ok"})
                    if self.quiet: continue
                    if self.spinner: self.spinner.stop(); self.spinner = None
                    if _is_compact():
                        print(f"  {C.GRAY}\u2699\ufe0f {_tool_summary(event['name'], event.get('args', {}))}{C.RESET}", flush=True)
                    else:
                        print(f"\n{C.GRAY}[Tool {event['current']}/{event['total']}] {event['name']}({json.dumps(event['args'])}){C.RESET}")
                elif et == "tool_result":
                    if self.last_process:
                        self.last_process[-1]["result"] = event['result'][:200]
                        if str(event['result']).lower().startswith("error"):
                            self.last_process[-1]["status"] = "error"
                    if not self.quiet:
                        if not _is_compact():
                            res = event['result']
                            if len(res) > 800: res = res[:800] + "..."
                            print(f"{C.DIM}{res}{C.RESET}\n")
                        # The next tool-loop iteration is about to re-prefill the
                        # (now history-laden) prompt — show its wait instead of
                        # a silent freeze. The final answer's first text stops it.
                        self._start_spinner()
                elif et == "stream_progress":
                    # Live phase/size on the spinner: turns a silent
                    # gateway-buffered wait into visible progress ("writing
                    # docker.md · 8.4KB · 41s"), and proves the stream is alive.
                    if self.spinner and not self.quiet:
                        el = int(event.get("elapsed") or 0)
                        cc = int(event.get("content_chars") or 0)
                        ac = int(event.get("arg_chars") or 0)
                        if ac > 200:
                            self.spinner.set_msg(f"streaming tool call · {ac / 1000:.1f}KB")
                        elif cc > 0:
                            self.spinner.set_msg(f"streaming · {cc} chars")
                        else:
                            self.spinner.set_msg(f"generating · {el}s")
                elif et == "usage":
                    # Real per-request usage from the backend (Phase A). Counted
                    # live and persisted; a turn that yields NONE gets one
                    # estimate entry at turn end (below).
                    self._sess_usage["in"] += event.get("in", 0)
                    self._sess_usage["out"] += event.get("out", 0)
                    self._sess_usage["req"] += 1
                    if event.get("secs"):
                        self._sess_usage["gen_secs"] = self._sess_usage.get("gen_secs", 0.0) + float(event["secs"])
                    try:
                        self.db.log_usage(self.cid,
                                          (self.backend.profile.get("model", "") if self.backend else ""),
                                          self.cfg.get("backend", ""),
                                          event.get("in", 0), event.get("out", 0), est=False)
                    except Exception:
                        pass
                elif et == "turn_end":
                    # Estimation fallback: backends that report no usage get one
                    # estimated entry per turn (marked est=1 so /tokens can show
                    # honest "(estimated)" markers).
                    if self._sess_usage["req"] == 0 and self.backend:
                        try:
                            _est_in = est_tok(" ".join(str(mm.get("content", "")) for mm in msgs)) if msgs else 0
                            _est_out = est_tok(event.get("text") or "")
                            self._sess_usage = {"in": self._sess_usage["in"] + _est_in,
                                                "out": self._sess_usage["out"] + _est_out,
                                                "req": self._sess_usage["req"] + 1}
                            self.db.log_usage(self.cid,
                                              (self.backend.profile.get("model", "") if self.backend else ""),
                                              self.cfg.get("backend", ""),
                                              _est_in, _est_out, est=True)
                        except Exception:
                            pass
                    # Verified-changes footer: from the LEDGER (ground truth of
                    # what actually changed on disk), never from the model's words.
                    if not self.quiet:
                        led = event.get("ledger")
                        files = led.files_changed() if led else []
                        if files:
                            shown = ", ".join(os.path.basename(f) for f in files[:5])
                            more = f" +{len(files) - 5}" if len(files) > 5 else ""
                            print(f"{C.GREEN}\u270f\ufe0f  changed: {shown}{more}{C.RESET}", flush=True)
                        elif event.get("claimed_done"):
                            print(f"{C.YELLOW}\u26a0 no files were actually changed this turn{C.RESET}", flush=True)
                elif et == "notice":
                    if fmt: fmt.flush()
                    flush(thinking=True)
                    current_block = ""
                    if self.spinner: self.spinner.stop(); self.spinner = None
                    if not self.quiet:
                        self._render_notice(event)
                    if event.get("fatal"): break
            flush(thinking=False)                               # render the final answer (or empty)
            if fmt: fmt.flush()                                 # emit any markdown-buffered tail
            if self._step_count > 0 and not self.quiet:
                _errs = sum(1 for s in self.last_process if s["status"] == "error")
                tag = f"{self._step_count} steps" + (f" ({_errs} failed)" if _errs else "")
                print(f"{C.DIM}\u2699\ufe0f {tag} \u2014 /process for details{C.RESET}")
            else:
                print()
            return current_block
        except Exception as e:
            if self.spinner: self.spinner.stop(); self.spinner = None
            self._errored = True
            _dbg_exc(e)
            if (current_block or "").strip() or did_tools or any((x or "").strip() for x in buf):
                # Mid-stream / mid-tool interruption: snapshot the in-flight
                # state -- executed tool results are already in msgs -- so the
                # turn can CONTINUE instead of restarting from scratch.
                self._pending_checkpoint = [dict(m) for m in msgs]
                return ""
            self._pending_checkpoint = None
            if self.quiet: sys.stderr.write(f"Error: {e}\n")
            else: self.err(f"Tool chat error: {e}")
            return ""
        finally:
            # Stop the spinner on EVERY exit -- a clean return with no streamed
            # events (empty/broken reply) would otherwise leave it spinning into
            # the next prompt and stack with it on small screens.
            if self.spinner: self.spinner.stop(); self.spinner = None

    # ---- Session persistence (save/resume the last session across restarts) ----
    def _last_cid_file(self):
        return CONFIG_DIR / "last_cid"

    def _get_last_cid(self):
        try:
            v = self._last_cid_file().read_text().strip()
            return int(v) if v else None
        except Exception:
            return None

    def _set_last_cid(self, cid):
        try:
            self._last_cid_file().write_text(str(cid))
        except OSError:
            pass

    def _clear_last_cid(self):
        try:
            f = self._last_cid_file()
            if f.exists(): f.unlink()
        except OSError:
            pass

    def _persist_session(self):
        if self.cid: self._set_last_cid(self.cid)
        else: self._clear_last_cid()

    @staticmethod
    def _ago(ts):
        try:
            st = time.strptime(str(ts)[:19], "%Y-%m-%d %H:%M:%S")
            t = calendar.timegm(st)
        except Exception:
            return "recently"
        d = time.time() - t
        if d < 60: return "just now"
        if d < 3600: return f"{int(d // 60)}m ago"
        if d < 86400: return f"{int(d // 3600)}h ago"
        return f"{int(d // 86400)}d ago"

    def _restore_session_context(self, conv):
        """Restore a resumed session's working set: Build/Plan mode + active
        skills are re-applied so the session continues with the tools it started
        with (config is NOT persisted -- current-session only). A cwd mismatch
        warns with the fix instead of silently answering in the wrong tree."""
        if not conv:
            return
        keys = conv.keys() if hasattr(conv, "keys") else []
        if "tools_mode" in keys and conv["tools_mode"] is not None:
            want = bool(conv["tools_mode"])
            if want != bool(self.cfg.get("tools_enabled", False)):
                self.cfg.set("tools_enabled", want, save=False)
                mode = "Build" if want else "Plan"
                if not self.quiet:
                    print(f"{C.DIM}[Session tools mode restored: {mode}]{C.RESET}")
        if "skills_json" in keys and conv["skills_json"]:
            try:
                names = json.loads(conv["skills_json"]) or []
            except Exception:
                names = []
            restored = []
            for n in names:
                _meta, body = self.skills.load(n)
                if body:
                    self.active_session_skills.append((n, body))
                    restored.append(n)
            if restored and not self.quiet:
                print(f"{C.DIM}[Session skills restored: {', '.join(restored)}]{C.RESET}")
        if "cwd" in keys and conv["cwd"] and conv["cwd"] != os.getcwd() and not self.quiet:
            # compare WORKSPACE roots: launching from a subdir of the same repo
            # is not a mismatch
            cur_ws = self._current_workspace()
            try:
                same_ws = bool(cur_ws) and os.path.realpath(conv["cwd"]).startswith(os.path.realpath(cur_ws).rstrip("/") + os.sep) if cur_ws else False
            except OSError:
                same_ws = False
            if not same_ws:
                print(f"{C.YELLOW}[!] Session was started in {conv['cwd']}{C.RESET}")
            print(f"    {C.DIM}You're in {os.getcwd()}. Run `cd {conv['cwd']}` for its files, "
                  f"or continue here (paths in history refer to the old dir).{C.RESET}")

    def _activate(self, cid, banner=False):
        self.cid = cid
        self._persist_session()
        conv = self.db.get_conv(cid) or {}
        self._restore_session_context(conv)
        if banner and not self.quiet:
            if conv:
                n = len(self.db.get_msgs(cid))
                ago = self._ago(conv["updated_at"])
                prev = self.db.last_msg_model(cid)
                cur = (self.backend.profile.get("model", "") if self.backend else "").strip()
                if prev and cur and prev != cur:
                    tail = f" \u2014 now on {cur}; /retry to re-answer with the current model"
                elif prev:
                    tail = f" \u2014 was {prev}"
                else:
                    tail = ""
                slug = (conv["slug"] or "") if "slug" in conv.keys() else ""
                name = f"{slug or conv['title']}"
                ws = (conv["workspace"] or "") if "workspace" in conv.keys() else ""
                ws_s = f" @ {os.path.basename(ws.rstrip('/'))}" if ws else ""
                print(f"{C.DIM}[Resumed: \"{name}\"{ws_s} \u2014 {n} message{'' if n == 1 else 's'}, last active {ago}{tail}]{C.RESET}")
            ck = self.db.get_resume_state(cid)
            if ck:
                steps = self._count_tool_steps(ck)
                print(f"{C.YELLOW}[Interrupted turn pending: {steps} tool step{'s' if steps != 1 else ''} completed. /retry to continue, or send a new message.]{C.RESET}")

    def _maybe_resume(self):
        mode = self._resume_mode
        if mode == "load" and self._resume_arg is not None:
            try:
                cid = int(self._resume_arg)
            except (ValueError, TypeError):
                self.err(f"Invalid session id: {self._resume_arg}"); return
            conv = self.db.get_conv(cid)
            if conv: self._activate(cid, banner=True)
            else: self.err("Session not found.")
            return
        if mode == "new":
            self.cid = None; self._clear_last_cid(); return
        if mode == "session":
            # create-or-resume by NAME (ai -S webproject): exact slug match ->
            # resume it (restoring its tools/skills context); no match -> start
            # a fresh session tagged with the slug so the next -S finds it.
            nm = (self._resume_arg or "").strip()
            conv = self.db.get_conv_by_slug(nm, workspace=self._current_workspace()) if nm else None
            if conv:
                self._activate(conv["id"], banner=True)
                self.db.set_conv_slug(conv["id"], nm)   # refresh casing if changed
            else:
                cid = self.db.new_conv(nm or "New Chat",
                                       self.backend.profile.get("model", "") if self.backend else "",
                                       self.cfg.get("backend", ""),
                                       cwd=os.getcwd(),
                                       tools_mode=bool(self.cfg.get("tools_enabled", False)),
                                       skills=[n for n, _ in self.active_session_skills] or None,
                                       workspace=self._current_workspace())
                self.db.set_conv_slug(cid, nm)
                self._activate(cid, banner=False)
                if not self.quiet:
                    print(f"{C.DIM}[New named session: {nm}]{C.RESET}")
            return
        resume = (mode == "continue") or (mode == "auto" and self.cfg.get("auto_resume", True))
        if not resume: return
        # WORKSPACE isolation: inside a detected workspace, resume only that
        # workspace's last session — never another project's, never a global
        # fallback (fresh start instead). Outside workspaces (home/tmp), keep
        # the global last-cid behavior: that's personal-chat territory.
        ws = self._current_workspace()
        if ws:
            cand = self.db.last_conv_in_workspace(ws)
            if cand:
                self._activate(cand["id"], banner=True)
            return
        here = os.getcwd()
        cand = self.db.last_conv_in_cwd(here)
        cid = cand["id"] if cand else self._get_last_cid()
        if cid and self.db.get_conv(cid):
            self._activate(cid, banner=True)
        elif cid:
            self._clear_last_cid()  # stale pointer (session deleted)

    # ---- Interrupted-turn continuation (never restart from scratch) ----
    @staticmethod
    def _count_tool_steps(msgs):
        """Number of tool steps actually executed in an in-flight msgs list."""
        c = 0
        for m in msgs or []:
            if not isinstance(m, dict): continue
            if m.get("role") == "tool":
                c += 1
            elif m.get("role") == "user" and isinstance(m.get("content"), list):
                c += sum(1 for b in m["content"] if isinstance(b, dict) and b.get("type") == "tool_result")
        return c

    def _auto_continue_attempt(self, pending):
        """One continuation attempt: re-send the in-flight msgs (executed tool
        results included) with a 'continue, don't redo' instruction. Shows a
        notice + short window first so the user can Ctrl+C to abort."""
        n = self._count_tool_steps(pending)
        if not self.quiet:
            print(f"{C.DIM}\u21bb connection dropped after {n} tool step{'s' if n != 1 else ''} \u00b7 resuming in 2s (Ctrl+C to skip){C.RESET}")
            try:
                time.sleep(2.0)
            except KeyboardInterrupt:
                print(f"\n{C.YELLOW}[Auto-resume skipped. Checkpoint kept \u2014 /retry to continue later.]{C.RESET}")
                return ""
        note = ("Your previous response was INTERRUPTED mid-task (connection dropped). "
                "The already-executed tool calls and their results are in the history above. "
                "CONTINUE from exactly where you left off. Do NOT re-execute or repeat completed "
                "tool calls. If a tool call appears without its result yet, re-issue ONLY that call "
                "to finish it, then continue the task.")
        cont = [dict(m) for m in pending]
        for m in cont:
            if m.get("role") == "system":
                m["content"] = m["content"] + "\n\n[INTERRUPTED \u2014 continue]\n" + note
                break
        try:
            return self._stream_tool_chat(cont)
        except KeyboardInterrupt:
            print(f"\n{C.YELLOW}[Auto-resume stopped by you \u2014 checkpoint kept. /retry to continue later.]{C.RESET}")
            return ""

    def _handle_interruption(self, pending, model):
        """A turn failed mid-stream after doing work. Persist the checkpoint,
        then auto-continue (config auto_continue, default ON) up to
        max_auto_continue times. On success the final reply is saved normally;
        on failure the checkpoint stays for /retry."""
        self._pending_checkpoint = None
        try:
            self.db.set_resume_state(self.cid, json.dumps(pending))
        except (TypeError, ValueError):
            self.db.set_resume_state(self.cid, "[]")
        if not self.cfg.get("auto_continue", True):
            n = self._count_tool_steps(pending)
            if not self.quiet:
                print(f"{C.YELLOW}[Interrupted turn: {n} tool step{'s' if n != 1 else ''} completed. Run /retry to continue, or send a new message.]{C.RESET}")
            return
        total = max(1, int(self.cfg.get("max_auto_continue", 2)))
        for attempt in range(1, total + 1):
            reply = self._auto_continue_attempt(pending)
            if reply:
                self.db.clear_resume_state(self.cid)
                self.db.save_msg(self.cid, "assistant", reply, model, est_tok(reply))
                self.last_reply = reply
                self._persist_session()
                if not self.quiet:
                    print(f"{C.DIM}[Resumed after interruption \u2014 reply saved]{C.RESET}")
                return
            pending = self._pending_checkpoint
            self._pending_checkpoint = None
            if not pending:
                break
            if attempt < total and not self.quiet:
                print(f"{C.YELLOW}[Auto-resume failed \u2014 trying again ({total - attempt} left)...]{C.RESET}")
        if not self.quiet:
            self.warn("Could not auto-resume after retries. Checkpoint kept \u2014 run /retry, or send a new message.")

    def _continue_from_checkpoint(self, cid, model):
        """Manual /retry after an interrupted turn: continue from the checkpoint
        instead of regenerating from the user message alone."""
        ck = self.db.get_resume_state(cid)
        if not ck:
            return False
        self.cid = cid
        reply = self._auto_continue_attempt(ck)
        if reply:
            self.db.clear_resume_state(cid)
            self.db.save_msg(cid, "assistant", reply, model, est_tok(reply))
            self.last_reply = reply
            self._persist_session()
            self.success("Resumed and completed the interrupted turn.")
            return True
        self.warn("Could not complete the interrupted turn yet. Checkpoint kept.")
        return False

    _WS_MARKERS = (".git", "package.json", "pyproject.toml", "go.mod", "Cargo.toml",
                   "composer.json", "pom.xml", "Gemfile", "mix.exs", "deno.json",
                   "CONTEXT.md", ".ai")

    @classmethod
    def _workspace_root(cls, start=None):
        """The project/workspace root for a directory: nearest ancestor (incl.
        itself) carrying a workspace marker (.git first, then manifests, then
        CONTEXT.md/.ai). Returns None outside any workspace (home/tmp). Nested
        repos resolve to the NEAREST marker. Per-dir cached."""
        try:
            d = os.path.realpath(start or os.getcwd())
        except OSError:
            return None
        cache = cls._ws_cache
        if d in cache:
            return cache[d]
        root = None
        cur = d
        while True:
            for marker in cls._WS_MARKERS:
                if os.path.exists(os.path.join(cur, marker)):
                    root = cur
                    break
            if root is not None:
                break
            parent = os.path.dirname(cur)
            if parent == cur:
                break
            cur = parent
        cache[d] = root
        return root

    _ws_cache = {}

    def _current_workspace(self):
        """Workspace root of the CWD (cached per dir); runs the one-time
        legacy backfill on first use so old sessions get anchored too."""
        if not self._ws_backfilled:
            self._ws_backfilled = True
            try:
                self.db.backfill_workspaces(self._workspace_root)
            except Exception:
                pass
        return self._workspace_root()

    def _project_context(self):
        """Read ./CONTEXT.md (or .ai/context.md) — per-session cached, refreshed
        when the file's mtime changes (the model may rewrite it mid-session).
        Returns '' when absent. Gives every session durable project memory:
        stack, structure, conventions, gotchas."""
        for cand in ("CONTEXT.md", os.path.join(".ai", "context.md")):
            if getattr(self, "_ctx_disabled", False):
                return ""
            p = Path(cand)
            try:
                if not p.is_file():
                    continue
                mt = p.stat().st_mtime
                if self._ctx_cache and self._ctx_cache[0] == (str(p), mt):
                    return self._ctx_cache[1]
                body = p.read_text(errors="replace")[: self.cfg.get("max_context_md", 12000)]
                self._ctx_cache = ((str(p), mt), body)
                return body
            except OSError:
                continue
        return ""

    def _suggest_skill(self, user_input):
        """One-line hint when the input strongly matches a skill (opt-in via
        skill_suggest, default on). Keyword triggers come from the skill body:
        distinctive tokens (playwright, pentest, deploy, finops...) appearing in
        the user's message. Never fires for an already-active session skill or
        when any skill is active in session mode (avoid noise); zero cost when
        it doesn't match."""
        if not self.cfg.get("skill_suggest", True) or self.quiet:
            return
        if self.active_session_skills:
            return
        text = user_input.lower()
        best = None
        for name, meta in self.skills.list():
            body_l = (name + " " + (self.skills.load(name)[1] or "")).lower()
            for kw in self._skill_trigger_words(name, body_l):
                if kw in text:
                    best = (name, kw)
                    break
            if best:
                break
        if best:
            name, kw = best
            print(f"{C.DIM} tip: this sounds like the '{name}' skill — /skill {name} to activate for this task{C.RESET}")

    @staticmethod
    def _skill_trigger_words(name, body_l):
        """Distinctive trigger tokens per bundled skill (name stems + signature
        terms from the body). Short/generic words are excluded."""
        TRIGGERS = {
            "frontend-tester": ("playwright", "e2e test", "end-to-end test", "test scenario"),
            "pentest": ("pentest", "penetration test", "vulnerability scan", "exploit"),
            "brainstorm": ("brainstorm", "ide", "brainstorming"),
            "fullstack": ("fullstack", "full-stack", "landing page", "web platform", "build a website"),
            "cloud-arch": ("cloud architecture", "cloud infra", "kubernetes", "terraform"),
            "data-engineer": ("data pipeline", "etl", "data warehouse", "airflow"),
            "finops": ("finops", "cloud cost", "billing optimization"),
            "commit": ("commit message", "write a commit", "conventional commit"),
            "python": ("python refactor", "python package", "pip package"),
            "qa": ("qa test", "test plan", "manual testing", "corner case"),
            "reverse-engineer": ("reverse engineer", "reverse-engineer", "prd from code"),
            "review": ("code review", "pr review", "review this pr"),
        }
        return TRIGGERS.get(name, ())

    def _assemble_system_prompt(self):
        """The FULL system prompt for a turn: persona+tool rules, active session
        skills, autoload catalog, CONTEXT.md project memory, and the gather-
        first workflow line. Used by _chat AND the startup warm-priming call so
        the two prefixes are byte-identical -- Ollama's KV cache only hits on an
        exact prefix match, so any divergence silently wastes the prime."""
        sysp = self.cfg.system_prompt()
        if self.active_session_skills:
            sysp += "\n\n" + "\n\n".join(f"# Active skill: {n}\n{b}" for n, b in self.active_session_skills)
        if self.cfg.get("skill_autoload", False):
            cat = self.skills.catalog()
            if cat:
                sysp += "\n\n" + cat
        _ctx = self._project_context()
        if _ctx:
            sysp += ("\n\n# Project context (CONTEXT.md — kept current by you; update it with "
                     "write_file when you learn durable facts about this project):\n" + _ctx)
        if (self.backend and self.backend._eff("gather_first", True)
                and not getattr(self.backend, "_local_chat_model", lambda: False)()):
            sysp += (
                "\n\nWORKFLOW: gather ALL the context you need up front, then act. "
                "In your first one or two responses, batch the reads you'll need "
                "(read_file / list_files / search_files) into a single response with "
                "several parallel calls. Then stop reading and EXECUTE with "
                "write_file / run_command. Never re-read a file you already fetched; "
                "for large files page once per line-range with "
                "read_file(path, start=LINE) in the same batched response.")
        return sysp

    _TITLE_STRIP_RE = re.compile(
        r"^(hey|hi|hello|halo|hai|yo|bro|bang|kak|mas|mbak|pak|bu)[,!.,\s]+"      # greetings
        r"|^(tolong|please|coba|bisa( gak| nggak| tidak)?|bisakah|could you|can you|"
        r"would you|i want( to)?|i need( to)?|saya mau|aku mau|bantu(in|kan)?( saya| aku)?)[\s,.]+"
        r"|^(buatkan|buat|bikin(in|kan)?|make me|create|generate)[\s,.]+", re.IGNORECASE)

    @classmethod
    def _smart_title(cls, src):
        """Derive a session title from the first message: strip greetings and
        please/make-me prefixes (EN+ID), collapse whitespace, keep the first
        task-bearing clause (split on sentence enders). Falls back to the raw
        first line. Pure heuristic -- free, instant, no LLM call."""
        line = (src or "").strip().splitlines()[0] if (src or "").strip() else ""
        if not line:
            return "New Chat"
        t = line.strip()
        prev = None
        # strip repeatedly ("tolong bantu saya buatkan..." has 2-3 layers)
        for _ in range(4):
            if t == prev:
                break
            prev = t
            t = cls._TITLE_STRIP_RE.sub("", t, count=1).strip(" ,.!:;-\t")
        # first clause only
        for sep in (".", "?", "!", ";", "\u2014", " | ", " -- "):
            if sep in t:
                t = t.split(sep, 1)[0].strip()
                break
        t = re.sub(r"\s+", " ", t)
        return t or line[:40]

    _GH_URL_RE = re.compile(r"https?://(?:www\.)?github\.com/([\w.\-]+)/([\w.\-]+)/(?:issues|pull)/?(\d+)?", re.IGNORECASE)
    _GH_REPO_RE = re.compile(r"https?://(?:www\.)?github\.com/([\w.\-]+)/([\w.\-]+?)(?:\.git)?/?$", re.IGNORECASE)
    _TRACEBACK_RE = re.compile(
        r"^\s*(?:Traceback \(most recent call last\):|\w+Error:|\w+Exception:|"
        r"panic:|runtime error:|FATAL:|at \S+\(\S+:\d+:\d+\)|\s+at \S+ \(\S+:\d+:\d+\))",
        re.MULTILINE | re.IGNORECASE)
    _DIFF_RE = re.compile(r"^(?:diff --git |--- a/|\+\+\+ b/|@@ -\d+(?:,\d+)? \+\d+(?:,\d+)? @@)", re.MULTILINE)
    _FRAME_RE = re.compile(r'File "([^"]+)", line (\d+)')

    @classmethod
    def _classify_paste(cls, text):
        """Cheap classifier for pasted content: traceback / diff / github-issue /
        github-repo / json / yaml / markdown / code / plain. Drives the /paste
        preview (recognition header + context offers) — never blocks sending."""
        t = (text or "").strip()
        if not t:
            return "empty", {}
        n_trace = len(cls._TRACEBACK_RE.findall(t))
        if n_trace >= 1 or re.search(r"\b(Error|Exception|Traceback)\b", t.splitlines()[-1] or "") and t.count("\n") >= 3:
            frames = [(f, int(l)) for f, l in cls._FRAME_RE.findall(t)][:8]
            return "traceback", {"frames": frames, "files": sorted({f for f, _ in frames})}
        if cls._DIFF_RE.search(t):
            return "diff", {"files": sorted(set(re.findall(r"^diff --git a/(\S+)", t, re.MULTILINE))
                                 | set(re.findall(r"^\+\+\+ b/(\S+)", t, re.MULTILINE)))}
        m = cls._GH_URL_RE.search(t)
        if m and len(t) <= 400:      # the paste IS (mostly) the link
            kind = "pull" if "/pull/" in m.group(0).lower() else "issue"
            return f"github-{kind}", {"org": m.group(1), "repo": m.group(2), "n": m.group(3), "url": m.group(0)}
        m2 = cls._GH_REPO_RE.search(t)
        if m2 and len(t) <= 200 and t.count("\n") == 0:
            return "github-repo", {"org": m2.group(1), "repo": m2.group(2), "url": m2.group(0)}
        s = t.lstrip()
        if s.startswith("{") or s.startswith("["):
            try:
                json.loads(s)
                return "json", {}
            except Exception:
                pass
        first = t.splitlines()[0]
        if first.startswith("---") or first.startswith("# ") or re.match(r"^#{1,3} \S", t):
            return "markdown", {}
        if re.match(r"^\S+\s*[:=]\s", t, re.MULTILINE) and re.search(r"^\S+:$|^\s+\S+:", t, re.MULTILINE) and "{" not in t[:5]:
            return "yaml", {}
        lines = t.splitlines()
        codey = sum(1 for ln in lines if re.match(r"^\s{4,}|\S.*[{};()=]\s*$", ln))
        if len(lines) >= 3 and codey >= max(2, len(lines) // 3):
            return "code", {}
        return "plain", {}

    def _traceback_context(self, frames):
        """Attach bounded source snippets around a traceback's file:line frames
        (the deepest N LOCAL frames that exist on disk). Gives the model the
        failing code without the user manually @-referencing files."""
        out = []
        shown = 0
        for path, line in reversed(frames):        # deepest frame first
            if shown >= 5:
                break
            if not os.path.exists(path):
                continue
            lo = max(1, line - 6)
            hi = line + 6
            content = FileReader.read(path, 4000, start_line=lo, end_line=hi)
            if content and not content.startswith("[Error"):
                out.append(f"\n--- {path} (lines {lo}-{hi}, error at line {line}) ---\n```\n{content}\n```")
                shown += 1
        return "".join(out)

    def _cmd_paste_preview(self, text):
        """Interactive smart-paste preview: classify, show a recognition header
        + stats, offer context actions (attach traceback sources / fetch a GH
        link), let the user edit or send raw. Non-TTY or declined -> send raw.
        Returns the (possibly enriched) text to send, or None to abort."""
        kind, info = self._classify_paste(text)
        nl = text.count("\n") + 1
        toks = est_tok(text)
        labels = {"traceback": "stack trace / error", "diff": "diff / patch",
                  "github-issue": "GitHub issue/PR link", "github-repo": "GitHub repo link",
                  "json": "JSON", "yaml": "YAML", "markdown": "markdown doc",
                  "code": "code block", "plain": "text", "empty": ""}
        label = labels.get(kind, "text")
        print(f"{C.CYAN}[Paste: {label} — {nl} line{'s' if nl != 1 else ''}, ~{toks} tokens]{C.RESET}")
        head = "\n".join(text.splitlines()[:6])
        if nl > 6:
            head += f"\n{C.DIM}  … (+{nl - 6} more lines){C.RESET}"
        print(head)
        enriched = text
        extra = ""
        if kind == "traceback" and info.get("frames"):
            files = ", ".join(os.path.basename(f) for f in info["files"][:4]) or "(none found)"
            print(f"{C.YELLOW}  files referenced: {files}{C.RESET}")
            extra = " [a]ttach source around frames"
        elif kind.startswith("github-"):
            extra = f" [f]etch {info.get('url', 'it')}"
        elif kind == "diff":
            extra = " review/apply it yourself after sending"
        prompt = f"{C.GREEN}Send? [Enter=send raw{(' | ' + extra) if extra else ''} | e=edit | Esc=cancel]{C.RESET} "
        try:
            ans = input(prompt).strip().lower()
        except (EOFError, KeyboardInterrupt):
            return None
        if ans == "\x1b" or ans.lower() in ("esc", "q", "cancel"):
            return None
        if ans == "e":
            import tempfile as _tf, subprocess as _sp
            with _tf.NamedTemporaryFile("w", suffix=".txt", delete=False) as f:
                f.write(text); tmp = f.name
            ed = os.environ.get("EDITOR") or next((e for e in ("nano", "vim", "vi") if shutil.which(e)), "vi")
            _sp.run([ed, tmp])
            enriched = open(tmp, encoding="utf-8", errors="replace").read()
            os.unlink(tmp)
            return enriched.strip() or None
        if ans == "a" and kind == "traceback":
            ctx = self._traceback_context(info.get("frames") or [])
            if ctx:
                enriched = text + "\n" + ctx
                print(f"{C.DIM}  attached source around {ctx.count('--- ')} frame(s){C.RESET}")
            else:
                print(f"{C.DIM}  no local files for those frames; sending raw{C.RESET}")
        if ans == "f" and kind.startswith("github-"):
            try:
                body = Tools.run("fetch_url", {"url": info["url"]})
                if not body.lower().startswith("error"):
                    enriched = text + f"\n\n--- Fetched {info['url']} ---\n{body[:8000]}"
                    print(f"{C.DIM}  fetched ({len(body)} chars){C.RESET}")
                else:
                    print(f"{C.DIM}  fetch failed; sending raw{C.RESET}")
            except Exception:
                print(f"{C.DIM}  fetch failed; sending raw{C.RESET}")
        return enriched

    def _chat(self, user_input, title=None):
        if not self.backend:
            self.err("No backend configured. Run /setup")
            return

        title_src = title or user_input
        user_input = self._attach_files(user_input)
        if not self.cid:
            # Capture the session's working set ONCE at creation: project dir,
            # Build/Plan mode, active skills. Resume restores them so a session
            # continues with the tools it started with.
            self.cid = self.db.new_conv(
                "New Chat", self.backend.profile.get("model", ""), self.cfg.get("backend", ""),
                cwd=os.getcwd(),
                tools_mode=bool(self.cfg.get("tools_enabled", False)),
                skills=[n for n, _ in self.active_session_skills] or None,
                workspace=self._current_workspace())
            first_line = self._smart_title(title_src)
            self.db.rename_conv(self.cid, first_line[:40] + ("..." if len(first_line) > 40 else ""))

        model = self.backend.profile.get("model", "")
        self.db.save_msg(self.cid, "user", user_input, model, est_tok(user_input))
        self.last_user_msg = user_input
        self.db.clear_resume_state(self.cid)   # a fresh user turn supersedes any pending checkpoint

        sysp = self._assemble_system_prompt()
        msgs = [{"role": "system", "content": sysp}]
        msgs.extend(self.db.get_msgs(self.cid))

        # Local non-thinking chat models over-use tools on casual questions
        # (qwen2.5 lists files for 'say hi') — a 60s+ tool loop on slow phones.
        # Tell them to answer trivial chat directly so tools only fire when real,
        # and to summarize web content instead of pasting raw pages.
        if getattr(self.backend, "_local_chat_model", lambda: False)():
            msgs[0]["content"] += (
                "\n\nIf the user's request is a simple question or casual chat that "
                "needs no files or commands, ANSWER DIRECTLY in plain text and do "
                "NOT call any tool.\n"
                "For factual questions you can't answer from memory, use web_search "
                "or weather FIRST. Only call fetch_url on a URL that web_search "
                "returned or that you are certain exists \u2014 never invent URLs with "
                "placeholders like YOUR_API_KEY. Reply with a CONCISE SUMMARY in "
                "your own words \u2014 never paste raw page text.")

        # Strategy-first: when enabled, ask the model to outline a strategy before
        # show it, and inject it so the model executes deliberately (less wandering).
        if self.backend._eff("strategy_first", False) and not self.quiet:
            strategy = self._make_strategy(title_src)
            if strategy:
                self._show_strategy(strategy)
                msgs[0]["content"] += ("\n\nYou committed to the strategy below for this "
                    "task — execute it step by step, reasoning briefly before each action; "
                    "revise only if a step becomes impossible:\n" + strategy)

        # AI ALWAYS uses tools. tools_enabled (Build Mode) only toggles write access.
        reply = self._stream_tool_chat(msgs)
        pending = self._pending_checkpoint
        self._pending_checkpoint = None

        if reply:
            self.db.clear_resume_state(self.cid)
            self.db.save_msg(self.cid, "assistant", reply, model, est_tok(reply))
            self.last_reply = reply
            self._persist_session()
            if self.cfg.get("tts_replies", False): TermuxAPI.speak(reply)
            if self.cfg.get("show_tokens", True) and not self.quiet:
                print(self._usage_line())
        elif pending:
            self._handle_interruption(pending, model)
        # Auto-compact long conversations to stay within the context budget.
        # Model-aware: the trigger is a FRACTION of the effective window —
        # cloud uses the model's registry window (gpt-4o 128k, gemini 1M...),
        # local uses its num_ctx — instead of a fixed 3000-token guess. That's
        # the pi-style '(auto)': compaction fires at the right moment per model.
        if self.cid and self.cfg.get("auto_compact", True) and not self.quiet:
            win = self._effective_window()
            threshold = int(win * float(self.cfg.get("compact_at", 0.8)))
            if self.db.get_conv_tokens(self.cid) > threshold:
                self.info(f"Auto-compacting long conversation ({self.db.get_conv_tokens(self.cid)}t > {threshold}t = {int(self.cfg.get('compact_at', 0.8) * 100)}% of {win // 1000}k)...")
                ok, cmsg = self._compact_conversation(self.cid)
                if ok: self.success(cmsg)

    def _usage_line(self):
        """Pi-style usage footer after each reply:
            ↑1.2k ↓340 · 12.1k/32k (38%) (auto)
        Real numbers from usage events (est → '~' markers when estimated);
        context is conversation tokens vs the model's effective window
        (local = num_ctx). '(auto)' shows when auto-compact is armed."""
        u = self._sess_usage
        gen = u.get("out", 0) and u.get("gen_secs") and (u["out"] / u["gen_secs"]) or None
        speed = f" \u00b7 {gen:.0f} tok/s" if gen else ""
        est_mark = "~" if u["req"] and self.db.usage_totals(self.cid, days=1).get("est", 1) > 0 and u["in"] == 0 else ""
        win = self._effective_window()
        conv_t = self.db.get_conv_tokens(self.cid) if self.cid else 0
        pct = min(100.0, conv_t * 100.0 / win) if win else 0.0
        auto = " (auto)" if self.cfg.get("auto_compact", True) else ""
        def _fmt(n):
            return f"{n / 1e6:.1f}M" if n >= 1e6 else (f"{n / 1e3:.1f}k" if n >= 1000 else str(n))
        return (f"{C.DIM}\u2191{est_mark}{_fmt(u['in'])} \u2193{est_mark}{_fmt(u['out'])}{speed} \u00b7 "
                f"{_fmt(conv_t)}/{_fmt(win)} ({pct:.0f}%) (r{u['req']}){auto}{C.RESET}")

    def _effective_window(self):
        """The effective context window for the ACTIVE model: local models
        use their num_ctx tuning (the phone's real limit); cloud models use the
        CONTEXT_WINDOWS registry with the config context_window fallback."""
        if not self.backend:
            return int(self.cfg.get("context_window", 32000))
        if getattr(self.backend, "is_local", False):
            nctx = self.backend._eff("num_ctx") or 0
            return int(nctx) if nctx else int(self.cfg.get("context_window", 32000))
        return context_window_for(self.backend.profile.get("model", ""),
                                  fallback=self.cfg.get("context_window", 32000))

    def _make_strategy(self, task):
        """Produce a concise numbered strategy for a task via a non-tool completion.
        Returns the strategy text (or '' on failure)."""
        sysp = ("You are a strategy assistant. Given a task, output a concise NUMBERED step-by-step strategy. "
                "For each step state what you will do and which tool you would use "
                "(read_file, list_files, search_files, run_command, write_file). "
                "Use the minimum number of steps. If the task needs no tools, say \"No tools needed\" "
                "and answer directly. Do NOT execute anything yet.")
        msgs = [{"role": "system", "content": sysp}, {"role": "user", "content": task}]
        spinner = None
        if not self.quiet:
            spinner = Spinner("strategizing"); spinner.start()
        strategy = ""
        try:
            for chunk in self.backend.chat(msgs, stream=True):
                if spinner: spinner.stop(); spinner = None
                strategy += chunk
        except Exception as e:
            if spinner: spinner.stop(); spinner = None
            if not self.quiet: self.err(f"Strategy planning failed: {e}")
            return ""
        finally:
            if spinner: spinner.stop(); spinner = None
        return strategy.strip()

    def _show_strategy(self, strategy):
        if self.quiet: return
        print(f"\n{C.CYAN}{C.BOLD}\u250c\u2500 strategy \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500{C.RESET}")
        for line in strategy.splitlines():
            print(f"{C.CYAN}\u2502{C.RESET} {line}")
        print(f"{C.CYAN}{C.BOLD}\u2514\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500{C.RESET}\n")

    def _compact_conversation(self, cid):
        """Summarize a conversation and replace its history with the summary
        plus the last two messages. Returns (ok, message)."""
        msgs = self.db.get_msgs(cid, limit=1000)
        if len(msgs) < 4:
            return False, "Not enough messages to compact."
        transcript = "\n\n".join(f"{m['role'].capitalize()}: {m['content'][:1200]}" for m in msgs)
        summary = self._ask(
            "Summarize the conversation below concisely as a running context note: "
            "preserve key facts, decisions, file paths, commands, and any open tasks. "
            "Do not add commentary.\n\n" + transcript, show=False).strip()
        if not summary:
            return False, "Compaction failed (empty summary)."
        keep = msgs[-2:]
        self.db.clear_conv_msgs(cid)
        self.db.save_msg(cid, "user", f"[Summary of the earlier conversation]\n{summary}")
        for m in keep:
            self.db.save_msg(cid, m["role"], m["content"])
        return True, f"Compacted to a summary + {len(keep)} recent message(s). Tokens now ~{self.db.get_conv_tokens(cid)}."

    def _match_price(self, model):
        m = (model or "").lower()
        for key, rate in PRICING.items():
            k = key.lower()
            if k in m or m in k:
                return rate
        return 0.0

    # ---------- one-shot / CLI helpers ----------

    def _read_stdin(self):
        """Return piped stdin text, or None when stdin is a terminal."""
        if sys.stdin.isatty():
            return None
        try:
            data = sys.stdin.read()
        except Exception:
            return None
        return data if data.strip() else None

    def _override_model(self, model):
        """Override the active model for this process only (not persisted)."""
        if not model or not self.backend:
            return
        prof = getattr(self.backend, "profile", None)
        if isinstance(prof, dict):
            prof["model"] = model

    def _apply_skill_args(self, skills_str):
        """Activate comma-separated skills for this run (CLI --skill). Missing
        skills warn + (in a TTY) ask to continue without; on decline return False
        so the caller exits. Non-TTY runs warn and continue (can't prompt)."""
        names = [n.strip() for n in (skills_str or "").split(",") if n.strip()]
        missing = []
        for n in names:
            _meta, body = self.skills.load(n)
            if body:
                self.active_session_skills.append((n, body))
            else:
                missing.append(n)
        if missing:
            avail = ", ".join(nm for nm, _ in self.skills.list()) or "(none)"
            self.warn(f"Skill not found: {', '.join(missing)}. Available: {avail}")
            if IS_TTY and sys.stdin.isatty():
                ans = input(f"\n{C.YELLOW}Continue without the missing skill(s)? [Y/n]{C.RESET} ").strip().lower()
                if ans == "n":
                    return False
            # non-TTY: warn + continue (no prompt possible)
        return True

    @staticmethod
    def _strip_code_fence(text):
        lines = text.strip().splitlines()
        if lines and lines[0].strip().startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        return "\n".join(lines)

    def _ask(self, prompt, json_mode=False, show=True):
        """Plain text completion with NO tools. Returns the reply string.
        show=True streams to stdout (formatted in a TTY, raw when piped);
        show=False captures silently (used by the command generator)."""
        if not self.backend:
            if self.quiet: sys.stderr.write("Error: No backend configured.\n")
            else: self.err("No backend configured. Run /setup")
            return ""
        sysp = self.cfg.system_prompt()
        if json_mode:
            sysp = (sysp + "\n" if sysp else "") + "You must respond with valid JSON only. No markdown, no prose, no code fences."
        msgs = []
        if sysp: msgs.append({"role": "system", "content": sysp})
        msgs.append({"role": "user", "content": prompt})

        fmt = MarkdownFormatter(fold=self.cfg.get("fold_long_blocks", True), fold_head=self.cfg.get("fold_head", 8)) if (show and not self.quiet and not json_mode) else None
        spinner = Spinner(self._spinner_msg()) if (show and not self.quiet) else None
        if spinner: spinner.start()
        reply = ""
        try:
            for chunk in self.backend.chat(msgs, stream=True):
                if spinner: spinner.stop(); spinner = None
                if fmt: fmt.feed(chunk)
                elif show: print(chunk, end="", flush=True)
                reply += chunk
            if fmt: fmt.flush()
            if show: print()
        except Exception as e:
            if spinner: spinner.stop(); spinner = None
            self._errored = True
            _dbg_exc(e)
            if self.quiet: sys.stderr.write(f"Error: {e}\n")
            else: self.err(str(e))
        finally:
            if spinner: spinner.stop(); spinner = None
        return reply

    def oneshot(self, prompt, stdin_data=None):
        """Send one prompt through the normal (tool-aware) chat path and exit."""
        if stdin_data:
            prompt = (prompt or "") + ("\n\n" if prompt else "") + "--- stdin ---\n" + stdin_data
        if not prompt or not prompt.strip():
            return
        self._chat(prompt)

    def json_oneshot(self, prompt, stdin_data=None):
        if stdin_data:
            prompt = (prompt or "") + ("\n\n" if prompt else "") + "--- stdin ---\n" + stdin_data
        if not prompt or not prompt.strip():
            sys.stderr.write("Error: no prompt provided.\n")
            return
        self._ask(prompt, json_mode=True, show=True)

    def command_gen(self, task, stdin_data=None):
        """Generate a shell command for TASK. In a TTY: confirm and run it.
        When piped: print the command only (pipe to bash to execute)."""
        if not self.backend:
            sys.stderr.write("Error: No backend configured. Run 'ai' to set up.\n")
            return 1
        prompt = ("Output ONLY a single shell command that accomplishes the task. "
                  "No explanation, no markdown, no backticks, no leading '$'. "
                  "Just the raw command on one line.\n\nTask: " + task)
        if stdin_data:
            prompt += "\n\nContext from stdin:\n" + stdin_data[:4000]
        cmd = self._strip_code_fence(self._ask(prompt, show=False)).strip()
        cmd = next((ln.strip() for ln in cmd.splitlines() if ln.strip()), "")
        if not cmd:
            sys.stderr.write("Error: no command generated.\n")
            return 1
        print(cmd)
        sys.stdout.flush()
        if not (IS_TTY and sys.stdin.isatty()):
            return 0  # non-interactive: caller pipes to bash explicitly
        try:
            ans = input(rl_wrap(f"\n{C.YELLOW}Run this command? [y/N]{C.RESET} ")).strip().lower()
        except (EOFError, KeyboardInterrupt):
            ans = ""
        if ans not in ("y", "yes"):
            print("Not running.")
            return 0
        try:
            subprocess.run(cmd, shell=True)
        except Exception as e:
            sys.stderr.write(f"Error running command: {e}\n")
            return 1
        return 0

    _CMD_DISPATCH = {
        "/n": "_cmd_new", "/h": "_cmd_history", "/l": "_cmd_load", "/p": "_cmd_paste",
        "/t": "_cmd_tools", "/sk": "_cmd_skill", "/m": "_cmd_model", "/b": "_cmd_backend",
        "/r": "_cmd_regen", "/d": "_cmd_diff",
        "/new": "_cmd_new", "/continue": "_cmd_continue", "/tools": "_cmd_tools", "/strategy": "_cmd_strategy", "/think": "_cmd_think", "/skill": "_cmd_skill", "/multi": "_cmd_multi",
        "/history": "_cmd_history", "/load": "_cmd_load", "/delete": "_cmd_delete", "/save": "_cmd_save", "/sessions": "_cmd_sessions", "/session": "_cmd_session", "/unsave": "_cmd_unsave", "/import": "_cmd_import", "/prune": "_cmd_prune",
        "/search": "_cmd_search", "/export": "_cmd_export", "/backup": "_cmd_backup", "/model": "_cmd_model", "/models": "_cmd_models",
        "/backends": "_cmd_backends", "/backend": "_cmd_backend", "/profile": "_cmd_profile",
        "/status": "_cmd_status", "/copy": "_cmd_copy", "/paste": "_cmd_paste",
        "/speak": "_cmd_speak", "/share": "_cmd_share", "/expand": "_cmd_expand", "/last": "_cmd_expand", "/fold": "_cmd_fold", "/graphify": "_cmd_graphify", "/process": "_cmd_process", "/clear": "_cmd_clear",
        "/setup": "_cmd_setup", "/update": "_cmd_update", "/config": "_cmd_config",
        "/system": "_cmd_system", "/server": "_cmd_server", "/cost": "_cmd_cost",
        "/undo": "_cmd_undo", "/show": "_cmd_show", "/rename": "_cmd_rename",
        "/tokens": "_cmd_tokens", "/diff": "_cmd_diff", "/compact": "_cmd_compact",
        "/regen": "_cmd_regen", "/retry": "_cmd_regen",
        "/tune": "_cmd_tune",
        "/context": "_cmd_context", "/bench": "_cmd_bench",
    }

    # Toggle commands that accept a unified boolean: bare = flip,
    # explicit on|off|true|false = set. (cmd, config_key)
    TOGGLES = {
        "/tools": "tools_enabled", "/strategy": "strategy_first",
        "/think": "extended_thinking", "/multi": "multi_line",
        "/fold": "fold_long_blocks",
    }

    def _execute_command(self, cmd_str):
        parts = shlex.split(cmd_str)
        if not parts: return
        cmd = parts[0].lower().rstrip(".,;:!?")
        args = parts[1:]
        # Unified boolean grammar: '/<toggle> on|off|true|false' sets,
        # bare '/<toggle>' flips. Commands with their own richer args
        # (/process on|off|auto) are untouched.
        if cmd in self.TOGGLES and len(args) == 1 and args[0].lower() in ("on", "off", "true", "false"):
            key = self.TOGGLES[cmd]
            val = args[0].lower() in ("on", "true")
            if key == "multi_line":
                self.multi_line = val
            self.cfg.set(key, val)
            label = cmd.lstrip("/")
            extra = "  (Enter once sends; Enter on an empty line submits multi-line input)" if (key == "multi_line" and val) else ""
            self.success(f"{label}: {'ON' if val else 'OFF'}{extra}")
            return
        mname = self._CMD_DISPATCH.get(cmd)
        if mname:
            getattr(self, mname)(args)
        elif cmd in ("/exit", "/quit"):
            sys.exit(0)
        elif cmd == "/help":
            self.print_help()
        else:
            self.warn(f"Unknown command: {cmd}. Type /help for options.")

    def main_loop(self):
        self.print_startup_status()
        days = self.cfg.get("prune_days", 0) or 0
        if days > 0:
            n = self.db.prune_old(days)
            if n:
                print(f"{C.DIM}[Pruned {n} old unpinned session(s) (>{days}d old).]{C.RESET}")
        self._maybe_resume()
        
        last_ctrl_c = 0.0
        
        while True:
            try:
                # Safety net: never render the prompt over a still-spinning
                # indicator (an empty/broken reply can leave self.spinner running).
                if self.spinner: self.spinner.stop(); self.spinner = None
                try:
                    b_name, b_prof = self.cfg.active_profile()
                    b_model = b_prof.get("model", "N/A")[:12] if b_prof else "N/A"
                except:
                    b_name, b_model = "none", "N/A"
                
                tok_count = self.db.get_conv_tokens(self.cid) if self.cid else 0
                # Mode is always visible (green BUILD = writes allowed, dim PLAN =
                # read-only) so you never act in the wrong mode by accident.
                if self.cfg.get("tools_enabled", False):
                    mode_s = f"{C.GREEN}BUILD{C.RESET}"
                else:
                    mode_s = "plan"
                # Multi-line input is visible in the prompt (¶) so a silent
                # config toggle can never surprise you with double-Enter.
                ml = "\u00b6" if self.multi_line else ""
                # Context pressure: % of the model's effective window in use.
                try:
                    _win = self._effective_window()
                    _pct = min(99, int(tok_count * 100 / _win)) if _win else 0
                    ctx_s = f" | {_pct}%" if tok_count else ""
                except Exception:
                    ctx_s = ""
                info_str = f"{C.DIM}[{b_name}:{b_model} | {mode_s} | {tok_count}t{ctx_s}{ml}]{C.RESET}"
                
                if self.multi_line:
                    prefix = f"{C.GREEN}┌─ {info_str}\n{C.GREEN}└─▸{C.RESET} "
                else:
                    prefix = f"{info_str} {C.GREEN}▸{C.RESET} "
                    
                user_input = input(rl_wrap(prefix)).strip()
                if not user_input: continue
                
                if self.multi_line:
                    buf = user_input + "\n"
                    while True:
                        line = input("   ")
                        if not line.strip(): break
                        buf += line + "\n"
                    user_input = buf.strip()

                if user_input.startswith("/"):
                    self._execute_command(user_input)
                else:
                    self._suggest_skill(user_input)
                    self._chat(user_input)

            except KeyboardInterrupt:
                now = time.time()
                if now - last_ctrl_c < 2.0:
                    print("\nExiting...")
                    sys.exit(0)
                else:
                    last_ctrl_c = now
                    print(f"\n{C.YELLOW}Press Ctrl+C again to exit.{C.RESET}")
                    if self.spinner: self.spinner.stop(); self.spinner = None
            except EOFError:
                print("\nGoodbye!")
                sys.exit(0)
            except Exception as e:
                _dbg_exc(e)
                self.err(f"Error: {e}")
