import json
import os
from typing import List, Dict
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class QuestionManager:
    def __init__(self, storage_path: str):
        self.storage_path = storage_path
        self.questions = self._load()

    def _load(self) -> List[Dict]:
        if os.path.exists(self.storage_path):
            try:
                with open(self.storage_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                return []
        return []

    def _save(self):
        with open(self.storage_path, 'w', encoding='utf-8') as f:
            json.dump(self.questions, f, ensure_ascii=False, indent=2)

    def add_question(self, question: str, context: str, priority: int = 1, category: str = "general"):
        self.questions.append({
            "id": len(self.questions) + 1,
            "question": question,
            "context": context[:500],
            "priority": priority,
            "category": category,
            "created_at": datetime.now().isoformat(),
            "answered": False,
            "answer": None,
            "answered_at": None
        })
        self._save()
        logger.info(f"تم إضافة سؤال: {question[:50]}...")

    def mark_answered(self, question_id: int, answer: str):
        for q in self.questions:
            if q["id"] == question_id:
                q["answered"] = True
                q["answer"] = answer[:500]
                q["answered_at"] = datetime.now().isoformat()
                break
        self._save()

    def get_pending_count(self) -> int:
        return len([q for q in self.questions if not q.get("answered", False)])

    def get_all_unanswered(self) -> List[Dict]:
        return [q for q in self.questions if not q.get("answered", False)]
