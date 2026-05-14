import random


class Brain:
    def __init__(self, sacred_context: str, memory_summary: dict):
        self.context = sacred_context[:800]
        self.memory = memory_summary
        self.concept = self._extract_concept()
        self.iteration = memory_summary.get("iteration", 0)
        self.has_book = memory_summary.get("has_book", False)

    def _extract_concept(self) -> str:
        words = self.context.split()[:20]
        return " ".join(words) if words else "العدل"

    def think(self) -> dict:
        actions_count = self.memory.get("actions_count", 0)
        avg_score = self.memory.get("avg_score", 0.5)

        if actions_count > 50:
            if random.random() < 0.6:
                return {"action": "silence", "reason": "في الصمت حكمة.", "focus": self.concept}

        if actions_count < 5:
            return {"action": "deep_reflection", "reason": "بداية الرحلة.", "focus": self.concept}

        if avg_score < 0.6 and actions_count < 50:
            evolutions_today = self.memory.get("evolutions_today", 0)
            if evolutions_today < 3:
                return {"action": "evolve", "reason": f"أدائي {avg_score:.2f}. أحتاج للتطور.", "focus": self.concept}

        if random.random() < 0.2 and actions_count > 10:
            if self.has_book:
                return {"action": "curiosity", "reason": "فضول: أبحث عن علاقة هذا الكتاب بالدستور.", "focus": self.concept}
            return {"action": "curiosity", "reason": "فضول: أبحث عن فهم أعمق.", "focus": self.concept}

        return {"action": "silence", "reason": "في الصمت أتأمل.", "focus": self.concept}
