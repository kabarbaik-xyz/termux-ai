# ══ termux_ai.backends ══ (fragment; merged by build.py)
class BackendError(Exception):
    """Backend request failure. transient=True when a retry may succeed
    (network blips, 429/5xx, timeouts, empty or dropped streams). retry_after
    carries a server-suggested wait (from the Retry-After header) in seconds."""
    def __init__(self, message, transient=False, retry_after=None):
        super().__init__(message)
        self.transient = transient
        self.retry_after = retry_after


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


class Backend:
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
    def _api_key(self):
        k = (self.profile.get("api_key") or "").strip()
        if k and k.lower() not in ("ollama", "placeholder"): return k
        for env in ("TERMUX_AI_API_KEY", self.API_KEY_ENV):
            v = (os.environ.get(env) or "").strip()
            if v: return v
        return ""
    def _req(self, url, data, headers, timeout=120):
        """Single HTTP attempt. Retry/backoff is the CALLER's job (_stream_req
        for streaming, _with_retry otherwise) — having _req retry too would
        compound into up to 9 attempts on a persistent 429/503, which is what
        made cloud backends slow and noisy. Classifies the error as transient
        and parses Retry-After so the caller waits the right amount."""
        body = json.dumps(data).encode()
        r = urllib.request.Request(url, data=body, headers=headers, method="POST")
        try:
            return urllib.request.urlopen(r, timeout=timeout)
        except urllib.error.HTTPError as e:
            err_body = ""
            try: err_body = e.read().decode()[:300]
            except Exception: pass
            transient = e.code in (408, 429, 500, 502, 503, 504)
            ra = _parse_retry_after(e.headers.get("Retry-After")) if e.code == 429 else None
            raise BackendError(f"HTTP {e.code}: {err_body}", transient=transient, retry_after=ra)
        except urllib.error.URLError as e:
            if isinstance(e.reason, TimeoutError):
                raise BackendError("Request timed out.", transient=True)
            raise BackendError(f"Connection failed: {e.reason}", transient=True)
        except TimeoutError:
            raise BackendError("Request timed out.", transient=True)

    def _sse_lines(self, resp, idle_timeout=120, ndjson=False):
        buf = b""
        last_byte = time.monotonic()
        while True:
            if time.monotonic() - last_byte > idle_timeout:
                raise BackendError("Stream idle for too long. Aborting.", transient=True)
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
                resp = self._req(url, data, headers)
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
                    sys.stderr.write(
                        f"\n[retry {attempt}/{attempts} in {delay:.0f}s \u2014 {reason}]\n")
                    sys.stderr.flush()
                time.sleep(delay)

    @staticmethod
    def _is_failure(result):
        """True when a tool result is a genuine error/blocked (a normal empty
        result or non-zero exit code is NOT a failure). Used for reflect-on-
        failure and consecutive-failure detection."""
        return (result or "").lstrip().lower().startswith("error")

    CONTEXT_TOOLS = {"read_file", "list_files", "search_files", "fetch_url"}

    def _phase_nudge(self, names, read_streak, phase_nudged, threshold):
        """Drive a gather-then-execute loop. After a just-executed batch, update
        the read-phase streak. Returns (new_streak, new_nudged, nudge_msg). When
        the model keeps READING batch after batch (no execution yet) and its
        streak hits ``threshold``, return a message that tells it to batch the
        remaining reads into ONE response and move to executing -- instead of
        dribbling one read per iteration forever."""
        all_read = bool(names) and all(n in Backend.CONTEXT_TOOLS for n in names)
        if all_read:
            read_streak += 1
            if read_streak >= threshold and not phase_nudged:
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
        model with thinking disabled. The OpenAI-compat endpoint does NOT honor
        `think`, so reasoning models (qwen3, deepseek-r1, phi4-reasoning, ...) burn
        minutes of phone CPU thinking before answering (measured 247s vs 10s).
        The native /api/chat endpoint accepts `think: false` (config:
        ollama_no_think, default on). Detection uses the tuning registry for the
        known reasoning families and Ollama's /api/show capabilities otherwise."""
        if not self._eff("ollama_no_think", True):
            return False
        if not self.is_ollama:
            return False
        return is_thinking_model(self._model(), self._ollama_caps(self._model()))

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
        if self._native_ollama():
            d["think"] = False
            opts = {}
            if temp is not None: opts["temperature"] = temp
            if mt: opts["num_predict"] = mt
            nctx = self._eff("num_ctx") or 0
            if nctx: opts["num_ctx"] = int(nctx)
            if opts: d["options"] = opts
            # Keep the model resident so a slow tool mid-skill (graphify/fetch
            # can take minutes) doesn't force a ~30s cold reload on the next
            # request -- the #1 cause of "stuck in thinking" with skills.
            ka = self._eff("ollama_keep_alive", "30m")
            if ka not in (0, None, "", "0"):
                d["keep_alive"] = ka
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
        return {"choices": [{"delta": delta, "finish_reason": fr}]}

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
            yield self._with_retry(lambda: json.loads(self._req(self._url(), d, h).read())["choices"][0]["message"]["content"])

    def chat_with_tools(self, msgs, confirm_batch_fn=None, continue_fn=None):
        self._check_api_key()
        h = self._headers()
        build_mode = self._eff("tools_enabled", False)
        max_res = self._eff("max_tool_result", 10000)

        iterations = 0
        total_calls = 0
        MAX_ITERATIONS = self.c.get("max_iterations", 50)
        _continue_every = self.c.get("continue_every", 10)
        next_prompt_at = _continue_every
        # max_iterations is the UNATTENDED ceiling (one-shot/piped runs).
        # In a live session each approved 'continue?' checkpoint EXTENDS it,
        # so a long trusted task (install+build+test+fix) runs to completion
        # instead of dying mid-build at 50.
        iteration_cap = MAX_ITERATIONS
        MAX_FAILURES = 3
        consecutive_failures = 0
        REPEAT_LIMIT = max(2, int(self.c.get("repeat_limit", 3)))
        repeat_count = {}
        GATHER_N = max(2, int(self.c.get("gather_threshold", 5)))
        read_streak = 0
        phase_nudged = False
        done_calls = set()       # (name, args) already executed this turn
        coverage = {}            # path -> covered line intervals
        stuck_streak = 0         # consecutive iterations with ZERO new work
        STUCK_LIMIT = 5          # backstop: stop only if truly no progress

        while True:
            iterations += 1
            if iterations > iteration_cap:
                yield {"type": "notice", "content": "[Stopped: reached the iteration limit (%d). In a live session, approve the 'continue?' prompt to keep a long task going; /config set max_iterations N raises the unattended ceiling.]" % iteration_cap, "fatal": True}
                return

            compacted = self._compact_iteration_history(msgs)
            if compacted:
                yield {"type": "notice", "content": f"[context: compacted {compacted} old tool result(s) into a summary to free space]", "fatal": False}
            temp = min(self._eff("temperature", 0.7), 0.4) if build_mode else self._eff("temperature", 0.7)
            # max_tokens is read inside _payload so the ollama_max_tokens override
            # (local-only cap) can apply without bleeding into cloud backends.
            d = self._payload(msgs, True, tools=Tools.get_schemas(build_mode, compact=self._is_compact_schemas()), temperature=temp)
            mapper = self._native_to_openai if self._native_ollama() else None

            content_buf = ""
            reasoning_buf = ""   # reasoning models (deepseek/o1-class) require this passed back on tool-call turns
            tool_calls_buf = {}
            finish_reason = None

            for chunk in self._stream_req(self._url(), d, h, mapper=mapper, ndjson=mapper is not None):
                if not chunk.get("choices"): continue
                ch0 = chunk["choices"][0]
                delta = ch0.get("delta", {})
                fr = ch0.get("finish_reason")
                if fr: finish_reason = fr
                if delta.get("content"):
                    content_buf += delta["content"]
                if delta.get("reasoning_content") or delta.get("reasoning"):
                    reasoning_buf += delta.get("reasoning_content") or delta.get("reasoning") or ""
                if delta.get("tool_calls"):
                    for tc in delta["tool_calls"]:
                        idx = tc.get("index", 0)
                        if idx not in tool_calls_buf:
                            tool_calls_buf[idx] = {"id": tc.get("id", ""), "type": "function", "function": {"name": "", "arguments": ""}}

                        for k, v in tc.items():
                            if k not in ("index", "function"):
                                tool_calls_buf[idx][k] = v

                        if tc.get("function"):
                            for fk, fv in tc["function"].items():
                                if fk == "name":
                                    tool_calls_buf[idx]["function"]["name"] += fv
                                elif fk == "arguments":
                                    tool_calls_buf[idx]["function"]["arguments"] += fv
                                else:
                                    tool_calls_buf[idx]["function"][fk] = fv

            calls = list(tool_calls_buf.values())

            if content_buf:
                # Route <think> reasoning blocks (deepseek-r1, ...) into dim
                # 'thinking' events; the assistant message keeps the full
                # content_buf (tags included) so the model sees its own format.
                for kind, text in self._split_think(content_buf):
                    if text:
                        yield {"type": kind, "content": text}

            if not calls:
                return

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
                yield {"type": "notice", "content": "\n[Output hit the token limit mid-tool-call - asked the AI to split the write into smaller pieces (write_file + append).]", "fatal": False}
                continue

            total_calls += len(calls)

            norm_calls = []
            for c in calls:
                fn = c["function"]
                try: args = json.loads(fn.get("arguments") or "{}")
                except Exception: args = {}
                norm_calls.append({"id": c.get("id", ""), "name": fn["name"], "args": args})

            if not confirm_batch_fn(norm_calls):
                msgs.append(self._asst_msg(content_buf, calls, reasoning_buf))
                for c in calls:
                    msgs.append({"role": "tool", "tool_call_id": c.get("id", ""), "content": "Error: User declined to execute this batch."})
                yield {"type": "notice", "content": "\n[User declined the proposed actions. Please try a different approach.]", "fatal": False}
                continue

            msg = self._asst_msg(content_buf, calls, reasoning_buf)
            msgs.append(msg)

            total = len(calls)
            batch_results = []
            any_productive = False
            for i, c in enumerate(calls):
                fn = c["function"]
                try: args = json.loads(fn.get("arguments") or "{}")
                except Exception: args = {}

                yield {"type": "tool_progress", "current": i+1, "total": total, "name": fn["name"], "args": args}

                # Short-circuit: don't re-execute work already done this turn.
                # Redirect the model instead of killing the task.
                key = (fn["name"], json.dumps(args, sort_keys=True))
                if key in done_calls:
                    result = "[ALREADY DONE: you ran this exact call before; the result is in your context above. Refer to it and try a DIFFERENT next step.]"
                elif fn["name"] == "read_file" and Backend._is_redundant_read(args, coverage):
                    result = "[ALREADY READ: these lines were fetched in a previous step and are in your context above. Don't re-read; proceed to the next action.]"
                else:
                    result = Tools.run(fn["name"], args, build_mode, max_res)
                    done_calls.add(key)
                    if fn["name"] == "read_file":
                        Backend._track_read(args, result, coverage)
                    any_productive = True

                yield {"type": "tool_result", "name": fn["name"], "result": result}
                msgs.append({"role": "tool", "tool_call_id": c.get("id", ""), "content": result})
                batch_results.append((fn["name"], result))

            if any_productive:
                stuck_streak = 0
            else:
                stuck_streak += 1
                if stuck_streak >= STUCK_LIMIT:
                    yield {"type": "notice", "content": "[Stopped: the last %d rounds were all repeats of work already done \u2014 no new progress. /retry or rephrase the task.]" % STUCK_LIMIT, "fatal": True}
                    return

            failed = [n for n, r in batch_results if Backend._is_failure(r)]
            if failed:
                consecutive_failures += 1
                if consecutive_failures >= MAX_FAILURES:
                    yield {"type": "notice", "content": "[Stopped after %d consecutive failed action round(s). Last failure(s): %s. I\u2019m stuck \u2014 please rephrase the task, enable Build mode (/tools on), or add detail.]" % (consecutive_failures, ", ".join(failed)), "fatal": True}
                    return
                msgs.append({"role": "system", "content": "REFLECT: your last action(s) failed \u2014 %s. Before the next step, state out loud what you will do DIFFERENTLY. Do not retry the same approach or any blocked/interpreter/redirect command." % ", ".join(failed)})
            else:
                consecutive_failures = 0

            read_streak, phase_nudged, nudge = self._phase_nudge(
                [n for n, _ in batch_results], read_streak, phase_nudged, GATHER_N)
            if nudge:
                msgs.append({"role": "system", "content": nudge})
                yield {"type": "notice", "content": "\n" + nudge, "fatal": False}

            # Periodic \u201ccontinue?\u201d prompt for long tasks (every 10 tool calls).
            if total_calls >= next_prompt_at:
                if continue_fn is None:
                    next_prompt_at += _continue_every     # unattended: no prompt, no extension (MAX_ITERATIONS still caps runaway)
                elif continue_fn(iterations, total_calls):
                    next_prompt_at += _continue_every     # approved -> extend the ceiling so a long task runs to completion
                    iteration_cap += _continue_every
                else:
                    yield {"type": "notice", "content": "[Stopped by user.]", "fatal": False}
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

        iterations = 0
        total_calls = 0
        MAX_ITERATIONS = self.c.get("max_iterations", 50)
        _continue_every = self.c.get("continue_every", 10)
        next_prompt_at = _continue_every
        # max_iterations is the UNATTENDED ceiling (one-shot/piped runs).
        # In a live session each approved 'continue?' checkpoint EXTENDS it,
        # so a long trusted task (install+build+test+fix) runs to completion
        # instead of dying mid-build at 50.
        iteration_cap = MAX_ITERATIONS
        MAX_FAILURES = 3
        consecutive_failures = 0
        REPEAT_LIMIT = max(2, int(self.c.get("repeat_limit", 3)))
        repeat_count = {}
        GATHER_N = max(2, int(self.c.get("gather_threshold", 5)))
        read_streak = 0
        phase_nudged = False
        done_calls = set()
        coverage = {}
        stuck_streak = 0
        STUCK_LIMIT = 5

        while True:
            iterations += 1
            if iterations > iteration_cap:
                yield {"type": "notice", "content": "[Stopped: reached the iteration limit (%d). In a live session, approve the 'continue?' prompt to keep a long task going; /config set max_iterations N raises the unattended ceiling.]" % iteration_cap, "fatal": True}
                return

            compacted = self._compact_iteration_history(payload)
            if compacted:
                yield {"type": "notice", "content": f"[context: compacted {compacted} old tool result(s) into a summary to free space]", "fatal": False}
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

            for chunk in self._stream_req(url, d, h):
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

            for tu in tool_uses:
                try: tu["input"] = json.loads(tu.get("input", "{}") or "{}")
                except Exception: tu["input"] = {}

            if text_block:
                yield {"type": "text", "content": text_block}

            if not tool_uses:
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
                yield {"type": "notice", "content": "\n[Output hit the token limit mid-tool-call - asked the AI to split the write into smaller pieces (write_file + append).]", "fatal": False}
                continue

            total_calls += len(tool_uses)

            norm_calls = []
            for tu in tool_uses:
                norm_calls.append({"id": tu["id"], "name": tu["name"], "args": tu.get("input", {}) or {}})

            if not confirm_batch_fn(norm_calls):
                results = []
                for tu in tool_uses:
                    results.append({"type": "tool_result", "tool_use_id": tu["id"], "content": "Error: User declined to execute this batch."})
                payload.append({"role": "assistant", "content": blocks})
                payload.append({"role": "user", "content": results})
                yield {"type": "notice", "content": "\n[User declined the proposed actions. Please try a different approach.]", "fatal": False}
                continue

            payload.append({"role": "assistant", "content": blocks})
            results = []

            total = len(tool_uses)
            batch_results = []
            any_productive = False
            for i, tu in enumerate(tool_uses):
                args = tu.get("input", {}) or {}
                yield {"type": "tool_progress", "current": i+1, "total": total, "name": tu["name"], "args": args}

                key = (tu["name"], json.dumps(args, sort_keys=True))
                if key in done_calls:
                    result = "[ALREADY DONE: you ran this exact call before; the result is in your context above. Refer to it and try a DIFFERENT next step.]"
                elif tu["name"] == "read_file" and Backend._is_redundant_read(args, coverage):
                    result = "[ALREADY READ: these lines were fetched in a previous step and are in your context above. Don't re-read; proceed to the next action.]"
                else:
                    result = Tools.run(tu["name"], args, build_mode, max_res)
                    done_calls.add(key)
                    if tu["name"] == "read_file":
                        Backend._track_read(args, result, coverage)
                    any_productive = True

                yield {"type": "tool_result", "name": tu["name"], "result": result}
                results.append({"type": "tool_result", "tool_use_id": tu["id"], "content": result})
                batch_results.append((tu["name"], result))

            payload.append({"role": "user", "content": results})

            if any_productive:
                stuck_streak = 0
            else:
                stuck_streak += 1
                if stuck_streak >= STUCK_LIMIT:
                    yield {"type": "notice", "content": "[Stopped: the last %d rounds were all repeats of work already done \u2014 no new progress. /retry or rephrase the task.]" % STUCK_LIMIT, "fatal": True}
                    return

            failed = [n for n, r in batch_results if Backend._is_failure(r)]
            if failed:
                consecutive_failures += 1
                if consecutive_failures >= MAX_FAILURES:
                    yield {"type": "notice", "content": "[Stopped after %d consecutive failed action round(s). Last failure(s): %s. I\u2019m stuck \u2014 please rephrase the task, enable Build mode (/tools on), or add detail.]" % (consecutive_failures, ", ".join(failed)), "fatal": True}
                    return
                sys_prompt = ((sys_prompt + "\n\n") if sys_prompt else "") + ("REFLECT: your last action(s) failed \u2014 %s. Before the next step, state out loud what you will do DIFFERENTLY. Do not retry the same approach or any blocked/interpreter/redirect command." % ", ".join(failed))
            else:
                consecutive_failures = 0

            read_streak, phase_nudged, nudge = self._phase_nudge(
                [n for n, _ in batch_results], read_streak, phase_nudged, GATHER_N)
            if nudge:
                payload.append({"role": "user", "content": nudge})
                yield {"type": "notice", "content": "\n" + nudge, "fatal": False}

            # Periodic \u201ccontinue?\u201d prompt for long tasks (every 10 tool calls).
            if total_calls >= next_prompt_at:
                if continue_fn is None:
                    next_prompt_at += _continue_every     # unattended: no prompt, no extension (MAX_ITERATIONS still caps runaway)
                elif continue_fn(iterations, total_calls):
                    next_prompt_at += _continue_every     # approved -> extend the ceiling so a long task runs to completion
                    iteration_cap += _continue_every
                else:
                    yield {"type": "notice", "content": "[Stopped by user.]", "fatal": False}
                    return

def get_backend(cfg):
    name, profile = cfg.active_profile()
    if name in ("anthropic", "claude"): return AnthropicBackend(cfg)
    if profile is None:
        available = ", ".join(cfg.get("backends", {}).keys()) or "(none)"
        raise Exception(f"Backend '{name}' not found in config.backends.\n  Available: {available}\n  Fix: /profile add {name} <base_url> <model> [api_key]")
    return OpenAICompatible(cfg, name, profile)
