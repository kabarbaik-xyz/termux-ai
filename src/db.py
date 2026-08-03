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
        self._migrate_schema()
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT, model TEXT, backend TEXT, pinned INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT, conversation_id INTEGER, role TEXT,
                content TEXT, model TEXT, tokens INTEGER DEFAULT 0, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (conversation_id) REFERENCES conversations(id));
        """)
        self.conn.commit()
        _secure_file(DB_FILE)

    def _table_cols(self, table):
        try: return {r["name"] for r in self.conn.execute(f"PRAGMA table_info({table})").fetchall()}
        except sqlite3.Error: return set()

    def _migrate_schema(self):
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

    def new_conv(self, title="New Chat", model="", backend=""):
        cur = self.conn.execute("INSERT INTO conversations (title, model, backend) VALUES (?,?,?)", (title, model, backend))
        self.conn.commit()
        return cur.lastrowid

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

    def list_convs(self, limit=20):
        return self.conn.execute(
            "SELECT id, title, model, updated_at, (SELECT COUNT(*) FROM messages WHERE conversation_id = conversations.id) as msg_count FROM conversations ORDER BY updated_at DESC LIMIT ?", (limit,)
        ).fetchall()

    def list_sessions(self, limit=50):
        """Saved sessions: pinned first, then most recently active, with message counts."""
        return self.conn.execute(
            "SELECT id, title, model, updated_at, pinned, (SELECT COUNT(*) FROM messages WHERE conversation_id = conversations.id) as msg_count FROM conversations ORDER BY pinned DESC, updated_at DESC LIMIT ?", (limit,)
        ).fetchall()

    def search_convs(self, query):
        return self.conn.execute(
            "SELECT id, title, model FROM conversations WHERE title LIKE ? OR id IN (SELECT conversation_id FROM messages WHERE content LIKE ?) ORDER BY updated_at DESC",
            (f"%{query}%", f"%{query}%")
        ).fetchall()

    def del_conv(self, cid):
        self.conn.execute("DELETE FROM messages WHERE conversation_id = ?", (cid,))
        self.conn.execute("DELETE FROM conversations WHERE id = ?", (cid,))
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
