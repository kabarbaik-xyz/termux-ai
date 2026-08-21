# ══ termux_ai.db ══ (fragment; merged by build.py)
class Database:
    def __init__(self):
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        _secure_dir(CONFIG_DIR)
        self.conn = sqlite3.connect(str(DB_FILE), timeout=10)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA busy_timeout=10000")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.conn.execute("PRAGMA secure_delete=ON")  # zero freed pages: deleted chats unrecoverable from the file
        self._migrate_schema()
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT, model TEXT, backend TEXT, pinned INTEGER DEFAULT 0,
                cwd TEXT, tools_mode INTEGER, skills_json TEXT, slug TEXT, workspace TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT, conversation_id INTEGER, role TEXT,
                content TEXT, model TEXT, tokens INTEGER DEFAULT 0, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (conversation_id) REFERENCES conversations(id));
            CREATE TABLE IF NOT EXISTS resume_state (
                cid INTEGER PRIMARY KEY, msgs TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
            CREATE TABLE IF NOT EXISTS usage_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT, cid INTEGER, model TEXT, backend TEXT,
                tin INTEGER DEFAULT 0, tout INTEGER DEFAULT 0, est INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
        """)
        self.conn.commit()
        self._init_fts()

    def log_usage(self, cid, model, backend, tin, tout, est=False):
        """Persist one request's real (or estimated) token usage."""
        self.conn.execute(
            "INSERT INTO usage_log (cid, model, backend, tin, tout, est) VALUES (?,?,?,?,?,?)",
            (cid, model or "", backend or "", int(tin or 0), int(tout or 0), 1 if est else 0))
        self.conn.commit()

    def usage_totals(self, cid=None, days=None):
        """Aggregated usage {tin, tout, requests, est} for a session (cid), a
        time window (days), or everything."""
        sql = "SELECT COALESCE(SUM(tin),0) tin, COALESCE(SUM(tout),0) tout, COUNT(*) n, COALESCE(SUM(est),0) est FROM usage_log WHERE 1=1"
        params = []
        if cid is not None:
            sql += " AND cid = ?"; params.append(cid)
        if days:
            sql += " AND created_at >= datetime('now', ?)"; params.append(f"-{int(days)} days")
        row = self.conn.execute(sql, params).fetchone()
        return {"tin": row["tin"], "tout": row["tout"], "requests": row["n"], "est": row["est"]}

    def usage_by_model(self, days=None):
        """Per-model usage rows: {model: {tin, tout, requests, est}}."""
        sql = "SELECT model, COALESCE(SUM(tin),0) tin, COALESCE(SUM(tout),0) tout, COUNT(*) n, COALESCE(SUM(est),0) est FROM usage_log"
        params = []
        if days:
            sql += " WHERE created_at >= datetime('now', ?)"; params.append(f"-{int(days)} days")
        sql += " GROUP BY model ORDER BY (SUM(tin)+SUM(tout)) DESC"
        out = {}
        for r in self.conn.execute(sql, params).fetchall():
            out[r["model"]] = {"tin": r["tin"], "tout": r["tout"], "requests": r["n"], "est": r["est"]}
        return out

    def _init_fts(self):
        """FTS5 full-text index over messages (external-content: the index holds
        only tokens, messages stays the source of truth). /search becomes an
        instant MATCH instead of a full-table LIKE scan. Falls back silently to
        LIKE when FTS5 is unavailable (exotic builds)."""
        try:
            self.conn.executescript("""
                CREATE VIRTUAL TABLE IF NOT EXISTS msg_fts USING fts5(
                    content, content='messages', content_rowid='id');
                CREATE TRIGGER IF NOT EXISTS messages_fts_ai AFTER INSERT ON messages BEGIN
                    INSERT INTO msg_fts(rowid, content) VALUES (new.id, new.content);
                END;
                CREATE TRIGGER IF NOT EXISTS messages_fts_ad AFTER DELETE ON messages BEGIN
                    INSERT INTO msg_fts(msg_fts, rowid, content) VALUES('delete', old.id, old.content);
                END;
                CREATE TRIGGER IF NOT EXISTS messages_fts_au AFTER UPDATE ON messages BEGIN
                    INSERT INTO msg_fts(msg_fts, rowid, content) VALUES('delete', old.id, old.content);
                    INSERT INTO msg_fts(rowid, content) VALUES (new.id, new.content);
                END;
            """)
            self.conn.execute("INSERT INTO msg_fts(msg_fts) VALUES('rebuild')")  # sync older rows once per open
            self.conn.commit()
            self._fts_ok = True
        except Exception:
            self._fts_ok = False
        _secure_file(DB_FILE)

    def _table_cols(self, table):
        try: return {r["name"] for r in self.conn.execute(f"PRAGMA table_info({table})").fetchall()}
        except sqlite3.Error: return set()

    def _migrate_schema(self):
        # Safety net: snapshot the DB BEFORE any schema change. Migrations are
        # additive in practice, but if anything ever goes wrong here the user's
        # history is recoverable from the pre-migration backup (kept, rotating,
        # alongside /backup snapshots).
        conv_cols = self._table_cols("conversations")
        msg_cols = self._table_cols("messages")
        needs_alter = (conv_cols and any(c not in conv_cols for c in (
            "title", "model", "backend", "created_at", "updated_at", "pinned",
            "cwd", "tools_mode", "skills_json", "slug", "workspace"))) or \
                     (msg_cols and any(c not in msg_cols for c in (
                         "conversation_id", "role", "content", "model", "tokens", "created_at")))
        if needs_alter:
            try:
                ts = time.strftime("%Y%m%d-%H%M%S")
                self.conn.execute("VACUUM INTO ?", (str(CONFIG_DIR / f"backup-premigrate-{ts}.db"),))
            except Exception:
                pass   # migration proceeds even if the snapshot fails
        try:
            self.conn.execute("BEGIN")
            conv_cols = self._table_cols("conversations")
            if conv_cols:
                if "title" not in conv_cols: self.conn.execute("ALTER TABLE conversations ADD COLUMN title TEXT")
                if "model" not in conv_cols: self.conn.execute("ALTER TABLE conversations ADD COLUMN model TEXT")
                if "backend" not in conv_cols: self.conn.execute("ALTER TABLE conversations ADD COLUMN backend TEXT")
                if "created_at" not in conv_cols: self.conn.execute("ALTER TABLE conversations ADD COLUMN created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
                if "updated_at" not in conv_cols: self.conn.execute("ALTER TABLE conversations ADD COLUMN updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
                if "pinned" not in conv_cols: self.conn.execute("ALTER TABLE conversations ADD COLUMN pinned INTEGER DEFAULT 0")
                if "cwd" not in conv_cols: self.conn.execute("ALTER TABLE conversations ADD COLUMN cwd TEXT")
                if "tools_mode" not in conv_cols: self.conn.execute("ALTER TABLE conversations ADD COLUMN tools_mode INTEGER")
                if "skills_json" not in conv_cols: self.conn.execute("ALTER TABLE conversations ADD COLUMN skills_json TEXT")
                if "slug" not in conv_cols: self.conn.execute("ALTER TABLE conversations ADD COLUMN slug TEXT")
                if "workspace" not in conv_cols: self.conn.execute("ALTER TABLE conversations ADD COLUMN workspace TEXT")

            msg_cols = self._table_cols("messages")
            if msg_cols:
                if "conversation_id" not in msg_cols: self.conn.execute("ALTER TABLE messages ADD COLUMN conversation_id INTEGER")
                if "role" not in msg_cols: self.conn.execute("ALTER TABLE messages ADD COLUMN role TEXT")
                if "content" not in msg_cols: self.conn.execute("ALTER TABLE messages ADD COLUMN content TEXT")
                if "model" not in msg_cols: self.conn.execute("ALTER TABLE messages ADD COLUMN model TEXT")
                if "tokens" not in msg_cols: self.conn.execute("ALTER TABLE messages ADD COLUMN tokens INTEGER DEFAULT 0")
                if "created_at" not in msg_cols: self.conn.execute("ALTER TABLE messages ADD COLUMN created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP")

            self.conn.execute("COMMIT")
        except Exception as e:
            self.conn.execute("ROLLBACK")
            raise e

    def new_conv(self, title="New Chat", model="", backend="", cwd="", tools_mode=None, skills=None, workspace=None):
        import json as _json
        cur = self.conn.execute(
            "INSERT INTO conversations (title, model, backend, cwd, tools_mode, skills_json, workspace) VALUES (?,?,?,?,?,?,?)",
            (title, model, backend, cwd,
             1 if tools_mode else (0 if tools_mode is not None else None),
             _json.dumps(skills) if skills else None, workspace))
        self.conn.commit()
        return cur.lastrowid

    def set_conv_slug(self, cid, slug):
        self.conn.execute("UPDATE conversations SET slug = ? WHERE id = ?", ((slug or "").strip() or None, cid))
        self.conn.commit()

    def get_conv_by_slug(self, slug, workspace=None):
        """Most recent conversation with this slug (exact, case-insensitive).
        When a workspace is given, the slug only resolves WITHIN it."""
        if workspace:
            row = self.conn.execute(
                "SELECT * FROM conversations WHERE slug = ? COLLATE NOCASE AND workspace = ? "
                "ORDER BY updated_at DESC LIMIT 1", ((slug or "").strip(), workspace)).fetchone()
            return row      # workspace-scoped miss is a MISS (no global fallback)
        row = self.conn.execute(
            "SELECT * FROM conversations WHERE slug = ? COLLATE NOCASE ORDER BY updated_at DESC LIMIT 1",
            ((slug or "").strip(),)).fetchone()
        return row

    def backfill_workspaces(self, root_of):
        """One-time: legacy rows have NULL workspace. Derive root-of-cwd per row
        (root_of is a callable dir->root; falls back to the cwd itself when the
        dir is gone). Idempotent."""
        rows = self.conn.execute("SELECT id, cwd FROM conversations WHERE workspace IS NULL AND cwd IS NOT NULL").fetchall()
        for r in rows:
            try:
                ws = root_of(r["cwd"]) or r["cwd"]
            except Exception:
                ws = r["cwd"]
            self.conn.execute("UPDATE conversations SET workspace = ? WHERE id = ?", (ws, r["id"]))
        if rows:
            self.conn.commit()
        return len(rows)

    def last_conv_in_workspace(self, workspace, limit=50):
        """Most recently updated conversation anchored to this workspace root."""
        return self.conn.execute(
            "SELECT * FROM conversations WHERE workspace = ? ORDER BY updated_at DESC LIMIT 1",
            (workspace,)).fetchone()

    def list_convs(self, limit=20, workspace=None):
        if workspace:
            return self.conn.execute(
                "SELECT id, title, model, updated_at, (SELECT COUNT(*) FROM messages WHERE conversation_id = conversations.id) as msg_count FROM conversations WHERE workspace = ? ORDER BY updated_at DESC LIMIT ?",
                (workspace, limit)).fetchall()
        return self.conn.execute(
            "SELECT id, title, model, updated_at, (SELECT COUNT(*) FROM messages WHERE conversation_id = conversations.id) as msg_count FROM conversations ORDER BY updated_at DESC LIMIT ?",
            (limit,)).fetchall()

    def last_conv_in_cwd(self, cwd, limit=50):
        """Most recently updated conversation started in this cwd (NULL cwd
        rows are legacy and ignored -- they have no project anchor)."""
        row = self.conn.execute(
            "SELECT * FROM conversations WHERE cwd = ? ORDER BY updated_at DESC LIMIT 1", (cwd,)).fetchone()
        return row

    def save_msg(self, cid, role, content, model="", tokens=0):
        self.conn.execute("INSERT INTO messages (conversation_id, role, content, model, tokens) VALUES (?,?,?,?,?)", (cid, role, content, model, tokens))
        self.conn.execute("UPDATE conversations SET updated_at = CURRENT_TIMESTAMP WHERE id = ?", (cid,))
        self.conn.commit()

    def get_msgs(self, cid, limit=1000):
        rows = self.conn.execute("SELECT role, content FROM messages WHERE conversation_id = ? ORDER BY id DESC LIMIT ?", (cid, limit)).fetchall()
        return [{"role": r["role"], "content": r["content"]} for r in rows][::-1]

    def last_msg_model(self, cid):
        row = self.conn.execute(
            "SELECT model FROM messages WHERE conversation_id = ? AND model != '' ORDER BY id DESC LIMIT 1", (cid,)).fetchone()
        return row["model"] if row else ""

    def list_sessions(self, limit=50):
        """Saved sessions: pinned first, then most recently active, with message counts."""
        return self.conn.execute(
            "SELECT id, title, model, updated_at, pinned, (SELECT COUNT(*) FROM messages WHERE conversation_id = conversations.id) as msg_count FROM conversations ORDER BY pinned DESC, updated_at DESC LIMIT ?", (limit,)
        ).fetchall()

    def search_convs(self, query, workspace=None):
        q = (query or "").strip()
        # Fast path: FTS5 MATCH (instant, ranked by the index). The user term is
        # quoted so raw punctuation can't break FTS syntax; any failure falls
        # back to the original LIKE scan (always correct, just linear).
        if q and getattr(self, "_fts_ok", False):
            try:
                match = '"%s"' % q.replace('"', '""')
                sql = ("SELECT DISTINCT c.id, c.title, c.model FROM conversations c "
                       "JOIN messages m ON m.conversation_id = c.id "
                       "WHERE (m.id IN (SELECT rowid FROM msg_fts WHERE msg_fts MATCH ?) "
                       "OR c.title LIKE ?) ")
                params = [match, f"%{q}%"]
                if workspace:
                    sql += "AND c.workspace = ? "
                    params.append(workspace)
                sql += "ORDER BY c.updated_at DESC LIMIT 200"
                return self.conn.execute(sql, params).fetchall()
            except Exception:
                pass
        sql = ("SELECT id, title, model FROM conversations WHERE (title LIKE ? OR id IN "
               "(SELECT conversation_id FROM messages WHERE content LIKE ?)) ")
        params = [f"%{q}%", f"%{q}%"]
        if workspace:
            sql += "AND workspace = ? "
            params.append(workspace)
        sql += "ORDER BY updated_at DESC"
        return self.conn.execute(sql, params).fetchall()

    def del_conv(self, cid):
        self.conn.execute("DELETE FROM messages WHERE conversation_id = ?", (cid,))
        self.conn.execute("DELETE FROM conversations WHERE id = ?", (cid,))
        self.conn.execute("DELETE FROM resume_state WHERE cid = ?", (cid,))
        self.conn.commit()

    def set_resume_state(self, cid, msgs):
        self.conn.execute(
            "INSERT INTO resume_state (cid, msgs) VALUES (?,?) ON CONFLICT(cid) DO UPDATE SET msgs=excluded.msgs, created_at=CURRENT_TIMESTAMP",
            (cid, msgs))
        self.conn.commit()

    def get_resume_state(self, cid):
        row = self.conn.execute("SELECT msgs FROM resume_state WHERE cid= ?", (cid,)).fetchone()
        if not row: return None
        try: return json.loads(row["msgs"])
        except Exception: return None

    def clear_resume_state(self, cid):
        self.conn.execute("DELETE FROM resume_state WHERE cid = ?", (cid,))
        self.conn.commit()

    def prune_old(self, days):
        """Delete unpinned conversations untouched for more than `days` days
        (and their messages). Returns the number of sessions deleted."""
        if not days or days <= 0:
            return 0
        cutoff = f"-{int(days)} days"
        self.conn.execute(
            "DELETE FROM messages WHERE conversation_id IN (SELECT id FROM conversations WHERE pinned = 0 AND updated_at < datetime('now', ?))", (cutoff,))
        cur = self.conn.execute(
            "DELETE FROM conversations WHERE pinned = 0 AND updated_at < datetime('now', ?)", (cutoff,))
        self.conn.commit()
        return cur.rowcount

    def rename_conv(self, cid, title):
        self.conn.execute("UPDATE conversations SET title = ? WHERE id = ?", (title, cid))
        self.conn.commit()

    def set_pinned(self, cid, v):
        self.conn.execute("UPDATE conversations SET pinned = ? WHERE id = ?", (1 if v else 0, cid))
        self.conn.commit()

    def get_conv(self, cid):
        return self.conn.execute("SELECT * FROM conversations WHERE id = ?", (cid,)).fetchone()

    def clear_conv_msgs(self, cid):
        self.conn.execute("DELETE FROM messages WHERE conversation_id = ?", (cid,))
        self.conn.commit()

    def undo_last_msg_pair(self, cid):
        """Remove the last exchange. If the last message is an unanswered user
        prompt, drop just that; otherwise drop the last assistant reply and the
        user prompt immediately before it. Returns rows deleted."""
        rows = self.conn.execute(
            "SELECT id, role FROM messages WHERE conversation_id = ? ORDER BY id DESC", (cid,)
        ).fetchall()
        if not rows:
            return 0
        ids = [rows[0]["id"]]
        if rows[0]["role"] == "assistant":
            for r in rows[1:]:
                if r["role"] == "user":
                    ids.append(r["id"])
                    break
        placeholders = ",".join("?" for _ in ids)
        self.conn.execute(
            f"DELETE FROM messages WHERE conversation_id = ? AND id IN ({placeholders})",
            (cid, *ids))
        self.conn.commit()
        return len(ids)

    def get_total_tokens(self):
        row = self.conn.execute("SELECT SUM(tokens) as t FROM messages").fetchone()
        return row["t"] if row and row["t"] else 0

    def get_conv_tokens(self, cid):
        if not cid: return 0
        row = self.conn.execute("SELECT SUM(tokens) as t FROM messages WHERE conversation_id = ?", (cid,)).fetchone()
        return row["t"] if row and row["t"] else 0

    def get_tokens_by_model(self):
        rows = self.conn.execute("SELECT model, SUM(tokens) AS t FROM messages WHERE tokens > 0 GROUP BY model").fetchall()
        return {r["model"]: r["t"] for r in rows if r["model"]}

    def close(self):
        self.conn.close()
