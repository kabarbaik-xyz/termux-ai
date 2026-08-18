class App:  # BUILD-SHIM: stripped by build.py at merge (lets this class-body fragment compile standalone)
    # ---- slash-command handlers (dispatched by App._execute_command via _CMD_DISPATCH).
    # Each takes (self, args) where args is the list of tokens after the command.

    def _cmd_new(self, args):
        self.cid = None
        self._clear_last_cid()
        self.success("Started new chat.")

    def _cmd_tools(self, args):
        v = not self.cfg.get("tools_enabled", False)
        self.cfg.set("tools_enabled", v)
        self.success(f"Tool mode: {'Build (Write/Read allowed)' if v else 'Plan (Read-only allowed)'}.")

    def _cmd_strategy(self, args):
        v = not self.cfg.get("strategy_first", False)
        self.cfg.set("strategy_first", v)
        self.success(f"Strategy-first mode {'ON (model outlines a strategy before acting)' if v else 'OFF'}.")

    def _cmd_context(self, args):
        """/context          — show the project memory file (CONTEXT.md)
        /context init     — create a starter CONTEXT.md in the cwd (skips if present)
        /context edit     — open it in $EDITOR (or nano/vi)
        /context refresh  — drop the session cache (auto-refreshes on mtime change anyway)
        /context off      — stop attaching it for this session"""
        sub = args[0].lower() if args else ""
        path = next((c for c in (Path("CONTEXT.md"), Path(".ai/context.md")) if c.is_file()), None)
        if sub == "init":
            if path:
                self.info(f"{path} already exists."); return
            starter = ("# Project context\n\n## What this is\n(one sentence)\n\n## Stack\n"
                       "- \n\n## Structure\n- \n\n## Conventions\n- \n\n## Gotchas / decisions\n- \n")
            try:
                Path("CONTEXT.md").write_text(starter)
                self._ctx_cache = None
                self.success("Created CONTEXT.md — it's attached to every message now. Fill it in or ask the AI to.")
            except OSError as e:
                self.err(f"Could not write CONTEXT.md: {e}")
            return
        if sub == "off":
            self._ctx_disabled = True
            self.success("CONTEXT.md attachment disabled for this session.")
            return
        if sub == "refresh":
            self._ctx_cache = None
            self.success("Context cache dropped; re-read on the next message.")
            return
        if sub == "edit":
            if not path:
                self.warn("No CONTEXT.md here. /context init first."); return
            import subprocess as _sp
            ed = os.environ.get("EDITOR", "")
            ed = ed if ed else next((e for e in ("nano", "vim", "vi") if shutil.which(e)), "vi")
            _sp.run([ed, str(path)])
            self._ctx_cache = None
            return
        if not path:
            self.info("No CONTEXT.md in this directory. It's a project-memory file attached to "
                      "every message (stack, structure, conventions, gotchas) so sessions don't "
                      "re-discover the project each time.")
            self.info("  /context init   — create a starter file")
            return
        body = self._project_context() or "(empty)"
        n = len(body.splitlines())
        self.info(f"{path} ({n} lines) — attached to every message this session:")
        print(body[:4000])

    def _cmd_tune(self, args):
        """Per-model auto-tuning report + optional manual override.
        /tune                  show the active model's detected profile & effective values
        /tune <key> <value>    set a per-model override (config model_tuning.<model>.<key>)
        /tune reset            remove overrides for the active model"""
        if not self.backend:
            self.err("No backend configured."); return
        name = self.backend._model()
        prof = getattr(self.backend, "profile", {}) or {}
        caps = self.backend._ollama_caps(name) if hasattr(self.backend, "_ollama_caps") else None
        source = "/api/show" if caps else "registry"
        thinking = is_thinking_model(name, caps)
        kind = "reasoning" if thinking else "non-thinking"
        t = self.backend._tuning()
        ovr = (self.cfg.get("model_tuning") or {}).get(name.lower(), {})

        if args and args[0].lower() in ("reset", "clear"):
            if ovr:
                (self.cfg.get("model_tuning") or {}).pop(name.lower(), None)
                self.cfg.save()
                self.success(f"Cleared manual overrides for {name}.")
            else:
                self.info(f"No manual overrides for {name}.")
            return

        if len(args) >= 2:
            key, val = args[0], args[1]
            if key not in TUNING_KEYS:
                self.err(f"Unknown tuning key: {key}. Valid: {', '.join(TUNING_KEYS)}")
                return
            if val.lower() in ("true", "false"):
                val = val.lower() == "true"
            else:
                try: val = float(val)
                except ValueError: pass
            mt = self.cfg.get("model_tuning") or {}
            mt.setdefault(name.lower(), {})[key] = val
            self.cfg.set("model_tuning", mt)
            self.success(f"{name}: {key} = {val} (manual override, applies to this model on local and cloud).")
            return

        self.info(f"Model: {C.BOLD}{name}{C.RESET} ({kind}; detected via {source})")
        self.info(f"Backend: {self.backend.name} | local: {self.backend.is_local} | ollama: {self.backend.is_ollama}")
        rows = [("thinking", thinking), ("native route", self.backend._native_ollama() if self.backend.is_ollama else "n/a"),
                ("schema mode", self.backend._schema_mode())]
        for key in ("temperature", "num_ctx", "max_tokens", "ollama_max_tokens", "ollama_keep_alive",
                    "strategy_first", "gather_first", "compact_schemas", "ollama_no_think"):
            if key in ("num_ctx", "ollama_no_think", "ollama_max_tokens", "ollama_keep_alive") and not self.backend.is_ollama: continue
            v = self.backend._eff(key)
            rows.append((key, v))
        for k, v in rows:
            mark = "  (override)" if k in ovr else ("  (registry)" if k in t else "  (global)")
            print(f"  {k:<18} {C.DIM}{mark}{C.RESET} {v if v is not None else '(unset)'}")
        self.info("Auto-tuning is on by default. Override only if needed: /tune <key> <value>")

    def _cmd_think(self, args):
        v = not self.cfg.get("extended_thinking", False)
        self.cfg.set("extended_thinking", v)
        name, _ = self.cfg.active_profile()
        extra = "" if name in ("anthropic", "claude") else " (only the Anthropic backend uses this)"
        self.success(f"Extended thinking {'ON' + extra if v else 'OFF'}.")

    def _cmd_skill(self, args):
        # /skill              list
        # /skill <name> [x]   run (once) or toggle (session)
        # /skill off          clear session skills
        # /skill show|edit|new|seed ...
        if not args or args[0] in ("list", "ls"):
            items = self.skills.list()
            if not items:
                self.info("No skills yet. Create one with /skill new <name>, or /skill seed for examples.")
                return
            active = {n for n, _ in self.active_session_skills}
            for nm, meta in items:
                mark = f"{C.GREEN}*{C.RESET}" if nm in active else " "
                desc = meta.get("description", "")
                if len(desc) > 66: desc = desc[:63] + "..."
                print(f"  {mark} {C.BOLD}{nm}{C.RESET} {C.DIM}[{meta.get('mode','once')}]{C.RESET} {desc}")
            return
        sub = args[0]
        if sub == "off":
            if self.active_session_skills:
                self.active_session_skills.clear()
                self.success("Cleared all session skills.")
            else: self.info("No session skills active.")
            return
        if sub == "seed":
            written = self.skills.seed()
            self.success("Seeded examples: " + (", ".join(written) if written else "(all already present)") + ".")
            return
        if sub == "auto":
            v = not self.cfg.get("skill_autoload", False)
            self.cfg.set("skill_autoload", v)
            self.success("Skill auto-load " + ("ON (skill descriptions added to every prompt; a capable model can read_file the matching skill on its own)" if v else "OFF") + ".")
            return
        if sub == "show" and len(args) >= 2:
            meta, body = self.skills.load(args[1])
            if meta is None: self.err(f"No skill '{args[1]}'."); return
            print(f"{C.BOLD}#{meta.get('name', args[1])}{C.RESET} {C.DIM}[{meta.get('mode','once')}]{C.RESET}")
            print(meta.get("description", ""))
            print(f"\n{body}")
            return
        if sub == "edit" and len(args) >= 2:
            self._edit_skill(args[1]); return
        if sub == "new" and len(args) >= 2:
            self._new_skill(args[1]); return
        # default: run skill <name> [args...]
        meta, body = self.skills.load(sub)
        if meta is None:
            self.err(f"No skill '{sub}'. Use /skill list."); return
        if meta.get("mode", "once") == "session":
            names = [n for n, _ in self.active_session_skills]
            if sub in names:
                self.active_session_skills = [(n, b) for n, b in self.active_session_skills if n != sub]
                self.success(f"Session skill '{sub}' OFF.")
            else:
                self.active_session_skills.append((sub, body))
                self.success(f"Session skill '{sub}' ON (applies to the rest of this session; /skill off clears).")
            return
        if not self.backend: self.err("No backend configured."); return
        extra = " ".join(args[1:]) if len(args) > 1 else ""
        prompt = body + ("\n\n" + extra if extra else "")
        title = f"/skill {sub}" + (f" {extra[:20]}" if extra else "")
        self._chat(prompt, title=title)

    def _new_skill(self, name):
        if not Skills.valid_name(name):
            self.err("Invalid skill name: use lowercase, digits, single hyphens (e.g. code-review)."); return
        self.skills.ensure_dir()
        p = self.skills.path_for(name)
        if p.exists(): self.warn(f"Skill '{name}' already exists."); return
        p.write_text(
            "---\nname: %s\ndescription: What this skill does and when to use it.\nmode: once\n---\n"
            "Write the skill's instructions here.\n" % name, encoding="utf-8")
        self.success(f"Created {p}.")
        self._edit_skill(name)

    def _edit_skill(self, name):
        editor = os.environ.get("EDITOR") or os.environ.get("VISUAL")
        if not editor:
            self.warn("Set $EDITOR to edit skills (e.g. `export EDITOR=nano`)."); return
        p = self.skills.path_for(name)
        if not p.exists():
            p = self.skills._discover().get(name)
            if not p: self.err(f"No skill '{name}'."); return
        try: subprocess.run([editor, str(p)])
        except Exception as e: self.err(str(e))

    def _cmd_multi(self, args):
        v = not self.multi_line
        self.multi_line = v
        self.cfg.set("multi_line", v)
        self.success(f"Multi-line input {'enabled' if v else 'disabled'}.")

    def _cmd_history(self, args):
        convs = self.db.list_convs()
        if not convs: self.info("No history."); return
        for c in convs:
            print(f"{C.BOLD}{c['id']}{C.RESET}. [{c['msg_count']}] {c['title']} {C.DIM}({fmt_time(c['updated_at'])}){C.RESET}")

    def _cmd_save(self, args):
        if not self.cid: self.warn("No active session to save. Send a message first."); return
        conv = self.db.get_conv(self.cid)
        name = " ".join(args).strip() or conv["title"]
        self.db.rename_conv(self.cid, name)
        self.db.set_pinned(self.cid, 1)
        self.success(f"Saved session as \"{name}\" (pinned). Resume with /load {self.cid} or /load {name}")

    def _cmd_unsave(self, args):
        if not self.cid: self.warn("No active session."); return
        self.db.set_pinned(self.cid, 0)
        self.success("Removed session bookmark (chat kept).")

    def _cmd_sessions(self, args):
        rows = self.db.list_sessions(limit=50)
        if not rows:
            self.info("No sessions yet. Send a message to start one.")
            return
        print(f"{C.BOLD}Saved & recent sessions (● = pinned):{C.RESET}")
        for r in rows:
            pin = f"{C.GREEN}●{C.RESET}" if r["pinned"] else " "
            title = (r["title"] or "(untitled)").strip()
            if len(title) > 42: title = title[:39] + "..."
            model = (r["model"] or "").strip()
            model_s = f" [{model}]" if model else ""
            ago = self._ago(r["updated_at"])
            print(f" {pin} {C.BOLD}{r['id']}{C.RESET}. {title} {C.DIM}({r['msg_count']} msg, last {ago}{model_s}){C.RESET}")

    def _cmd_continue(self, args):
        cid = self._get_last_cid()
        conv = self.db.get_conv(cid) if cid else None
        if conv:
            self._activate(cid, banner=True)
        else:
            self.warn("No previous session to continue. Send a message to start one.")

    def _cmd_load(self, args):
        if not args: self.warn("Usage: /load <id|name>"); return
        arg = " ".join(args).strip()
        if arg.isdigit():
            cid = int(arg)
            conv = self.db.get_conv(cid)
            if not conv: self.err("Chat not found."); return
        else:
            results = self.db.search_convs(arg)
            if not results:
                self.err(f"No session matching \"{arg}\"."); return
            cid = results[0]["id"]
            conv = self.db.get_conv(cid)
        self.cid = cid
        self._persist_session()
        self.success(f"Loaded chat: {conv['title']}")

    def _cmd_delete(self, args):
        if not args: self.warn("Usage: /delete <id>"); return
        try: cid = int(args[0])
        except ValueError: self.err("Invalid ID."); return
        self.db.del_conv(cid)
        if self.cid == cid: self.cid = None
        if self._get_last_cid() == cid: self._clear_last_cid()
        self.success("Chat deleted.")

    def _cmd_search(self, args):
        if not args: self.warn("Usage: /search <query>"); return
        query = " ".join(args)
        results = self.db.search_convs(query)
        if not results: self.info("No matches found.")
        for r in results:
            print(f"{C.BOLD}{r['id']}{C.RESET}. {r['title']} {C.DIM}({r['model']}){C.RESET}")

    def _cmd_export(self, args):
        if not self.cid: self.warn("No active chat to export."); return
        conv = self.db.get_conv(self.cid)
        msgs = self.db.get_msgs(self.cid)
        if args:
            filename = os.path.expanduser(" ".join(args))   # /export <path>
        else:
            safe_title = re.sub(r"[^\w\-.]", "_", conv['title'].strip()) or "chat"
            filename = f"chat_{self.cid}_{safe_title}.md"
        try:
            with open(filename, "w", encoding="utf-8") as f:
                f.write(f"# {conv['title']}\n\n")
                for m in msgs:
                    f.write(f"**{m['role'].capitalize()}:** {m['content']}\n\n")
            self.success(f"Exported chat to {filename}")
        except OSError as e:
            self.err(f"Could not write {filename}: {e}")

    def _cmd_model(self, args):
        name, prof = self.cfg.active_profile()
        if not args:
            self.info(f"Current model: {prof.get('model', 'N/A')}")
        else:
            self.cfg.set_path(f"backends.{name}.model", args[0])
            self.success(f"Model set to {args[0]}")
            self.backend = get_backend(self.cfg)
            if self.cid:
                n = len(self.db.get_msgs(self.cid))
                self.info(f"Context preserved: {n} message(s) stay in this chat for the new model.")

    def _cmd_backends(self, args):
        backends = self.cfg.get("backends", {})
        active = self.cfg.get("backend", "ollama")
        self.info("Available backends:")
        for b in backends:
            marker = f"{C.GREEN}*{C.RESET}" if b == active else " "
            b_model = backends[b].get("model", "N/A")
            print(f"  {marker} {C.BOLD}{b}{C.RESET} {C.DIM}({b_model}){C.RESET}")

    def _cmd_models(self, args):
        """List local Ollama models with size, capabilities, and a num_ctx
        suggestion based on free RAM (helps avoid the Android OOM killer)."""
        name, prof = self.cfg.active_profile()
        base = (prof.get("base_url") or "").rstrip("/")
        if not base or ("localhost" not in base and "127.0.0.1" not in base):
            self.err("Active backend isn't a local Ollama server.")
            self.info("Switch with /backend <name>, or list with /backends.")
            return
        base = base[:-3] if base.endswith("/v1") else base
        try:
            with urllib.request.urlopen(base + "/api/tags", timeout=8) as r:
                models = (json.loads(r.read()) or {}).get("models", [])
        except Exception as e:
            self.err(f"Can't reach Ollama at {base}: {e}"); return
        if not models:
            self.info("No models pulled yet. Try: ollama pull qwen3:1.7b"); return
        active = (prof.get("model") or "").lower()
        self.info(f"Local Ollama models ({len(models)}):")
        for mm in sorted(models, key=lambda x: x.get("size", 0)):
            nm = mm.get("name", "?"); gb = mm.get("size", 0) / 1e9
            caps = self.backend._ollama_caps(nm) if hasattr(self.backend, "_ollama_caps") else []
            flags = ", ".join(f for f, k in (("reasoning", "thinking"), ("tools", "tools")) if k in caps) or "chat"
            mark = f" {C.GREEN}\u2190 active{C.RESET}" if nm.lower().startswith(active) else ""
            print(f"  {nm:<26} {gb:5.1f} GB  [{flags}]{mark}")
        free = _free_ram_gb()
        if free is None: return
        am = next((mm for mm in models if mm.get("name", "").lower().startswith(active)), None)
        mgb = (am.get("size", 0) / 1e9) if am else 0
        sugg = _suggest_num_ctx(free, mgb); cur = self.cfg.get("num_ctx", 0) or 0
        self.info("")
        self.info(f"Free RAM: {free:.1f} GB  |  headroom after model load: ~{max(0, free - mgb - 0.5):.1f} GB")
        self.info(f"Suggested num_ctx: {sugg}  (current: {cur or 'default'})")
        if not cur:
            self.info(f"  Set with: {C.CYAN}/config set num_ctx {sugg}{C.RESET}")
        # max_tokens heads-up: a high cap on a slow phone CPU is the other half
        # of "stuck in thinking" (8192 tokens @ ~6 tok/s = ~20 min worst case).
        # Suggest the LOCAL-ONLY override so it doesn't cap cloud backends.
        mt = self.cfg.get("max_tokens", 4096) or 4096
        if mt > 2048:
            self.info(f"max_tokens: {mt} \u2014 high for phone CPU. Cap local only (cloud unaffected): {C.CYAN}/config set ollama_max_tokens 2048{C.RESET}")

    def _cmd_backend(self, args):
        if not args:
            self.warn("Usage: /backend <name> to switch active backend.")
        else:
            name = args[0]
            backends = self.cfg.get("backends", {})
            if name in backends:
                self.cfg.set("backend", name)
                self.backend = get_backend(self.cfg)
                self.success(f"Switched to backend: {name}")
                if self.cid:
                    self.info(f"Context preserved: {len(self.db.get_msgs(self.cid))} message(s) stay in this chat.")
            else:
                self.err(f"Backend '{name}' not found. Use /backends to see available options.")

    def _cmd_profile(self, args):
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
            if key.endswith(".api_key"):
                self._warn_plaintext_key(key.split(".")[-2] if "." in key else "", val)
            self.success(f"Set {key} = {val}")
            self.backend = get_backend(self.cfg)
        elif args[0] == "add" and len(args) >= 4:
            name, base, model = args[1], args[2], args[3]
            key = args[4] if len(args) > 4 else ""
            self.cfg.set_path(f"backends.{name}", {"base_url": base, "model": model, "api_key": key})
            self._warn_plaintext_key(name, key)
            self.success(f"Added profile '{name}'.")
        else:
            self.warn("Invalid profile command.")

    def _cmd_status(self, args):
        st = TermuxAPI.status()
        print(f"{C.BOLD}Termux API:{C.RESET} TTS: {'✓' if st['tts'] else '✗'}, Clipboard: {'✓' if st['clipboard'] else '✗'}, Share: {'✓' if st['share'] else '✗'}")
        name, prof = self.cfg.active_profile()
        print(f"{C.BOLD}Backend:{C.RESET} {name} ({prof.get('model', 'N/A')})")
        print(f"{C.BOLD}Tools:{C.RESET} {'Build Mode' if self.cfg.get('tools_enabled') else 'Plan Mode'} | Strategy-first: {'ON' if self.cfg.get('strategy_first') else 'off'} | Thinking: {'ON' if self.cfg.get('extended_thinking') else 'off'} | Skills: {len(self.active_session_skills)} active{' (autoload)' if self.cfg.get('skill_autoload') else ''}")

    def _cmd_copy(self, args):
        if self.last_reply: TermuxAPI.copy(self.last_reply); self.success("Copied to clipboard.")
        else: self.warn("Nothing to copy.")

    def _cmd_paste(self, args):
        text = TermuxAPI.paste()
        if text: self._chat(text)
        else: self.warn("Clipboard empty.")

    def _cmd_speak(self, args):
        if self.last_reply: TermuxAPI.speak(self.last_reply)
        else: self.warn("Nothing to speak.")

    def _cmd_share(self, args):
        if self.last_reply: TermuxAPI.share(self.last_reply)
        else: self.warn("Nothing to share.")

    def _cmd_fold(self, args):
        if not args:
            self.info(f"Folding long lists/tables: {'ON' if self.cfg.get('fold_long_blocks', True) else 'OFF'} (head {self.cfg.get('fold_head', 8)}). Use /fold on|off.")
            return
        v = args[0].lower() in ("on", "true", "1", "yes")
        self.cfg.set("fold_long_blocks", v)
        self.success(f"Folding long lists/tables {'ON' if v else 'OFF'}.")

    def _cmd_expand(self, args):
        if not self.last_reply:
            self.warn("No last reply to expand."); return
        if IS_TTY and shutil.which("less"):
            try:
                subprocess.run(["less", "-R"], input=self.last_reply); return
            except Exception:
                pass
        print(self.last_reply)

    def _cmd_clear(self, args):
        os.system('clear' if os.name != 'nt' else 'cls')

    def _cmd_graphify(self, args):
        """Run graphify directly — no model round-trip needed."""
        path = args[0] if args and not args[0] in ("all", "deps", "calls", "api", "models") else "."
        mode = "all"
        for a in args:
            if a in ("all", "deps", "calls", "api", "models"):
                mode = a; break
        result = Tools._graphify(path, mode)
        if not result or len(result) < 50 or "No source files" in result:
            self.warn("No source files found. Usage: /graphify [path] [all|deps|calls|api|models]")
            return
        print(result)
        try:
            docs = Path("docs"); docs.mkdir(exist_ok=True)
            (docs / "code-graph.md").write_text(result, encoding="utf-8")
            self.success(f"Saved to docs/code-graph.md ({len(result)} chars). Skills will reuse it.")
        except OSError:
            pass

    def _cmd_process(self, args):
        """Show the last turn's tool-call log, or toggle compact process mode.
        /process           → show last turn's steps
        /process on        → compact: suppress tool chatter, show summary only
        /process off       → verbose: full tool calls printed live
        /process auto      → smart: compact when 4+ steps, inline otherwise"""
        if not args:
            if not self.last_process:
                self.info("No tool steps in the last turn.")
                return
            mode = self.cfg.get("compact_process", "on")
            self.info(f"Last turn: {len(self.last_process)} step(s) | compact mode: {mode}")
            print()
            for s in self.last_process:
                mark = f"{C.RED}\u2717{C.RESET}" if s["status"] == "error" else f"{C.GREEN}\u2713{C.RESET}"
                a = s.get("args", {})
                detail = ""
                if s["name"] == "read_file": detail = a.get("path", "")
                elif s["name"] == "write_file": detail = a.get("path", "")
                elif s["name"] == "search_files": detail = f'"{a.get("query", "")[:40]}"'
                elif s["name"] == "run_command": detail = a.get("command", "")[:50]
                elif s["name"] == "fetch_url": detail = a.get("url", "")[:50]
                else: detail = json.dumps(a)[:60]
                r = s.get("result", "")
                if len(r) > 80: r = r[:77] + "..."
                print(f"  {s['step']:>3}. {mark} {C.BOLD}{s['name']}{C.RESET} {C.DIM}{detail}{C.RESET}")
                if r: print(f"       {C.DIM}{r}{C.RESET}")
            return
        sub = args[0].lower()
        if sub in ("on", "off", "auto"):
            self.cfg.set("compact_process", sub)
            desc = {"on": "compact (suppress tool chatter, show summary)",
                    "off": "verbose (full tool calls printed live)",
                    "auto": "smart (compact when 4+ steps, inline otherwise)"}[sub]
            self.success(f"Process display: {desc}.")
        else:
            self.info(f"Compact process: {self.cfg.get('compact_process', 'on')}. Use /process on|off|auto.")

    def _cmd_setup(self, args):
        self._run_setup("")

    def _cmd_update(self, args):
        self._self_update()

    def _cmd_config(self, args):
        if args and args[0] == "set" and len(args) >= 3:
            key = args[1]
            val = parse_value(" ".join(args[2:]))
            self.cfg.set_path(key, val)
            if key.endswith(".api_key"):
                self._warn_plaintext_key(key.split(".")[-2] if "." in key else "", val)
            if key.split(".")[0] in ("backend", "backends"):
                try: self.backend = get_backend(self.cfg)
                except Exception as e: self.err(str(e))
            self.success(f"Set {key} = {val}")
        elif args and args[0] == "get" and len(args) >= 2:
            v = self.cfg.get(args[1])
            print(json.dumps(v, indent=2) if not isinstance(v, str) else v)
        else:
            print(json.dumps(self.cfg.masked_dict(), indent=2))

    def _cmd_system(self, args):
        if args:
            self.cfg.set("system_instruction", " ".join(args))
            self.success("Persona updated (tool-use rules are always appended).")
        else:
            persona = self.cfg.get("system_instruction") or self.cfg.get("system_prompt") or "(built-in default)"
            self.info("Persona (tool-use rules appended automatically):\n" + persona)

    def _cmd_server(self, args):
        if not args:
            self.warn("Usage: /server <start|stop|status|pull|models|search|show|rm>")
            return
        a = args[0]
        if a in ("start", "stop", "status"):
            ServerManager.manage(a)
        elif a == "pull":
            if len(args) < 2:
                self.warn("Usage: /server pull <model>  e.g. /server pull qwen2.5:3b"); return
            model = ServerManager.pull(args[1])
            if model:
                self.success(f"Model '{model}' pulled.")
                name, prof = self.cfg.active_profile()
                base = (prof or {}).get("base_url", "")
                if "localhost" in base or "127.0.0.1" in base:
                    if input("Set it as the active model now? [y/N] ").strip().lower() in ("y", "yes"):
                        self._override_model(model)
                        self.success(f"Active model -> {model}.")
                else:
                    self.info(f"Your active backend ({name}) isn't local; use /backend ollama + /model {model} to switch to it.")
        elif a in ("models", "list"):
            ServerManager.models()
        elif a == "search":
            if len(args) < 2: self.warn("Usage: /server search <query>  e.g. /server search qwen"); return
            ServerManager.search(" ".join(args[1:]))
        elif a == "show":
            if len(args) < 2: self.warn("Usage: /server show <model>"); return
            ServerManager.show(args[1])
        elif a == "rm":
            if len(args) < 2: self.warn("Usage: /server rm <model>"); return
            if input(f"Remove model '{args[1]}'? This frees its storage. [y/N] ").strip().lower() in ("y", "yes"):
                ServerManager.rm(args[1])
        else:
            self.err(f"Unknown action '{a}'. Use start|stop|status|pull|models|search|show|rm.")

    def _cmd_cost(self, args):
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

    def _cmd_undo(self, args):
        if self.cid:
            self.db.undo_last_msg_pair(self.cid)
            self.success("Undid last message pair.")
        else: self.warn("No active chat.")

    def _cmd_prune(self, args):
        if args:
            try: days = max(0, int(args[0]))
            except ValueError: self.warn("Usage: /prune [days]"); return
        else:
            days = int(self.cfg.get("prune_days", 0) or 0)
        if days <= 0:
            self.info("Auto-prune is off (config prune_days=0). Run /prune <days> to prune once, or set prune_days.")
            return
        n = self.db.prune_old(days)
        self.success(f"Pruned {n} session(s) untouched for >{days}d (pinned kept).")

    def _cmd_import(self, args):
        if not args: self.warn("Usage: /import <file>"); return
        path = os.path.expanduser(" ".join(args))
        try:
            with open(path, encoding="utf-8") as f:
                lines = f.read().splitlines()
        except OSError as e:
            self.err(f"Could not read {path}: {e}"); return
        title = "Imported chat"
        msgs = []
        cur_role, cur = None, []
        def flush():
            nonlocal cur_role, cur
            if cur_role and cur:
                msgs.append({"role": cur_role, "content": "\n".join(cur).strip()})
            cur = []
        for ln in lines:
            if ln.startswith("# "):
                title = ln[2:].strip()
                continue
            mm = re.match(r"^\*\*(User|Assistant):\*\*\s*(.*)$", ln)
            if mm:
                flush()
                cur_role = "user" if mm.group(1) == "User" else "assistant"
                cur = [mm.group(2)]
            elif cur_role:
                cur.append(ln)
        flush()
        if not msgs:
            self.err("No messages found in file."); return
        model = (self.backend.profile.get("model", "") if self.backend else "") or ""
        cid = self.db.new_conv(title, model, self.cfg.get("backend", ""))
        for msg in msgs:
            self.db.save_msg(cid, msg["role"], msg["content"])
        self.cid = cid
        self._persist_session()
        self.success(f"Imported {len(msgs)} message(s) into session #{cid} \"{title}\".")

    def _cmd_show(self, args):
        if not self.cid: self.warn("No active chat."); return
        conv = self.db.get_conv(self.cid)
        msgs = self.db.get_msgs(self.cid, limit=1000)
        model = self.db.last_msg_model(self.cid)
        print(f"\n{C.BOLD}#{self.cid} {conv['title']}{C.RESET} {C.DIM}[model: {model or 'n/a'}]{C.RESET}")
        for mm in msgs:
            col = C.GREEN if mm["role"] == "user" else (C.CYAN if mm["role"] == "assistant" else C.GRAY)
            print(f"\n{col}{C.BOLD}{mm['role'].capitalize()}:{C.RESET} {mm['content']}")
        print()

    def _cmd_rename(self, args):
        if not self.cid: self.warn("No active chat."); return
        if not args: self.info(f"Current title: {self.db.get_conv(self.cid)['title']}"); return
        title = " ".join(args)
        self.db.rename_conv(self.cid, title)
        self.success(f"Renamed to: {title}")

    def _cmd_tokens(self, args):
        if not self.cid: self.warn("No active chat."); return
        self.info(f"This chat: {self.db.get_conv_tokens(self.cid)} tokens | All chats: {self.db.get_total_tokens()} tokens")

    def _cmd_diff(self, args):
        try:
            r = subprocess.run(["git", "diff", "HEAD"], capture_output=True, text=True, timeout=15)
            out = r.stdout.strip()
            if out: print(out)
            else: self.info("No uncommitted changes (relative to HEAD).")
            if r.stderr.strip(): print(f"{C.DIM}{r.stderr.strip()}{C.RESET}")
        except FileNotFoundError: self.err("git not found.")
        except Exception as e: self.err(str(e))

    def _cmd_compact(self, args):
        if not self.cid: self.warn("No active chat."); return
        if not self.backend: self.err("No backend configured."); return
        self.info("Compacting conversation...")
        ok, cmsg = self._compact_conversation(self.cid)
        (self.success if ok else self.warn)(cmsg)

    def _cmd_regen(self, args):
        # Handles both /regen and /retry; /retry <model> overrides the model first.
        if self.cid and self.last_user_msg:
            if args:
                self._override_model(args[0])
                self.success(f"Retrying with model {args[0]}.")
            # An interrupted turn resumes from its checkpoint (never redoes
            # already-completed tool steps) instead of restarting from scratch.
            if self.db.get_resume_state(self.cid):
                model = (self.backend.profile.get("model", "") if self.backend else "") or ""
                self._continue_from_checkpoint(self.cid, model)
                return
            self.db.undo_last_msg_pair(self.cid)
            self._chat(self.last_user_msg)
        else: self.warn("Nothing to regenerate.")
