import os
import base64
import hashlib
import logging
from datetime import datetime
from pathlib import Path

from github import Github

from app.config import GITHUB_TOKEN, GITHUB_REPO, GITHUB_BRANCH

logger = logging.getLogger(__name__)


def is_binary_file(file_path: str) -> bool:
    binary_extensions = ['.db', '.sqlite', '.sqlite3', '.pdf', '.zip', '.png', '.jpg', '.jpeg']
    if any(file_path.endswith(ext) for ext in binary_extensions):
        return True
    try:
        with open(file_path, 'rb') as f:
            chunk = f.read(1024)
        return b'\x00' in chunk
    except:
        return True


def get_file_hash(file_path: str) -> str:
    sha256 = hashlib.sha256()
    with open(file_path, 'rb') as f:
        for chunk in iter(lambda: f.read(4096), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


def verify_db_integrity(db_path: str) -> bool:
    import sqlite3
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("PRAGMA integrity_check")
        result = cursor.fetchone()
        conn.close()
        return result[0] == "ok"
    except Exception as e:
        logger.error(f"فشل التحقق من قاعدة البيانات: {e}")
        return False


def sync_to_github(local_path: str, repo_path: str, commit_message: str = None) -> bool:
    if not GITHUB_TOKEN:
        return False
    if not os.path.exists(local_path):
        return False
    if commit_message is None:
        commit_message = f"Backup: {datetime.now().isoformat()}"

    try:
        g = Github(GITHUB_TOKEN)
        repo = g.get_repo(GITHUB_REPO)

        with open(local_path, 'rb') as f:
            raw_bytes = f.read()

        if is_binary_file(local_path):
            content = base64.b64encode(raw_bytes).decode('utf-8')
        else:
            content = raw_bytes.decode('utf-8', errors='replace')

        try:
            contents = repo.get_contents(repo_path, ref=GITHUB_BRANCH)
            repo.update_file(contents.path, commit_message, content, contents.sha, branch=GITHUB_BRANCH)
        except:
            repo.create_file(repo_path, commit_message, content, branch=GITHUB_BRANCH)
        return True
    except Exception as e:
        logger.error(f"فشل رفع {repo_path}: {e}")
        return False


def sync_from_github(local_path: str, repo_path: str) -> bool:
    if not GITHUB_TOKEN:
        return False
    try:
        g = Github(GITHUB_TOKEN)
        repo = g.get_repo(GITHUB_REPO)
        contents = repo.get_contents(repo_path, ref=GITHUB_BRANCH)
        content_bytes = base64.b64decode(contents.content)
        os.makedirs(os.path.dirname(local_path), exist_ok=True)
        with open(local_path, 'wb') as f:
            f.write(content_bytes)
        return True
    except:
        return False


def backup_agent_state(event: str = "manual"):
    logger.info(f"بدء النسخ الاحتياطي (الحدث: {event})")

    from app.config import (
        DB_PATH, PERSISTENT_DIR, CURRENT_BOOK_FILE,
        PENDING_QUESTIONS_FILE, BOOKS_DIR
    )

    MOODS_FILE = f"{PERSISTENT_DIR}/moods.json"
    DESIGN_FILE = f"{PERSISTENT_DIR}/design.json"
    LEARNING_LOG_FILE = f"{PERSISTENT_DIR}/learning_log.json"

    files_to_backup = [
        (DB_PATH, "data/constitution.db"),
        (MOODS_FILE, "data/moods.json"),
        (DESIGN_FILE, "data/design.json"),
        (CURRENT_BOOK_FILE, "data/current_book.txt"),
        (PENDING_QUESTIONS_FILE, "data/pending_questions.json"),
        (LEARNING_LOG_FILE, "data/learning_log.json"),
    ]

    for local_path, repo_path in files_to_backup:
        if os.path.exists(local_path):
            sync_to_github(local_path, repo_path, f"Backup: {event}")

    if os.path.exists(BOOKS_DIR):
        for book_file in os.listdir(BOOKS_DIR):
            book_path = os.path.join(BOOKS_DIR, book_file)
            if os.path.isfile(book_path):
                sync_to_github(book_path, f"data/books/{book_file}", f"Backup book: {book_file}")

    logger.info("تم النسخ الاحتياطي")


def restore_agent_state():
    logger.info("استعادة الذاكرة من GitHub...")

    from app.config import (
        DB_PATH, PERSISTENT_DIR, CURRENT_BOOK_FILE,
        PENDING_QUESTIONS_FILE
    )

    MOODS_FILE = f"{PERSISTENT_DIR}/moods.json"
    DESIGN_FILE = f"{PERSISTENT_DIR}/design.json"
    LEARNING_LOG_FILE = f"{PERSISTENT_DIR}/learning_log.json"

    files_to_restore = [
        (DB_PATH, "data/constitution.db"),
        (MOODS_FILE, "data/moods.json"),
        (DESIGN_FILE, "data/design.json"),
        (CURRENT_BOOK_FILE, "data/current_book.txt"),
        (PENDING_QUESTIONS_FILE, "data/pending_questions.json"),
        (LEARNING_LOG_FILE, "data/learning_log.json"),
    ]

    for local_path, repo_path in files_to_restore:
        sync_from_github(local_path, repo_path)

    if os.path.exists(DB_PATH):
        if not verify_db_integrity(DB_PATH):
            logger.error("قاعدة البيانات تالفة بعد الاستعادة!")
