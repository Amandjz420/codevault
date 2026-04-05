"""
LLM query service with effort tiers (low/medium/high).
Combines semantic vector search with Neo4j graph context for richer answers.
"""
import time
import logging
from django.conf import settings

logger = logging.getLogger(__name__)

EFFORT_CONFIG = {
    "low": {
        "description": "Fast semantic search only. No graph traversal.",
        "vector_results": 5,
        "graph_hops": 0,
        "models": {
            "openai": "gpt-4o-mini",
            "google": "gemini-3.1-pro-preview",
            "anthropic": "claude-haiku-20240307",
        },
    },
    "medium": {
        "description": "Semantic search + 1-hop graph expansion.",
        "vector_results": 8,
        "graph_hops": 1,
        "models": {
            "openai": "gpt-4o",
            "google": "gemini-3.1-pro-preview",
            "anthropic": "claude-3-5-sonnet-20241022",
        },
    },
    "high": {
        "description": "Full graph traversal + multi-hop reasoning + code synthesis.",
        "vector_results": 15,
        "graph_hops": 3,
        "models": {
            "openai": "gpt-4o",
            "google": "gemini-3.1-pro-preview",
            "anthropic": "claude-opus-4-5",
        },
    },
}


def get_llm_provider():
    """Determine which LLM provider is available based on configured API keys."""
    if getattr(settings, 'OPENAI_API_KEY', None):
        return 'openai'
    if getattr(settings, 'ANTHROPIC_API_KEY', None):
        return 'anthropic'
    if getattr(settings, 'GOOGLE_API_KEY', None):
        return 'google'
    return None


class LLMQueryService:
    """Answers natural-language questions about a codebase."""

    def __init__(self, graph_service, vector_service):
        self.graph = graph_service
        self.vector = vector_service
        self.provider = get_llm_provider()

    def query(self, question: str, effort: str = 'medium') -> dict:
        start = time.time()
        config = EFFORT_CONFIG.get(effort, EFFORT_CONFIG['medium'])

        # 1. Vector search
        vector_hits = self.vector.search(question, n_results=config['vector_results'])

        # 2. Graph expansion
        graph_context = []
        if config['graph_hops'] > 0 and vector_hits:
            for hit in vector_hits[:3]:
                meta = hit.get('metadata', {})
                if meta.get('type') == 'function':
                    ctx = self.graph.get_function_context(meta.get('name', ''))
                    if ctx:
                        graph_context.append(ctx)

        if config['graph_hops'] >= 3:
            # High effort: pull endpoints, models, signals too
            graph_context.append({"all_endpoints": self.graph.get_all_endpoints()[:10]})
            graph_context.append({"all_models": self.graph.get_all_models()[:10]})

        # 3. Build prompt
        prompt = self._build_prompt(question, vector_hits, graph_context, effort)

        # 4. Call LLM
        answer, model_used, tokens = self._call_llm(prompt, config)

        latency_ms = int((time.time() - start) * 1000)

        return {
            "answer": answer,
            "effort": effort,
            "model": model_used,
            "tokens_used": tokens,
            "latency_ms": latency_ms,
            "context_files": list({
                h['metadata'].get('file_path')
                for h in vector_hits
                if h.get('metadata', {}).get('file_path')
            }),
        }

    def _build_prompt(self, question: str, vector_hits: list, graph_context: list, effort: str) -> str:
        config = EFFORT_CONFIG.get(effort, EFFORT_CONFIG['medium'])
        parts = [
            "You are an expert code analyst for a Python/Django codebase.",
            f"Effort level: {effort} — {config['description']}",
            "",
            f"Question: {question}",
            "",
            "=== Relevant Code Snippets (semantic search) ===",
        ]

        for i, hit in enumerate(vector_hits[:8], 1):
            meta = hit.get('metadata', {})
            parts.append(
                f"\n[{i}] {meta.get('type', '').upper()}: {meta.get('name', '')} "
                f"({meta.get('file_path', '')}:{meta.get('start_line', '')})"
            )
            parts.append(hit.get('document', '')[:800])

        if graph_context:
            parts.append("\n=== Structural Context (knowledge graph) ===")
            for ctx in graph_context:
                parts.append(str(ctx)[:600])

        parts.append("\n=== Answer ===")
        parts.append(
            "Provide a clear, specific answer. "
            "Reference exact file paths and function names where applicable. "
            "If the answer cannot be determined from the context, say so."
        )

        return '\n'.join(parts)

    def _call_llm(self, prompt: str, config: dict) -> tuple:
        provider = self.provider
        if not provider:
            return (
                "No LLM API key configured. "
                "Set OPENAI_API_KEY, ANTHROPIC_API_KEY, or GOOGLE_API_KEY in your environment.",
                "none",
                0,
            )

        model = config['models'].get(provider, list(config['models'].values())[0])

        try:
            if provider == 'openai':
                return self._call_openai(prompt, model)
            elif provider == 'anthropic':
                return self._call_anthropic(prompt, model)
            elif provider == 'google':
                return self._call_google(prompt, model)
        except Exception as e:
            logger.error(f"[LLM] Error calling {provider}/{model}: {e}")
            return f"LLM error: {str(e)}", model, 0

        return "Unexpected provider state.", provider, 0

    def _call_openai(self, prompt: str, model: str) -> tuple:
        from openai import OpenAI
        client = OpenAI(api_key=settings.OPENAI_API_KEY)
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=2000,
        )
        return resp.choices[0].message.content, model, resp.usage.total_tokens

    def _call_anthropic(self, prompt: str, model: str) -> tuple:
        import anthropic
        client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        resp = client.messages.create(
            model=model,
            max_tokens=2000,
            messages=[{"role": "user", "content": prompt}],
        )
        tokens = resp.usage.input_tokens + resp.usage.output_tokens
        return resp.content[0].text, model, tokens

    def _call_google(self, prompt: str, model: str) -> tuple:
        import google.generativeai as genai
        genai.configure(api_key=settings.GOOGLE_API_KEY)
        m = genai.GenerativeModel(model)
        resp = m.generate_content(prompt)
        usage = getattr(resp, 'usage_metadata', None)
        total = getattr(usage, 'total_token_count', 0) if usage else 0
        return resp.text, model, total
