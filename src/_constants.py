# ══ termux_ai._constants ══ (fragment; merged by build.py)
CONFIG_DIR = Path(os.path.expanduser("~/.config/termux-ai"))
CONFIG_FILE = CONFIG_DIR / "config.json"
DB_FILE = CONFIG_DIR / "ai_history.db"
HIST_FILE = CONFIG_DIR / "history"
PID_FILE = CONFIG_DIR / "server.pid"

def _secure_dir(path, mode=0o700):
    try: os.chmod(path, mode)
    except OSError: pass

def _secure_file(path, mode=0o600):
    try: os.chmod(path, mode)
    except OSError: pass

IS_TERMUX = "com.termux" in os.environ.get("PREFIX", "")
IS_TTY = hasattr(sys.stdout, "isatty") and sys.stdout.isatty()

try:
    import readline
    HAVE_READLINE = True
except ImportError:
    HAVE_READLINE = False

try:
    import tiktoken
    _ENC = tiktoken.get_encoding("cl100k_base")
    def est_tok(t): return len(_ENC.encode(t))
except ImportError:
    def est_tok(t): return len(t) // 4

PRICING = {
    "gpt-4o": 0.005, "gpt-4o-mini": 0.00015, "gpt-3.5-turbo": 0.0005,
    "claude-3-5-sonnet": 0.003, "claude-3-opus": 0.015,
    "llama3.2": 0.0, "llama3": 0.0, "glm-4.6": 0.001, "big-pickle": 0.001
}

class C:
    RESET, BOLD, DIM, ITALIC, UNDER = "\033[0m", "\033[1m", "\033[2m", "\033[3m", "\033[4m"
    RED, GREEN, YELLOW, BLUE, MAGENTA, CYAN, WHITE, GRAY = (
        "\033[31m", "\033[32m", "\033[33m", "\033[34m", "\033[35m", "\033[36m", "\033[37m", "\033[90m"
    )

if not IS_TTY:
    for a in dir(C):
        if not a.startswith("_") and a != "RESET":
            setattr(C, a, "")

_ANSI_RE = re.compile(r"\001?\033\[[0-9;]*m\002?")

def vlen(s): return len(_ANSI_RE.sub("", s))
def pad(s, width): return s + " " * max(0, width - vlen(s))
def mask(key): return "" if not key else "*" * len(key) if len(key) <= 8 else key[:4] + "…" + key[-4:]

def parse_value(v):
    v = v.strip()
    low = v.lower()
    if low in ("true", "on", "yes"): return True
    if low in ("false", "off", "no"): return False
    try: return int(v)
    except ValueError: pass
    try: return float(v)
    except ValueError: pass
    if len(v) >= 2 and v[0] == v[-1] and v[0] in ("'", '"'): return v[1:-1]
    return v

def fmt_time(ts):
    if not ts: return ""
    try:
        from datetime import datetime
        dt = datetime.strptime(ts[:19], "%Y-%m-%d %H:%M:%S")
        now = datetime.now()
        delta = now - dt
        if delta.days == 0: return dt.strftime("today %H:%M")
        if delta.days == 1: return dt.strftime("yest %H:%M")
        if delta.days < 7: return f"{delta.days}d ago"
        return dt.strftime("%m-%d %H:%M")
    except Exception: return ts[:16]
