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
    # ── fast chat models (keep /v1 path; micro schemas + tuned num_ctx cut
    #    prompt cost and avoid the Ollama default 4096-context truncation
    #    that makes tool sessions loop). num_ctx is sent on the native path;
    #    on /v1 Ollama ignores it (harmless). Keep the model resident 2h so
    #    idle doesn't evict the KV cache mid-session. ────────────────────────
    (re.compile(r"(?:^|/)qwen2\.5|(?:^|/)qwen2"), {"thinking": False, "strategy_first": False,
                                                   "temperature": 0.6, "num_ctx": 8192,
                                                   "ollama_max_tokens": 2048, "ollama_keep_alive": "2h",
                                                   "compact_schemas": True}),
    (re.compile(r"(?:^|/)llama3"),            {"thinking": False, "temperature": 0.6,
                                               "num_ctx": 8192, "ollama_max_tokens": 2048,
                                               "ollama_keep_alive": "2h", "compact_schemas": True}),
    (re.compile(r"(?:^|/)gemma"),             {"thinking": False, "num_ctx": 8192,
                                               "ollama_max_tokens": 2048, "ollama_keep_alive": "2h",
                                               "compact_schemas": True}),
    # ── cloud reasoning families (OpenAI-compat /api/v1 reasoning_content) ────
    (re.compile(r"(?:^|/)o[1-3](?:-|$)"),     {"thinking": True}),
    (re.compile(r"(?:^|/)gemini-2\.[05].*(think|flash|pro)"), {"thinking": True}),
]

# Keys a tuning profile may carry, and which read-site they feed (for /tune display).
TUNING_KEYS = ("thinking", "ollama_no_think", "temperature", "num_ctx",
               "max_tokens", "ollama_max_tokens", "ollama_keep_alive",
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


_O_SERIES = re.compile(r"(?:^|/)o[1-3](?:-|$)")


def needs_completion_tokens(name, base_url=""):
    """True for OpenAI o-series models on the OFFICIAL api.openai.com endpoint:
    the Responses-era API requires max_completion_tokens and rejects max_tokens
    (and only accepts temperature=1). Other gateways (OpenRouter, opencode, vLLM
    ...) happily accept max_tokens, so only the official host is special-cased."""
    return "api.openai.com" in (base_url or "") and bool(_O_SERIES.search((name or "").lower()))

# Context windows by model family (tokens). First-match-wins on the
# lowercased name; falls back to config context_window. LOCAL models'
# effective window is their num_ctx (the real limit on the phone), so the
# registry is mainly for cloud families.
CONTEXT_WINDOWS = [
    (re.compile(r"(?:^|/)gpt-4\.1"), 1047576),
    (re.compile(r"(?:^|/)gpt-4o"), 128000),
    (re.compile(r"(?:^|/)o[1-3](?:-|$)"), 200000),
    (re.compile(r"(?:^|/)claude-(?:3|4|sonnet|opus|haiku)"), 200000),
    (re.compile(r"(?:^|/)gemini"), 1048576),
    (re.compile(r"(?:^|/)deepseek"), 64000),
    (re.compile(r"(?:^|/)grok"), 131072),
    (re.compile(r"(?:^|/)mistral|mixtral"), 32768),
    (re.compile(r"(?:^|/)qwen3"), 32768),
    (re.compile(r"(?:^|/)qwen2|llama3|gemma|phi"), 8192),
]


def context_window_for(name, fallback=32000):
    """Best-effort context window for a model name (cloud registry first,
    config fallback). Local models should pass their num_ctx explicitly."""
    nm = (name or "").lower()
    for pat, win in CONTEXT_WINDOWS:
        if pat.search(nm):
            return win
    return int(fallback or 32000)
