import sqlite3
from typing import Optional, List, Dict, Tuple
from contextlib import contextmanager
import logging

logger = logging.getLogger(__name__)


class DatabaseManager:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._conn = None
        self._connect()

    def _connect(self):
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_tables()
        logger.info(f"قاعدة البيانات متصلة: {self.db_path}")

    def _init_tables(self):
        cursor = self._conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS decisions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                iteration INTEGER,
                timestamp TEXT,
                action TEXT,
                focus TEXT,
                context_preview TEXT,
                reflection TEXT,
                self_score REAL,
                gate_passed BOOLEAN,
                gate_reason TEXT,
                book_used TEXT
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS evolutions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                reason TEXT,
                old_brain_hash TEXT,
                new_brain_hash TEXT,
                success BOOLEAN,
                test_result TEXT
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS constitutional_memory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                concept TEXT,
                context TEXT,
                insights TEXT,
                related_concepts TEXT,
                importance_score REAL DEFAULT 0.5,
                source TEXT,
                created_at TEXT,
                last_accessed TEXT,
                reviewed_count INTEGER DEFAULT 0
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS chat_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT,
                user_message TEXT,
                agent_response TEXT,
                user_feedback BOOLEAN,
                timestamp TEXT
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS books (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                filename TEXT,
                filepath TEXT,
                uploaded_at TEXT,
                is_current BOOLEAN,
                chunks_count INTEGER,
                text_length INTEGER,
                last_read TEXT
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS constitution_cache (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                text TEXT,
                hash TEXT,
                updated_at TEXT
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER,
                feedback BOOLEAN,
                timestamp TEXT
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS auto_learning_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                concept TEXT,
                book_name TEXT,
                insight TEXT,
                success BOOLEAN
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS agent_art (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                mood TEXT,
                art_svg TEXT,
                description TEXT,
                prompt TEXT
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS daily_evolution_tracker (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT UNIQUE,
                evolutions_count INTEGER DEFAULT 0
            )
        """)

        self._conn.commit()

    @contextmanager
    def cursor(self):
        cursor = self._conn.cursor()
        try:
            yield cursor
            self._conn.commit()
        except Exception as e:
            self._conn.rollback()
            raise e
        finally:
            cursor.close()

    def execute(self, query: str, params: tuple = ()):
        with self.cursor() as cursor:
            cursor.execute(query, params)
            return cursor.rowcount

    def fetch_all(self, query: str, params: tuple = ()):
        with self.cursor() as cursor:
            cursor.execute(query, params)
            return cursor.fetchall()

    def fetch_one(self, query: str, params: tuple = ()):
        with self.cursor() as cursor:
            cursor.execute(query, params)
            return cursor.fetchone()

    def get_maturity_stats(self) -> dict:
        with self.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) FROM decisions")
            total_decisions = cursor.fetchone()[0] or 0

            cursor.execute("SELECT AVG(self_score) FROM decisions WHERE self_score IS NOT NULL")
            avg_score = cursor.fetchone()[0] or 0.5

            cursor.execute("SELECT COUNT(*) FROM evolutions WHERE success = 1")
            successful_evolutions = cursor.fetchone()[0] or 0

            cursor.execute("SELECT COUNT(*) FROM constitutional_memory")
            concepts_count = cursor.fetchone()[0] or 0

            cursor.execute("SELECT AVG(importance_score) FROM constitutional_memory")
            avg_importance = cursor.fetchone()[0] or 0.5

            cursor.execute("SELECT COUNT(*) FROM auto_learning_log WHERE success = 1 AND timestamp > datetime('now', '-7 days')")
            weekly_learnings = cursor.fetchone()[0] or 0

            cursor.execute("SELECT COUNT(*) FROM agent_art WHERE timestamp > datetime('now', '-7 days')")
            weekly_artworks = cursor.fetchone()[0] or 0

            return {
                "total_decisions": total_decisions,
                "avg_self_score": float(avg_score),
                "successful_evolutions": successful_evolutions,
                "concepts_in_memory": concepts_count,
                "avg_importance_score": float(avg_importance),
                "weekly_learnings": weekly_learnings,
                "weekly_artworks": weekly_artworks
            }

    def close(self):
        if self._conn:
            self._conn.close()
