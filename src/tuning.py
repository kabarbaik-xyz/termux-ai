# ══ termux_ai.tuning ══ (fragment; merged by build.py)
# Per-model auto-tuning registry. The goal is automation: every model family
# gets sensible defaults automatically, so users don't have to tune by hand.
# First-match-wins on the lowercased model name. Unknown models fall back to
# Ollama /api/show capabilities (when available) then to non-thinking defaults.
MODEL_TUNING = [
    # ── reasoning models (route through the native Ollama shim with think:false;
    #    lower temperature keeps their chain-of-thought focused) ──────────────
    # `(?:^|/)` matches bare names ("qwen3:1.7b") and provider-prefixed cloud
    # IDs ("qwen/qwen3-30b-a3b", "deepseek/deepseek-r1", "openai/o1").
    (re.compile(r"(?:^|/)qwen3|(?:^|/)qwq"),  {"thinking": True, "temperature": 0.6,
                                               "num_ctx": 16384, "strategy_first": False, "compact_schemas": True}),
    (re.compile(r"(?:^|/)deepseek-r1"),       {"thinking": True, "temperature": 0.6,
                                               "compact_schemas": True}),
    (re.compile(r"(?:^|/)phi4(?:-reasoning)?"), {"thinking": True, "temperature": 0.6,
                                                 "compact_schemas": True}),
    # ── fast chat models (keep /v1 path; compact schemas cut prompt cost) ─────
    (re.compile(r"(?:^|/)qwen2\.5|(?:^|/)qwen2"), {"thinking": False, "strategy_first": False, "compact_schemas": True}),
    (re.compile(r"(?:^|/)llama3"),            {"thinking": False, "temperature": 0.6, "compact_schemas": True}),
    (re.compile(r"(?:^|/)gemma"),             {"thinking": False, "compact_schemas": True}),
    # ── cloud reasoning families (OpenAI-compat /api/v1 reasoning_content) ────
    (re.compile(r"(?:^|/)o[1-3](?:-|$)"),     {"thinking": True}),
    (re.compile(r"(?:^|/)gemini-2\.[05].*(think|flash|pro)"), {"thinking": True}),
]

# Keys a tuning profile may carry, and which read-site they feed (for /tune display).
TUNING_KEYS = ("thinking", "ollama_no_think", "temperature", "num_ctx",
               "strategy_first", "gather_first", "compact_schemas")


def tuning_for(name):
    """Return the first matching tuning profile for a model name (dict), or {}."""
    nm = (name or "").lower()
    for pat, prof in MODEL_TUNING:
        if pat.search(nm):
            return dict(prof)
    return {}


def is_thinking_model(name, caps=None):
    """Best-effort 'does this model think?' detection.
    1. Ollama /api/show capabilities are authoritative when provided.
    2. The registry knows the major reasoning families.
    3. Default: not a reasoning model."""
    if caps:
        if "thinking" in caps:
            return True
        if caps and all(c in ("completion", "tools", "embedding") for c in caps):
            return False
    t = tuning_for(name)
    if t.get("thinking") is not None:
        return bool(t.get("thinking"))
    return False