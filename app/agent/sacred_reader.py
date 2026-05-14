import hashlib
import logging
from pathlib import Path
from typing import List

import chromadb
from chromadb.utils import embedding_functions

logger = logging.getLogger(__name__)


class SacredReader:
    def __init__(self, file_path: str):
        self.file_path = Path(file_path)
        self._sacred_text = ""
        self._hash = ""

        self.chroma_client = chromadb.PersistentClient(path="/data/chroma_db")
        self.collection_name = "constitution"
        self.embedding_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name="all-MiniLM-L6-v2"
        )

        self._load()
        self._init_vector_store()

    def _load(self):
        if not self.file_path.exists():
            return
        with open(self.file_path, 'r', encoding='utf-8') as f:
            self._sacred_text = f.read()
        self._hash = hashlib.md5(self._sacred_text.encode()).hexdigest()
        logger.info(f"تم تحميل الدستور: {len(self._sacred_text):,} حرفاً")

    def _init_vector_store(self):
        try:
            try:
                self.chroma_client.delete_collection(self.collection_name)
            except:
                pass

            collection = self.chroma_client.create_collection(
                name=self.collection_name,
                embedding_function=self.embedding_fn
            )

            chunk_size = 500
            words = self._sacred_text.split()
            chunks = []
            ids = []
            for i in range(0, len(words), chunk_size):
                chunk = " ".join(words[i:i+chunk_size])
                chunks.append(chunk)
                ids.append(f"chunk_{i}")

            collection.add(
                documents=chunks,
                ids=ids,
                metadatas=[{"source": "constitution", "index": i} for i in range(len(chunks))]
            )
            logger.info(f"تم فهرسة {len(chunks)} مقطعاً في ChromaDB")

        except Exception as e:
            logger.error(f"فشل تهيئة ChromaDB: {e}")

    def semantic_search(self, query: str, top_k: int = 3) -> List[str]:
        try:
            collection = self.chroma_client.get_collection(self.collection_name)
            results = collection.query(query_texts=[query], n_results=top_k)
            return results['documents'][0] if results['documents'] else []
        except Exception as e:
            logger.error(f"خطأ في البحث الدلالي: {e}")
            return []

    @property
    def sacred_text(self) -> str:
        return self._sacred_text

    @property
    def hash(self) -> str:
        return self._hash
