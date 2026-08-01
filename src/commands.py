    # ---- slash-command handlers (dispatched by App._execute_command via _CMD_DISPATCH).
    # Each takes (self, args) where args is the list of tokens after the command.

    def _cmd_new(self, args):
        self.cid = None
        self.success("Started new chat.")

    def _cmd_tools(self, args):
        v = not self.cfg.get("tools_enabled", False)
        self.cfg.set("tools_enabled", v)
        self.success(f"Tool mode: {'Build (Write/Read allowed)' if v else 'Plan (Read-only allowed)'}.")

    def _cmd_strategy(self, args):
        v = not self.cfg.get("strategy_first", False)
        self.cfg.set("strategy_first", v)
        self.success(f"Strategy-first mode {'ON (model outlines a strategy before acting)' if v else 'OFF'}.")

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

    def _cmd_load(self, args):
        if not args: self.warn("Usage: /load <id>"); return
        try: cid = int(args[0])
        except ValueError: self.err("Invalid ID."); return
        conv = self.db.get_conv(cid)
        if conv:
            self.cid = cid
            self.success(f"Loaded chat: {conv['title']}")
        else: self.err("Chat not found.")

    def _cmd_delete(self, args):
        if not args: self.warn("Usage: /delete <id>"); return
        try: cid = int(args[0])
        except ValueError: self.err("Invalid ID."); return
        self.db.del_conv(cid)
        if self.cid == cid: self.cid = None
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

    def _cmd_backends(self, args):
        backends = self.cfg.get("backends", {})
        active = self.cfg.get("backend", "ollama")
        self.info("Available backends:")
        for b in backends:
            marker = f"{C.GREEN}*{C.RESET}" if b == active else " "
            b_model = backends[b].get("model", "N/A")
            print(f"  {marker} {C.BOLD}{b}{C.RESET} {C.DIM}({b_model}){C.RESET}")

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
            self.success(f"Set {key} = {val}")
            self.backend = get_backend(self.cfg)
        elif args[0] == "add" and len(args) >= 4:
            name, base, model = args[1], args[2], args[3]
            key = args[4] if len(args) > 4 else ""
            self.cfg.set_path(f"backends.{name}", {"base_url": base, "model": model, "api_key": key})
            self.success(f"Added profile '{name}'.")
        else:
            self.warn("Invalid profile command.")

    def _cmd_status(self, args):
        st = TermuxAPI.status()
        print(f"{C.BOLD}Termux API:{C.RESET} TTS: {'✓' if st['tts'] else '✗'}, Clipboard: {'✓' if st['clipboard'] else '✗'}, Share: {'✓' if st['share'] else '✗'}")
        name, prof = self.cfg.active_profile()
        print(f"{C.BOLD}Backend:{C.RESET} {name} ({prof.get('model', 'N/A')})")
        print(f"{C.BOLD}Tools:{C.RESET} {'Build Mode' if self.cfg.get('tools_enabled') else 'Plan Mode'} | Strategy-first: {'ON' if self.cfg.get('strategy_first') else 'off'} | Thinking: {'ON' if self.cfg.get('extended_thinking') else 'off'} | Skills: {len(self.active_session_skills)}")

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

    def _cmd_clear(self, args):
        os.system('clear' if os.name != 'nt' else 'cls')

    def _cmd_setup(self, args):
        self._run_setup("")

    def _cmd_update(self, args):
        self._self_update()

    def _cmd_config(self, args):
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

    def _cmd_system(self, args):
        if args:
            self.cfg.set("system_instruction", " ".join(args))
            self.success("Persona updated (tool-use rules are always appended).")
        else:
            persona = self.cfg.get("system_instruction") or self.cfg.get("system_prompt") or "(built-in default)"
            self.info("Persona (tool-use rules appended automatically):\n" + persona)

    def _cmd_server(self, args):
        if not args:
            self.warn("Usage: /server <start|stop|status>")
        else:
            ServerManager.manage(args[0])

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

    def _cmd_show(self, args):
        if not self.cid: self.warn("No active chat."); return
        conv = self.db.get_conv(self.cid)
        msgs = self.db.get_msgs(self.cid, limit=1000)
        print(f"\n{C.BOLD}#{self.cid} {conv['title']}{C.RESET}")
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
            self.db.undo_last_msg_pair(self.cid)
            self._chat(self.last_user_msg)
        else: self.warn("Nothing to regenerate.")
