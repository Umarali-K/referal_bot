import sqlite3
from typing import Optional, Tuple, List, Dict


class DB:
    def __init__(self, path: str = "bot.db"):
        self.conn = sqlite3.connect(path)
        self.conn.execute("PRAGMA journal_mode=WAL;")
        self._init()

    def _init(self):
        self.conn.execute("""
        CREATE TABLE IF NOT EXISTS users(
            user_id INTEGER PRIMARY KEY,
            referrer_id INTEGER,
            joined_ok INTEGER DEFAULT 0,
            banned INTEGER DEFAULT 0
        );
        """)

        self.conn.execute("""
        CREATE TABLE IF NOT EXISTS referrals(
            referrer_id INTEGER,
            invited_user_id INTEGER UNIQUE,
            created_at INTEGER DEFAULT (strftime('%s','now'))
        );
        """)

        # 1 martalik flaglar: near_sent, win_sent, ...
        self.conn.execute("""
        CREATE TABLE IF NOT EXISTS user_flags(
            user_id INTEGER,
            key TEXT,
            created_at INTEGER DEFAULT (strftime('%s','now')),
            UNIQUE(user_id, key)
        );
        """)

        self.conn.execute("""
        CREATE TABLE IF NOT EXISTS settings(
            key TEXT PRIMARY KEY,
            value TEXT
        );
        """)

        self.conn.commit()

    # ---------- users ----------
    def ensure_user(self, user_id: int, referrer_id: Optional[int] = None):
        cur = self.conn.cursor()
        cur.execute("SELECT user_id FROM users WHERE user_id=?", (user_id,))
        if cur.fetchone() is None:
            cur.execute(
                "INSERT INTO users(user_id, referrer_id) VALUES(?, ?)",
                (user_id, referrer_id),
            )
            self.conn.commit()

    def get_user(self, user_id: int) -> Optional[Tuple[int, Optional[int], int, int]]:
        cur = self.conn.cursor()
        cur.execute(
            "SELECT user_id, referrer_id, joined_ok, banned FROM users WHERE user_id=?",
            (user_id,)
        )
        return cur.fetchone()

    def set_joined_ok(self, user_id: int, ok: bool):
        self.conn.execute(
            "UPDATE users SET joined_ok=? WHERE user_id=?",
            (1 if ok else 0, user_id),
        )
        self.conn.commit()

    def is_banned(self, user_id: int) -> bool:
        cur = self.conn.cursor()
        cur.execute("SELECT banned FROM users WHERE user_id=?", (user_id,))
        row = cur.fetchone()
        return bool(row and int(row[0]) == 1)

    def ban_user(self, user_id: int):
        self.conn.execute("UPDATE users SET banned=1 WHERE user_id=?", (user_id,))
        self.conn.commit()

    def unban_user(self, user_id: int):
        self.conn.execute("UPDATE users SET banned=0 WHERE user_id=?", (user_id,))
        self.conn.commit()

    # ---------- referrals ----------
    def add_referral_if_unique(self, referrer_id: int, invited_user_id: int) -> bool:
        try:
            self.conn.execute(
                "INSERT INTO referrals(referrer_id, invited_user_id) VALUES(?, ?)",
                (referrer_id, invited_user_id),
            )
            self.conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def referrals_count(self, referrer_id: int) -> int:
        cur = self.conn.cursor()
        cur.execute("SELECT COUNT(*) FROM referrals WHERE referrer_id=?", (referrer_id,))
        return int(cur.fetchone()[0])

    def referrals_count_since(self, referrer_id: int, since_ts: int) -> int:
        cur = self.conn.cursor()
        cur.execute(
            "SELECT COUNT(*) FROM referrals WHERE referrer_id=? AND created_at>=?",
            (referrer_id, since_ts)
        )
        return int(cur.fetchone()[0])

    # ---------- flags ----------
    def flag_set(self, user_id: int, key: str) -> bool:
        cur = self.conn.cursor()
        cur.execute("SELECT 1 FROM user_flags WHERE user_id=? AND key=?", (user_id, key))
        return cur.fetchone() is not None

    def set_flag(self, user_id: int, key: str) -> bool:
        try:
            self.conn.execute(
                "INSERT INTO user_flags(user_id, key) VALUES(?, ?)",
                (user_id, key)
            )
            self.conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def clear_flags(self, user_id: int):
        self.conn.execute("DELETE FROM user_flags WHERE user_id=?", (user_id,))
        self.conn.commit()

    def wipe_flags(self):
        self.conn.execute("DELETE FROM user_flags")
        self.conn.commit()

    # ---------- settings ----------
    def get_setting(self, key: str) -> Optional[str]:
        cur = self.conn.cursor()
        cur.execute("SELECT value FROM settings WHERE key=?", (key,))
        row = cur.fetchone()
        return row[0] if row else None

    def set_setting(self, key: str, value: str):
        self.conn.execute(
            "INSERT INTO settings(key,value) VALUES(?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )
        self.conn.commit()

    def get_target(self, default: int) -> int:
        v = self.get_setting("invite_target")
        if not v:
            return default
        try:
            return int(v)
        except Exception:
            return default

    def set_target(self, n: int):
        self.set_setting("invite_target", str(int(n)))

    # ---------- stats / ranking ----------
    def users_count(self) -> int:
        cur = self.conn.cursor()
        cur.execute("SELECT COUNT(*) FROM users")
        return int(cur.fetchone()[0])

    def referrals_total(self) -> int:
        cur = self.conn.cursor()
        cur.execute("SELECT COUNT(*) FROM referrals")
        return int(cur.fetchone()[0])

    def top_referrers(self, limit: int = 10) -> List[Tuple[int, int]]:
        cur = self.conn.cursor()
        cur.execute("""
            SELECT referrer_id, COUNT(*) AS c
            FROM referrals
            GROUP BY referrer_id
            ORDER BY c DESC
            LIMIT ?
        """, (limit,))
        return [(int(r[0]), int(r[1])) for r in cur.fetchall()]

    def top_referrers_since(self, since_ts: int, limit: int = 10) -> List[Tuple[int, int]]:
        cur = self.conn.cursor()
        cur.execute("""
            SELECT referrer_id, COUNT(*) AS c
            FROM referrals
            WHERE created_at >= ?
            GROUP BY referrer_id
            ORDER BY c DESC
            LIMIT ?
        """, (since_ts, limit))
        return [(int(r[0]), int(r[1])) for r in cur.fetchall()]

    def user_rank(self, user_id: int) -> int:
        """Umumiy ranking (1 dan boshlanadi). Agar referral yo'q bo'lsa ham rank qaytaradi."""
        my_cnt = self.referrals_count(user_id)
        cur = self.conn.cursor()
        cur.execute("""
            SELECT 1 + COUNT(*) FROM (
                SELECT referrer_id, COUNT(*) AS c
                FROM referrals
                GROUP BY referrer_id
            ) t
            WHERE t.c > ?
        """, (my_cnt,))
        return int(cur.fetchone()[0])

    def users_near_goal(self, target_minus_1: int, limit: int = 50) -> List[Tuple[int, int]]:
        """4/5 dagilar (ya'ni target-1)."""
        cur = self.conn.cursor()
        cur.execute("""
            SELECT r.referrer_id, COUNT(*) AS c
            FROM referrals r
            JOIN users u ON u.user_id = r.referrer_id
            WHERE u.banned = 0
            GROUP BY r.referrer_id
            HAVING c = ?
            ORDER BY r.referrer_id ASC
            LIMIT ?
        """, (target_minus_1, limit))
        return [(int(r[0]), int(r[1])) for r in cur.fetchall()]

    # ---------- resets ----------
    def reset_user_progress(self, user_id: int):
        self.conn.execute("DELETE FROM referrals WHERE referrer_id=?", (user_id,))
        self.clear_flags(user_id)
        self.conn.commit()

    def wipe_all_referrals(self):
        self.conn.execute("DELETE FROM referrals")
        self.wipe_flags()
        self.conn.commit()