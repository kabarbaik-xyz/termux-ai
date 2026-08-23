# ══ termux_ai.backends ══ (fragment; merged by build.py)
class BackendError(Exception):
    """Backend request failure. transient=True when a retry may succeed
    (network blips, 429/5xx, timeouts, empty or dropped streams). retry_after
    carries a server-suggested wait (from the Retry-After header) in seconds."""
    def __init__(self, message, transient=False, retry_after=None):
        super().__init__(message)
        self.transient = transient
        self.retry_after = retry_after


class _ConnPool:
    """Tiny keep-alive pool for backend POSTs. stdlib urlopen opens a fresh
    TCP+TLS handshake per request (~0.3-0.5s on phone networks); a tool loop
    makes 5-20 requests per turn, so reusing connections cuts real seconds off
    EVERY cloud backend. One persistent http.client connection per
    (scheme, host, port); a stale/broken connection is dropped and reopened
    transparently (one retry on first use)."""

    _MAX_LIFETIME = 300.0   # re-handshake every 5 min (avoids half-dead NAT sockets)

    def __init__(self):
        self._conns = {}          # (scheme, host, port) -> [conn, born_ts, in_use]
        self._lock = threading.Lock()

    @staticmethod
    def _key(url):
        u = urllib.parse.urlparse(url)
        scheme = u.scheme or "https"
        host = u.hostname or ""
        port = u.port or (443 if scheme == "https" else 80)
        return (scheme, host, port), (u.path or "/") + (("?" + u.query) if u.query else "")

    def post(self, url, headers, body, timeout=120):
        """POST via a pooled connection. Returns (response, conn). The response
        is already begun; callers stream .read(). After fully reading, callers
        must call recycle()/drop so the socket returns to the pool."""
        (scheme, host, port), path = self._key(url)
        last = None
        for _attempt in (1, 2):
            conn, fresh = self._take(scheme, host, port, timeout)
            try:
                conn.request("POST", path, body=body, headers=headers)
                resp = conn.getresponse()
                self._mark(scheme, host, port, conn, resp)
                return resp, conn
            except Exception as e:
                last = e
                self._drop(scheme, host, port)
                if fresh:
                    raise    # a brand-new connection failing is a real error
        raise last

    def _take(self, scheme, host, port, timeout):
        with self._lock:
            slot = self._conns.get((scheme, host, port))
            if slot and not slot[2] and (time.monotonic() - slot[1]) < self._MAX_LIFETIME:
                slot[2] = True
                return slot[0], False
        # http.client timeouts are PER SOCKET OP (connect, each read) -- not
        # whole-stream -- which is the right shape for buffered gateways. Give
        # reads generous headroom beyond connect: a big doc can sit silently
        # server-side >100s before a burst of SSE arrives.
        rt = max(timeout, 240)
        if scheme == "https":
            return http.client.HTTPSConnection(host, port, timeout=rt), True
        return http.client.HTTPConnection(host, port, timeout=rt), True

    def _mark(self, scheme, host, port, conn, resp):
        """Mark the slot reusable only if the response allows keep-alive."""
        try:
            ka = not resp.will_close
        except Exception:
            ka = False
        with self._lock:
            if ka:
                self._conns[(scheme, host, port)] = [conn, time.monotonic(), False]
            else:
                self._conns.pop((scheme, host, port), None)

    def recycle(self, conn):
        """No-op bookkeeping kept for clarity: _mark already returned the conn."""
        return None

    def _drop(self, scheme, host, port):
        with self._lock:
            slot = self._conns.pop((scheme, host, port), None)
        if slot:
            try: slot[0].close()
            except Exception: pass

    def drop_conn(self, conn):
        try: conn.close()
        except Exception: pass

    def close(self):
        with self._lock:
            conns = list(self._conns.values()); self._conns.clear()
        for slot in conns:
            try: slot[0].close()
            except Exception: pass


_POOL = _ConnPool()


def _parse_retry_after(val):
    """Parse an HTTP Retry-After header (integer seconds or HTTP-date) into a
    clamped delay in seconds, or None when unparseable."""
    if not val:
        return None
    s = str(val).strip()
    if s.isdigit():
        return min(int(s), 60)   # honor the server's ask, capped at 60s
    return None   # HTTP-date form is rare for LLM gateways; fall back to backoff


class ThinkFilter:
    """Streaming filter that strips <think>...</think> reasoning blocks
    (deepseek-r1, phi-reasoning, ...) out of a content stream so the raw
    chain-of-thought isn't dumped to the screen. Handles tags split across
    chunk boundaries. feed() returns the safe-to-emit text; flush() drains the
    tail (discarded if still inside an open <think> block)."""
    _OPEN, _CLOSE = "<think>", "</think>"

    def __init__(self):
        self.in_think = False
        self.tail = ""

    def feed(self, chunk):
        self.tail += chunk
        out = []
        while self.tail:
            tag = self._CLOSE if self.in_think else self._OPEN
            idx = self.tail.find(tag)
            if idx == -1:
                # Hold back a suffix that could be the start of a partial tag,
                # so a split "<thi" + "nk>" isn't emitted as visible text.
                hold = 0
                for n in range(min(len(self.tail), len(tag) - 1), 0, -1):
                    if self.tail[-n:] == tag[:n]:
                        hold = n; break
                safe = self.tail[:-hold] if hold else self.tail
                self.tail = self.tail[-hold:] if hold else ""
                if not self.in_think:        # inside <think>: suppress reasoning
                    out.append(safe)
                break
            if not self.in_think and idx > 0:
                out.append(self.tail[:idx])
            self.in_think = not self.in_think
            self.tail = self.tail[idx + len(tag):]
        return "".join(out)

    def flush(self):
        """End of stream: emit any pending text outside a think block."""
        r = "" if self.in_think else self.tail
        self.tail = ""
        return r


def _free_ram_gb():
    """Free RAM in GB from /proc/meminfo (Linux/Android), or None when
    unavailable. Used to suggest an OOM-safe Ollama num_ctx."""
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemAvailable:"):
                    return int(line.split()[1]) / 1048576.0
    except Exception:
        return None
    return None


def _suggest_num_ctx(free_gb, model_gb):
    """Conservative Ollama context-length suggestion (tokens) given free RAM
    and the model file size. KV-cache sizing is model-dependent, so this picks
    a safe tier from the headroom after the model loads rather than pretending
    to compute it exactly."""
    head = (free_gb or 0) - (model_gb or 0) - 0.5   # OS + process overhead
    if head < 1.0:  return 2048
    if head < 2.0:  return 4096
    if head < 4.0:  return 8192
    return 16384


# ── Tool-selection gate ───────────────────────────────────────────────────────
# Small LOCAL non-thinking models (qwen2.5:1.7b/3b, llama3.2, ...) loop tools on
# trivial questions: they see file tools + a "gather context" workflow and answer
# 'what can I do for you?' with list_files/read_file calls. Every tool iteration
# re-prefills the whole prompt + growing history on a slow phone (~40-75s each),
# so a 3-4 round loop is 200s+ while `ollama run` (no tools) answers instantly.
# Deterministic three-way gate for these models:
#   chat      -> NO tools at all (model can only answer directly)
#   knowledge -> web-only tools (web_search + fetch_url), no file/command tools
#   task      -> the full toolset
# Cloud models are smarter and keep the full toolset every turn.
_TASK_RE = re.compile(
    r"\b(create|build|write|make|fix|install|run|read|list|search|find|clone|edit|"
    r"update|delete|remove|add|debug|test|refactor|implement|check|configure|setup|"
    r"migrate|deploy|start|stop|compile|execute|generate|format|lint|init|review|patch|"
    r"buat|bikin|tulis|perbaiki|benahi|hapus|jalankan|instal|install|edit|ubah|ganti|"
    r"tambah|baca|cari|lihat|unduh|kompres|bongkar|susun|rapikan)\b",
    re.IGNORECASE)
_PATH_RE = re.compile(r"(?:^|[\s\"'`])(?:\.{1,2}/|~/|/|[\w.\-]+/)[\w.\-]*(?:/[\w.\-]+)+")
_EXT_RE = re.compile(r"\b[\w\-]+\.(py|js|ts|tsx|jsx|go|rs|c|h|cpp|hpp|java|kt|rb|sh|"
                     r"bash|zsh|json|yaml|yml|toml|md|txt|html|css|sql|lock|env|ini|cfg|conf|log|db)\b",
                     re.IGNORECASE)
_ACTION_RE = re.compile(
    r"\b(can you|help me|i need|i want( to)?|please|would you|could you|show me|"
    r"give me|do it|do that|tolong|bisakah|bisa kah|bolehkah|minta tolong)\b", re.IGNORECASE)
_SELF_CHAT_RE = re.compile(
    r"\bwhat (can|should|do|could|would|will) (i|you)\b|\bwhat('?s| is| are) (your|my)\b|"
    r"\bwho are you\b|\bhow are you\b|\bcan i call you\b|\bdo you (know|like|understand|have)\b|"
    r"\bhow do you\b|\byou are (a|an|the)\b|"
    r"\bsiapa kamu\b|\bkamu siapa\b|\bapa yang bisa kamu\b|\bkamu bisa apa\b|"
    r"\bapa kabar\b|\bkabarmu\b|\bsiapa namamu\b|\bnama kamu siapa\b", re.IGNORECASE)
_KNOWLEDGE_RE = re.compile(
    r"\b(who|when|where|why|how)\b|\bwhat('?s| is| are| was| were| does| did)\b|"
    r"\btell me (about|the|more)\b|\binformation about\b|\bexplain\b|\bdefine\b|"
    r"\bmeaning of\b|\bhistory of\b|\bcapital of\b|\bpopulation\b|\bweather\b|"
    r"\bforecast\b|\bnews\b|\bcurrent\b|\blatest\b|\btoday'?s\b|"
    r"\bapa itu\b|\bapa yang dimaksud\b|\bsiapa(?! kamu)\b|\bkapan\b|\bdi mana\b|\bdimana\b|"
    r"\bmengapa\b|\bkenapa\b|\bbagaimana\b|\bberapa\b|\bcuaca\b|\bhujan\b|"
    r"\bberita\b|\bterbaru\b", re.IGNORECASE)
# Short acknowledgments that continue an in-flight task ("ok lanjutkan",
# "yes, do it") -- only keep tools when the PREVIOUS user turn was a task.
_CONTINUE_RE = re.compile(
    r"\b(ok|oke|okay|okey|ya|iya|yap|sip|gas|lanjut\w*|lanjutkan|continue|"
    r"proceed|keep going|go on|silakan|silahkan|tolong lanjut)\b", re.IGNORECASE)
# Self-heal: a small local model answering WITHOUT tools (the gate classified
# the message as chat) but whose text reads like it WANTED tools ("I can't
# access files" / "maaf, saya tidak bisa mengakses file"). One retry with tools
# offered fixes the misclassification instead of the user rephrasing.
_WANTS_TOOLS_RE = re.compile(
    r"i (can'?t|cannot|don'?t have|am unable to) (access|read|open|see|check|list|run|execute)"
    r"|i (do not|don'?t) have (access|the ability|permission)"
    r"|no (access|tool|file) (to|for)"
    r"|as (an? )?(ai|language model|text model)[,.]? i (can'?t|cannot|don'?t|am unable)"
    r"|tidak bisa (mengakses|membaca|membuka|melihat|menjalankan|mengeksekusi)"
    r"|tidak dapat (mengakses|membaca|membuka|melihat|menjalankan)"
    r"|saya tidak (bisa|dapat|punya akses) (mengakses|membaca|melihat|membuka)"
    r"|maaf,? saya (tidak|ga|gak|nggak) (bisa|dapat)", re.IGNORECASE)


def _chat_kind(text):
    """Classify a user message for tool selection:
    'chat'      — pure casual chat, no tools
    'knowledge' — a factual question the model may not know offline -> web tools
    'task'      — file/command work -> full toolset
    Heuristics, not AI: task verbs/paths/extensions win first, then self-chat
    ("what can I do for you?"), then knowledge words, else length decides."""
    t = (text or "").strip()
    if not t:
        return "chat"
    if _PATH_RE.search(t) or _EXT_RE.search(t):
        return "task"            # has a file path / filename extension -> a task
    if _TASK_RE.search(t):
        return "task"            # explicit task verb -> a task
    if _ACTION_RE.search(t):
        return "task"            # "can you ...", "help me ..." -> a task
    tl = t.lower()
    if _SELF_CHAT_RE.search(tl):
        return "chat"            # "what can I do for you?" -> just chat
    if _KNOWLEDGE_RE.search(tl):
        return "knowledge"       # "who is Prabowo?", "weather today" -> web lookup
    return "chat" if len(t) <= 120 else "task"   # no signals: short = chat


class LoopGuard:
    """Shared agentic-loop bookkeeping used by BOTH chat_with_tools backends so
    the two loops can never drift again: the iteration ceiling (UNATTENDED cap;
    each approved 'continue?' checkpoint EXTENDS it so an attended long task runs
    to completion), the periodic checkpoint, the consecutive-failure guard, and
    the stuck-repeat backstop."""
    MAX_FAILURES = 3
    STUCK_LIMIT = 5

    def __init__(self, cfg, continue_fn=None):
        self.max_iterations = max(1, int(cfg.get("max_iterations", 50)))
        self.continue_every = max(1, int(cfg.get("continue_every", 10)))
        self.mode = (cfg.get("continue_mode") or "auto").lower()   # auto | prompt
        self.next_prompt_at = self.continue_every
        self.iteration_cap = self.max_iterations
        self.continue_fn = continue_fn
        self.iterations = 0
        self.total_calls = 0
        self.consecutive_failures = 0
        self.stuck_streak = 0

    def begin_iteration(self):
        """Top of each loop iteration. Returns a fatal stop notice when the
        iteration ceiling is hit, else None."""
        self.iterations += 1
        if self.iterations > self.iteration_cap:
            return {"level": "error", "icon": "\u2716",
                    "text": f"iteration limit reached ({self.iteration_cap})",
                    "hint": "/retry to continue \u00b7 /config set max_iterations N to raise the ceiling"}
        return None

    def note_calls(self, n):
        self.total_calls += n

    def note_results(self, any_productive, failed_names):
        """After executing a batch: returns (fatal_notice, reflect_msg).
        fatal_notice stops the task (stuck repeats / consecutive failures);
        reflect_msg is the REFLECT-on-failure system note for the next turn."""
        if any_productive:
            self.stuck_streak = 0
        else:
            self.stuck_streak += 1
            if self.stuck_streak >= self.STUCK_LIMIT:
                return {"level": "error", "icon": "\u2716",
                        "text": f"{self.STUCK_LIMIT} rounds with no new progress (repeated work)",
                        "hint": "/retry or rephrase the task"}, None
        if failed_names:
            self.consecutive_failures += 1
            if self.consecutive_failures >= self.MAX_FAILURES:
                return {"level": "error", "icon": "\u2716",
                        "text": f"{self.consecutive_failures} failed rounds in a row: {', '.join(failed_names[:3])}",
                        "hint": "rephrase the task \u00b7 /tools on enables Build mode \u00b7 add detail"}, None
            return None, ("REFLECT: your last action(s) failed \u2014 %s. Before the next step, state out loud what you "
                          "will do DIFFERENTLY. Do not retry the same approach or any blocked/interpreter/redirect command."
                          % ", ".join(failed_names))
        self.consecutive_failures = 0
        return None, None

    def checkpoint(self):
        """Periodic 'continue?' gate. Returns "stop" when the user declined;
        None to keep going. continue_mode=auto (default, pi-style) extends the
        ceiling itself and keeps working without a prompt -- runaway safety
        stays with the stuck-detector / 3-failure guard / repeat limits, and
        Ctrl+C still interrupts (checkpoint -> /retry). continue_mode=prompt
        asks the user every continue_every calls (the pre-7.4 behavior)."""
        if self.total_calls < self.next_prompt_at:
            return None
        if self.continue_fn is None:
            self.next_prompt_at += self.continue_every   # unattended: no prompt, no extension
            return None
        if self.mode == "auto":
            self.next_prompt_at += self.continue_every   # keep going; safety = the backstops
            self.iteration_cap += self.continue_every
            return None
        if self.continue_fn(self.iterations, self.total_calls):
            self.next_prompt_at += self.continue_every   # approved -> extend the ceiling
            self.iteration_cap += self.continue_every
            return None
        return "stop"


# Done-claim guard: the model's final text CLAIMS the work is complete (EN+ID)
# while the ledger shows zero successful mutations this turn. One corrective
# retry; a second claim passes through with an honest warning to the user.
_DONE_CLAIM_RE = re.compile(
    r"\b(fixed|done|created|written|updated|added|implemented|applied|patched|"
    r"selesai|diperbaiki|dibuat|dibuatkan|ditulis|diupdate|ditambahkan|diterapkan|"
    r"berhasil\s+(memperbaiki|membuat|menulis|menambahkan|mengubah)|sudah\s+(diperbaiki|dibuat|ditulis|diubah|selesai))\b",
    re.IGNORECASE)


class MutationLedger:
    """Ground truth for what a turn ACTUALLY changed on disk (write_file /
    edit_file / mutating commands), recorded by the executor — never taken
    from the model's narration. Drives the verified-changes footer and the
    done-claim guard: 'said fixed' can no longer diverge from 'did fix'."""

    def __init__(self):
        self.entries = []          # {tool, path, ok, detail}

    def record(self, tool, path, ok, detail=""):
        self.entries.append({"tool": tool, "path": path, "ok": bool(ok), "detail": detail})

    def successful(self):
        return [e for e in self.entries if e["ok"]]

    def files_changed(self):
        """Unique paths with at least one successful write/edit."""
        seen = []
        for e in self.successful():
            if e.get("path") and e["path"] not in seen:
                seen.append(e["path"])
        return seen

    def failed_paths(self):
        return sorted({e["path"] for e in self.entries if not e["ok"] and e.get("path")})

    def empty(self):
        return not self.successful()


class OpenAIDeltaAccumulator:
    """Merges streamed OpenAI-compat deltas (content, reasoning_content,
    tool_calls fragments) into complete buffers. Extracted from the tool loop
    so the merge rules (string-concat name/arguments, id/type overwrite,
    reasoning fallback field) live in ONE tested place."""

    def __init__(self):
        self.content = ""
        self.reasoning = ""
        self.tool_calls = {}     # index -> {id, type, function:{name, arguments}}
        self.finish_reason = None

    def feed(self, chunk, live_thinking=None):
        """Merge one parsed SSE chunk. live_thinking(s) (optional) receives
        native LOCAL thinking chunks for immediate dim display."""
        if not isinstance(chunk, dict) or not chunk.get("choices"):
            return
        ch0 = chunk["choices"][0]
        delta = ch0.get("delta") or {}
        fr = ch0.get("finish_reason")
        if fr: self.finish_reason = fr
        if delta.get("content"):
            self.content += delta["content"]
        if delta.get("reasoning_content") or delta.get("reasoning"):
            r = delta.get("reasoning_content") or delta.get("reasoning") or ""
            self.reasoning += r
            if live_thinking:
                live_thinking(r)
        if delta.get("tool_calls"):
            for tc in delta["tool_calls"]:
                idx = tc.get("index", 0)
                slot = self.tool_calls.setdefault(idx, {"id": "", "type": "function",
                                                        "function": {"name": "", "arguments": ""}})
                for k, v in tc.items():
                    if k not in ("index", "function"):
                        slot[k] = v
                if tc.get("function"):
                    for fk, fv in tc["function"].items():
                        # Some gateways (opencode/big-pickle) emit name=None or
                        # arguments=None in filler deltas -- concatenating would
                        # crash the whole turn with a TypeError.
                        if fv is None:
                            continue
                        if fk == "name":
                            slot["function"]["name"] += fv
                        elif fk == "arguments":
                            slot["function"]["arguments"] += fv
                        else:
                            slot["function"][fk] = fv

    @property
    def calls(self):
        """Ordered list of complete tool calls (by stream index)."""
        return [self.tool_calls[k] for k in sorted(self.tool_calls)]


class _PooledResponse:
    """Adapter over http.client responses returned by _ConnPool.post. Mimics
    the urllib surface our code uses: .read(n), .status, context-manager, and
    raises nothing exotic. The pooled connection was already marked for reuse
    by the pool (based on keep-alive); errors mid-read are surfaced as OSError.

    First-byte watchdog: a gateway that connects but then sends NOTHING is the
    worst failure mode (the UI spins 'prefilling' until the idle timeout). The
    socket timeout starts TIGHT (first_byte_timeout); the first data read
    relaxes it to the normal idle value so long buffered generations still
    complete."""

    def __init__(self, resp, conn, first_byte_timeout=60.0, idle_timeout=240.0):
        self._resp = resp
        self._conn = conn
        self._first_byte_timeout = float(first_byte_timeout)
        self._idle_timeout = float(idle_timeout)
        self._got_first = False
        try:
            if getattr(conn, "sock", None) is not None:
                conn.sock.settimeout(self._first_byte_timeout)
        except OSError:
            pass

    @property
    def status(self):
        return self._resp.status

    def read(self, n=-1):
        data = self._resp.read(n if n and n > 0 else None)
        if data and not self._got_first:
            self._got_first = True
            try:
                if getattr(self._conn, "sock", None) is not None:
                    self._conn.sock.settimeout(self._idle_timeout)
            except OSError:
                pass
        return data

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        # Nothing to close per-request: the socket lives in the pool. A failed
        # body read already dropped/reopened the connection via the pool's
        # retry on next use.
        return False


class Backend:

    @staticmethod
    def _usage_from_chunk(evt):
        """Pull real usage (input, output) from a stream chunk of ANY backend:
        OpenAI-compat final chunk (usage.prompt_tokens/completion_tokens),
        Anthropic message_start (usage.input_tokens) / message_delta
        (usage.output_tokens), native Ollama final event (prompt_eval_count/
        eval_count). Returns (tin, tout, kind) or None; kind says which field
        arrived so callers can merge over multiple events."""
        if not isinstance(evt, dict):
            return None
        u = evt.get("usage")
        if not isinstance(u, dict) and isinstance(evt.get("message"), dict):
            u = evt["message"].get("usage")   # Anthropic message_start nests it
        if isinstance(u, dict):
            tin = u.get("prompt_tokens") or u.get("input_tokens") or u.get("input_tokens_details")
            tout = u.get("completion_tokens") or u.get("output_tokens")
            if isinstance(tin, dict):
                tin = sum(v for v in tin.values() if isinstance(v, (int, float))) or None
            if isinstance(tout, dict):
                tout = sum(v for v in tout.values() if isinstance(v, (int, float))) or None
            if tin is not None or tout is not None:
                return (int(tin or 0), int(tout or 0), "both" if (tin is not None and tout is not None) else ("in" if tin is not None else "out"))
        # native Ollama final event
        if evt.get("done") and (evt.get("prompt_eval_count") or evt.get("eval_count")):
            return (int(evt.get("prompt_eval_count") or 0), int(evt.get("eval_count") or 0), "both")
        return None
    def __init__(self, cfg):
        self.c = cfg
        self.profile = {}
        self.is_local = False
        self.is_ollama = False
    API_KEY_ENV = "OPENAI_API_KEY"

    def _tuning(self):
        """Effective tuning profile for the active model: registry + any user
        overrides from config `model_tuning.<model>` (user wins)."""
        t = tuning_for(self._model())
        nm = (self._model() or "").lower()
        for k, v in ((self.c.get("model_tuning") or {}).get(nm, {}) or {}).items():
            if k in TUNING_KEYS:
                t[k] = v
        return t

    def _eff(self, key, default=None):
        """Effective config value for `key`, resolved for the ACTIVE model:
        profile.settings -> model tuning -> local_defaults (if local) -> global.
        This is what lets a per-model profile tune behavior for BOTH local and
        cloud backends without a user touching anything."""
        s = self.profile.get("settings") or {}
        if key in s:
            return s[key]
        t = self._tuning()
        if key in t:
            return t[key]
        if self.is_local and key in (self.c.get("local_defaults") or {}):
            return self.c["local_defaults"][key]
        return self.c.get(key, default)

    def _is_compact_schemas(self):
        """Use compact tool schemas for local backends and for models whose
        tuning profile opts in (small/reasoning local models re-evaluate the
        full schema every call). Cloud models without a profile stay full."""
        if self.is_local:
            return True
        return bool(self._tuning().get("compact_schemas"))

    def _local_chat_model(self):
        """True for slow LOCAL non-thinking chat models (registry-only, NO
        network): these get micro schemas + a chat-directive that stops
        trivial-question tool loops — the #1 'why is it so slow' cause on small
        models (qwen2.5 keeps listing files for 'say hi')."""
        return self.is_local and not is_thinking_model(self._model(), None)

    def _tools_for(self, msgs, build_mode):
        """Which tools to offer this turn (small local chat models only):
          None  -> no tools (pure casual chat that would otherwise loop tool
                   calls for minutes on a slow phone)
          "web" -> web-only tools (web_search + fetch_url) so a knowledge
                   question can be looked up without the file-tool loop
          "plan"-> the read-only toolset (Plan mode: read/list/search + the
                   allowlisted run_command) -- restores documented Plan mode
          "all" -> the full toolset (tasks; and every non-gated backend)
        Cloud backends are NEVER gated: full tools in Build mode, read-only
        in Plan mode, every turn, regardless of phrasing. Small local chat
        models keep the gate for responsiveness, with task-stickiness so a
        mid-task "ok"/"lanjutkan" never drops the toolset.
        """
        full = "all" if build_mode else "plan"
        if not self._local_chat_model():
            return full
        user_idx = [i for i, mm in enumerate(msgs) if mm.get("role") == "user"]
        last_text = (msgs[user_idx[-1]].get("content") or "") if user_idx else ""
        kind = _chat_kind(last_text)
        if kind == "task":
            return full
        if kind == "knowledge":
            return "web"
        # chat-like message: keep tools when a task is in flight or just ran
        # (the loop iterates with tool rounds appended after the last user
        # message; and a fresh "ok, lanjutkan" turn right after a task turn
        # must not drop the toolset mid-job)
        if user_idx and any(mm.get("role") == "assistant" and mm.get("tool_calls")
                            for mm in msgs[user_idx[-1] + 1:]):
            return full
        if len(last_text) <= 60 and _CONTINUE_RE.search(last_text):
            prev_text = (msgs[user_idx[-2]].get("content") or "") if len(user_idx) >= 2 else ""
            if _chat_kind(prev_text) == "task":
                return full
        return None

    def _schema_mode(self):
        """full | compact | micro — which tool-schema level to send.
        micro (names + params only) is for slow LOCAL non-thinking chat models:
        the ~614-token compact schema is re-tokenized every call, and cutting it
        to ~300 tokens shaves seconds off each cold prefill on slow hardware.
        Thinking local models go through the native shim (num_ctx 16384 gives
        room); cloud keeps full unless a registry profile opts into compact."""
        if self.is_local:
            if self._local_chat_model():
                return "micro"
            return "compact"
        return "compact" if self._tuning().get("compact_schemas") else "full"
    def _api_key(self):
        k = (self.profile.get("api_key") or "").strip()
        if k and k.lower() not in ("ollama", "placeholder"): return k
        for env in ("TERMUX_AI_API_KEY", self.API_KEY_ENV):
            v = (os.environ.get(env) or "").strip()
            if v: return v
        return ""
    def _req(self, url, data, headers, timeout=120):
        """Single HTTP attempt via the KEEP-ALIVE POOL (fresh TCP+TLS per
        request was costing ~0.3-0.5s x every call in tool loops). Retry/backoff
        is the CALLER's job (_stream_req / _with_retry). Classifies errors as
        transient and parses Retry-After so the caller waits the right amount.
        Returns a response-like object: .read(n), .status, context manager."""
        body = json.dumps(data).encode()
        try:
            resp, _conn = _POOL.post(url, headers, body, timeout=timeout)
            if resp.status >= 400:
                err_body = ""
                try: err_body = resp.read().decode()[:300]
                except Exception: pass
                _POOL.drop_conn(_conn)
                transient = resp.status in (408, 429, 500, 502, 503, 504)
                ra = None
                try:
                    ra = _parse_retry_after(resp.getheader("Retry-After")) if resp.status == 429 else None
                except Exception:
                    pass
                raise BackendError(f"HTTP {resp.status}: {err_body}", transient=transient, retry_after=ra)
            try:
                _fbt = float(self.c.get("first_byte_timeout", 60) or 60)
            except (TypeError, ValueError):
                _fbt = 60.0
            try:
                _idt = float(self.c.get("stream_idle_timeout", 240) or 240)
            except (TypeError, ValueError):
                _idt = 240.0
            return _PooledResponse(resp, _conn, first_byte_timeout=_fbt, idle_timeout=_idt)
        except http.client.HTTPException as e:
            raise BackendError(f"Connection failed: {e}", transient=True)
        except OSError as e:
            if isinstance(e, TimeoutError) or "timed out" in str(e).lower():
                raise BackendError("Gateway sent nothing (first-byte timeout) — the backend is "
                                   "silent or overloaded. /retry continues.", transient=True)
            raise BackendError(f"Connection failed: {e}", transient=True)

    # Read-only, independent tools safe to run concurrently in a batch.
    SAFE_PARALLEL = {"read_file", "list_files", "search_files", "fetch_url", "web_search", "weather", "graphify", "project_info"}  # not test/git-mutations: side effects
    def _run_batch(self, items, build_mode, max_res, done_calls, coverage, ledger=None):
        """Execute a batch of [(name, args)] tool calls, preserving the ORIGINAL
        order in the returned [(name, result, was_new)] list. Read-only tools run
        in a small thread pool (config parallel_tools, default on — they're
        independent: separate files/requests, no shared mutable state); mutating
        tools (write_file, run_command, clone_repo) run sequentially AFTER the
        reads so a batch's reads always see pre-write state, exactly like the
        old sequential loop. Already-done / redundant-read short-circuits are
        claimed sequentially (done_calls/coverage stay race-free)."""
        results = [None] * len(items)
        par, seq = [], []
        for idx, (name, args) in enumerate(items):
            key = (name, json.dumps(args, sort_keys=True))
            if key in done_calls:
                results[idx] = (name, "[ALREADY DONE: you ran this exact call before; the result is in your context above. Refer to it and try a DIFFERENT next step.]", False, True)
                continue
            if name == "read_file" and Backend._is_redundant_read(args, coverage):
                results[idx] = (name, "[ALREADY READ: these lines were fetched in a previous step and are in your context above. Don't re-read; proceed to the next action.]", False, True)
                continue
            done_calls.add(key)
            (par if name in Backend.SAFE_PARALLEL else seq).append((idx, name, args))

        def _exec(name, args):
            try:
                return Tools.run_checked(name, args, build_mode, max_res)
            except Exception as e:   # defensive: a worker crash must not kill the batch
                return False, f"Error: {e}"

        if par:
            if len(par) >= 2 and self.c.get("parallel_tools", True):
                with concurrent.futures.ThreadPoolExecutor(
                        max_workers=min(int(self.c.get("parallel_workers", 4)), len(par))) as ex:
                    outs = list(ex.map(lambda t: _exec(t[1], t[2]), par))
            else:
                outs = [_exec(n, a) for _, n, a in par]
            for (idx, name, args), (ok, r) in zip(par, outs):
                results[idx] = (name, r, True, ok)
                if ledger is not None and name in ("write_file", "edit_file"):
                    ledger.record(name, args.get("path", ""), ok, r[:120])
                if name == "read_file":
                    Backend._track_read(args, r, coverage)
        for idx, name, args in seq:
            ok, r = _exec(name, args)
            results[idx] = (name, r, True, ok)
            if ledger is not None and name in ("write_file", "edit_file"):
                ledger.record(name, args.get("path", ""), ok, r[:120])
            elif ledger is not None and name == "run_command" and ok and not args.get("command", "").strip().startswith(("echo", "cat ", "ls", "grep")):
                ledger.record("run_command", "", True, (args.get("command") or "")[:80])
            elif ledger is not None and name == "git" and ok and (args.get("action") or "") in ("commit", "stage", "checkout_file"):
                ledger.record("git:" + (args.get("action") or ""), args.get("path") or "", True, r[:80])
            if name == "read_file":
                Backend._track_read(args, r, coverage)
        return results

    def _sse_lines(self, resp, idle_timeout=None, ndjson=False):
        if idle_timeout is None:
            try: idle_timeout = float(self.c.get("stream_idle_timeout", 240) or 240)
            except (TypeError, ValueError): idle_timeout = 240.0
        buf = b""
        last_byte = time.monotonic()
        while True:
            if time.monotonic() - last_byte > idle_timeout:
                raise BackendError("Stream idle for too long (gateway went silent mid-generation; buffered "
                                   "providers can pause on long outputs). Aborting this attempt \u2014 "
                                   "/retry continues from the checkpoint, /bench compares backends.", transient=True)
            chunk = resp.read(4096)
            if not chunk: break
            buf += chunk
            last_byte = time.monotonic()
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                line = line.decode("utf-8", "replace").rstrip("\r")
                if ndjson:
                    # Native Ollama /api/chat streams plain newline-delimited
                    # JSON (no "data:" prefix) — parse every non-empty line.
                    line = line.strip()
                    if not line: continue
                    try: yield json.loads(line)
                    except Exception: pass
                    continue
                if not line.startswith("data:"): continue
                d = line[5:].strip()
                if d == "[DONE]": return
                try: yield json.loads(d)
                except Exception: pass

    @staticmethod
    def _transient(e):
        """True when a backend error is worth retrying (network hiccups,
        throttling, timeouts, dropped/empty streams)."""
        if isinstance(e, BackendError): return e.transient
        if isinstance(e, (TimeoutError, ConnectionError, OSError)): return True
        return type(e).__name__ in ("IncompleteRead", "RemoteDisconnected",
                                    "ChunkedEncodingError", "ProtocolError")

    def _with_retry(self, fn):
        """Run fn() retrying transient errors with exponential backoff
        (config: retries, retry_delay). Honors a server Retry-After hint when
        present. Used for non-streaming requests."""
        attempts = max(1, int(self.c.get("retries", 3)))
        base = float(self.c.get("retry_delay", 1.0))
        for attempt in range(1, attempts + 1):
            try:
                return fn()
            except Exception as e:
                if not self._transient(e) or attempt >= attempts:
                    raise
                time.sleep(getattr(e, "retry_after", None) or (base * (2 ** (attempt - 1))))

    @staticmethod
    def _has_payload(evt):
        """True when an SSE event carries real content (vs whitespace-only or
        empty deltas). Lets a drop that happened before anything meaningful was
        streamed be retried without duplicating output."""
        if not isinstance(evt, dict):
            return True
        if evt.get("type") == "content_block_delta":        # Anthropic
            return bool((evt.get("delta") or {}).get("text") or "")
        choices = evt.get("choices") or []                  # OpenAI
        if choices:
            d = (choices[0] or {}).get("delta") or {}
            return bool((d.get("content") or "").strip() or d.get("tool_calls"))
        return True

    def _stream_req(self, url, data, headers, notify=None, mapper=None, ndjson=False):
        """Yield parsed SSE events for ONE request, retrying transient failures
        with exponential backoff (config: retries, retry_delay). A retry only
        happens when NOTHING MEANINGFUL was emitted yet: whitespace-only deltas
        and empty bodies don't count, so a flaky endpoint that drops before
        sending real content is retried instead of erroring. A drop AFTER real
        content propagates (retrying would duplicate output).
        `mapper` (optional) converts each raw event before payload/retry logic
        (used for the native-Ollama shim, whose SSE shape differs from OpenAI).
        `ndjson` (optional) parses plain newline-delimited JSON lines instead of
        SSE "data:" lines (native Ollama /api/chat stream format)."""
        attempts = max(1, int(self.c.get("retries", 3)))
        base = float(self.c.get("retry_delay", 1.0))
        for attempt in range(1, attempts + 1):
            emitted = False
            try:
                _req_data = data
                try:
                    resp = self._req(url, _req_data, headers)
                except BackendError as _be:
                    _msg = str(_be).lower()
                    _dropped = False
                    if "400" in _msg:
                        # Self-heal strict gateways: strip the optional field the
                        # gateway complained about, retry ONCE, remember.
                        if _req_data.get("stream_options") and "stream_options" in _msg:
                            data = {k: v for k, v in _req_data.items() if k != "stream_options"}
                            self.c["usage_stream"] = False
                            _dropped = True
                        elif _req_data.get("reasoning_effort") and "reasoning" in _msg:
                            data = {k: v for k, v in _req_data.items() if k != "reasoning_effort"}
                            try: self.profile.pop("reasoning_effort", None)
                            except Exception: pass
                            _dropped = True
                    if _dropped:
                        resp = self._req(url, data, headers)
                    else:
                        raise
                for evt in self._sse_lines(resp, ndjson=ndjson):
                    if mapper:
                        evt = mapper(evt)
                    if self._has_payload(evt):
                        emitted = True
                    yield evt
                if not emitted:
                    raise BackendError("Empty response from backend (no content).", transient=True)
                return
            except Exception as e:
                if emitted or not self._transient(e) or attempt >= attempts:
                    raise
                delay = getattr(e, "retry_after", None) or (base * (2 ** (attempt - 1)))
                if notify:
                    notify(attempt, attempts, delay)
                else:
                    reason = str(e).split(":")[0][:50].strip() or "transient error"
                    sys.stderr.write(f"\u21bb retry {attempt}/{attempts} in {delay:.0f}s \u00b7 {reason}\n")
                    sys.stderr.flush()
                time.sleep(delay)


    CONTEXT_TOOLS = {"read_file", "list_files", "search_files", "fetch_url", "web_search", "weather"}
    FILE_TOOLS = {"read_file", "list_files", "search_files"}
    WEB_TOOLS = {"fetch_url", "web_search", "weather"}

    def _phase_nudge(self, names, read_streak, phase_nudged, threshold):
        """Drive a gather-then-execute loop. After a just-executed batch, update
        the read-phase streak. Returns (new_streak, new_nudged, nudge_msg). When
        the model keeps READING batch after batch (no execution yet) and its
        streak hits ``threshold``, return a message that tells it to stop probing
        and act -- instead of dribbling one read per iteration forever. Web-only
        loops (fetch/search/weather) get their own 'you have enough, answer now'
        message; file-read loops keep the batched-reads + execute message."""
        all_read = bool(names) and all(n in Backend.CONTEXT_TOOLS for n in names)
        if all_read:
            read_streak += 1
            if read_streak >= threshold and not phase_nudged:
                if all(n in Backend.WEB_TOOLS for n in names):
                    return read_streak, True, (
                        f"[Research phase: {read_streak} consecutive iterations and you're still only probing the web. "
                        "Stop fetching more URLs. Pick the ONE most relevant result you already have, summarize it "
                        "in your own words, and ANSWER the user now. Only fetch again if a single targeted page "
                        "would clearly answer the question.]")
                return read_streak, True, (
                    f"[Context phase: {read_streak} consecutive iterations and you're still only reading. "
                    "Stop reading one file per step. Batch the remaining reads (read_file/list_files/search_files) "
                    "into a SINGLE response with several calls at once, then EXECUTE the task with "
                    "write_file/run_command. Never re-read something already fetched; page big files with "
                    "read_file(path, start=LINE) once per page in the same batched response.]")
            return read_streak, phase_nudged, None
        # Execution (non-read) call: phase is over; allow a future re-read spiral
        # to nudge again.
        return 0, (False if names else phase_nudged), None

    @staticmethod
    def _read_covered(intervals, lo, hi):
        for a, b in intervals:
            if lo >= a and hi <= b:
                return True
        return False

    @staticmethod
    def _read_union(intervals, lo, hi):
        out = []
        for a, b in intervals:
            if hi + 1 < a or b + 1 < lo:
                out.append((a, b))
            else:
                lo, hi = min(lo, a), max(hi, b)
        out.append((lo, hi))
        return out

    @staticmethod
    def _is_redundant_read(args, coverage):
        """True if the requested line range was already fetched this turn.
        Full reads (no start/end) are never flagged redundant -- we track the
        ACTUAL lines returned for those, so the model can always page further."""
        if args.get("start") is None and args.get("end") is None:
            return False
        path = args.get("path", "")
        lo = int(args.get("start") or 1)
        hi = int(args.get("end") or 2000000000)
        return Backend._read_covered(coverage.get(path, []), lo, hi)

    @staticmethod
    def _track_read(args, result, coverage):
        """Mark the ACTUALLY-returned lines as covered -- not the theoretical
        whole file. For a full read, count newlines in the result so paging
        further is never falsely blocked."""
        path = args.get("path", "")
        if not path:
            return
        if args.get("start") is not None or args.get("end") is not None:
            lo = int(args.get("start") or 1)
            hi = int(args.get("end") or 2000000000)
        else:
            n = (result or "").count("\n") + 1 if result else 0
            lo, hi = 1, n
        coverage[path] = Backend._read_union(coverage.get(path, []), lo, hi)

    def _compact_iteration_history(self, msgs, budget=None, keep_recent=None):
        """When accumulated tool results exceed the budget, SUMMARIZE old rounds
        via a quick LLM call instead of crudely truncating — like pi's
        auto-compaction. The model sees a coherent summary + recent results
        intact, so it stays oriented and doesn't spiral into re-reading.

        Returns the number of old messages compacted (0 if none needed).
        Falls back to _trim_iteration_history if the summary call fails."""
        if budget is None:
            budget = self._eff("iteration_history_budget", 30000)
        if keep_recent is None:
            keep_recent = self.c.get("compact_keep_recent", 8000)

        def _tok(x):
            return est_tok(x if isinstance(x, str) else str(x))
        total = sum(_tok(m.get("content", "")) for m in msgs)
        if total <= budget:
            return 0

        # Find the first assistant message that started a tool round.
        first_round = None
        for i, m in enumerate(msgs):
            if m.get("role") == "assistant" and (m.get("tool_calls") or (
                    isinstance(m.get("content"), list) and
                    any(isinstance(b, dict) and b.get("type") == "tool_use" for b in m["content"]))):
                first_round = i
                break
        if first_round is None:
            return 0

        # Walk backwards to find how much to keep (keep_recent tokens).
        acc = 0
        keep_from = len(msgs)
        for i in range(len(msgs) - 1, first_round - 1, -1):
            acc += _tok(msgs[i].get("content", ""))
            if acc >= keep_recent:
                keep_from = i
                break

        # Adjust keep_from to a round boundary so every kept tool result still
        # follows its assistant's tool_calls (the API's hard requirement).
        # Prefer the next assistant-with-tools at/after the budget line; if the
        # line fell inside the final round (after its assistant, before its
        # results), roll back to that assistant so its results stay attached.
        def _is_round_start(mm):
            return mm.get("role") == "assistant" and (mm.get("tool_calls") or (
                isinstance(mm.get("content"), list) and
                any(isinstance(b, dict) and b.get("type") == "tool_use" for b in mm["content"])))

        boundary = None
        for i in range(keep_from, len(msgs)):
            if _is_round_start(msgs[i]):
                boundary = i
                break
        if boundary is not None:
            keep_from = boundary
        else:
            for i in range(keep_from - 1, first_round - 1, -1):
                if _is_round_start(msgs[i]):
                    keep_from = i
                    break

        if keep_from <= first_round + 1:
            return 0  # not enough old rounds to compact

        old = msgs[first_round:keep_from]

        # Build a compact summarization prompt from the old tool results.
        parts = []
        for m in old:
            c = m.get("content", "")
            if isinstance(c, list):  # Anthropic content blocks
                c = " ".join(str(b.get("text", b.get("content", ""))) for b in c if isinstance(b, dict))
            if m.get("role") == "tool":
                parts.append("[tool result]: " + str(c)[:1500])
            elif m.get("role") == "user" and isinstance(m.get("content"), list):
                parts.append("[tool result]: " + str(c)[:1500])
            elif m.get("role") == "assistant" and c:
                parts.append("[reasoning]: " + str(c)[:300])
        if not parts:
            return 0

        compact_msgs = [
            {"role": "system", "content": (
                "Summarize these tool results from a coding session concisely. "
                "For each file read, note: filename, purpose, key sections/functions, important values. "
                "For each command/action, note what was done and the result. "
                "Preserve all filenames, function names, and key data points. Under 400 words.")},
            {"role": "user", "content": "\n\n".join(parts[:30])},
        ]

        try:
            summary = "".join(self.chat(compact_msgs, stream=False))
        except Exception:
            return self._trim_iteration_history(msgs, budget)
        if not summary or len(summary) < 20:
            return self._trim_iteration_history(msgs, budget)

        # Replace old rounds with a single summary message.
        new_hist = msgs[:first_round] + [
            {"role": "user", "content": "[Summary of earlier tool work in this session]\n" + summary}
        ] + msgs[keep_from:]
        if not self._history_rounds_valid(new_hist):
            return 0  # defensive: never emit an orphaned tool result (API hard 400)
        msgs[:] = new_hist
        return len(old)

    @staticmethod
    def _history_rounds_valid(msgs):
        """True when every tool result still follows its assistant tool_calls
        (the API's hard requirement, e.g. 'Messages with role tool must be a
        response to a preceding message with tool_calls'). Handles OpenAI 'tool'
        role messages and Anthropic user-message tool_result blocks."""
        expect = False
        for mm in msgs:
            if not isinstance(mm, dict):
                continue
            r = mm.get("role")
            if r == "assistant":
                expect = bool(mm.get("tool_calls")) or (
                    isinstance(mm.get("content"), list) and
                    any(isinstance(b, dict) and b.get("type") == "tool_use" for b in mm["content"]))
            elif r == "tool":
                if not expect:
                    return False
            elif r in ("user", "system"):
                if isinstance(mm.get("content"), list) and any(
                        isinstance(b, dict) and b.get("type") == "tool_result" for b in mm["content"]):
                    if not expect:
                        return False
                else:
                    expect = False
        return True

    @staticmethod
    def _split_think(content):
        """Split complete content into [(kind, text)] segments on <think>...
        </think> reasoning blocks (deepseek-r1, phi-reasoning). Returns a list
        of ('text', s) / ('thinking', s) tuples; an unclosed <think> (output
        truncated mid-thought) is treated as thinking to the end."""
        if not content:
            return []
        parts = []
        pos = 0
        while pos < len(content):
            oi = content.find("<think>", pos)
            if oi == -1:
                parts.append(("text", content[pos:])); break
            if oi > pos:
                parts.append(("text", content[pos:oi]))
            ci = content.find("</think>", oi + 7)
            if ci == -1:                       # unclosed -> rest is thinking
                parts.append(("thinking", content[oi + 7:])); break
            parts.append(("thinking", content[oi + 7:ci]))
            pos = ci + 8
        return parts

    @staticmethod
    def _asst_msg(content, calls, reasoning=""):
        """Build an OpenAI assistant message. Reasoning models (DeepSeek / o1-class
        via OpenAI-compat gateways like OpenRouter, opencode) stream `reasoning_content`
        and REQUIRE it passed back on subsequent tool-call turns -- dropping it
        yields HTTP 400 "The reasoning_content in the thinking mode must be passed
        back to the API." Only attached when present (non-reasoning models send
        none and are unaffected)."""
        m = {"role": "assistant", "content": content, "tool_calls": calls}
        if reasoning:
            m["reasoning_content"] = reasoning
        return m

    @staticmethod
    def _trim_iteration_history(msgs, budget=30000):
        """Bound accumulated tool-result size for long agentic loops so context
        doesn't balloon. When the budget IS exceeded, trims by VALUE: cheap,
        reproducible results (list_files / search_files / run_command) are cut
        FIRST; file contents (read_file) survive as long as possible. The most
        recent round is always protected -- the model must see what it just
        fetched (trimming the latest starves it and causes runaway re-reads).

        The budget defaults high (30k) so the model KEEPS what it read and
        doesn't spiral into re-reading; lower it via iteration_history_budget
        only if your model has a genuinely small context window."""
        LOW_VALUE = {"list_files", "search_files", "run_command"}
        HEAD = 2500  # chars kept when a result is trimmed (was 600 -- too little)

        def _tok(x):
            return est_tok(x if isinstance(x, str) else str(x))
        current = sum(_tok(m.get("content", "")) for m in msgs)
        if current <= budget:
            return

        # Map tool_call_id -> tool name so we can trim by value.
        id_to_name = {}
        for m in msgs:
            if m.get("role") != "assistant":
                continue
            for tc in (m.get("tool_calls") or []):
                if tc.get("id"):
                    id_to_name[tc["id"]] = (tc.get("function") or {}).get("name", "")
            if isinstance(m.get("content"), list):
                for b in m["content"]:
                    if isinstance(b, dict) and b.get("type") == "tool_use" and b.get("id"):
                        id_to_name[b["id"]] = b.get("name", "")

        # Protect the latest pending round (results the model hasn't acted on).
        protect_from = 0
        for i, mm in enumerate(msgs):
            if mm.get("role") == "assistant" and (mm.get("tool_calls") or (
                    isinstance(mm.get("content"), list) and
                    any(isinstance(b, dict) and b.get("type") == "tool_use" for b in mm["content"]))):
                protect_from = i + 1

        # Collect trimmable results: (priority, order_index, target_dict).
        # priority 0 = low-value (trim first), 1 = high-value (trim last).
        targets = []
        for i, mm in enumerate(msgs):
            if i >= protect_from:
                break
            if mm.get("role") == "tool" and isinstance(mm.get("content"), str) and len(mm["content"]) > HEAD:
                is_low = id_to_name.get(mm.get("tool_call_id", ""), "") in LOW_VALUE
                targets.append((0 if is_low else 1, i, mm))
            elif mm.get("role") == "user" and isinstance(mm.get("content"), list):
                for block in mm["content"]:
                    if isinstance(block, dict) and block.get("type") == "tool_result" \
                            and isinstance(block.get("content"), str) and len(block["content"]) > HEAD:
                        is_low = id_to_name.get(block.get("tool_use_id", ""), "") in LOW_VALUE
                        targets.append((0 if is_low else 1, i, block))
        # Low-value first, then high-value; within each, oldest first.
        targets.sort(key=lambda t: (t[0], t[1]))

        trimmed_n = 0
        for _prio, _idx, target in targets:
            if current <= budget:
                break
            c = target["content"]
            old = _tok(c)
            target["content"] = c[:HEAD] + "\n...[older tool result trimmed]"
            current -= old - _tok(target["content"])
            trimmed_n += 1
        return trimmed_n

class OpenAICompatible(Backend):
    def __init__(self, cfg, profile_name, profile):
        super().__init__(cfg)
        self.name = profile_name
        self.profile = profile or {}
        self._caps_cache = {}   # model name -> capabilities list (from Ollama /api/show)
        base = (self.profile.get("base_url") or "").lower()
        self.is_local = bool(self.profile.get("local")) or any(
            h in base for h in ("localhost", "127.0.0.1", "0.0.0.0", "[::1]"))
        self.is_ollama = self.is_local and (
            profile_name.lower() == "ollama" or "ollama" in base or ":11434" in base)

    def _headers(self):
        k = self._api_key()
        h = {"Content-Type": "application/json", "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"}
        if k: h["Authorization"] = f"Bearer {k}"
        return h

    def _native_ollama(self):
        """True when talking to a LOCAL Ollama server running a THINKING-capable
        model -- route through the native /api/chat endpoint because the /v1
        endpoint can't control thinking AT ALL: think:false by default
        (responsive: measured 247s vs 10s), think:true when the user opts in
        via ollama_no_think=false. Detection uses the tuning registry for the
        known reasoning families and Ollama's /api/show capabilities otherwise."""
        if not self.is_ollama:
            return False
        return is_thinking_model(self._model(), self._ollama_caps(self._model()))

    def _warm(self, sysp=None, tools=None):
        """Best-effort: pre-load the local Ollama model AND prime its KV cache
        (system prompt + tool schemas) in the background at CLI startup, so the
        user's FIRST real turn reuses the cache instead of paying a ~30s cold
        load + full prefill. Runs off the UI thread; failures are swallowed."""
        if not self.is_ollama:
            return
        try:
            base = (self.profile.get("base_url") or "").rstrip("/")
            base = base[:-3] if base.endswith("/v1") else base
            msgs = []
            if sysp:
                msgs.append({"role": "system", "content": sysp})
            msgs.append({"role": "user", "content": "."})
            d = {"model": self._model(), "messages": msgs, "stream": False,
                 "think": False,   # match the default fast path so the cache priming matches
                 "keep_alive": self._eff("ollama_keep_alive", "2h"),
                 "options": {"num_predict": 1}}
            if tools is not None:
                d["tools"] = tools
            req = urllib.request.Request(base + "/api/chat", data=json.dumps(d).encode(),
                                         headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=120) as r:
                r.read()
        except Exception:
            pass

    def _ollama_caps(self, model):
        """Return the capabilities list for an Ollama model (cached). Falls back
        to a name-based heuristic (qwen3/deepseek-r1/phi4-reasoning/... -> has
        thinking) if /api/show is unavailable (old Ollama, cold model, etc.)."""
        if model in self._caps_cache:
            return self._caps_cache[model]
        caps = []
        base = (self.profile.get("base_url") or "").rstrip("/")
        base = base[:-3] if base.endswith("/v1") else base
        if base:
            try:
                req = urllib.request.Request(base + "/api/show",
                    data=json.dumps({"name": model}).encode(),
                    headers={"Content-Type": "application/json"})
                with urllib.request.urlopen(req, timeout=10) as r:
                    caps = (json.loads(r.read()) or {}).get("capabilities") or []
            except Exception:
                caps = []   # fall through to heuristic
        if not caps:
            # name-based fallback (only when /api/show is unavailable): the
            # confirmed Ollama thinking-protocol families. Other reasoning
            # models (deepseek-r1, phi4-reasoning, ...) are detected
            # authoritatively by /api/show when actually pulled, so the
            # heuristic stays conservative to avoid sending think:false to a
            # model whose Ollama build may reject it.
            m = (model or "").lower()
            if any(k in m for k in ("qwen3", "qwq")):
                caps = ["thinking"]
        self._caps_cache[model] = caps
        return caps

    def _url(self):
        base = (self.profile.get("base_url") or "").rstrip("/")
        if not base: raise Exception(f"Profile '{self.name}' has no base_url.\n  Fix: /profile set {self.name}.base_url <url>")
        if self._native_ollama():
            # native endpoint: http://host:11434/api/chat (strip a /v1 suffix)
            base = base[:-3] if base.endswith("/v1") else base
            return base + "/api/chat"
        return f"{base}/chat/completions"

    def _payload(self, msgs, stream, tools=None, temperature=None, max_tokens=None):
        """Build the request body for this backend. Native Ollama (qwen3, no-think)
        moves temperature/max_tokens under `options`, adds `think: false`, and
        normalizes assistant tool_calls so `arguments` is an OBJECT (the model
        streams them as JSON strings in the OpenAI shape; Ollama's native parser
        rejects the round-trip with "can't find closing '}' symbol")."""
        temp = temperature if temperature is not None else self._eff("temperature")
        mt = max_tokens if max_tokens is not None else self._eff("max_tokens", 4096)
        if self._native_ollama():
            msgs = self._native_messages(msgs)
            # Ollama-specific max-tokens override so a low local cap (slow phone
            # CPU) doesn't bleed into cloud (config: ollama_max_tokens).
            omt = self._eff("ollama_max_tokens") or 0
            if omt and max_tokens is None:
                mt = omt
        d = {"model": self._model(), "messages": msgs, "stream": stream}
        if tools is not None:
            d["tools"] = tools
        # Reasoning-effort control (per-profile opt-in, e.g. bynara's reasoning
        # models): 'low' = shortest thinking / fastest reply, 'high' = deep.
        # Documented no-op on non-reasoning models (bynara) and ignored by
        # unknown gateways; a 400 mentioning it is stripped + retried once by
        # _stream_req (same self-healing stream_options has). NEVER sent on
        # the native Ollama path (local thinking is controlled by the shim).
        if not self._native_ollama():
            reff = (self.profile.get("reasoning_effort") or "").strip().lower()
            if reff in ("low", "medium", "high", "minimal"):
                d["reasoning_effort"] = reff
        # Ask OpenAI-compat streams for usage in the final chunk (pi-style
        # accounting). Native Ollama reports usage on its final NDJSON event;
        # Anthropic reports it in message_start/message_delta. If a strict
        # gateway 400s on stream_options, _stream_req disables it for the
        # process and retries once (usage falls back to estimates).
        if (stream and not self._native_ollama()
                and bool(self.c.get("usage_stream", True))):
            d["stream_options"] = {"include_usage": True}
        if self._native_ollama():
            d["think"] = not bool(self._eff("ollama_no_think", True))
            opts = {}
            if temp is not None: opts["temperature"] = temp
            if mt: opts["num_predict"] = mt
            nctx = self._eff("num_ctx") or 0
            if nctx: opts["num_ctx"] = int(nctx)
            if opts: d["options"] = opts
            # Keep the model resident so a slow tool mid-skill (graphify/fetch
            # can take minutes) doesn't force a ~30s cold reload on the next
            # request -- the #1 cause of "stuck in thinking" with skills.
            ka = self._eff("ollama_keep_alive", "2h")
            if ka not in (0, None, "", "0"):
                d["keep_alive"] = ka
        else:
            # o-series on the OFFICIAL OpenAI API needs max_completion_tokens
            # (max_tokens 400s) and only accepts temperature=1 (omit it).
            o_series = needs_completion_tokens(self._model(), self.profile.get("base_url") or "")
            if o_series:
                if mt: d["max_completion_tokens"] = mt
            else:
                if temp is not None: d["temperature"] = temp
                if mt: d["max_tokens"] = mt
        return d

    @staticmethod
    def _native_messages(msgs):
        """Normalize the message history for Ollama's native /api/chat endpoint:
        assistant tool_calls must carry `arguments` as an object, not a JSON
        string (the OpenAI streaming shape the tool loop accumulates)."""
        out = []
        for mm in msgs:
            if mm.get("role") == "assistant" and mm.get("tool_calls"):
                norm_tcs = []
                for tc in mm["tool_calls"]:
                    fn = dict(tc.get("function") or {})
                    args = fn.get("arguments")
                    if isinstance(args, str):
                        try:
                            args = json.loads(args) if args.strip() else {}
                        except Exception:
                            args = {}
                    if not isinstance(args, dict):
                        args = {}
                    fn["arguments"] = args
                    ntc = {k: v for k, v in tc.items() if k != "function"}
                    ntc["function"] = fn
                    norm_tcs.append(ntc)
                mm = {**mm, "tool_calls": norm_tcs}
            out.append(mm)
        return out

    @staticmethod
    def _native_to_openai(evt):
        """Map a native Ollama /api/chat SSE event into the OpenAI shape the
        rest of the tool loop consumes. Native tool_calls carry dict arguments
        and use `done_reason`; OpenAI expects JSON-string arguments and
        `finish_reason`."""
        if not isinstance(evt, dict):
            return evt
        msg = evt.get("message") or {}
        delta = {"role": "assistant"}
        if msg.get("content"):
            delta["content"] = msg["content"]
        if msg.get("thinking"):
            # native thinking stream (think:true) -> OpenAI reasoning_content
            # convention, so the tool loop can display it live AND pass it back
            delta["reasoning_content"] = msg["thinking"]
        tcs = msg.get("tool_calls")
        if tcs:
            out = []
            for i, tc in enumerate(tcs):
                fn = tc.get("function") or {}
                args = fn.get("arguments")
                if isinstance(args, dict):
                    args = json.dumps(args)
                elif not isinstance(args, str):
                    args = "{}"
                out.append({"id": tc.get("id") or f"call_{i}", "type": "function",
                            "function": {"name": fn.get("name", ""), "arguments": args}})
            delta["tool_calls"] = out
        fr = evt.get("finish_reason")
        if fr is None and evt.get("done_reason"):
            fr = evt["done_reason"]
        out = {"choices": [{"delta": delta, "finish_reason": fr}]}
        # carry native usage through so the loop's extractor sees it
        if evt.get("done") and (evt.get("prompt_eval_count") or evt.get("eval_count")):
            out["usage"] = {"prompt_tokens": evt.get("prompt_eval_count") or 0,
                            "completion_tokens": evt.get("eval_count") or 0}
        return out

    def _model(self):
        m = self.profile.get("model")
        if not m: raise Exception(f"Profile '{self.name}' has no model set.\n  Fix: /profile set {self.name}.model <name>")
        return m

    def _check_api_key(self):
        base = self.profile.get("base_url", "")
        if not self._api_key() and "localhost" not in base and "127.0.0.1" not in base:
            raise Exception(f"Profile '{self.name}' has no api_key set.\n  Fix: /profile set {self.name}.api_key YOUR_KEY")

    def chat(self, msgs, stream=None):
        self._check_api_key()
        if stream is None: stream = self.c.get("stream", True)
        d = self._payload(msgs, stream)
        h = self._headers()
        mapper = self._native_to_openai if self._native_ollama() else None
        if stream:
            tf = ThinkFilter()
            for chunk in self._stream_req(self._url(), d, h, mapper=mapper, ndjson=mapper is not None):
                choices = chunk.get("choices") or [{}]
                if t := choices[0].get("delta", {}).get("content", ""):
                    piece = tf.feed(t)
                    if piece: yield piece
            piece = tf.flush()
            if piece: yield piece
        elif mapper:
            body = json.loads(self._with_retry(lambda: self._req(self._url(), d, h).read()))
            yield (body.get("message") or {}).get("content", "")
        else:
            _body = self._with_retry(lambda: json.loads(self._req(self._url(), d, h).read()))
            yield _body["choices"][0]["message"]["content"]

    def chat_with_tools(self, msgs, confirm_batch_fn=None, continue_fn=None):
        self._check_api_key()
        h = self._headers()
        build_mode = self._eff("tools_enabled", False)
        max_res = self._eff("max_tool_result", 10000)

        # Shared loop bookkeeping (iteration ceiling + checkpoints + failure
        # guards) so the OpenAI and Anthropic loops can never drift.
        guard = LoopGuard(self.c, continue_fn)
        ledger = MutationLedger()   # ground truth: what actually changed on disk
        claim_corrected = False     # done-claim guard fires at most once per turn
        auto_verified = False       # auto-verify runs at most once per turn
        self_heal = False   # one-shot: re-offer tools when a no-tools answer wanted them
        GATHER_N = max(2, int(self.c.get("gather_threshold", 5)))
        read_streak = 0
        phase_nudged = False
        done_calls = set()       # (name, args) already executed this turn
        coverage = {}            # path -> covered line intervals
        stuck_streak = 0         # consecutive iterations with ZERO new work
        STUCK_LIMIT = 5          # backstop: stop only if truly no progress

        while True:
            _stop = guard.begin_iteration()
            if _stop:
                yield {"type": "notice", **_stop, "fatal": True}
                return

            compacted = self._compact_iteration_history(msgs)
            if compacted:
                yield {"type": "notice", "level": "info", "icon": "\u23f3", "text": f"context compacted \u00b7 {compacted} old results \u2192 summary", "fatal": False}
            # Deterministic tool-selection gate: small local chat models get NO
            # tools for casual chat (else they loop tool calls for minutes on a
            # slow phone), web-only tools for knowledge questions, and the full
            # toolset for tasks. Temperature clamp only applies when tools are
            # actually on so pure chat keeps the tuned temperature.
            # Self-heal: if a previous no-tools answer looked like it WANTED
            # tools, force the toolset on this retry (one shot per turn).
            if self_heal:
                tools_sel = "all" if build_mode else "plan"
            else:
                tools_sel = self._tools_for(msgs, build_mode)
            temp = min(self._eff("temperature", 0.7), 0.4) if tools_sel else self._eff("temperature", 0.7)
            # max_tokens is read inside _payload so the ollama_max_tokens override
            # (local-only cap) can apply without bleeding into cloud backends.
            _smode = self._schema_mode()
            if tools_sel == "all":
                schemas = Tools.get_schemas(True, compact=_smode != "full", micro=_smode == "micro")
            elif tools_sel == "plan":
                # Plan mode: read-only toolset (no write_file/clone_repo) + the
                # allowlisted run_command -- restores documented Plan mode.
                schemas = Tools.get_schemas(False, compact=_smode != "full", micro=_smode == "micro")
            elif tools_sel == "web":
                schemas = [s for s in Tools.get_schemas(build_mode, compact=_smode != "full", micro=_smode == "micro")
                           if s["function"]["name"] in ("web_search", "fetch_url", "weather")]
            else:
                schemas = None
            d = self._payload(msgs, True, tools=schemas, temperature=temp)
            mapper = self._native_to_openai if self._native_ollama() else None

            acc = OpenAIDeltaAccumulator()
            _live = []   # native LOCAL thinking chunks, re-yielded dim as they arrive
            _usage = {}
            _t_stream0 = time.monotonic()
            _prog_t0 = _t_stream0; _prog_args = 0; _prog_content = 0; _prog_last = 0.0
            for chunk in self._stream_req(self._url(), d, h, mapper=mapper, ndjson=mapper is not None):
                acc.feed(chunk, live_thinking=(_live.append if mapper else None))
                # Progress beacon (throttled to ~1/s): lets the UI show WHAT is
                # streaming (content chars, or write_file argument bytes for the
                # doc case) even when the gateway buffers and nothing renders
                # for tens of seconds. Cheap: int counters, one compare.
                _d = (chunk.get("choices") or [{}])[0].get("delta") if chunk.get("choices") else None
                if _d:
                    _prog_content += len(_d.get("content") or "")
                    for _tc in (_d.get("tool_calls") or []):
                        _fn = _tc.get("function") or {}
                        _prog_args += len(_fn.get("arguments") or "") + len(_fn.get("name") or "")
                _now = time.monotonic()
                if _now - _prog_last >= 1.0:
                    _prog_last = _now
                    yield {"type": "stream_progress", "elapsed": _now - _prog_t0,
                           "content_chars": _prog_content, "arg_chars": _prog_args}
                _u = Backend._usage_from_chunk(chunk)
                if _u:
                    _usage.update({"in": _usage.get("in", 0) + (0 if _u[2] == "out" else _u[0]),
                                   "out": _usage.get("out", 0) + (0 if _u[2] == "in" else _u[1])})
                if _live:
                    yield {"type": "thinking", "content": "".join(_live)}
                    _live.clear()
            if _usage:
                yield {"type": "usage", **_usage, "secs": round(time.monotonic() - _t_stream0, 2)}

            content_buf, reasoning_buf = acc.content, acc.reasoning
            calls = acc.calls
            finish_reason = acc.finish_reason

            if content_buf:
                # Route <think> reasoning blocks (deepseek-r1, ...) into dim
                # 'thinking' events; the assistant message keeps the full
                # content_buf (tags included) so the model sees its own format.
                for kind, text in self._split_think(content_buf):
                    if text:
                        yield {"type": kind, "content": text}

            if not calls:
                # Self-heal a mis-gated turn ONCE: the gate dropped tools (it
                # read the message as casual chat) but the model's answer says
                # it needed them. Re-offer tools and let it retry; a second
                # tool-less answer stands (never loop).
                if (tools_sel is None and not self_heal
                        and _WANTS_TOOLS_RE.search(content_buf or "")):
                    self_heal = True
                    msgs.append({"role": "system", "content":
                                 "Correction: tools ARE available for this request. If the task "
                                 "needs files, commands, or the web, call the appropriate tool now."})
                    yield {"type": "notice", "level": "info", "icon": "\u21bb", "text": "retrying with tools available", "fatal": False}
                    continue
                # Done-claim guard: the answer claims completion (EN+ID) but the
                # ledger shows zero successful mutations. One corrective retry;
                # a second claim passes with an honest no-changes warning.
                if (build_mode and not claim_corrected and ledger.empty()
                        and len(content_buf or "") > 20
                        and _DONE_CLAIM_RE.search(content_buf)):
                    claim_corrected = True
                    msgs.append({"role": "system", "content":
                                 "CORRECTION: you described changes as complete, but NO file was actually "
                                 "written or edited this turn (execution log is empty). Execute the changes "
                                 "now with write_file/edit_file, or state clearly that you could not and why."})
                    yield {"type": "notice", "level": "warn", "icon": "\u26a0",
                           "text": "answer claimed changes but nothing was executed \u00b7 asking the model to actually do it",
                           "fatal": False}
                    continue
                yield {"type": "turn_end", "ledger": ledger, "text": content_buf,
                       "claimed_done": bool(_DONE_CLAIM_RE.search(content_buf or ""))}
                return

            # Oversized single write coaching: a >15KB write_file will be
            # executed as-is (the model already paid for it), but the next
            # message tells it to CONTINUE the document in append sections --
            # so the remainder streams in smaller chunks instead of another
            # monolith (faster first-file + less loss on any mid-turn drop).
            _big_write = next((c for c in calls
                               if c.get("function", {}).get("name") == "write_file"
                               and len(c["function"].get("arguments") or "") > 15000), None)
            if _big_write and finish_reason != "length":
                msgs.append({"role": "system", "content":
                             "Note: that was a very large single write_file. Continue any remaining "
                             "document sections as write_file(append=true) calls of one section each, "
                             "not one giant call."})
                yield {"type": "notice", "level": "info", "icon": "\u2139",
                       "text": "large write \u00b7 asking the model to continue in sections", "fatal": False}

            if finish_reason == "length" and calls:
                # Output was truncated mid-tool-call -> the arguments are almost
                # certainly incomplete (often parse to {}). Executing would just
                # fail with "Path is missing" and the model would flail. Instead
                # tell it to split the work into smaller writes and continue.
                msgs.append(self._asst_msg(content_buf, calls, reasoning_buf))
                note = ("Your previous response was TRUNCATED by the output token limit "
                        "(finish_reason=length), so the tool-call arguments were incomplete. "
                        "Do NOT retry the same large call. Break big file writes into sections: "
                        "write the opening with write_file, then append the rest in parts using "
                        "write_file(append=true). Keep each call well under the output limit.")
                for c in calls:
                    msgs.append({"role": "tool", "tool_call_id": c.get("id", ""), "content": note})
                yield {"type": "notice", "level": "warn", "icon": "\u26a0", "text": "output hit the token limit \u00b7 asking the model to split the write", "fatal": False}
                continue

            guard.note_calls(len(calls))

            norm_calls = []
            for c in calls:
                fn = c["function"]
                try: args = json.loads(fn.get("arguments") or "{}")
                except Exception: args = {}
                norm_calls.append({"id": c.get("id", ""), "name": fn["name"], "args": args})

            # Stream-time sandbox guard: catch doomed writes BEFORE executing
            # (the old path executed, failed, and burned a full corrective
            # round). A write outside cwd gets one system correction asking
            # for a relative path; the whole batch is skipped this round.
            _bad_paths = []
            for nc in norm_calls:
                if nc["name"] in ("write_file", "edit_file"):
                    _p = os.path.expanduser(nc["args"].get("path", "") or "")
                    if _p and not os.path.isabs(_p):
                        _p = os.path.join(os.getcwd(), _p)
                    try:
                        _inside = os.path.commonpath([os.path.realpath(_p), os.path.realpath(os.getcwd())]) == os.path.realpath(os.getcwd())
                    except (ValueError, OSError):
                        _inside = False
                    if not _inside:
                        _bad_paths.append(nc["args"].get("path", ""))
            if _bad_paths:
                msgs.append(self._asst_msg(content_buf, calls, reasoning_buf))
                note = ("SANDBOX: write paths must stay inside the current working directory "
                        "(%s). These were outside: %s. "
                        "Re-issue the SAME writes with RELATIVE paths (e.g. 'rust-guidebook.md'), "
                        "keeping the content identical." % (os.getcwd(), ", ".join(_bad_paths[:3])))
                for c in calls:
                    msgs.append({"role": "tool", "tool_call_id": c.get("id", ""), "content": note})
                yield {"type": "notice", "level": "warn", "icon": "\u26a0",
                       "text": f"write path outside sandbox \u00b7 asking for a relative path",
                       "fatal": False}
                continue

            if not confirm_batch_fn(norm_calls):
                msgs.append(self._asst_msg(content_buf, calls, reasoning_buf))
                for c in calls:
                    msgs.append({"role": "tool", "tool_call_id": c.get("id", ""), "content": "Error: User declined to execute this batch."})
                yield {"type": "notice", "level": "warn", "icon": "\u2716", "text": "batch declined \u2014 trying a different approach", "fatal": False}
                continue

            msg = self._asst_msg(content_buf, calls, reasoning_buf)
            msgs.append(msg)

            total = len(calls)
            items = []
            for c in calls:
                fn = c["function"]
                try: args = json.loads(fn.get("arguments") or "{}")
                except Exception: args = {}
                items.append((fn["name"], args))
            # Execute the batch (read-only calls in parallel, mutators sequential
            # after the reads; original order preserved for the API contract).
            outcomes = self._run_batch(items, build_mode, max_res, done_calls, coverage, ledger)
            batch_results = []
            any_productive = any(w for _, _, w, _ok in outcomes)
            for i, (c, (name, result, _, _ok)) in enumerate(zip(calls, outcomes)):
                yield {"type": "tool_progress", "current": i+1, "total": total, "name": name, "args": json.loads(c["function"].get("arguments") or "{}")}
                yield {"type": "tool_result", "name": name, "result": result}
                msgs.append({"role": "tool", "tool_call_id": c.get("id", ""), "content": result})
                batch_results.append((name, result))

            # Auto-verify: mutations happened this turn and the project has a
            # test runner -> run the suite ONCE and feed the parsed result back
            # before the model can claim done. Skipped when already run this
            # turn, when tests already ran in-batch, or when disabled.
            if (build_mode and self.c.get("auto_verify", True) and not auto_verified
                    and ledger.successful()
                    and not any(n == "test" for n, _, _w, _ok in outcomes)):
                auto_verified = True
                try:
                    summary = Tools.run("test", {})
                    yield {"type": "notice", "level": "info", "icon": "\u23f3",
                           "text": "auto-verify \u00b7 running the project tests", "fatal": False}
                    msgs.append({"role": "system", "content":
                                 "AUTO-VERIFY: the project's tests were just run after your edits. Result:\n" + summary[:3000]
                                 + ("\nFix the failures before answering." if "failed=0" not in summary and "Error" in summary else "")})
                except Exception:
                    pass   # no runner / test tool unavailable: skip silently
            failed = [n for n, _, _w, ok in outcomes if not ok]   # structured flags (run_checked), no string sniffing
            _stop, _reflect = guard.note_results(any_productive, failed)
            if _stop:
                yield {"type": "notice", **_stop, "fatal": True}
                return
            if _reflect:
                msgs.append({"role": "system", "content": _reflect})

            read_streak, phase_nudged, nudge = self._phase_nudge(
                [n for n, _ in batch_results], read_streak, phase_nudged, GATHER_N)
            if nudge:
                msgs.append({"role": "system", "content": nudge})   # full coaching -> the MODEL
                _short = ("answer from what you have" if "still only probing the web" in nudge
                          else "batch the reads, then act")
                yield {"type": "notice", "level": "info", "icon": "\u21bb", "text": f"coaching: {_short}", "fatal": False}

            # Periodic \u201ccontinue?\u201d checkpoint (LoopGuard extends the ceiling
            # only on approval; unattended runs stay capped).
            if guard.checkpoint() == "stop":
                yield {"type": "notice", "level": "warn", "icon": "\u2716", "text": "stopped by user", "fatal": False}
                return

class AnthropicBackend(Backend):
    def __init__(self, cfg):
        super().__init__(cfg)
        self.profile = cfg.get("backends", {}).get("anthropic", {})
    API_KEY_ENV = "ANTHROPIC_API_KEY"

    def _headers(self):
        k = self._api_key() or self.c.get("api_keys", {}).get("anthropic", "")
        if not k: raise Exception("Anthropic key missing.\n  Fix: /profile set anthropic.api_key KEY")
        return {"Content-Type": "application/json", "x-api-key": k, "anthropic-version": "2023-06-01"}

    def _model(self): return self.profile.get("model") or "claude-3-5-sonnet-20241022"

    @staticmethod
    def _split_system(msgs):
        sys_prompt, payload = "", []
        for m in msgs:
            if m["role"] == "system": sys_prompt = m["content"]
            else: payload.append(m)
        return sys_prompt, payload

    def chat(self, msgs, stream=None):
        sys_prompt, payload = self._split_system(msgs)
        if stream is None: stream = self.c.get("stream", True)
        d = {"model": self._model(), "messages": payload, "max_tokens": self._eff("max_tokens", 4096), "stream": stream}
        if sys_prompt: d["system"] = sys_prompt
        h = self._headers()
        url = "https://api.anthropic.com/v1/messages"
        if stream:
            for chunk in self._stream_req(url, d, h):
                if chunk.get("type") == "content_block_delta":
                    if t := chunk.get("delta", {}).get("text", ""): yield t
        else: yield self._with_retry(lambda: json.loads(self._req(url, d, h).read())["content"][0]["text"])

    def chat_with_tools(self, msgs, confirm_batch_fn=None, continue_fn=None):
        sys_prompt, payload = self._split_system(msgs)
        h = self._headers()
        url = "https://api.anthropic.com/v1/messages"
        build_mode = self._eff("tools_enabled", False)
        max_res = self._eff("max_tool_result", 10000)

        # Shared loop bookkeeping (iteration ceiling + checkpoints + failure
        # guards) so the OpenAI and Anthropic loops can never drift.
        guard = LoopGuard(self.c, continue_fn)
        ledger = MutationLedger()   # ground truth: what actually changed on disk
        claim_corrected = False     # done-claim guard fires at most once per turn
        auto_verified = False       # auto-verify runs at most once per turn
        GATHER_N = max(2, int(self.c.get("gather_threshold", 5)))
        read_streak = 0
        phase_nudged = False
        done_calls = set()
        coverage = {}

        while True:
            _stop = guard.begin_iteration()
            if _stop:
                yield {"type": "notice", **_stop, "fatal": True}
                return

            compacted = self._compact_iteration_history(payload)
            if compacted:
                yield {"type": "notice", "level": "info", "icon": "\u23f3", "text": f"context compacted \u00b7 {compacted} old results \u2192 summary", "fatal": False}
            thinking_on = bool(self._eff("extended_thinking", False))
            d = {"model": self._model(), "messages": payload, "tools": Tools.to_anthropic_schema(build_mode), "stream": True}
            if thinking_on:
                # Extended thinking (Claude 3.7/4): genuine hidden reasoning before acting.
                budget = max(1024, int(self._eff("thinking_budget", 8000)))
                d["max_tokens"] = budget + max(int(self._eff("max_tokens", 4096)), 2048)
                d["thinking"] = {"type": "enabled", "budget_tokens": budget}
                # thinking requires temperature to be unset (the API defaults it to 1)
            else:
                d["max_tokens"] = self._eff("max_tokens", 4096)
                d["temperature"] = min(self._eff("temperature", 0.7), 0.4) if build_mode else self._eff("temperature", 0.7)
            if sys_prompt: d["system"] = sys_prompt

            content_blocks = {}
            text_block = ""
            stop_reason = None

            _usage = {}
            _t_stream0 = time.monotonic()
            _prog_t0 = _t_stream0; _prog_last = 0.0; _prog_content = 0
            for chunk in self._stream_req(url, d, h):
                _dt = chunk.get("delta") or {} if chunk.get("type") == "content_block_delta" else {}
                _prog_content += len(_dt.get("text") or "") if isinstance(_dt, dict) else 0
                _now = time.monotonic()
                if _now - _prog_last >= 1.0:
                    _prog_last = _now
                    yield {"type": "stream_progress", "elapsed": _now - _prog_t0,
                           "content_chars": _prog_content, "arg_chars": 0}
                _u = Backend._usage_from_chunk(chunk)
                if _u:
                    _usage.update({"in": _usage.get("in", 0) + (0 if _u[2] == "out" else _u[0]),
                                   "out": _usage.get("out", 0) + (0 if _u[2] == "in" else _u[1])})
                evt_type = chunk.get("type")
                if evt_type == "message_delta":
                    sr = chunk.get("delta", {}).get("stop_reason")
                    if sr: stop_reason = sr
                elif evt_type == "content_block_start":
                    idx = chunk.get("index")
                    block = chunk.get("content_block", {})
                    if block.get("type") == "thinking":
                        content_blocks[idx] = {"type": "thinking", "thinking": "", "signature": ""}
                    else:
                        content_blocks[idx] = block
                        if block.get("type") == "tool_use":
                            content_blocks[idx]["input"] = ""
                elif evt_type == "content_block_delta":
                    idx = chunk.get("index")
                    delta = chunk.get("delta", {})
                    dt = delta.get("type")
                    if dt == "text_delta":
                        text = delta.get("text", "")
                        content_blocks[idx]["text"] += text
                        text_block += text
                    elif dt == "input_json_delta":
                        content_blocks[idx]["input"] += delta.get("partial_json", "")
                    elif dt == "thinking_delta":
                        content_blocks[idx]["thinking"] += delta.get("thinking", "")
                        yield {"type": "thinking", "content": delta.get("thinking", "")}
                    elif dt == "signature_delta":
                        content_blocks[idx]["signature"] += delta.get("signature", "")

            blocks = [content_blocks[k] for k in sorted(content_blocks.keys())]
            tool_uses = [b for b in blocks if b.get("type") == "tool_use"]
            if _usage:
                yield {"type": "usage", **_usage, "secs": round(time.monotonic() - _t_stream0, 2)}

            for tu in tool_uses:
                try: tu["input"] = json.loads(tu.get("input", "{}") or "{}")
                except Exception: tu["input"] = {}

            if text_block:
                yield {"type": "text", "content": text_block}

            if not tool_uses:
                if (build_mode and not claim_corrected and ledger.empty()
                        and len(text_block or "") > 20
                        and _DONE_CLAIM_RE.search(text_block)):
                    claim_corrected = True
                    payload.append({"role": "user", "content":
                                 "CORRECTION: you described changes as complete, but NO file was actually "
                                 "written or edited this turn (execution log is empty). Execute the changes "
                                 "now with write_file/edit_file, or state clearly that you could not and why."})
                    yield {"type": "notice", "level": "warn", "icon": "\u26a0",
                           "text": "answer claimed changes but nothing was executed \u00b7 asking the model to actually do it",
                           "fatal": False}
                    continue
                yield {"type": "turn_end", "ledger": ledger, "text": text_block,
                       "claimed_done": bool(_DONE_CLAIM_RE.search(text_block or ""))}
                return

            if stop_reason == "max_tokens" and tool_uses:
                # Output truncated mid-tool-call -> inputs are incomplete. Don't
                # execute; tell the model to split the work into smaller writes.
                results = []
                note = ("Your previous response was TRUNCATED by the output token limit "
                        "(stop_reason=max_tokens), so the tool-call inputs were incomplete. "
                        "Do NOT retry the same large call. Break big file writes into sections: "
                        "write the opening with write_file, then append the rest in parts using "
                        "write_file(append=true). Keep each call well under the output limit.")
                for tu in tool_uses:
                    results.append({"type": "tool_result", "tool_use_id": tu["id"], "content": note})
                payload.append({"role": "assistant", "content": blocks})
                payload.append({"role": "user", "content": results})
                yield {"type": "notice", "level": "warn", "icon": "\u26a0", "text": "output hit the token limit \u00b7 asking the model to split the write", "fatal": False}
                continue

            guard.note_calls(len(tool_uses))

            norm_calls = []
            for tu in tool_uses:
                norm_calls.append({"id": tu["id"], "name": tu["name"], "args": tu.get("input", {}) or {}})

            if not confirm_batch_fn(norm_calls):
                results = []
                for tu in tool_uses:
                    results.append({"type": "tool_result", "tool_use_id": tu["id"], "content": "Error: User declined to execute this batch."})
                payload.append({"role": "assistant", "content": blocks})
                payload.append({"role": "user", "content": results})
                yield {"type": "notice", "level": "warn", "icon": "\u2716", "text": "batch declined \u2014 trying a different approach", "fatal": False}
                continue

            payload.append({"role": "assistant", "content": blocks})
            results = []

            total = len(tool_uses)
            items = [(tu["name"], (tu.get("input") or {})) for tu in tool_uses]
            # Execute the batch (read-only calls in parallel, mutators sequential
            # after the reads; original order preserved for the API contract).
            outcomes = self._run_batch(items, build_mode, max_res, done_calls, coverage, ledger)
            batch_results = []
            any_productive = any(w for _, _, w, _ok in outcomes)
            for i, (tu, (name, result, _, _ok)) in enumerate(zip(tool_uses, outcomes)):
                yield {"type": "tool_progress", "current": i+1, "total": total, "name": name, "args": (tu.get("input") or {})}
                yield {"type": "tool_result", "name": name, "result": result}
                results.append({"type": "tool_result", "tool_use_id": tu["id"], "content": result})
                batch_results.append((name, result))

            payload.append({"role": "user", "content": results})

            # Auto-verify: mutations happened this turn and the project has a
            # test runner -> run the suite ONCE and feed the parsed result back
            # before the model can claim done. Skipped when already run this
            # turn, when tests already ran in-batch, or when disabled.
            if (build_mode and self.c.get("auto_verify", True) and not auto_verified
                    and ledger.successful()
                    and not any(n == "test" for n, _, _w, _ok in outcomes)):
                auto_verified = True
                try:
                    summary = Tools.run("test", {})
                    yield {"type": "notice", "level": "info", "icon": "\u23f3",
                           "text": "auto-verify \u00b7 running the project tests", "fatal": False}
                    payload.append({"role": "user", "content":
                                 "AUTO-VERIFY: the project's tests were just run after your edits. Result:\n" + summary[:3000]
                                 + ("\nFix the failures before answering." if "failed=0" not in summary and "Error" in summary else "")})
                except Exception:
                    pass   # no runner / test tool unavailable: skip silently
            failed = [n for n, _, _w, ok in outcomes if not ok]   # structured flags (run_checked), no string sniffing
            _stop, _reflect = guard.note_results(any_productive, failed)
            if _stop:
                yield {"type": "notice", **_stop, "fatal": True}
                return
            if _reflect:
                sys_prompt = ((sys_prompt + "\n\n") if sys_prompt else "") + _reflect

            read_streak, phase_nudged, nudge = self._phase_nudge(
                [n for n, _ in batch_results], read_streak, phase_nudged, GATHER_N)
            if nudge:
                payload.append({"role": "user", "content": nudge})  # full coaching -> the MODEL
                _short = ("answer from what you have" if "still only probing the web" in nudge
                          else "batch the reads, then act")
                yield {"type": "notice", "level": "info", "icon": "\u21bb", "text": f"coaching: {_short}", "fatal": False}

            # Periodic \u201ccontinue?\u201d checkpoint (LoopGuard extends the ceiling
            # only on approval; unattended runs stay capped).
            if guard.checkpoint() == "stop":
                yield {"type": "notice", "level": "warn", "icon": "\u2716", "text": "stopped by user", "fatal": False}
                return

def get_backend(cfg):
    name, profile = cfg.active_profile()
    if name in ("anthropic", "claude"): return AnthropicBackend(cfg)
    if profile is None:
        available = ", ".join(cfg.get("backends", {}).keys()) or "(none)"
        raise Exception(f"Backend '{name}' not found in config.backends.\n  Available: {available}\n  Fix: /profile add {name} <base_url> <model> [api_key]")
    return OpenAICompatible(cfg, name, profile)
