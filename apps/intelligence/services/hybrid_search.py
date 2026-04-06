"""
Hybrid search service combining keyword (Neo4j) and semantic (ChromaDB) results.
Uses reciprocal rank fusion to merge and deduplicate hits from both sources.
"""
import logging

logger = logging.getLogger(__name__)


class HybridSearchService:
    """Combines Neo4j keyword search with ChromaDB semantic search."""

    def __init__(self, graph_service, vector_service,
                 keyword_weight: float = 0.6, semantic_weight: float = 0.4):
        self.graph = graph_service
        self.vector = vector_service
        self.keyword_weight = keyword_weight
        self.semantic_weight = semantic_weight

    def search(self, query: str, n_results: int = 10, filter_type: str = None) -> list:
        """
        Run keyword + semantic search, merge with reciprocal rank fusion.
        Returns results in the same format as VectorService.search().
        """
        keyword_hits = self._keyword_search(query, filter_type)
        semantic_hits = self.vector.search(query, n_results=n_results, filter_type=filter_type)

        merged = self._merge(keyword_hits, semantic_hits)

        # Sort by combined score descending, return top n_results
        merged.sort(key=lambda h: h.get('_score', 0), reverse=True)
        # Strip internal score before returning
        for hit in merged:
            hit.pop('_score', None)
        return merged[:n_results]

    def _keyword_search(self, query: str, filter_type: str = None) -> list:
        """Run Neo4j keyword searches and normalize to vector-hit format."""
        hits = []

        if filter_type in (None, 'any', 'function'):
            try:
                functions = self.graph.search_functions(query)
                for fn in functions:
                    hits.append({
                        "document": self._function_to_document(fn),
                        "metadata": {
                            "file_path": fn.get("file", ""),
                            "type": "function",
                            "name": fn.get("name", ""),
                            "start_line": fn.get("line", 0),
                            "parent_class": fn.get("parent_class", ""),
                            "is_method": str(fn.get("is_method", False)),
                        },
                        "distance": None,
                        "id": None,
                        "_source": "keyword",
                    })
            except Exception as e:
                logger.warning(f"[HybridSearch] Keyword function search failed: {e}")

        if filter_type in (None, 'any', 'class'):
            try:
                classes = self.graph.search_classes(query)
                for cls in classes:
                    hits.append({
                        "document": self._class_to_document(cls),
                        "metadata": {
                            "file_path": cls.get("file", ""),
                            "type": "class",
                            "name": cls.get("name", ""),
                            "start_line": cls.get("line", 0),
                            "is_django_model": str(cls.get("is_django_model", False)),
                        },
                        "distance": None,
                        "id": None,
                        "_source": "keyword",
                    })
            except Exception as e:
                logger.warning(f"[HybridSearch] Keyword class search failed: {e}")

        return hits

    def _merge(self, keyword_hits: list, semantic_hits: list) -> list:
        """Merge keyword and semantic hits using reciprocal rank fusion."""
        scored = {}  # key -> hit dict with _score

        k = 60  # RRF constant

        # Score keyword hits by reciprocal rank
        for rank, hit in enumerate(keyword_hits):
            key = self._hit_key(hit)
            rrf = 1.0 / (k + rank + 1)
            score = rrf * self.keyword_weight
            if key in scored:
                scored[key]['_score'] += score
            else:
                hit['_score'] = score
                scored[key] = hit

        # Score semantic hits by reciprocal rank
        for rank, hit in enumerate(semantic_hits):
            key = self._hit_key(hit)
            rrf = 1.0 / (k + rank + 1)
            score = rrf * self.semantic_weight
            if key in scored:
                # Boost: appeared in both sources
                scored[key]['_score'] += score
                # Prefer the semantic hit's document (has embedding-quality text)
                if hit.get('document'):
                    scored[key]['document'] = hit['document']
                if hit.get('distance') is not None:
                    scored[key]['distance'] = hit['distance']
                if hit.get('id'):
                    scored[key]['id'] = hit['id']
            else:
                hit['_score'] = score
                scored[key] = hit

        return list(scored.values())

    @staticmethod
    def _hit_key(hit: dict) -> tuple:
        """Dedup key from metadata: (file_path, type, name)."""
        meta = hit.get('metadata', {})
        return (
            meta.get('file_path', ''),
            meta.get('type', ''),
            meta.get('name', ''),
        )

    @staticmethod
    def _function_to_document(fn: dict) -> str:
        parts = [f"Function: {fn.get('name', '')}"]
        if fn.get('parent_class'):
            parts.append(f"Class: {fn['parent_class']}")
        if fn.get('docstring'):
            parts.append(f"Docstring: {fn['docstring']}")
        if fn.get('code'):
            parts.append(f"Code:\n{fn['code'][:1500]}")
        return '\n'.join(parts)

    @staticmethod
    def _class_to_document(cls: dict) -> str:
        parts = [f"Class: {cls.get('name', '')}"]
        if cls.get('bases'):
            bases = cls['bases']
            if isinstance(bases, list):
                parts.append(f"Bases: {', '.join(bases)}")
            else:
                parts.append(f"Bases: {bases}")
        if cls.get('docstring'):
            parts.append(f"Docstring: {cls['docstring']}")
        if cls.get('is_django_model'):
            parts.append("Type: Django ORM Model")
        return '\n'.join(parts)
