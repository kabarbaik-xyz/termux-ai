# ══ termux_ai.backends ══ (fragment; merged by build.py)
class BackendError(Exception):
    """Backend request failure. transient=True when a retry may succeed
    (network blips, 429/5xx, timeouts, empty or dropped streams)."""
    def __init__(self, message, transient=False):
        super().__init__(message)
        self.transient = transient

class Backend:
    def __init__(self, cfg): self.c = cfg
    API_KEY_ENV = "OPENAI_API_KEY"
    def _api_key(self):
        k = (self.profile.get("api_key") or "").strip()
        if k and k.lower() not in ("ollama", "placeholder"): return k
        for env in ("TERMUX_AI_API_KEY", self.API_KEY_ENV):
            v = (os.environ.get(env) or "").strip()
            if v: return v
        return ""
    def _req(self, url, data, headers, timeout=120):
        body = json.dumps(data).encode()
        for attempt in range(3):
            r = urllib.request.Request(url, data=body, headers=headers, method="POST")
            try:
                return urllib.request.urlopen(r, timeout=timeout)
            except urllib.error.HTTPError as e:
                err_body = ""
                try: err_body = e.read().decode()[:300]
                except Exception: pass
                transient = e.code in (408, 429, 500, 502, 503, 504)
                if transient and attempt < 2:
                    time.sleep(0.5 * (2 ** attempt))
                    continue
                raise BackendError(f"HTTP {e.code}: {err_body}", transient=transient)
            except urllib.error.URLError as e:
                if isinstance(e.reason, TimeoutError):
                    if attempt < 2:
                        time.sleep(0.5 * (2 ** attempt))
                        continue
                    raise BackendError("Request timed out.", transient=True)
                if attempt < 2:
                    time.sleep(0.5 * (2 ** attempt))
                    continue
                raise BackendError(f"Connection failed: {e.reason}", transient=True)
            except TimeoutError:
                if attempt < 2:
                    time.sleep(0.5 * (2 ** attempt))
                    continue
                raise BackendError("Request timed out.", transient=True)

    def _sse_lines(self, resp, idle_timeout=120):
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
        (config: retries, retry_delay). Used for non-streaming requests."""
        attempts = max(1, int(self.c.get("retries", 3)))
        base = float(self.c.get("retry_delay", 1.0))
        for attempt in range(1, attempts + 1):
            try:
                return fn()
            except Exception as e:
                if not self._transient(e) or attempt >= attempts:
                    raise
                time.sleep(base * (2 ** (attempt - 1)))

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

    def _stream_req(self, url, data, headers, notify=None):
        """Yield parsed SSE events for ONE request, retrying transient failures
        with exponential backoff (config: retries, retry_delay). A retry only
        happens when NOTHING MEANINGFUL was emitted yet: whitespace-only deltas
        and empty bodies don't count, so a flaky endpoint that drops before
        sending real content is retried instead of erroring. A drop AFTER real
        content propagates (retrying would duplicate output)."""
        attempts = max(1, int(self.c.get("retries", 3)))
        base = float(self.c.get("retry_delay", 1.0))
        for attempt in range(1, attempts + 1):
            emitted = False
            try:
                resp = self._req(url, data, headers)
                for evt in self._sse_lines(resp):
                    if self._has_payload(evt):
                        emitted = True
                    yield evt
                if not emitted:
                    raise BackendError("Empty response from backend (no content).", transient=True)
                return
            except Exception as e:
                if emitted or not self._transient(e) or attempt >= attempts:
                    raise
                delay = base * (2 ** (attempt - 1))
                if notify:
                    notify(attempt, attempts, delay)
                else:
                    sys.stderr.write(
                        f"\n[network hiccup \u2014 retrying in {delay:.0f}s ({attempt}/{attempts})]\n")
                    sys.stderr.flush()
                time.sleep(delay)

    @staticmethod
    def _is_failure(result):
        """True when a tool result is a genuine error/blocked (a normal empty
        result or non-zero exit code is NOT a failure). Used for reflect-on-
        failure and consecutive-failure detection."""
        return (result or "").lstrip().lower().startswith("error")

    @staticmethod
    def _trim_iteration_history(msgs, budget=8000):
        """Bound accumulated tool-result size for long agentic loops so context
        doesn't balloon. Truncates OLDER tool results to a head snippet -- but
        NEVER touches the results of the most recent tool-call round: the model
        must see what it just fetched to continue (trimming the latest result
        starves it and causes runaway re-reads, never completing the task)."""
        def _tok(x):
            return est_tok(x if isinstance(x, str) else str(x))
        current = sum(_tok(m.get("content", "")) for m in msgs)
        if current <= budget:
            return
        # Protect everything after the last assistant message that requested
        # tools (OpenAI tool_calls OR Anthropic tool_use blocks): that is the
        # pending round whose results the model hasn't acted on yet.
        protect_from = 0
        for i, mm in enumerate(msgs):
            if mm.get("role") == "assistant" and (mm.get("tool_calls") or (
                    isinstance(mm.get("content"), list) and
                    any(isinstance(b, dict) and b.get("type") == "tool_use" for b in mm["content"]))):
                protect_from = i + 1
        for i, mm in enumerate(msgs):
            if current <= budget or i >= protect_from:
                break
            if mm.get("role") == "tool" and isinstance(mm.get("content"), str) and len(mm["content"]) > 200:
                old = _tok(mm["content"])
                mm["content"] = mm["content"][:600] + "\n...[older tool result trimmed]"
                current -= old - _tok(mm["content"])
            elif mm.get("role") == "user" and isinstance(mm.get("content"), list):
                for block in mm["content"]:
                    if isinstance(block, dict) and block.get("type") == "tool_result" and isinstance(block.get("content"), str) and len(block["content"]) > 200:
                        old = _tok(block["content"])
                        block["content"] = block["content"][:600] + "\n...[older tool result trimmed]"
                        current -= old - _tok(block["content"])

class OpenAICompatible(Backend):
    def __init__(self, cfg, profile_name, profile):
        super().__init__(cfg)
        self.name = profile_name
        self.profile = profile or {}

    def _headers(self):
        k = self._api_key()
        h = {"Content-Type": "application/json", "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"}
        if k: h["Authorization"] = f"Bearer {k}"
        return h

    def _url(self):
        base = (self.profile.get("base_url") or "").rstrip("/")
        if not base: raise Exception(f"Profile '{self.name}' has no base_url.\n  Fix: /profile set {self.name}.base_url <url>")
        return f"{base}/chat/completions"

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
        d = {"model": self._model(), "messages": msgs, "temperature": self.c.get("temperature"), "stream": stream, "max_tokens": self.c.get("max_tokens", 4096)}
        h = self._headers()
        if stream:
            for chunk in self._stream_req(self._url(), d, h):
                choices = chunk.get("choices") or [{}]
                if t := choices[0].get("delta", {}).get("content", ""): yield t
        else: yield self._with_retry(lambda: json.loads(self._req(self._url(), d, h).read())["choices"][0]["message"]["content"])

    def chat_with_tools(self, msgs, confirm_batch_fn=None, continue_fn=None):
        self._check_api_key()
        h = self._headers()
        build_mode = self.c.get("tools_enabled", False)
        max_res = self.c.get("max_tool_result", 10000)

        iterations = 0
        total_calls = 0
        MAX_ITERATIONS = self.c.get("max_iterations", 50)
        _continue_every = self.c.get("continue_every", 10)
        next_prompt_at = _continue_every
        MAX_FAILURES = 3
        consecutive_failures = 0

        while True:
            iterations += 1
            if iterations > MAX_ITERATIONS:
                yield {"type": "notice", "content": "[Stopped: reached the maximum of %d iterations to prevent runaway loops.]" % MAX_ITERATIONS, "fatal": True}
                return

            self._trim_iteration_history(msgs)
            temp = min(self.c.get("temperature", 0.7), 0.4) if build_mode else self.c.get("temperature", 0.7)
            d = {"model": self._model(), "messages": msgs, "temperature": temp, "stream": True, "tools": Tools.get_schemas(build_mode), "max_tokens": self.c.get("max_tokens", 4096)}

            content_buf = ""
            tool_calls_buf = {}
            finish_reason = None

            for chunk in self._stream_req(self._url(), d, h):
                if not chunk.get("choices"): continue
                ch0 = chunk["choices"][0]
                delta = ch0.get("delta", {})
                fr = ch0.get("finish_reason")
                if fr: finish_reason = fr
                if delta.get("content"):
                    content_buf += delta["content"]
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
                yield {"type": "text", "content": content_buf}

            if not calls:
                return

            if finish_reason == "length" and calls:
                # Output was truncated mid-tool-call -> the arguments are almost
                # certainly incomplete (often parse to {}). Executing would just
                # fail with "Path is missing" and the model would flail. Instead
                # tell it to split the work into smaller writes and continue.
                msgs.append({"role": "assistant", "content": content_buf, "tool_calls": calls})
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
                msgs.append({"role": "assistant", "content": content_buf, "tool_calls": calls})
                for c in calls:
                    msgs.append({"role": "tool", "tool_call_id": c.get("id", ""), "content": "Error: User declined to execute this batch."})
                yield {"type": "notice", "content": "\n[User declined the proposed actions. Please try a different approach.]", "fatal": False}
                continue

            msg = {"role": "assistant", "content": content_buf, "tool_calls": calls}
            msgs.append(msg)

            total = len(calls)
            batch_results = []
            for i, c in enumerate(calls):
                fn = c["function"]
                try: args = json.loads(fn.get("arguments") or "{}")
                except Exception: args = {}

                yield {"type": "tool_progress", "current": i+1, "total": total, "name": fn["name"], "args": args}

                result = Tools.run(fn["name"], args, build_mode, max_res)
                yield {"type": "tool_result", "name": fn["name"], "result": result}
                msgs.append({"role": "tool", "tool_call_id": c["id"], "content": result})
                batch_results.append((fn["name"], result))

            failed = [n for n, r in batch_results if Backend._is_failure(r)]
            if failed:
                consecutive_failures += 1
                if consecutive_failures >= MAX_FAILURES:
                    yield {"type": "notice", "content": "[Stopped after %d consecutive failed action round(s). Last failure(s): %s. I\u2019m stuck \u2014 please rephrase the task, enable Build mode (/tools on), or add detail.]" % (consecutive_failures, ", ".join(failed)), "fatal": True}
                    return
                msgs.append({"role": "system", "content": "REFLECT: your last action(s) failed \u2014 %s. Before the next step, state out loud what you will do DIFFERENTLY. Do not retry the same approach or any blocked/interpreter/redirect command." % ", ".join(failed)})
            else:
                consecutive_failures = 0

            # Periodic \u201ccontinue?\u201d prompt for long tasks (every 10 tool calls).
            if total_calls >= next_prompt_at:
                if continue_fn and not continue_fn(iterations, total_calls):
                    yield {"type": "notice", "content": "[Stopped by user.]", "fatal": False}
                    return
                next_prompt_at += _continue_every

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
        d = {"model": self._model(), "messages": payload, "max_tokens": self.c.get("max_tokens", 4096), "stream": stream}
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
        build_mode = self.c.get("tools_enabled", False)
        max_res = self.c.get("max_tool_result", 10000)

        iterations = 0
        total_calls = 0
        MAX_ITERATIONS = self.c.get("max_iterations", 50)
        _continue_every = self.c.get("continue_every", 10)
        next_prompt_at = _continue_every
        MAX_FAILURES = 3
        consecutive_failures = 0

        while True:
            iterations += 1
            if iterations > MAX_ITERATIONS:
                yield {"type": "notice", "content": "[Stopped: reached the maximum of %d iterations to prevent runaway loops.]" % MAX_ITERATIONS, "fatal": True}
                return

            self._trim_iteration_history(payload)
            thinking_on = bool(self.c.get("extended_thinking", False))
            d = {"model": self._model(), "messages": payload, "tools": Tools.to_anthropic_schema(build_mode), "stream": True}
            if thinking_on:
                # Extended thinking (Claude 3.7/4): genuine hidden reasoning before acting.
                budget = max(1024, int(self.c.get("thinking_budget", 8000)))
                d["max_tokens"] = budget + max(int(self.c.get("max_tokens", 4096)), 2048)
                d["thinking"] = {"type": "enabled", "budget_tokens": budget}
                # thinking requires temperature to be unset (the API defaults it to 1)
            else:
                d["max_tokens"] = self.c.get("max_tokens", 4096)
                d["temperature"] = min(self.c.get("temperature", 0.7), 0.4) if build_mode else self.c.get("temperature", 0.7)
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
            for i, tu in enumerate(tool_uses):
                args = tu.get("input", {}) or {}
                yield {"type": "tool_progress", "current": i+1, "total": total, "name": tu["name"], "args": args}

                result = Tools.run(tu["name"], args, build_mode, max_res)
                yield {"type": "tool_result", "name": tu["name"], "result": result}
                results.append({"type": "tool_result", "tool_use_id": tu["id"], "content": result})
                batch_results.append((tu["name"], result))

            payload.append({"role": "user", "content": results})

            failed = [n for n, r in batch_results if Backend._is_failure(r)]
            if failed:
                consecutive_failures += 1
                if consecutive_failures >= MAX_FAILURES:
                    yield {"type": "notice", "content": "[Stopped after %d consecutive failed action round(s). Last failure(s): %s. I\u2019m stuck \u2014 please rephrase the task, enable Build mode (/tools on), or add detail.]" % (consecutive_failures, ", ".join(failed)), "fatal": True}
                    return
                sys_prompt = ((sys_prompt + "\n\n") if sys_prompt else "") + ("REFLECT: your last action(s) failed \u2014 %s. Before the next step, state out loud what you will do DIFFERENTLY. Do not retry the same approach or any blocked/interpreter/redirect command." % ", ".join(failed))
            else:
                consecutive_failures = 0

            # Periodic \u201ccontinue?\u201d prompt for long tasks (every 10 tool calls).
            if total_calls >= next_prompt_at:
                if continue_fn and not continue_fn(iterations, total_calls):
                    yield {"type": "notice", "content": "[Stopped by user.]", "fatal": False}
                    return
                next_prompt_at += _continue_every

def get_backend(cfg):
    name, profile = cfg.active_profile()
    if name in ("anthropic", "claude"): return AnthropicBackend(cfg)
    if profile is None:
        available = ", ".join(cfg.get("backends", {}).keys()) or "(none)"
        raise Exception(f"Backend '{name}' not found in config.backends.\n  Available: {available}\n  Fix: /profile add {name} <base_url> <model> [api_key]")
    return OpenAICompatible(cfg, name, profile)
