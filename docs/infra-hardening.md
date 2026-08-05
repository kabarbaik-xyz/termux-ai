# Infrastructure Hardening — Termux AI CLI

**Target:** Termux AI v7.0.0  
**Scope:** Local configuration, file permissions, process management, network exposure.

---

## 1. Overview

Termux AI runs entirely on-device within the Termux sandbox. There is no server infrastructure, cloud deployment, or IaC (Terraform/CloudFormation). All hardening is at the level of **local file permissions, process management, and network egress controls**.

---

## 2. Storage Layout & Permissions

### Current State

| Artifact | Path | Mode | Secured? |
|----------|------|------|----------|
| Config directory | `~/.config/termux-ai/` | `0o700` | ✅ `_secure_dir()` |
| Config file | `~/.config/termux-ai/config.json` | `0o600` | ✅ `_secure_file()` |
| SQLite database | `~/.config/termux-ai/ai_history.db` | `0o600` | ✅ `_secure_file()` |
| PID file | `~/.config/termux-ai/server.pid` | `0o600` | ✅ `_secure_file()` |
| History file | `~/.config/termux-ai/history` | Inherited (dir `0o700`) | ⚠️ No explicit `_secure_file()` |
| Temp clone dirs | `$TMPDIR/ai_clone_*` | Default umask | ⚠️ No cleanup on success |

### Recommendation H-1: Secure the History File

**CIS Reference:** 3.3 (Sensitive Data at Rest)  
**Location:** `src/_constants.py`, `src/app.py` (readline history write)

```python
# After writing readline history:
readline.write_history_file(str(HISTORY_FILE))
_secure_file(HISTORY_FILE)  # Add this line — enforce 0o600
```

### Recommendation H-2: Clean Up clone_repo Temp Directories

**Location:** `src/tools.py:410-460`

```python
import atexit

# Track clone dirs at module level
_CLONE_DIRS = []

@staticmethod
def _clone_repo(url, depth=1, build_mode=False, timeout=120):
    # ... existing code ...
    target = tempfile.mkdtemp(prefix="ai_clone_")
    _CLONE_DIRS.append(target)  # Register for cleanup
    atexit.register(shutil.rmtree, target, ignore_errors=True)
    # ... rest of existing code ...
```

---

## 3. SQLite Database Hardening

### Current State (src/db.py)

| Setting | Value | Assessment |
|---------|-------|------------|
| Journal mode | `WAL` (Write-Ahead Logging) | ✅ Concurrent read-safe, crash-resistant |
| Busy timeout | `10000ms` (10s) | ✅ Prevents lock errors under load |
| Foreign keys | `ON` | ✅ Referential integrity enforced |
| File permissions | `0o600` | ✅ Owner-only access |
| Parameterized queries | ✅ All queries use `?` placeholders | ✅ No SQL injection risk |
| Encryption | ❌ None | ⚠️ Acceptable for single-user Termux; FDE recommended at OS level |

### Recommendation H-3: Enable SQLCipher (Optional)

For users storing sensitive conversation data, offer optional SQLCipher encryption:

```python
# In db.py, detect SQLCipher availability:
try:
    import pysqlcipher3.dbapi2 as sqlcipher
    conn = sqlcipher.connect(DB_FILE)
    conn.execute(f"PRAGMA key = '{passphrase}'")
except ImportError:
    import sqlite3
    conn = sqlite3.connect(DB_FILE)
```

**Priority:** Low — full-disk encryption on Android covers this.

---

## 4. Process Management & Privilege

### Current State (src/server.py)

| Aspect | Implementation | Assessment |
|--------|----------------|------------|
| Ollama server start | `subprocess.Popen(["ollama", "serve"], start_new_session=True)` | ✅ Separate process group |
| Process kill on timeout | `os.killpg(os.getpgid(pid), signal.SIGKILL)` | ✅ Clean group kill |
| PID file validation | `_pid_alive()` checks `os.kill(pid, 0)` | ✅ Detects stale PIDs |
| Cleanup on stop | `os.killpg` + PID file unlink | ✅ Clean shutdown |
| No privilege escalation | Never runs as root / never requests elevated privileges | ✅ |

### No Issues Found

The server lifecycle management is well-implemented. Process groups ensure clean timeout kills, and PID file management handles crash recovery correctly.

---

## 5. Network Exposure

### Local Network Services

| Service | Port | Exposed? | Assessment |
|---------|------|----------|------------|
| Ollama server | `127.0.0.1:11434` | Localhost only | ✅ Not externally exposed |
| termux-ai CLI | N/A | No listening socket | ✅ CLI only, no server |

### Outbound Network (fetch_url)

| Aspect | Control | Assessment |
|---------|---------|------------|
| Protocol restriction | `http://` and `https://` only | ✅ |
| Private IP blocking | IP literal check (private/loopback/link-local) | ✅ |
| DNS hostname rebinding | ❌ Not resolved (see V-01) | ⚠️ Medium risk |
| Response size cap | `500,000 bytes` (500 KB) | ✅ Prevents memory exhaustion |
| Timeout | `10 seconds` | ✅ |
| User-Agent | Static string `termux-ai/v7.0.0` | ✅ Non-spoofable |

### Recommendation H-4: Add Network Egress Allowlist (Optional)

For high-security environments, allow restricting outbound fetch_url to an allowlist:

```python
# Config option:
# "fetch_allowlist": ["raw.githubusercontent.com", "docs.example.com"]

FETCH_ALLOWLIST = self.cfg.get("fetch_allowlist", [])

@staticmethod
def _fetch_url(url, timeout=10, max_bytes=500000):
    # ... existing SSRF check ...
    host = urllib.parse.urlparse(url).hostname or ""
    if FETCH_ALLOWLIST and host not in FETCH_ALLOWLIST:
        return f"Error: host '{host}' not in fetch allowlist."
    # ... continue with fetch ...
```

---

## 6. API Key & Credential Management

### Current State

| Credential | Storage | Secured? |
|------------|---------|----------|
| OpenAI API key | `config.json` profile or `TERMUX_AI_API_KEY` env | ⚠️ Plaintext in config (0o600); ✅ env preferred |
| Anthropic API key | `config.json` profile or env | ⚠️ Same as above |
| GitHub token | `GITHUB_TOKEN` / `GH_TOKEN` env only | ✅ Not persisted to disk |
| Ollama | No key (local) | ✅ |

### Recommendation H-5: Prefer Environment Variables

```python
# In /setup or profile configuration:
# Warn when storing API key in config.json
if api_key and not from_env:
    print(f"{C.YELLOW}⚠ Storing API key in config.json (plaintext). "
          f"Consider using the {env_var} environment variable instead.{C.RESET}")
```

---

## 7. Security Group / Firewall Analogy

Termux AI has no cloud security groups, but the **Plan-mode allowlist functions identically to a firewall allowlist** for command execution:

| Firewall Concept | Termux AI Equivalent |
|------------------|---------------------|
| Inbound allowlist | N/A (no listening sockets) |
| Outbound allowlist | Plan-mode `PLAN_READONLY_CMDS` (~45 programs) |
| Default deny | ✅ Plan mode: anything not on the list is denied |
| Deny with logging | ⚠️ Blocked commands return error to AI; not logged persistently |
| Egress filtering | SSRF guard blocks private IPs; ⚠️ DNS gap (V-01) |

---

## 8. CIS Controls Summary

| CIS Control | Status | Notes |
|-------------|--------|-------|
| 3.3 — Sensitive Data at Rest | ⚠️ | Config 0o600 ✓; API keys plaintext ✗; no DB encryption |
| 3.4 — OS Crypto (Encryption) | ❌ | No encryption of stored credentials |
| 4.1 — Secure Asset Management | ✅ | Single built artifact; version-tracked |
| 5.1 — Access Revocation | ⚠️ | No in-app mechanism to revoke/rotate keys |
| 6.8 — Allowlist/Blocklist | ✅ | Plan-mode allowlist is exemplary |
| 12.3 — SSRF Protection | ✅ | Partial — IP literals blocked; DNS gap exists |
| 16.5 — Least Privilege | ✅ | Plan/Build mode separation; SAFE_TOOLS auto-approve |
| 16.7 — Manage Default Accounts | ✅ | No default credentials |
| 16.8 — Time Sync | ✅ | `date -s` blocked in Plan mode |

---

## 9. Summary of Recommendations

| ID | Priority | Recommendation | Effort |
|----|----------|----------------|--------|
| H-1 | Medium | Secure history file with `_secure_file(0o600)` | Trivial (1 line) |
| H-2 | Low | Clean up clone_repo temp dirs on session exit | Low (5 lines) |
| H-3 | Low | Optional SQLCipher for encrypted DB | Medium (feature flag) |
| H- Critical | Medium | Resolve DNS hostnames in SSRF check (V-01) | Low (10 lines) |
| H-5 | Medium | Warn when storing API keys in config.json | Trivial (3 lines) |
| H-6 | Low | Add optional fetch_url egress allowlist | Low (5 lines) |
| H-7 | Low | Add security event log (V-12) | Medium (20 lines) |
