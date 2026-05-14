import os
import sys
import json
import time
import random
import hashlib
import threading
from typing import Optional, Tuple, List
from datetime import datetime

from app.config import (
    GROQ_API_KEY, MAX_CODE_EXECUTION_TIME, MAX_EVOLUTIONS_PER_DAY,
    CONSTITUTION_WEIGHT, BOOK_WEIGHT, PENDING_QUESTIONS_FILE
)
from app.agent.sacred_reader import SacredReader
from app.agent.book_reader import BookReader
from app.agent.memory import ConstitutionalMemory
from app.agent.questions import QuestionManager
from app.agent.brain import Brain as BrainTemplate
from app.git_backup.backup import backup_agent_state
from docker_sandbox.sandbox_wrapper import SafeSandbox

import logging
logger = logging.getLogger(__name__)


class GroqClient:
    def __init__(self, api_key: str, role: str = "default"):
        self.api_key = api_key
        self.role = role
        self.available = bool(api_key)

    def call(self, prompt: str, system_prompt: str = None,
             context: str = "", book_context: str = "",
             temperature: float = 0.7, max_tokens: int = 800) -> str:
        if not self.available:
            return "Groq غير متوفر حالياً"

        for attempt in range(3):
            try:
                from groq import Groq
                client = Groq(api_key=self.api_key)

                full_prompt = prompt
                if context:
                    full_prompt = f"{prompt}\n\nمن الدستور:\n{context[:1000]}"
                if book_context:
                    full_prompt = f"{full_prompt}\n\nمن الكتاب:\n{book_context[:500]}"

                messages = []
                if system_prompt:
                    messages.append({"role": "system", "content": system_prompt})
                messages.append({"role": "user", "content": full_prompt})

                response = client.chat.completions.create(
                    model="llama-3.3-70b-versatile",
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens
                )
                return response.choices[0].message.content
            except Exception as e:
                if attempt == 2:
                    return f"خطأ: {str(e)[:100]}"
                time.sleep(2)
        return "خطأ في الاتصال"
