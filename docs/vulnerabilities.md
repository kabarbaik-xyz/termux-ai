# Vulnerability Findings — Termux AI CLI

**Target:** Termux AI v7.0.0  
**Total Findings:** 14 (0 Critical, 0 High, 3 Medium, 5 Low, 6 Informational)

**Remediation Status (v7.1.0):** V-01 ✅ | V-03 ✅ | V-06 ✅ | V-07 ✅ — 4 findings resolved. See [remediation-plan.md](remediation-plan.md) for details.

---

## V-01 — SSRF: DNS Rebinding Gap in fetch_url  ✅ REMEDIATED (v7.1.0)

| Field | Value |
|-------|-------|
| **Severity** | Medium |
| **OWASP** | A10:2021 — Server-Side Request Forgery |
| **NIST CSF** | PR.AC-5 |
| **Location** | `src/tools.py:265-275` (`_is_private_host`), `src/tools.py:305-308` (fetch guard) |
| **Exploitability** | Requires a malicious URL provided by the AI (prompt-influenced) |

### Description

The SSRF guard checks whether the hostname is a private/loopback/reserved IP **literal**. DNS hostnames that resolve to private IPs are not blocked. The code explicitly acknowledges this limitation:

```python
# src/tools.py:271-273
# DNS hostnames can't be fully checked cheaply (rebinding), so we only
# guard obvious literals -- the device is single-user and low-stakes.
```

An attacker who can influence the AI to call `fetch_url("http://evil.com/rebind")` — where `evil.com` resolves to `127.0.0.1` or `169.254.169.254` — can cause the CLI to fetch internal services.

### Impact

- Access to `127.0.0.1:11434` (Ollama API) — model manipulation, data exfiltration.
- Access to cloud metadata endpoints (`169.254.169.254`) — credential theft [verify: Termux/Android cloud context].
- Access to other localhost-bound services.

### Remediation

Resolve the hostname and validate the resolved IP before connecting:

```python
import socket

@staticmethod
def _is_private_host(host):
    host = (host or "").lower().strip()
    if not host:
        return False
    if host == "localhost" or host.endswith(".localhost"):
        return True
    try:
        ip = ipaddress.ip_address(host)
        return ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast
    except ValueError:
        # DNS hostname: resolve and check ALL resolved addresses
        if not Tools._allow_private():
            try:
                addrs = socket.getaddrinfo(host, None)
                for fam, _, _, _, sa in addrs:
                    resolved = ipaddress.ip_address(sa[0])
                    if resolved.is_private or resolved.is_loopback or resolved.is_link_local:
                        return True
            except socket.gaierror:
                pass
        return False
```

**Note:** Full DNS-rebinding prevention requires pinning the resolved IP for the actual connection (use `urllib3` with a custom connection pool, or check `resp.fp.raw._sock`). The above resolves the first-leg gap.

---

## V-02 — write_file TOCTOU Race (Symlink Swap)

| Field | Value |
|-------|-------|
| **Severity** | Medium |
| **OWASP** | A01:2021 — Broken Access Control |
| **NIST CSF** | PR.DS-1 |
| **Location** | `src/tools.py:~520-535` (`write_file` in `_run_impl`) |
| **Exploitability** | Requires concurrent local process with write access to CWD |

### Description

`write_file` resolves symlinks and checks `os.path.commonpath()` containment, then opens the file for writing. Between the `realpath()` check and the `open()`/`write_text()` call, a symlink could be swapped to point outside CWD:

```python
# Simplified flow:
inside_cwd = os.path.commonpath([os.path.realpath(p), os.path.realpath(cwd)]) == os.path.realpath(cwd)
# ... TOCTOU window: attacker swaps symlink target here ...
Path(p).write_text(content)  # writes through the swapped symlink
```

### Impact

In a single-user Termux environment with no concurrent malicious processes, risk is minimal. In shared/multi-app environments, a crafted symlink swap could write to arbitrary paths (e.g., `~/.bashrc`, `~/.ssh/authorized_keys`).

### Remediation

Open with `O_NOFOLLOW` to reject symlinks at the kernel level, or open the file then re-verify:

```python
import os

# Open with O_NOFOLLOW to reject symlinks
fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_NOFOLLOW, 0o600)
try:
    # Verify the fd still points inside CWD
    real_fd = os.path.realpath(f"/proc/self/fd/{fd}")
    if os.path.commonpath([real_fd, os.path.realpath(cwd)]) != os.path.realpath(cwd):
        os.close(fd)
        return "Error: path escaped CWD after open."
    os.write(fd, content.encode("utf-8"))
finally:
    os.close(fd)
```

---

## V-03 — Unrestricted read_file — Sensitive File Access  ✅ REMEDIATED (v7.1.0)

| Field | Value |
|-------|------- |
| **Severity** | Medium |
| **OWASP** | A01:2021 — Broken Access Control |
| **NIST CSF** | PR.AC-4 |
| **Location** | `src/tools.py:~510-516` (`read_file` in `_run_impl`), `src/fileio.py` (`FileReader.read`) |
| **Exploitability** | Requires AI to be prompted/induced to read a sensitive path |

### Description

`read_file` accepts any absolute or tilde-expanded path with no path restriction. The AI (or a prompt-injection payload in fetched content) can read any file the Termux user has access to:

```
read_file(path="/proc/self/environ")     → environment variables, API keys
read_file(path="~/.ssh/id_rsa")          → private SSH key
read_file(path="~/.config/termux-ai/config.json")  → stored API keys
```

`FileReader.read` has no path-based restrictions either.

### Impact

Exfiltration of API keys, SSH keys, and other secrets to the LLM backend. Prompt injection in fetched web pages or cloned repos can trigger this.

### Remediation

Add a configurable denylist for sensitive path patterns:

```python
SENSITIVE_PATHS = {
    "~/.ssh", "/proc/self/environ", "~/.config/termux-ai/config.json",
    "~/.gnupg", "/proc/self/maps", "~/.netrc", "~/.aws/credentials",
}

@staticmethod
def _is_sensitive(path):
    expanded = os.path.expanduser(path)
    real = os.path.realpath(expanded)
    for s in SENSITIVE_PATHS:
        if real.startswith(os.path.expanduser(s)):
            return True
    return False

# In read_file handler:
if Tools._is_sensitive(p):
    return "Error: Access to sensitive path denied (contains credentials/keys)."
```

Additionally, consider an explicit user-configurable allowlist for directories the AI may read.

---

## V-04 — API Keys Stored in Plaintext config.json

| Field | Value |
|-------|-------|
| **Severity** | Low |
| **OWASP** | A02:2021 — Cryptographic Failures |
| **NIST CSF** | PR.DS-1 |
| **CIS** | 3.3 |
| **Location** | `src/config.py` (`Config` class), `src/backends.py` (`_api_key` from profile) |
| **Exploitability** | Requires filesystem access to `~/.config/termux-ai/config.json` |

### Description

API keys for OpenAI/Anthropic backends are stored in `config.json` in cleartext. The file is mode `0o600` (owner read/write only), which mitigates multi-user risk, but any process running as the Termux user can read it.

### Remediation (Options)

1. **Prefer env vars** (already supported): document `TERMUX_AI_API_KEY` / `OPENAI_API_KEY` as the recommended method.
2. **Platform keystore**: use Android Keystore via `termux-api` for key storage [verify: API availability].
3. **File-based encryption**: encrypt the API key in config with a passphrase-derived AES key. Example using `cryptography`:

```python
from cryptography.fernet import Fernet
# On first set: key = Fernet.generate_key(); store in OS keyring or derive from passphrase
# On read: Fernet(key).decrypt(encrypted_blob)
```

---

## V-05 — AI_FETCH_ALLOW_PRIVATE Disables All SSRF Protection

| Field | Value |
|-------|-------|
| **Severity** | Low |
| **OWASP** | A05:2021 — Security Misconfiguration |
| **Location** | `src/tools.py:262-264` (`_allow_private`), `src/tools.py:305-308` |

### Description

The env var `AI_FETCH_ALLOW_PRIVATE=1` globally disables SSRF protection for all `fetch_url` calls in the session. If set (e.g., by a user who needed it once), the AI can fetch any private address without restriction.

### Remediation

Make it per-call rather than global, or require a more specific pattern:

```python
# Option A: Per-host allowlist instead of global bypass
FETCH_ALLOW_HOSTS = set(os.environ.get("AI_FETCH_ALLOW_HOSTS", "").split(","))

@staticmethod
def _is_private_host(host):
    if host in Tools.FETCH_ALLOW_HOSTS:
        return False
    # ... existing checks ...
```

---

## V-06 — clone_repo Temp Directory Accumulation  ✅ REMEDIATED (v7.1.0)

| Field | Value |
|-------|-------|
| **Severity** | Low |
| **NIST CSF** | PR.IP-7 |
| **Location** | `src/tools.py:410-460` (`_clone_repo`) |

### Description

`clone_repo` creates a temp directory (`tempfile.mkdtemp(prefix="ai_clone_")`). On success, the directory is returned to the AI but **never cleaned up**. Repeated clone operations accumulate directories in `$TMPDIR`/`/tmp`.

### Remediation

Track clone directories and clean them on session exit:

```python
# In App.__init__:
self._clone_dirs = []

# In _clone_repo success:
# (return path, but also register it for cleanup)
# App-level: add cleanup in __del__ or atexit
import atexit
atexit.register(lambda: shutil.rmtree(target, ignore_errors=True))
```

Or document that the AI should clean up after itself (current implicit behavior).

---

## V-07 — History File Lacks Explicit Permission Setting  ✅ REMEDIATED (v7.1.0)

| Field | Value |
|-------|-------|
| **Severity** | Low |
| **OWASP** | A02:2021 — Cryptographic Failures |
| **Location** | `src/_constants.py` (`HISTORY_FILE = CONFIG_DIR / "history"`), readline usage in `app.py` |

### Description

The SQLite DB, config.json, and PID file are all explicitly secured with `_secure_file(0o600)`. The readline history file (`~/.config/termux-ai/history`) is written by Python's `readline.write_history_file()` without explicit permission setting. The containing directory is `0o700`, which mitigates this, but for consistency it should be explicitly secured.

### Remediation

```python
# After writing history file:
readline.write_history_file(str(HISTORY_FILE))
_secure_file(HISTORY_FILE)  # enforce 0o600
```

---

## V-08 — No Rate Limiting on API Calls / Tool Calls

| Field | Value |
|-------|-------|
| **Severity** | Low |
| **OWASP** | A04:2021 — Insecure Design |
| **NIST CSF** | PR.AC-7 |
| **Location** | `src/app.py` (tool loop, `max_iterations`), `src/backends.py` (`_req`) |

### Description

Tool iterations are bounded by `max_iterations` (preventing infinite loops), but there is no rate limit on:
- Number of API calls per minute/hour (cost control).
- Number of `run_command` executions per session.
- Number of `fetch_url` calls per session.

A prompt-injection attack or runaway AI could rapidly consume API credits.

### Remediation

```python
# Simple sliding-window rate limiter
class RateLimiter:
    def __init__(self, max_calls, window_sec=60):
        self.calls = collections.deque()
        self.max = max_calls
        self.window = window_sec

    def check(self):
        now = time.time()
        self.calls = collections.deque(c for c in self.calls if now - c < self.window)
        if len(self.calls) >= self.max:
            return False
        self.calls.append(now)
        return True
```

---

## V-09 — GitHub Token Sent on All api.github.com Requests

| Field | Value |
|-------|-------|
| **Severity** | Informational |
| **OWASP** | A07:2021 — Identification and Authentication Failures |
| **Location** | `src/tools.py:298-301` |

### Description

When fetching `api.github.com`, the `GITHUB_TOKEN`/`GH_TOKEN` env var is automatically attached. This is convenient but means any `fetch_url` to GitHub API endpoints includes the token. If the AI is prompt-injected to fetch a crafted GitHub API URL, query parameters could be logged.

### Recommendation

This is by-design for authenticated GitHub API access. Document that `GITHUB_TOKEN` is sent automatically and consider scoping tokens with minimal permissions.

---

## V-10 — No TLS Certificate Pinning for API Backends

| Field | Value |
|-------|-------|
| **Severity** | Informational |
| **OWASP** | A02:2021 — Cryptographic Failures |
| **Location** | `src/backends.py` (`_req` uses `urllib.request`) |

### Description

API calls to OpenAI/Anthropic use `urllib.request.urlopen` with default TLS validation (validates against system CA store). No certificate pinning is applied. A compromised CA or MITM with a valid cert could intercept traffic.

### Recommendation

Standard TLS validation is adequate for this use case. Certificate pinning would add complexity disproportionate to the threat model of a single-user CLI. No action required.

---

## V-11 — Session Resume State Stored Unencrypted

| Field | Value |
|-------|-------|
| **Severity** | Informational |
| **Location** | `src/db.py` (`resume_state` table), `src/app.py` (`_pending_checkpoint`) |

### Description

Interrupted tool-call sessions are persisted to the `resume_state` SQLite table, including executed tool results. These may contain file contents, command output, or other sensitive data. The database is mode `0o600` but unencrypted.

### Recommendation

Acceptable for the threat model. If full-disk encryption is enabled on the Android device, data-at-rest is covered at the OS level.

---

## V-12 — No Audit/Security Event Logging

| Field | Value |
|-------|-------|
| **Severity** | Informational |
| **NIST CSF** | DE.AE-3 |
| **Location** | `src/app.py` (no security event log) |

### Description

There is no dedicated security event log. Tool executions, command approvals, and SSRF blocks are printed to stdout but not persisted. If an incident occurs, there is no forensic trail.

### Recommendation

Add optional structured logging to a security event log:

```python
import json, time
def log_security_event(event_type, detail):
    logf = CONFIG_DIR / "security.log"
    entry = {"ts": time.time(), "type": event_type, "detail": detail}
    with open(logf, "a") as f:
        f.write(json.dumps(entry) + "\n")
    _secure_file(logf)
```

---

## V-13 — Error Messages May Leak Internal Paths

| Field | Value |
|-------|-------|
| **Severity** | Informational |
| **OWASP** | A05:2021 — Security Misconfiguration |
| **Location** | `src/tools.py` (various error returns), `src/app.py` |

### Description

Error messages include full file paths, e.g., `"Error: Not found at /data/data/com.termux/files/home/..."`. This reveals the Termux sandbox path structure.

### Recommendation

Acceptable for a CLI tool where the user already has full shell access. No action required.

---

## V-14 — Python Version Dependency (cp314)

| Field | Value |
|-------|-------|
| **Severity** | Informational |
| **Location** | `pip freeze` output (numpy/pandas built for cp314) |

### Description

The installed numpy and pandas packages are built for CPython 3.14 (`cp314-cp314-android_aarch64`). These are pre-release/development builds. While not directly a security issue, pre-release runtime dependencies may have undiscovered vulnerabilities.

### Recommendation

Monitor for stable CPython 3.14 release and update when available. Not a direct security risk for the CLI itself (which uses only stdlib).
