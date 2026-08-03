# ══ termux_ai.config ══ (fragment; merged by build.py)
class Config:
    # Fixed tool-use discipline appended to EVERY system prompt, so a user's
    # /system persona override can never accidentally drop the agent rules.
    TOOL_RULES = (
        "WORKING WITH TOOLS \u2014 think, then act, one step at a time:\n"
        "1. Before EACH tool call, write 1-3 sentences: what you know, what you'll do, why.\n"
        "2. For a coding task, READ the relevant files first; prefer targeted reads over dumping whole files.\n"
        "3. If an action FAILS or is BLOCKED, do not retry it or anything similar \u2014 say what you'll do differently, then do that.\n"
        "4. Use the fewest steps that solve it. One well-chosen command beats several.\n"
        "5. YOU decide when you're done: answer with NO tool call the moment you can. The iteration limit is only an emergency brake.\n"
        "6. Be careful with destructive actions (rm, overwrites); prefer minimal, targeted changes."
    )

    DEFAULTS = {
        "backend": "ollama",
        "system_prompt": (
            "You are an AI pair-programmer and terminal assistant running in Termux on the "
            "user's Android device. You work in their current directory: you can run shell "
            "commands, read/write files, and search code.\n\n"
            "ENVIRONMENT: Termux (Android). Paths like /sdcard, ~ ($HOME), $PREFIX are valid; "
            "install packages with `pkg`. Commands run in a Linux shell.\n\n"
            "STYLE: be concise; use code blocks for commands and code; don't over-explain."
        ),
        "system_instruction": "",
        "temperature": 0.7,
        "max_tokens": 4096,
        "stream": True,
        "show_tokens": True,
        "tools_enabled": False,
        "strategy_first": False,
        "skill_autoload": False,
        "extended_thinking": False,
        "thinking_budget": 8000,
        "tts_replies": False,
        "multi_line": False,
        "auto_compact": True,
        "max_file_chars": 20000,
        "max_tool_result": 10000,
        "max_iterations": 50,
        "continue_every": 10,
        "auto_resume": True,
        "prune_days": 0,
        "retries": 3,
        "retry_delay": 1.0,
        "fold_long_blocks": True,
        "fold_head": 8,
        "attach_files": True,
        "api_keys": {"anthropic": ""},
        "backends": {"ollama": {"base_url": "http://localhost:11434/v1", "model": "llama3.2", "api_key": "ollama"}},
    }

    def __init__(self):
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        _secure_dir(CONFIG_DIR)
        self.cfg = json.loads(json.dumps(self.DEFAULTS))
        if CONFIG_FILE.exists():
            try:
                self._deep_update(self.cfg, json.loads(CONFIG_FILE.read_text()))
            except (json.JSONDecodeError, OSError, ValueError) as e:
                sys.stderr.write(f"[termux-ai] warning: could not read {CONFIG_FILE} ({e}); using defaults.\n")
        _secure_file(CONFIG_FILE)

    @staticmethod
    def _deep_update(base, new):
        for k, v in new.items():
            if isinstance(v, dict) and isinstance(base.get(k), dict): Config._deep_update(base[k], v)
            else: base[k] = v

    def save(self):
        CONFIG_FILE.write_text(json.dumps(self.cfg, indent=2))
        _secure_file(CONFIG_FILE)
    def get(self, k, d=None): return self.cfg.get(k, d)

    def set(self, k, v, save=True):
        self.cfg[k] = v
        if save: self.save()

    def set_path(self, dotted_key, v, save=True):
        parts = dotted_key.split(".")
        node = self.cfg
        for p in parts[:-1]:
            if p not in node or not isinstance(node[p], dict): node[p] = {}
            node = node[p]
        node[parts[-1]] = v
        if save: self.save()

    def system_prompt(self):
        """Effective system prompt = persona (user-overridable) + fixed tool rules."""
        persona = self.get("system_instruction") or self.get("system_prompt") or ""
        return (persona + "\n\n" + Config.TOOL_RULES) if persona else Config.TOOL_RULES
    def active_profile(self): return self.get("backend", "ollama"), self.get("backends", {}).get(self.get("backend", "ollama"))

    def masked_dict(self):
        def scrub(node):
            if isinstance(node, dict): return {k: (mask(v) if k == "api_key" and isinstance(v, str) else scrub(v)) for k, v in node.items()}
            return node
        return scrub(self.cfg)
