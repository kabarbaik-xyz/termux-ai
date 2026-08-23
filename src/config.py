# ══ termux_ai.config ══ (fragment; merged by build.py)
# The pre-7.2 Termux-only default persona, kept so existing Linux/macOS installs
# that never customized it get upgraded to a platform-aware prompt automatically.
LEGACY_PROMPT = (
    "You are an AI pair-programmer and terminal assistant running in Termux on the "
    "user's Android device. You work in their current directory: you can run shell "
    "commands, read/write files, and search code.\n\n"
    "ENVIRONMENT: Termux (Android). Paths like /sdcard, ~ ($HOME), $PREFIX are valid; "
    "install packages with `pkg`. Commands run in a Linux shell.\n\n"
    "STYLE: be concise; use code blocks for commands and code; don't over-explain."
)


def _platform_prompt():
    """Default persona for the *current* platform (Termux vs Linux vs macOS)."""
    if IS_TERMUX:
        device = "running in Termux on the user's Android device"
        env = ("ENVIRONMENT: Termux (Android). Paths like /sdcard, ~ ($HOME), $PREFIX are valid; "
               "install packages with `pkg`. Commands run in a Linux shell.")
    elif IS_MAC:
        device = "running on macOS"
        env = ("ENVIRONMENT: macOS. Install packages with `brew`. Commands run in a POSIX shell.")
    else:
        device = "running on Linux (Debian/Ubuntu or another distro)"
        env = ("ENVIRONMENT: Linux. Install packages with `apt-get` (Debian/Ubuntu), `dnf` "
               "(Fedora), `pacman` (Arch), or the distro's package manager. Commands run in a Linux shell.")
    return (
        f"You are an AI pair-programmer and terminal assistant {device}. You work in "
        "their current directory: you can run shell commands, read/write files, and "
        f"search code.\n\n{env}\n\n"
        "STYLE: be concise; use code blocks for commands and code; don't over-explain."
    )


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
        "6. Be careful with destructive actions (rm, overwrites); prefer minimal, targeted changes.\n"
        "7. Project memory: if a # Project context section names CONTEXT.md, KEEP IT CURRENT — when you learn a durable fact about the "
        "project (stack, structure, conventions, gotchas, decisions), update CONTEXT.md with write_file (preserve what's there; append "
        "or edit the relevant section). Do not write transient session state into it.\n"
        "8. LONG DOCUMENTS: when asked to CREATE a document/guide/report longer than ~a page, write it in SECTIONS — one write_file for "
        "the opening, then write_file(append=true) for each remaining section. Never emit one giant call."
    )

    DEFAULTS = {
        "backend": "ollama",
        "system_prompt": _platform_prompt(),
        "system_instruction": "",
        "temperature": 0.7,
        "max_tokens": 8192,
        # Context capacity: these should fit comfortably inside the model's real
        # context window. Setting them too low starves the model of files it
        # already read, forcing re-reads -- the #1 cause of tool-loop spirals.
        "context_window": 32000,
        "iteration_history_budget": 30000,
        "compact_process": "on",
        "compact_threshold": 4,
        "stream": True,
        "show_tokens": True,
        "tools_enabled": False,
        "strategy_first": False,
        "skill_autoload": False,
        "skill_suggest": True,   # one-line hint when the input strongly matches a skill
        "extended_thinking": False,
        "thinking_budget": 8000,
        "tts_replies": False,
        "multi_line": False,
        "auto_compact": True,
        "max_file_chars": 20000,
        "max_context_md": 12000,   # cap for the CONTEXT.md project-memory attachment
        "max_tool_result": 30000,
        "max_iterations": 100,
        "continue_every": 10,
        "continue_mode": "auto",   # auto = keep working pi-style (backstops still guard); prompt = ask to continue every continue_every calls
        "auto_verify": True,
        "usage_stream": True,
        "stream_idle_timeout": 240,
        "first_byte_timeout": 60,   # a gateway that connects but sends NOTHING is aborted this fast -> checkpoint + auto-resume (was: silent spin to the idle timeout)  # seconds without SSE bytes before a stream is declared dead (buffered gateways can pause >100s mid-generation)
        "compact_at": 0.8,      # auto-compact at this fraction of the model's effective context window   # ask cloud streams for real token usage (final-chunk accounting)   # after edits in Build mode, run the project's tests once and show the model the result before it can claim done   # auto = keep working pi-style (backstops still guard); prompt = ask to continue every continue_every calls
        "repeat_limit": 3,
        "re_read_limit": 3,
        "gather_first": True,
        "gather_threshold": 5,
        "continue_every": 10,
        "auto_resume": True,
        "prune_days": 0,
        "auto_continue": True,
        "max_auto_continue": 2,
        "retries": 3,
        "retry_delay": 1.0,
        "ollama_no_think": True,   # qwen3 on local Ollama: disable thinking via native API (the /v1 compat endpoint ignores `think` and qwen3 burns minutes of phone CPU thinking)
        "ollama_keep_alive": "2h", # keep the model loaded + KV cache resident between turns so idle doesn't force a ~30s cold reload mid-session
        "ollama_max_tokens": 0,    # Ollama-only max generation cap (0 = use max_tokens). Set low (e.g. 2048) for slow phone CPU WITHOUT lowering cloud's max_tokens
        "num_ctx": 0,              # optional Ollama context-length override (0 = Ollama default)
        "ollama_warm": True,     # pre-load the local model at startup so the first prompt is fast
        "fold_long_blocks": True,
        "fold_head": 8,
        "attach_files": True,
        "api_keys": {"anthropic": ""},
        # Per-model auto-tuning is applied automatically from the MODEL_TUNING
        # registry; users may override per-model via model_tuning (rarely needed).
        "model_tuning": {},
        "local_defaults": {},      # safety net: applied only to local backends
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

        # One-time migration: older installs saved capacity caps at the old
        # defaults (max_tokens=4096, max_tool_result=10000), which starved the
        # model and caused read-spirals. Bump them once; users who explicitly
        # set a DIFFERENT custom value are unaffected.
        if not self.cfg.get("_cap_v2"):
            changed = False
            if self.cfg.get("max_tokens") == 4096:
                self.cfg["max_tokens"] = 8192; changed = True
            if self.cfg.get("max_tool_result") == 10000:
                self.cfg["max_tool_result"] = 30000; changed = True
            self.cfg["_cap_v2"] = True
            if changed:
                try:
                    self.save()
                except OSError:
                    pass

        # One-time migration: /process compact display became the default ("on")
        # in 7.2.x. Existing installs still carry the OLD default ("auto") in
        # their saved config -- migrate them once. An explicit "off" or "on"
        # choice is never touched.
        if not self.cfg.get("_process_v1"):
            changed = False
            if self.cfg.get("compact_process", "on") == "auto":
                self.cfg["compact_process"] = "on"; changed = True
            self.cfg["_process_v1"] = True
            if changed:
                try:
                    self.save()
                except OSError:
                    pass

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
        """Effective system prompt = persona (user-overridable) + fixed tool rules.

        Auto-upgrades the pre-7.2 Termux-only default for existing Linux/macOS
        installs that never customized their persona; a user-set prompt is kept."""
        persona = self.get("system_instruction") or ""
        if not persona:
            sp = self.get("system_prompt") or ""
            if not sp or sp == LEGACY_PROMPT:
                sp = _platform_prompt()
            persona = sp
        return (persona + "\n\n" + Config.TOOL_RULES) if persona else Config.TOOL_RULES
    def active_profile(self): return self.get("backend", "ollama"), self.get("backends", {}).get(self.get("backend", "ollama"))

    def masked_dict(self):
        def scrub(node):
            if isinstance(node, dict): return {k: (mask(v) if k == "api_key" and isinstance(v, str) else scrub(v)) for k, v in node.items()}
            return node
        return scrub(self.cfg)
