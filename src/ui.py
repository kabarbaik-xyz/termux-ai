# ══ termux_ai.ui ══ (fragment; merged by build.py)
class MarkdownFormatter:
    def __init__(self, indent="      ", fold=True, fold_head=8):
        self.buffer = ""
        self.in_code_block = False
        self.first_line = True
        self.indent = indent
        self.fold = fold
        self.fold_head = fold_head
        self._run_type = None      # None | "list" | "table" (current foldable run)
        self._run_count = 0
        self._run_tail = []        # lines buffered beyond fold_head (the hidden part)

    def feed(self, text):
        self.buffer += text.replace("\r\n", "\n").replace("\r", "")
        while "\n" in self.buffer:
            line, self.buffer = self.buffer.split("\n", 1)
            self._handle_line(line + "\n")

    def flush(self):
        if self.buffer:
            line = self.buffer; self.buffer = ""
            self._handle_line(line)
        self._flush_run()

    def _handle_line(self, line):
        # Code-block lines never fold; they just close any pending run.
        if self.in_code_block:
            self._flush_run()
            self._print_line(line); return
        s = line.strip()
        is_list = bool(re.match(r"^\s*([-*]|\d+\.)\s", line))
        is_table = bool(len(s) > 1 and s.startswith("|") and s.rstrip().endswith("|"))
        kind = "list" if is_list else ("table" if is_table else None)
        if kind is None:
            self._flush_run()
            self._print_line(line); return
        if self._run_type != kind:
            self._flush_run()
            self._run_type = kind; self._run_count = 0; self._run_tail = []
        self._run_count += 1
        # Show the head live; buffer the overflow so a long list/table renders compact.
        if not self.fold or self._run_count <= self.fold_head:
            self._print_line(line)
        else:
            self._run_tail.append(line)

    def _flush_run(self):
        if self._run_type is not None and self._run_tail:
            pre = "" if self.first_line else self.indent
            print(f"{pre}{C.DIM}\u2026 {len(self._run_tail)} more \u2014 /expand to view{C.RESET}")
        self._run_type = None; self._run_count = 0; self._run_tail = []

    def _print_line(self, line):
        prefix = "" if self.first_line else self.indent
        self.first_line = False
        if line.strip().startswith("```"):
            self.in_code_block = not self.in_code_block
            print(f"{prefix}{C.DIM}{line}{C.RESET}", end="")
            return
        if self.in_code_block:
            print(f"{prefix}{C.CYAN}{line}{C.RESET}", end="")
            return
        if re.match(r"^#{1,6}\s", line):
            line = f"{C.BOLD}{C.MAGENTA}{line}{C.RESET}"
        else:
            parts = re.split(r"(`[^`]+`)", line)
            for i, part in enumerate(parts):
                if part.startswith("`") and part.endswith("`") and len(part) > 1:
                    parts[i] = f"{C.CYAN}{part[1:-1]}{C.RESET}"
                else:
                    part = re.sub(r"\*\*(.+?)\*\*", f"{C.BOLD}\\1{C.RESET}", part)
                    part = re.sub(r"(?<!\*)\*(?!\s)(.+?)(?<!\s)\*(?!\*)", f"{C.ITALIC}\\1{C.RESET}", part)
                    parts[i] = re.sub(r"(?<!\_)_(?!\s)(.+?)(?<!\s)_(?!\_)", f"{C.ITALIC}\\1{C.RESET}", part)
            line = "".join(parts)
            line = re.sub(r"^(\s*)([-*])\s", f"\\1{C.CYAN}\\2{C.RESET} ", line)
            line = re.sub(r"^(\s*)(\d+\.)\s", f"\\1{C.CYAN}\\2{C.RESET} ", line)
        print(f"{prefix}{line}", end="")


class Spinner:
    CHARS = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
    def __init__(self, msg="working"):
        self.msg = msg
        self._stop = False
        self._t = None
        self._started = False
        self._atexit_registered = False
        self._started_at = 0.0

    def set_msg(self, msg):
        self.msg = msg

    def start(self):
        self._started = True
        self._started_at = time.time()
        if not IS_TTY:
            sys.stdout.write(f"{C.DIM}… {self.msg}{C.RESET}"); sys.stdout.flush(); return
        self._stop = False
        self._t = threading.Thread(target=self._run, daemon=True)
        self._t.start()
        if not self._atexit_registered:
            atexit.register(self.stop)
            self._atexit_registered = True

    def _run(self):
        i = 0
        while not self._stop:
            # Show elapsed seconds once a prefill/generation is slow enough to
            # feel frozen -- turns "waiting silently" into "17s and counting".
            elapsed = int(time.time() - self._started_at)
            suff = f" {elapsed}s" if elapsed >= 3 else ""
            sys.stdout.write(f"\r{C.CYAN}{self.CHARS[i % len(self.CHARS)]}{C.RESET} {C.DIM}{self.msg}{suff}{C.RESET}")
            sys.stdout.flush(); time.sleep(0.08); i += 1

    def stop(self):
        if not self._started: return
        self._started = False
        if not IS_TTY:
            sys.stdout.write("\r" + " " * 20 + "\r"); sys.stdout.flush(); return
        self._stop = True
        if self._t: self._t.join(timeout=0.3)
        sys.stdout.write("\r" + " " * 30 + "\r"); sys.stdout.flush()

    def __del__(self):
        self.stop()
