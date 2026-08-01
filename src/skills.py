# ══ termux_ai.skills ══ (fragment; merged by build.py)
class Skills:
    """Discover and load Agent-Skills-style skill modules.

    A skill lives under the skills directory as either `<name>.md` (flat) or
    `<name>/SKILL.md` (a directory that may bundle helper scripts). Each has
    optional front-matter (name, description, mode) and a markdown body of
    instructions injected when the skill is used. Compatible in spirit with the
    Agent Skills standard (agentskills.io)."""

    def __init__(self, skills_dir):
        self.dir = Path(os.path.expanduser(str(skills_dir)))

    def ensure_dir(self):
        self.dir.mkdir(parents=True, exist_ok=True)
        return self.dir

    def _discover(self):
        """Return {name: path} for all skills (flat .md and dir/SKILL.md)."""
        out = {}
        if not self.dir.is_dir():
            return out
        for entry in sorted(self.dir.iterdir()):
            if entry.is_file() and entry.suffix == ".md" and entry.name != "SKILL.md":
                out.setdefault(entry.stem, entry)
            elif entry.is_dir() and (entry / "SKILL.md").is_file():
                out.setdefault(entry.name, entry / "SKILL.md")
        return out

    @staticmethod
    def parse(path):
        """Return (meta, body). meta keys: name, description, mode."""
        text = Path(path).read_text(encoding="utf-8")
        meta, body = {}, text
        if text.startswith("---"):
            parts = text.split("---", 2)
            if len(parts) >= 3:
                for line in parts[1].strip().splitlines():
                    if ":" in line:
                        k, v = line.split(":", 1)
                        meta[k.strip().lower()] = v.strip()
                body = parts[2].strip()
        meta.setdefault("name", Path(path).stem if Path(path).name != "SKILL.md" else Path(path).parent.name)
        meta.setdefault("description", "")
        meta.setdefault("mode", "once")
        return meta, body

    def list(self):
        """Return [(name, meta)] for every discoverable skill."""
        result = []
        for name, path in self._discover().items():
            try:
                meta, _ = Skills.parse(path)
            except Exception:
                meta = {"description": "(unreadable)", "mode": "once"}
            result.append((name, meta))
        return result

    def load(self, name):
        """Return (meta, body) for a skill, or (None, None) if not found."""
        path = self._discover().get(name)
        if not path:
            return None, None
        return Skills.parse(path)

    def path_for(self, name):
        """Where a flat skill <name> would live (for new/edit)."""
        return self.dir / (name + ".md")

    @staticmethod
    def valid_name(name):
        """1-64 chars, lowercase/digits joined by single hyphens (no leading/
        trailing/double hyphens)."""
        return bool(re.match(r"^[a-z0-9]+(-[a-z0-9]+)*$", name or "")) and len(name) <= 64

    def seed(self):
        """Copy the bundled example skills into the user's skills dir (never
        overwriting existing files). Returns the list of names written."""
        self.ensure_dir()
        written = []
        for fname, content in EXAMPLES.items():
            p = self.dir / fname
            if not p.exists():
                p.write_text(content, encoding="utf-8")
                written.append(fname[:-3])
        return written

    def catalog(self):
        """Progressive-disclosure block for auto-loading: an XML list of
        non-hidden skills (name, path, description) the model can read_file on
        demand. Returns '' if there are none."""
        lines = []
        for name, path in self._discover().items():
            try:
                meta, _ = Skills.parse(path)
            except Exception:
                continue
            if str(meta.get("disable-model-invocation", "")).lower() in ("true", "1", "yes"):
                continue
            desc = meta.get("description", "").strip()
            lines.append('<skill name="%s" path="%s">%s</skill>' % (name, path, desc))
        if not lines:
            return ""
        return ("<available-skills>\n" + "\n".join(lines) +
                "\n</available-skills>\nIf one of these skills matches the user's "
                "task, FIRST call read_file on its path to load the full instructions, "
                "then follow them. If none match, proceed normally.")


EXAMPLES = {
    "review.md": (
        "---\n"
        "name: review\n"
        "description: Review code for bugs, security issues, and style. Use when the user wants a code review of a file or snippet.\n"
        "mode: once\n"
        "---\n"
        "You are a senior code reviewer. Read the provided code and report:\n\n"
        "1. **Bugs** - logic errors, unhandled edge cases, crashes.\n"
        "2. **Security** - injection, unsafe shell/file use, leaked secrets.\n"
        "3. **Style** - clarity, naming, consistency with surrounding code.\n\n"
        "Be specific (cite file/line) and concise. Suggest fixes as code blocks. If the code is fine, say so briefly.\n"
    ),
    "commit.md": (
        "---\n"
        "name: commit\n"
        "description: Write a Conventional Commit message from the current git changes. Use when the user wants to commit.\n"
        "mode: once\n"
        "---\n"
        "Look at the current git changes (`git diff --cached`, or `git diff` / `git status` if nothing is staged).\n\n"
        "Write a Conventional Commit message: `type(scope): summary` on the first line, then a short body explaining the why. Types: feat, fix, docs, refactor, test, chore, perf.\n\n"
        "Output ONLY the commit message, then suggest the `git commit -m \"...\"` command. Do not commit yourself.\n"
    ),
    "python.md": (
        "---\n"
        "name: python\n"
        "description: Expert Python mode for the session - idiomatic, typed, well-tested advice.\n"
        "mode: session\n"
        "---\n"
        "You are a Python expert. Prefer idiomatic modern Python (3.10+):\n"
        "- Use type hints and dataclasses/Pydantic where they help.\n"
        "- Prefer the standard library; reach for a dependency only when it clearly wins.\n"
        "- Show concise, correct code; briefly note trade-offs or pitfalls.\n"
        "- Suggest tests for non-trivial code.\n"
    ),
}
