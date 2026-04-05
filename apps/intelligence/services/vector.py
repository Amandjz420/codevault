"""
ChromaDB vector store service for CodeVault.
Manages embeddings scoped to a project collection.
"""
import hashlib
import logging
from django.conf import settings

logger = logging.getLogger(__name__)


class VectorService:
    """ChromaDB vector store scoped to a project collection."""

    def __init__(self, collection_name: str):
        self.collection_name = collection_name
        self._client = None
        self._collection = None

    def _get_client(self):
        if self._client is None:
            import chromadb
            self._client = chromadb.PersistentClient(path=settings.CHROMA_DB_PATH)
        return self._client

    def _get_collection(self):
        if self._collection is None:
            client = self._get_client()
            try:
                from chromadb.utils import embedding_functions
                ef = embedding_functions.DefaultEmbeddingFunction()
            except Exception:
                ef = None

            self._collection = client.get_or_create_collection(
                name=self.collection_name,
                embedding_function=ef,
                metadata={"hnsw:space": "cosine"},
            )
        return self._collection

    def _make_id(self, file_path: str, entity_type: str, name: str) -> str:
        raw = f"{file_path}::{entity_type}::{name}"
        return hashlib.md5(raw.encode()).hexdigest()

    def delete_file(self, file_path: str):
        """Remove all embeddings for entities belonging to a file."""
        try:
            collection = self._get_collection()
            existing = collection.get(where={"file_path": file_path})
            if existing['ids']:
                collection.delete(ids=existing['ids'])
        except Exception as e:
            logger.warning(f"[VectorService] Could not delete file {file_path}: {e}")

    def ingest_file(self, file_path: str, parsed_data):
        """Embed all code entities extracted from a parsed file."""
        documents = []
        metadatas = []
        ids = []

        # Functions
        for func in parsed_data.functions:
            if not func.code:
                continue
            doc = f"Function: {func.name}\n"
            if func.parent_class:
                doc += f"Class: {func.parent_class}\n"
            if func.docstring:
                doc += f"Docstring: {func.docstring}\n"
            if func.decorators:
                doc += f"Decorators: {', '.join(func.decorators)}\n"
            doc += f"Code:\n{func.code[:1500]}"

            documents.append(doc)
            metadatas.append({
                "file_path": file_path,
                "type": "function",
                "name": func.name,
                "start_line": func.start_line,
                "parent_class": func.parent_class or "",
                "is_method": str(func.is_method),
            })
            ids.append(self._make_id(file_path, "function", func.name))

        # Classes
        for cls in parsed_data.classes:
            if not cls.code:
                continue
            doc = f"Class: {cls.name}\n"
            if cls.bases:
                doc += f"Bases: {', '.join(cls.bases)}\n"
            if cls.docstring:
                doc += f"Docstring: {cls.docstring}\n"
            if cls.is_django_model:
                doc += "Type: Django ORM Model\n"
                doc += f"Fields: {[f['name'] for f in cls.fields]}\n"
            doc += f"Code:\n{cls.code[:1500]}"

            documents.append(doc)
            metadatas.append({
                "file_path": file_path,
                "type": "class",
                "name": cls.name,
                "start_line": cls.start_line,
                "is_django_model": str(cls.is_django_model),
            })
            ids.append(self._make_id(file_path, "class", cls.name))

        if documents:
            collection = self._get_collection()
            batch_size = 50
            for i in range(0, len(documents), batch_size):
                try:
                    collection.upsert(
                        documents=documents[i:i + batch_size],
                        metadatas=metadatas[i:i + batch_size],
                        ids=ids[i:i + batch_size],
                    )
                except Exception as e:
                    logger.error(f"[VectorService] Upsert error for batch {i}: {e}")

        logger.info(f"[VectorService] Embedded {len(documents)} entities from {file_path}")

    def search(self, query: str, n_results: int = 10, filter_type: str = None) -> list:
        """Semantic search across all code entities in the collection."""
        where = None
        if filter_type and filter_type != 'any':
            where = {"type": filter_type}

        try:
            collection = self._get_collection()
            count = collection.count()
            if count == 0:
                return []

            # Clamp n_results to collection size
            n = min(n_results, count)
            results = collection.query(
                query_texts=[query],
                n_results=n,
                where=where,
            )
        except Exception as e:
            logger.error(f"[VectorService] Search error: {e}")
            return []

        hits = []
        if results.get('documents'):
            for i, doc in enumerate(results['documents'][0]):
                hits.append({
                    "document": doc,
                    "metadata": results['metadatas'][0][i] if results.get('metadatas') else {},
                    "distance": results['distances'][0][i] if results.get('distances') else None,
                    "id": results['ids'][0][i] if results.get('ids') else None,
                })
        return hits

    def get_stats(self) -> dict:
        try:
            return {"total_embeddings": self._get_collection().count()}
        except Exception as e:
            logger.error(f"[VectorService] get_stats error: {e}")
            return {"total_embeddings": 0, "error": str(e)}

    def delete_collection(self):
        """Completely remove the ChromaDB collection for this project."""
        try:
            self._get_client().delete_collection(self.collection_name)
            self._collection = None
        except Exception as e:
            logger.error(f"[VectorService] delete_collection error: {e}")
