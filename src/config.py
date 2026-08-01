# ══ termux_ai.config ══ (fragment; merged by build.py)
class Config:
    DEFAULTS = {
        "backend": "ollama",
        "system_prompt": "You are a helpful assistant. Be concise and clear. When using tools: (1) Do not repeat commands you have already run. (2) If a command fails, do not retry it without changing arguments. (3) Complete tasks in the minimum number of steps. (4) Only use tools when necessary.",
        "system_instruction": "",
        "temperature": 0.7,
        "max_tokens": 4096,
        "stream": True,
        "show_tokens": True,
        "tools_enabled": False,
        "tts_replies": False,
        "multi_line": False,
        "auto_compact": True,
        "max_file_chars": 20000,
        "max_tool_result": 10000,
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

    def system_prompt(self): return self.get("system_instruction") or self.get("system_prompt") or ""
    def active_profile(self): return self.get("backend", "ollama"), self.get("backends", {}).get(self.get("backend", "ollama"))

    def masked_dict(self):
        def scrub(node):
            if isinstance(node, dict): return {k: (mask(v) if k == "api_key" and isinstance(v, str) else scrub(v)) for k, v in node.items()}
            return node
        return scrub(self.cfg)
