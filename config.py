# ============================================================
# الإعدادات المركزية – الحارس الصامت v5.0
# ============================================================

import os

# متغيرات البيئة
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
GITHUB_REPO = os.environ.get("GITHUB_REPO", "sararazadz-prog/my")
GITHUB_BRANCH = os.environ.get("GITHUB_BRANCH", "main")
PERSISTENT_DIR = os.environ.get("PERSISTENT_DIR", "/data")

# حدود الأمان
MAX_BOOK_SIZE = 10 * 1024 * 1024  # 10MB
MAX_CODE_EXECUTION_TIME = 5  # seconds
MAX_EVOLUTIONS_PER_DAY = 3
MAX_REQUESTS_PER_MINUTE = 10  # Rate limiting

# فترات التعلم (بالثواني)
LEARNING_INTERVAL = 1800  # 30 دقيقة
CURIOSITY_INTERVAL = 3600  # ساعة
REVIEW_INTERVAL = 86400  # 24 ساعة
EVOLUTION_CHECK_INTERVAL = 3600  # ساعة
BACKUP_INTERVAL_ITERATIONS = 50
AGENT_DRAW_INTERVAL = 60000  # ملي ثانية

# مصادر الدستور
QURAN_URL = "https://cdn.jsdelivr.net/npm/quran-json@3.1.2/dist/quran.json"

# مسارات الملفات
CONSTITUTION_FILE = f"{PERSISTENT_DIR}/constitution.txt"
DB_PATH = f"{PERSISTENT_DIR}/constitution.db"
DESIGN_FILE = f"{PERSISTENT_DIR}/design.json"
MOODS_FILE = f"{PERSISTENT_DIR}/moods.json"
BOOKS_DIR = f"{PERSISTENT_DIR}/books"
CURRENT_BOOK_FILE = f"{PERSISTENT_DIR}/current_book.txt"
PENDING_QUESTIONS_FILE = f"{PERSISTENT_DIR}/pending_questions.json"
LEARNING_LOG_FILE = f"{PERSISTENT_DIR}/learning_log.json"
AGENT_ART_DIR = f"{PERSISTENT_DIR}/agent_art"
