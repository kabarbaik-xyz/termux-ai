# ══ termux_ai.app ══ (fragment; merged by build.py)
class App:
    COMMANDS = ["/new", "/show", "/history", "/load", "/rename", "/delete", "/regen", "/retry", "/export", "/compact", "/search", "/undo", "/diff", "/cost", "/setup", "/update", "/backends", "/backend", "/model", "/profile", "/system", "/config", "/tools", "/multi", "/tokens", "/status", "/copy", "/paste", "/speak", "/share", "/server", "/clear", "/help", "/exit", "/quit"]

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
        self._validate_config()
        self.setup_rl()
        self._ctrl_c_pressed = False
        self.spinner = None
        self._auto_approve_all = False
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
            "Context": [("/tokens", "Token usage"), ("/cost", "Cost estimate"), ("/compact", "Summarize to save tokens"), ("/diff", "Show git changes")],
            "Config": [("/setup", "Setup wizard"), ("/backends", "List backends"), ("/backend <n>", "Switch backend"), ("/model <n>", "Set model"), ("/tools", "Build/Plan mode"), ("/system [p]", "View/set prompt"), ("/config [set k v]", "View/set config"), ("/profile", "Manage profiles"), ("/update", "Self-update")],
            "Utils": [("/status", "System & API status"), ("/copy", "Copy reply"), ("/paste", "Paste+send"), ("/speak", "TTS reply"), ("/share", "Share reply"), ("/server", "Local server"), ("/clear", "Clear screen"), ("/exit", "Quit")]
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
            return True  # non-interactive one-shot: keep going (bounded by MAX_ITERATIONS)
        print(f"\n{C.YELLOW}Task is long: {iters} iterations, {calls} tool calls so far. Continue? [Y/n]{C.RESET}")
        try:
            return input("> ").strip().lower() in ("y", "")
        except (EOFError, KeyboardInterrupt):
            return False

    def _stream_tool_chat(self, msgs):
        self.spinner = None
        if not self.quiet:
            self.spinner = Spinner("thinking")
            self.spinner.start()
        fmt = None if self.quiet else MarkdownFormatter()
        full_reply = ""
        try:
            for event in self.backend.chat_with_tools(msgs, self._confirm_batch, self._continue_fn):
                et = event["type"]
                if et == "text":
                    if self.spinner: self.spinner.stop(); self.spinner = None
                    if fmt: fmt.feed(event["content"])
                    else: print(event["content"], end="", flush=True)
                    full_reply += event["content"]
                elif et == "tool_progress":
                    if self.quiet: continue
                    if self.spinner: self.spinner.stop(); self.spinner = None
                    print(f"\n{C.GRAY}[Tool {event['current']}/{event['total']}] {event['name']}({json.dumps(event['args'])}){C.RESET}")
                elif et == "tool_result":
                    if self.quiet: continue
                    res = event['result']
                    if len(res) > 200: res = res[:200] + "..."
                    print(f"{C.DIM}{res}{C.RESET}\n")
                elif et == "notice":
                    if self.spinner: self.spinner.stop(); self.spinner = None
                    if not self.quiet:
                        print(f"{C.YELLOW}{event['content']}{C.RESET}")
                    if event.get("fatal"): break
            if fmt: fmt.flush()
            print()
            return full_reply
        except Exception as e:
            if self.spinner: self.spinner.stop(); self.spinner = None
            self._errored = True
            if self.quiet: sys.stderr.write(f"Error: {e}\n")
            else: self.err(f"Tool chat error: {e}")
            return ""

    def _chat(self, user_input):
        if not self.backend:
            self.err("No backend configured. Run /setup")
            return

        title_src = user_input
        user_input = self._attach_files(user_input)
        if not self.cid:
            self.cid = self.db.new_conv("New Chat", self.backend.profile.get("model", ""), self.cfg.get("backend", ""))
            first_line = title_src.strip().splitlines()[0] if title_src.strip() else "New Chat"
            self.db.rename_conv(self.cid, first_line[:30] + ("..." if len(first_line) > 30 else ""))

        model = self.backend.profile.get("model", "")
        self.db.save_msg(self.cid, "user", user_input, model, est_tok(user_input))
        self.last_user_msg = user_input

        msgs = [{"role": "system", "content": self.cfg.system_prompt()}]
        msgs.extend(self.db.get_msgs(self.cid))

        # AI ALWAYS uses tools. tools_enabled (Build Mode) only toggles write access.
        reply = self._stream_tool_chat(msgs)

        if reply:
            self.db.save_msg(self.cid, "assistant", reply, model, est_tok(reply))
            self.last_reply = reply
            if self.cfg.get("tts_replies", False): TermuxAPI.speak(reply)
            # Auto-compact long conversations to stay within the context budget.
            if self.cfg.get("auto_compact", True) and not self.quiet \
                    and self.db.get_conv_tokens(self.cid) > self.cfg.get("auto_compact_threshold", 3000):
                self.info("Auto-compacting long conversation...")
                ok, cmsg = self._compact_conversation(self.cid)
                if ok: self.success(cmsg)

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

        fmt = MarkdownFormatter() if (show and not self.quiet and not json_mode) else None
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
            if self.quiet: sys.stderr.write(f"Error: {e}\n")
            else: self.err(str(e))
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
            ans = input(f"\n{C.YELLOW}Run this command? [y/N]{C.RESET} ").strip().lower()
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

    def _execute_command(self, cmd_str):
        parts = shlex.split(cmd_str)
        if not parts: return
        cmd = parts[0].lower().rstrip(".,;:!?")
        args = parts[1:]

        if cmd in ("/exit", "/quit"):
            sys.exit(0)
        elif cmd == "/help":
            self.print_help()
        elif cmd == "/new":
            self.cid = None
            self.success("Started new chat.")
        elif cmd == "/tools":
            v = not self.cfg.get("tools_enabled", False)
            self.cfg.set("tools_enabled", v)
            self.success(f"Tool mode: {'Build (Write/Read allowed)' if v else 'Plan (Read-only allowed)'}.")
        elif cmd == "/multi":
            v = not self.multi_line
            self.multi_line = v
            self.cfg.set("multi_line", v)
            self.success(f"Multi-line input {'enabled' if v else 'disabled'}.")
        elif cmd == "/history":
            convs = self.db.list_convs()
            if not convs: self.info("No history."); return
            for c in convs:
                print(f"{C.BOLD}{c['id']}{C.RESET}. [{c['msg_count']}] {c['title']} {C.DIM}({fmt_time(c['updated_at'])}){C.RESET}")
        elif cmd == "/load" and args:
            try: cid = int(args[0])
            except ValueError: self.err("Invalid ID."); return
            conv = self.db.get_conv(cid)
            if conv:
                self.cid = cid
                self.success(f"Loaded chat: {conv['title']}")
            else: self.err("Chat not found.")
        elif cmd == "/delete" and args:
            try: cid = int(args[0])
            except ValueError: self.err("Invalid ID."); return
            self.db.del_conv(cid)
            if self.cid == cid: self.cid = None
            self.success("Chat deleted.")
        elif cmd == "/search" and args:
            query = " ".join(args)
            results = self.db.search_convs(query)
            if not results: self.info("No matches found.")
            for r in results:
                print(f"{C.BOLD}{r['id']}{C.RESET}. {r['title']} {C.DIM}({r['model']}){C.RESET}")
        elif cmd == "/export":
            if not self.cid: self.warn("No active chat to export."); return
            conv = self.db.get_conv(self.cid)
            msgs = self.db.get_msgs(self.cid)
            safe_title = re.sub(r"[^\w\-.]", "_", conv['title'].strip()) or "chat"
            filename = f"chat_{self.cid}_{safe_title}.md"
            with open(filename, "w", encoding="utf-8") as f:
                f.write(f"# {conv['title']}\n\n")
                for m in msgs:
                    f.write(f"**{m['role'].capitalize()}:** {m['content']}\n\n")
            self.success(f"Exported chat to {filename}")
        elif cmd == "/model":
            name, prof = self.cfg.active_profile()
            if not args:
                self.info(f"Current model: {prof.get('model', 'N/A')}")
            else:
                self.cfg.set_path(f"backends.{name}.model", args[0])
                self.success(f"Model set to {args[0]}")
                self.backend = get_backend(self.cfg)
        elif cmd == "/backends":
            backends = self.cfg.get("backends", {})
            active = self.cfg.get("backend", "ollama")
            self.info("Available backends:")
            for b in backends:
                marker = f"{C.GREEN}*{C.RESET}" if b == active else " "
                b_model = backends[b].get("model", "N/A")
                print(f"  {marker} {C.BOLD}{b}{C.RESET} {C.DIM}({b_model}){C.RESET}")
        elif cmd == "/backend":
            if not args:
                self.warn("Usage: /backend <name> to switch active backend.")
            else:
                name = args[0]
                backends = self.cfg.get("backends", {})
                if name in backends:
                    self.cfg.set("backend", name)
                    self.backend = get_backend(self.cfg)
                    self.success(f"Switched to backend: {name}")
                else:
                    self.err(f"Backend '{name}' not found. Use /backends to see available options.")
        elif cmd == "/profile":
            if not args:
                self.info("Usage: /profile <set|add|list>")
                self.info("  /profile list")
                self.info("  /profile set <name>.<key> <value>")
                self.info("  /profile add <name> <base_url> <model> [api_key]")
            elif args[0] == "list":
                print(json.dumps(self.cfg.masked_dict().get("backends", {}), indent=2))
            elif args[0] == "set" and len(args) >= 3:
                key, val = args[1], " ".join(args[2:])
                self.cfg.set_path(f"backends.{key}", parse_value(val))
                self.success(f"Set {key} = {val}")
                self.backend = get_backend(self.cfg)
            elif args[0] == "add" and len(args) >= 4:
                name, base, model = args[1], args[2], args[3]
                key = args[4] if len(args) > 4 else ""
                self.cfg.set_path(f"backends.{name}", {"base_url": base, "model": model, "api_key": key})
                self.success(f"Added profile '{name}'.")
            else:
                self.warn("Invalid profile command.")
        elif cmd == "/status":
            st = TermuxAPI.status()
            print(f"{C.BOLD}Termux API:{C.RESET} TTS: {'✓' if st['tts'] else '✗'}, Clipboard: {'✓' if st['clipboard'] else '✗'}, Share: {'✓' if st['share'] else '✗'}")
            name, prof = self.cfg.active_profile()
            print(f"{C.BOLD}Backend:{C.RESET} {name} ({prof.get('model', 'N/A')})")
            print(f"{C.BOLD}Tools:{C.RESET} {'Build Mode' if self.cfg.get('tools_enabled') else 'Plan Mode'}")
        elif cmd == "/copy":
            if self.last_reply: TermuxAPI.copy(self.last_reply); self.success("Copied to clipboard.")
            else: self.warn("Nothing to copy.")
        elif cmd == "/paste":
            text = TermuxAPI.paste()
            if text: self._chat(text)
            else: self.warn("Clipboard empty.")
        elif cmd == "/speak":
            if self.last_reply: TermuxAPI.speak(self.last_reply)
            else: self.warn("Nothing to speak.")
        elif cmd == "/share":
            if self.last_reply: TermuxAPI.share(self.last_reply)
            else: self.warn("Nothing to share.")
        elif cmd == "/clear":
            os.system('clear' if os.name != 'nt' else 'cls')
        elif cmd == "/setup":
            self._run_setup("")
        elif cmd == "/update":
            self._self_update()
        elif cmd == "/config":
            if args and args[0] == "set" and len(args) >= 3:
                key = args[1]
                val = parse_value(" ".join(args[2:]))
                self.cfg.set_path(key, val)
                if key.split(".")[0] in ("backend", "backends"):
                    try: self.backend = get_backend(self.cfg)
                    except Exception as e: self.err(str(e))
                self.success(f"Set {key} = {val}")
            elif args and args[0] == "get" and len(args) >= 2:
                v = self.cfg.get(args[1])
                print(json.dumps(v, indent=2) if not isinstance(v, str) else v)
            else:
                print(json.dumps(self.cfg.masked_dict(), indent=2))
        elif cmd == "/system":
            if args:
                self.cfg.set("system_instruction", " ".join(args))
                self.success("System prompt updated.")
            else:
                sp = self.cfg.system_prompt()
                self.info("System prompt:" + (f"\n{sp}" if sp else " (using built-in default)"))
        elif cmd == "/server":
            if not args:
                self.warn("Usage: /server <start|stop|status>")
            else:
                ServerManager.manage(args[0])
        elif cmd == "/cost":
            by_model = self.db.get_tokens_by_model()
            if not by_model:
                self.info("No token usage recorded yet.")
                return
            total_t, total_c = 0, 0.0
            print(f"{C.BOLD}{'model':<26}{'tokens':>10}{'est. $':>10}{C.RESET}")
            for mdl, toks in sorted(by_model.items(), key=lambda x: -x[1]):
                total_t += toks
                cost = toks / 1000.0 * self._match_price(mdl)
                total_c += cost
                print(f"{(mdl or '?'):<26}{toks:>10}{cost:>10.4f}")
            print(f"{C.BOLD}{'TOTAL':<26}{total_t:>10}{total_c:>10.4f}{C.RESET}")
            print(f"{C.DIM}(estimate from the built-in price table; real spend varies by vendor){C.RESET}")
        elif cmd == "/undo":
            if self.cid:
                self.db.undo_last_msg_pair(self.cid)
                self.success("Undid last message pair.")
            else: self.warn("No active chat.")
        elif cmd == "/show":
            if not self.cid: self.warn("No active chat."); return
            conv = self.db.get_conv(self.cid)
            msgs = self.db.get_msgs(self.cid, limit=1000)
            print(f"\n{C.BOLD}#{self.cid} {conv['title']}{C.RESET}")
            for mm in msgs:
                col = C.GREEN if mm["role"] == "user" else (C.CYAN if mm["role"] == "assistant" else C.GRAY)
                print(f"\n{col}{C.BOLD}{mm['role'].capitalize()}:{C.RESET} {mm['content']}")
            print()
        elif cmd == "/rename":
            if not self.cid: self.warn("No active chat."); return
            if not args: self.info(f"Current title: {self.db.get_conv(self.cid)['title']}"); return
            title = " ".join(args)
            self.db.rename_conv(self.cid, title)
            self.success(f"Renamed to: {title}")
        elif cmd == "/tokens":
            if not self.cid: self.warn("No active chat."); return
            self.info(f"This chat: {self.db.get_conv_tokens(self.cid)} tokens | All chats: {self.db.get_total_tokens()} tokens")
        elif cmd == "/diff":
            try:
                r = subprocess.run(["git", "diff", "HEAD"], capture_output=True, text=True, timeout=15)
                out = r.stdout.strip()
                if out: print(out)
                else: self.info("No uncommitted changes (relative to HEAD).")
                if r.stderr.strip(): print(f"{C.DIM}{r.stderr.strip()}{C.RESET}")
            except FileNotFoundError: self.err("git not found.")
            except Exception as e: self.err(str(e))
        elif cmd == "/compact":
            if not self.cid: self.warn("No active chat."); return
            if not self.backend: self.err("No backend configured."); return
            self.info("Compacting conversation...")
            ok, cmsg = self._compact_conversation(self.cid)
            (self.success if ok else self.warn)(cmsg)
        elif cmd in ("/regen", "/retry"):
            if self.cid and self.last_user_msg:
                if cmd == "/retry" and args:
                    self._override_model(args[0])
                    self.success(f"Retrying with model {args[0]}.")
                self.db.undo_last_msg_pair(self.cid)
                self._chat(self.last_user_msg)
            else: self.warn("Nothing to regenerate.")
        else:
            self.warn(f"Unknown command: {cmd}. Type /help for options.")

    def main_loop(self):
        self.print_startup_status()
        
        last_ctrl_c = 0.0
        
        while True:
            try:
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
                    
                user_input = input(prefix).strip()
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
                self.err(f"Error: {e}")
