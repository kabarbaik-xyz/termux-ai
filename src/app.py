# ══ termux_ai.app ══ (fragment; merged by build.py)
def _dbg_exc(e):
    """Print a full traceback when AI_DEBUG is set; otherwise stay quiet (the
    caller still shows a one-line error). Set AI_DEBUG=1 to debug crashes."""
    if os.environ.get("AI_DEBUG"):
        import traceback
        traceback.print_exc()


class App:
    COMMANDS = ["/new", "/show", "/history", "/load", "/rename", "/delete", "/regen", "/retry", "/export", "/compact", "/search", "/undo", "/diff", "/cost", "/setup", "/update", "/backends", "/backend", "/model", "/profile", "/system", "/config", "/tools", "/strategy", "/think", "/skill", "/multi", "/tokens", "/status", "/copy", "/paste", "/speak", "/share", "/server", "/expand", "/last", "/fold", "/clear", "/help", "/exit", "/quit"]

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
        self._validate_config()
        self.setup_rl()
        self.spinner = None
        self._auto_approve_all = False
        self._auto_continue = False
        self.quiet = not IS_TTY  # suppress UI when stdout is piped (one-shot mode)
        self._errored = False  # set when a request fails (for one-shot exit codes)

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

    def _get_ollama_models(self):
        try:
            r = urllib.request.urlopen("http://localhost:11434/api/tags", timeout=2)
            data = json.loads(r.read().decode("utf-8"))
            return [m["name"] for m in data.get("models", [])]
        except Exception: return []

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
            self.info(f"Profile '{name}' configured!")

        elif choice == "3":
            key = input("Enter Anthropic API Key: ").strip()
            model = input("Enter Model ID [claude-3-5-sonnet-20241022]: ").strip() or "claude-3-5-sonnet-20241022"
            self.cfg.set_path("backends.anthropic", {"base_url": "https://api.anthropic.com/v1", "model": model, "api_key": key})
            self.cfg.set("backend", "anthropic")
            self.info("Anthropic configured!")
        else:
            self.warn(f"Invalid choice '{choice}'. Setup cancelled.")
            return

        try: self.backend = get_backend(self.cfg)
        except Exception as e: self.err(str(e))

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

            current_file = Path(__file__).resolve()
            old_code = current_file.read_text(encoding='utf-8')
            
            if new_code == old_code:
                self.info("Already up to date.")
                return
                
            backup = current_file.with_suffix('.bak')
            shutil.copy2(current_file, backup)
            current_file.write_text(new_code, encoding='utf-8')
            os.chmod(current_file, 0o755)
            self.success(f"Updated to v{m.group(1)}! Backup saved to {backup.name}. Please restart.")
        except Exception as e:
            self.err(f"Update failed: {e}")

    def setup_rl(self):
        if HAVE_READLINE:
            try:
                HIST_FILE.touch(exist_ok=True)
                readline.read_history_file(str(HIST_FILE))
                readline.set_history_length(1000)
                
                def completer(text, state):
                    cmds = [c for c in self.COMMANDS if c.startswith(text)]
                    if state < len(cmds):
                        return cmds[state]
                    return None
                readline.set_completer(completer)
                readline.set_completer_delims(' \t\n')
                readline.parse_and_bind("tab: complete")
            except Exception: pass

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
        if not IS_TTY: self.warn("Output is piped, UI disabled.")
        print(f"{C.DIM}----------------------------------------------------------{C.RESET}")

    def print_help(self):
        print(f"\n{C.BOLD}{C.CYAN}Termux AI Help{C.RESET}")
        print(f"{C.DIM}Version: {__version__}{C.RESET}\n")
        
        cats = {
            "Chat": [("/new", "Start new chat"), ("/show", "Show messages"), ("/regen", "Regenerate last reply"), ("/retry <m>", "Retry with a model"), ("/undo", "Undo last msg pair"), ("/multi", "Toggle multi-line")],
            "History": [("/history", "List chats"), ("/load <id>", "Load chat"), ("/rename <t>", "Rename chat"), ("/search <q>", "Search chats"), ("/export", "Export to md"), ("/delete <id>", "Delete chat")],
            "Skills": [("/skill", "List / run skills"), ("/skill new <n>", "Create a skill"), ("/skill seed", "Add example skills"), ("/skill auto", "Toggle auto-load skills")],
            "Context": [("/tokens", "Token usage"), ("/cost", "Cost estimate"), ("/compact", "Summarize to save tokens"), ("/diff", "Show git changes"), ("/strategy", "Toggle strategy-before-act"), ("/think", "Toggle extended thinking (Claude)")],
            "Config": [("/setup", "Setup wizard"), ("/backends", "List backends"), ("/backend <n>", "Switch backend"), ("/model <n>", "Set model"), ("/tools", "Build/Plan mode"), ("/system [p]", "View/set prompt"), ("/config [set k v]", "View/set config"), ("/profile", "Manage profiles"), ("/update", "Self-update")],
            "Utils": [("/status", "System & API status"), ("/copy", "Copy reply"), ("/paste", "Paste+send"), ("/speak", "TTS reply"), ("/share", "Share reply"), ("/server", "Local server: start/stop/pull"), ("/expand", "Full last reply (less)"), ("/last", "Alias: /expand"), ("/fold", "Fold long lists/tables"), ("/clear", "Clear screen"), ("/exit", "Quit")]
        }
        
        for cat, cmds in cats.items():
            print(f"{C.BOLD}{C.MAGENTA}{cat}{C.RESET}")
            for cmd, desc in cmds:
                print(f"  {C.CYAN}{cmd.ljust(15)}{C.RESET} {desc}")
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
        if all(c["name"] in Tools.SAFE_TOOLS for c in calls):
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
        print(f"\n{C.YELLOW}Task is long: {iters} iterations, {calls} tool calls so far.{C.RESET}")
        print(f"{C.DIM}[y] Yes  [a] Yes, don't ask again this task  [n] No{C.RESET}")
        try:
            choice = input("> ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            return False
        if choice == "a":
            self._auto_continue = True
            return True
        return choice in ("y", "")

    def _stream_tool_chat(self, msgs):
        self.spinner = None
        self._auto_continue = False  # reset per task: re-confirm long-task continuation each turn
        if not self.quiet:
            self.spinner = Spinner("thinking")
            self.spinner.start()
        fmt = None if self.quiet else MarkdownFormatter(fold=self.cfg.get("fold_long_blocks", True), fold_head=self.cfg.get("fold_head", 8))
        current_block = ""  # current text run; resets on each tool -> only the LAST run (the answer) is returned
        did_tools = False   # once any tool runs, later text is inter-step reasoning
        buf = []            # text buffered after the first tool, awaiting dim/normal render

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
                    flush(thinking=True)                        # preceding text was reasoning
                    current_block = ""                          # ...so it is not the saved answer
                    did_tools = True
                    if self.quiet: continue
                    if self.spinner: self.spinner.stop(); self.spinner = None
                    print(f"\n{C.GRAY}[Tool {event['current']}/{event['total']}] {event['name']}({json.dumps(event['args'])}){C.RESET}")
                elif et == "tool_result":
                    if self.quiet: continue
                    res = event['result']
                    if len(res) > 800: res = res[:800] + "..."
                    print(f"{C.DIM}{res}{C.RESET}\n")
                elif et == "notice":
                    if fmt: fmt.flush()
                    flush(thinking=True)
                    current_block = ""
                    if self.spinner: self.spinner.stop(); self.spinner = None
                    if not self.quiet:
                        print(f"{C.YELLOW}{event['content']}{C.RESET}")
                    if event.get("fatal"): break
            flush(thinking=False)                               # render the final answer (or empty)
            if fmt: fmt.flush()                                 # emit any markdown-buffered tail
            print()
            return current_block
        except Exception as e:
            if self.spinner: self.spinner.stop(); self.spinner = None
            self._errored = True
            _dbg_exc(e)
            if current_block or did_tools or buf:
                self.err("Connection dropped mid-reply (network hiccup). Nothing was saved - run /retry to regenerate with the same context.")
            elif self.quiet: sys.stderr.write(f"Error: {e}\n")
            else: self.err(f"Tool chat error: {e}")
            return ""
        finally:
            # Stop the spinner on EVERY exit -- a clean return with no streamed
            # events (empty/broken reply) would otherwise leave it spinning into
            # the next prompt and stack with it on small screens.
            if self.spinner: self.spinner.stop(); self.spinner = None

    def _chat(self, user_input, title=None):
        if not self.backend:
            self.err("No backend configured. Run /setup")
            return

        title_src = title or user_input
        user_input = self._attach_files(user_input)
        if not self.cid:
            self.cid = self.db.new_conv("New Chat", self.backend.profile.get("model", ""), self.cfg.get("backend", ""))
            first_line = title_src.strip().splitlines()[0] if title_src.strip() else "New Chat"
            self.db.rename_conv(self.cid, first_line[:30] + ("..." if len(first_line) > 30 else ""))

        model = self.backend.profile.get("model", "")
        self.db.save_msg(self.cid, "user", user_input, model, est_tok(user_input))
        self.last_user_msg = user_input

        sysp = self.cfg.system_prompt()
        if self.active_session_skills:
            sysp += "\n\n" + "\n\n".join(f"# Active skill: {n}\n{b}" for n, b in self.active_session_skills)
        if self.cfg.get("skill_autoload", False):
            cat = self.skills.catalog()
            if cat:
                sysp += "\n\n" + cat
        msgs = [{"role": "system", "content": sysp}]
        msgs.extend(self.db.get_msgs(self.cid))

        # Strategy-first: when enabled, ask the model to outline a strategy before
        # show it, and inject it so the model executes deliberately (less wandering).
        if self.cfg.get("strategy_first", False) and not self.quiet:
            strategy = self._make_strategy(title_src)
            if strategy:
                self._show_strategy(strategy)
                msgs[0]["content"] += ("\n\nYou committed to the strategy below for this "
                    "task — execute it step by step, reasoning briefly before each action; "
                    "revise only if a step becomes impossible:\n" + strategy)

        # AI ALWAYS uses tools. tools_enabled (Build Mode) only toggles write access.
        reply = self._stream_tool_chat(msgs)

        if reply:
            self.db.save_msg(self.cid, "assistant", reply, model, est_tok(reply))
            self.last_reply = reply
            if self.cfg.get("tts_replies", False): TermuxAPI.speak(reply)
            if self.cfg.get("show_tokens", True) and not self.quiet:
                print(f"{C.DIM}[{est_tok(reply)} tokens]{C.RESET}")
            # Auto-compact long conversations to stay within the context budget.
            if self.cfg.get("auto_compact", True) and not self.quiet \
                    and self.db.get_conv_tokens(self.cid) > self.cfg.get("auto_compact_threshold", 3000):
                self.info("Auto-compacting long conversation...")
                ok, cmsg = self._compact_conversation(self.cid)
                if ok: self.success(cmsg)

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
        spinner = Spinner("thinking") if (show and not self.quiet) else None
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
        "/new": "_cmd_new", "/tools": "_cmd_tools", "/strategy": "_cmd_strategy", "/think": "_cmd_think", "/skill": "_cmd_skill", "/multi": "_cmd_multi",
        "/history": "_cmd_history", "/load": "_cmd_load", "/delete": "_cmd_delete",
        "/search": "_cmd_search", "/export": "_cmd_export", "/model": "_cmd_model",
        "/backends": "_cmd_backends", "/backend": "_cmd_backend", "/profile": "_cmd_profile",
        "/status": "_cmd_status", "/copy": "_cmd_copy", "/paste": "_cmd_paste",
        "/speak": "_cmd_speak", "/share": "_cmd_share", "/expand": "_cmd_expand", "/last": "_cmd_expand", "/fold": "_cmd_fold", "/clear": "_cmd_clear",
        "/setup": "_cmd_setup", "/update": "_cmd_update", "/config": "_cmd_config",
        "/system": "_cmd_system", "/server": "_cmd_server", "/cost": "_cmd_cost",
        "/undo": "_cmd_undo", "/show": "_cmd_show", "/rename": "_cmd_rename",
        "/tokens": "_cmd_tokens", "/diff": "_cmd_diff", "/compact": "_cmd_compact",
        "/regen": "_cmd_regen", "/retry": "_cmd_regen",
    }

    def _execute_command(self, cmd_str):
        parts = shlex.split(cmd_str)
        if not parts: return
        cmd = parts[0].lower().rstrip(".,;:!?")
        args = parts[1:]
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
                info_str = f"{C.DIM}[{b_name}:{b_model} | {tok_count}t]{C.RESET}"
                
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
