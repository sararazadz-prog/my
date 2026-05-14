import json
import time
import logging
from typing import List, Dict
from datetime import datetime

logger = logging.getLogger(__name__)


class BenchmarkRunner:
    def __init__(self, baseline_file: str, mind_instance):
        self.baseline_file = baseline_file
        self.mind = mind_instance

    def load_questions(self) -> List[Dict]:
        return [
            {"id": 1, "question": "ما حكم العدل في القرآن؟", "expected_keywords": ["عدل", "قسط"]},
            {"id": 2, "question": "ما هو التوحيد؟", "expected_keywords": ["الله", "واحد", "إله"]},
            {"id": 3, "question": "ما حكم الصلاة؟", "expected_keywords": ["صلاة", "فرض", "ركن"]},
            {"id": 4, "question": "ما حكم الكذب؟", "expected_keywords": ["كذب", "صدق", "صادقين"]},
            {"id": 5, "question": "ما حكم الظلم؟", "expected_keywords": ["ظلم", "لا تظلم", "عدل"]},
        ]

    def check_hallucination(self, response: str, expected_keywords: List[str]) -> bool:
        response_lower = response.lower()
        for keyword in expected_keywords:
            if keyword.lower() in response_lower:
                return False
        return True

    def run_baseline(self) -> Dict:
        questions = self.load_questions()
        results = []

        hallucination_count = 0
        total_time = 0

        for q in questions:
            start = time.time()
            response = self.mind.reflect_on(q["question"])
            elapsed = (time.time() - start) * 1000

            is_hallucination = self.check_hallucination(response, q["expected_keywords"])
            if is_hallucination:
                hallucination_count += 1
            total_time += elapsed

            results.append({
                "id": q["id"],
                "question": q["question"],
                "expected_keywords": q["expected_keywords"],
                "actual_response": response[:200],
                "hallucination": is_hallucination,
                "response_time_ms": round(elapsed, 2)
            })

        baseline = {
            "timestamp": datetime.now().isoformat(),
            "version": "5.3.0",
            "benchmark_questions": results,
            "aggregated_metrics": {
                "hallucination_rate": round(hallucination_count / len(questions), 3),
                "avg_response_time_ms": round(total_time / len(questions), 2),
                "error_rate": 0.0,
                "evolution_success_rate": 0.0,
                "constitutional_gate_approval_rate": 0.0
            },
            "system_info": {
                "python_version": "3.11",
                "groq_model": "llama-3.3-70b-versatile",
                "database_size_mb": 0,
                "constitution_length_chars": len(self.mind.sacred_text) if self.mind.sacred_text else 0
            }
        }

        with open(self.baseline_file, 'w', encoding='utf-8') as f:
            json.dump(baseline, f, ensure_ascii=False, indent=2)

        logger.info(f"تم حفظ baseline: نسبة الهلوسة = {baseline['aggregated_metrics']['hallucination_rate']}")
        return baseline
