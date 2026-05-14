from typing import List, Dict
from datetime import datetime
import logging
from app.database.db_manager import DatabaseManager

logger = logging.getLogger(__name__)


class ConstitutionalMemory:
    def __init__(self, db: DatabaseManager):
        self.db = db

    def store(self, concept: str, context: str, insights: str, importance: float = 0.5, source: str = "user"):
        try:
            existing = self.db.fetch_one(
                "SELECT id, importance_score, reviewed_count FROM constitutional_memory WHERE concept LIKE ?",
                (f"%{concept[:50]}%",)
            )
            if existing:
                new_importance = min(1.0, existing[1] + 0.05)
                self.db.execute(
                    "UPDATE constitutional_memory SET insights = ?, importance_score = ?, last_accessed = ?, reviewed_count = ? WHERE id = ?",
                    (insights[:500], new_importance, datetime.now().isoformat(), existing[2] + 1, existing[0])
                )
            else:
                self.db.execute(
                    "INSERT INTO constitutional_memory (concept, context, insights, related_concepts, importance_score, source, created_at, last_accessed, reviewed_count) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (concept[:100], context[:500], insights[:500], "[]", importance, source, datetime.now().isoformat(), datetime.now().isoformat(), 0)
                )
        except Exception as e:
            logger.error(f"خطأ في تخزين الذاكرة: {e}")

    def recall(self, concept: str, limit: int = 5) -> List[Dict]:
        try:
            rows = self.db.fetch_all(
                """SELECT concept, context, insights, importance_score, source, created_at 
                   FROM constitutional_memory 
                   WHERE concept LIKE ? 
                   ORDER BY importance_score DESC, reviewed_count DESC 
                   LIMIT ?""",
                (f"%{concept}%", limit)
            )
            return [{
                "concept": r[0],
                "context": r[1],
                "insights": r[2],
                "importance": r[3],
                "source": r[4],
                "created_at": r[5]
            } for r in rows]
        except Exception as e:
            logger.error(f"خطأ في استدعاء الذاكرة: {e}")
            return []

    def get_summary(self) -> str:
        try:
            row = self.db.fetch_one("SELECT COUNT(*) FROM constitutional_memory")
            count = row[0] if row else 0
            if count == 0:
                return "الذاكرة لا تزال فارغة."
            rows = self.db.fetch_all(
                "SELECT concept, importance_score FROM constitutional_memory ORDER BY importance_score DESC LIMIT 5"
            )
            important = [f"{r[0]} ({r[1]:.1f})" for r in rows]
            return f"{count} مفهوماً. الأهم: {', '.join(important)}"
        except:
            return "الذاكرة غير متاحة"
