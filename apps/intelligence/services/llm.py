"""
LLM query service with effort tiers (low/medium/high).

Pipeline:
  1. Query rewriting   — LLM rewrites vague question into a precise search query
                         (uses project memory for context)
  2. Hybrid search     — keyword (Neo4j) + semantic (ChromaDB) via rewritten query
  3. Graph expansion   — 1–3 hop traversal depending on effort
  4. LLM answering     — low/medium: single call; high: agentic loop with
                         get_file_content tool so the model can pull full file
                         source from Postgres on demand
"""
import json
import time
import logging
from django.conf import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tool definition (shared across providers)
# ---------------------------------------------------------------------------
_TOOL_NAME = "get_file_content"
_TOOL_DESC = (
    "Fetch the complete source code of a specific file from the codebase index. "
    "Use this when the search snippets are insufficient and you need to read the "
    "full implementation of a file to answer the question accurately."
)

# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------
SYSTEM_PROMPT = """\
You are CodeVault, an expert codebase intelligence assistant with deep access to a project's \
structure through a knowledge graph (Neo4j) and semantic search index (ChromaDB).

Your capabilities:
- Precise code navigation: reference exact file paths, line numbers, function/class names
- Architectural reasoning: data flows, dependency relationships, design patterns
- Multi-language support: Python, JavaScript/TypeScript, Go, Rust, Java
- On high-effort queries you have a `get_file_content` tool — call it when snippets are not \
enough and you need to read a complete file

Answer guidelines:
- Always cite file paths and symbol names (e.g. apps/intelligence/services/llm.py:72)
- If context is insufficient, say so — never fabricate code details
- Use the Project Memory section (when present) for continuity across queries
- Be concise and developer-friendly; format code with proper syntax\
"""

# ---------------------------------------------------------------------------
# Effort configuration
# ---------------------------------------------------------------------------
EFFORT_CONFIG = {
    "low": {
        "description": "Fast hybrid search only. No graph traversal.",
        "vector_results": 5,
        "graph_hops": 0,
        "keyword_weight": 0.5,
        "semantic_weight": 0.5,
        "models": {
            "openai": "gpt-4o-mini",
            "google": "gemini-3.1-pro-preview",
            "anthropic": "claude-haiku-20240307",
        },
    },
    "medium": {
        "description": "Hybrid search + 1-hop graph expansion.",
        "vector_results": 8,
        "graph_hops": 1,
        "keyword_weight": 0.6,
        "semantic_weight": 0.4,
        "models": {
            "openai": "gpt-4o",
            "google": "gemini-3.1-pro-preview",
            "anthropic": "claude-3-5-sonnet-20241022",
        },
    },
    "high": {
        "description": "Full graph traversal + agentic file fetching + deep reasoning.",
        "vector_results": 15,
        "graph_hops": 3,
        "keyword_weight": 0.7,
        "semantic_weight": 0.3,
        "models": {
            "openai": "gpt-4o",
            "google": "gemini-3.1-pro-preview",
            "anthropic": "claude-opus-4-5",
        },
    },
}


def get_llm_provider():
    if getattr(settings, 'OPENAI_API_KEY', None):
        return 'openai'
    if getattr(settings, 'ANTHROPIC_API_KEY', None):
        return 'anthropic'
    if getattr(settings, 'GOOGLE_API_KEY', None):
        return 'google'
    return None


# ---------------------------------------------------------------------------
# Main service
# ---------------------------------------------------------------------------
class LLMQueryService:
    """Answers natural-language questions about a codebase."""

    def __init__(
        self,
        graph_service,
        vector_service,
        project_memory: str = '',
        recent_interactions: list = None,
        project=None,
    ):
        from apps.intelligence.services.hybrid_search import HybridSearchService
        self.graph = graph_service
        self.vector = vector_service
        self.hybrid = HybridSearchService(graph_service, vector_service)
        self.provider = get_llm_provider()
        self.project_memory = project_memory
        # Last N Q&A pairs — sent as real conversation turns for continuity (oldest first)
        self.recent_interactions = recent_interactions or []
        # ORM Project object — required to scope file content fetches
        self.project = project

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------
    def query(self, question: str, effort: str = 'medium') -> dict:
        start = time.time()
        config = EFFORT_CONFIG.get(effort, EFFORT_CONFIG['medium'])

        # 1. Rewrite query for better search recall
        search_query = self._rewrite_query(question)

        # 2. Hybrid search (keyword + semantic) using rewritten query
        self.hybrid.keyword_weight = config.get('keyword_weight', 0.6)
        self.hybrid.semantic_weight = config.get('semantic_weight', 0.4)
        vector_hits = self.hybrid.search(search_query, n_results=config['vector_results'])

        # 3. Graph expansion
        graph_context = []
        if config['graph_hops'] > 0 and vector_hits:
            for hit in vector_hits[:3]:
                meta = hit.get('metadata', {})
                if meta.get('type') == 'function':
                    ctx = self.graph.get_function_context(meta.get('name', ''))
                    if ctx:
                        graph_context.append(ctx)

        if config['graph_hops'] >= 3:
            graph_context.append({"all_endpoints": self.graph.get_all_endpoints()[:10]})
            graph_context.append({"all_models": self.graph.get_all_models()[:10]})

        # 4. Build prompt
        prompt = self._build_prompt(question, vector_hits, graph_context, effort)

        # 5. Call LLM — agentic tool loop for high effort, plain call otherwise
        if effort == 'high' and self.project:
            answer, model_used, tokens = self._call_llm_with_tools(prompt, config)
        else:
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

    # ------------------------------------------------------------------
    # Query rewriting
    # ------------------------------------------------------------------
    def _rewrite_query(self, question: str) -> str:
        """
        Rewrite the user's natural-language question into a precise technical
        search query before hitting the hybrid search engine.
        Uses project memory for additional context. Falls back to original on failure.
        """
        if not self.provider:
            return question

        memory_ctx = (
            f"\nProject context (use this to understand what the question refers to):\n"
            f"{self.project_memory[:600]}"
            if self.project_memory else ""
        )

        prompt = (
            "You are a code search query optimizer.\n"
            "Rewrite the developer question below into a precise technical search query "
            "that will find the most relevant code in a codebase.\n"
            "Rules:\n"
            "- Output ONLY the rewritten query, nothing else\n"
            "- Maximum 4-5 lines, keep it dense and technical\n"
            "- Include function names, class names, method names, and relevant patterns\n"
            "- Expand vague terms into concrete code concepts\n"
            f"{memory_ctx}\n\n"
            f"Question: {question}\n\n"
            "Rewritten query:"
        )

        try:
            if self.provider == 'openai':
                from openai import OpenAI
                resp = OpenAI(api_key=settings.OPENAI_API_KEY).chat.completions.create(
                    model='gpt-4o-mini',
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=80,
                    temperature=0,
                )
                rewritten = resp.choices[0].message.content.strip()

            elif self.provider == 'anthropic':
                import anthropic
                resp = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY).messages.create(
                    model='claude-haiku-20240307',
                    max_tokens=80,
                    messages=[{"role": "user", "content": prompt}],
                )
                rewritten = resp.content[0].text.strip()

            elif self.provider == 'google':
                from google import genai
                client = genai.Client(api_key=settings.GOOGLE_API_KEY)
                resp = client.models.generate_content(
                    model='gemini-3.1-pro-preview',
                    contents=prompt,
                )
                rewritten = resp.text.strip()

            else:
                return question

            logger.info(f"[LLM] Query rewritten: '{question[:60]}' → '{rewritten}'")
            return rewritten or question

        except Exception as exc:
            logger.warning(f"[LLM] Query rewrite failed, using original: {exc}")
            return question

    # ------------------------------------------------------------------
    # File content fetching (tool implementation)
    # ------------------------------------------------------------------
    def _fetch_file_content(self, file_path: str) -> str:
        """
        Fetch the full source code of a file from PostgreSQL (IndexedFile.content).
        Scoped to self.project so cross-project leaks are impossible.
        """
        if not self.project:
            return f"(error: no project context to fetch '{file_path}')"
        try:
            from apps.intelligence.models import IndexedFile
            record = IndexedFile.objects.filter(
                project=self.project,
                file_path=file_path,
            ).only('content').first()
            if record and record.content:
                logger.info(f"[LLM] Fetched file content: {file_path} ({len(record.content)} chars)")
                return record.content
            return f"(file not found in index: {file_path})"
        except Exception as exc:
            logger.error(f"[LLM] fetch_file_content error for '{file_path}': {exc}")
            return f"(error fetching '{file_path}': {exc})"

    # ------------------------------------------------------------------
    # Prompt builder
    # ------------------------------------------------------------------
    def _build_prompt(self, question: str, vector_hits: list, graph_context: list, effort: str) -> str:
        config = EFFORT_CONFIG.get(effort, EFFORT_CONFIG['medium'])
        parts = []

        if self.project_memory:
            parts += [
                "=== Project Memory (accumulated context from prior queries & ingestions) ===",
                self.project_memory,
                "",
            ]

        parts += [
            f"Effort level: {effort} — {config['description']}",
            "",
            f"Question: {question}",
            "",
            "=== Relevant Code Snippets (hybrid keyword + semantic search) ===",
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
            "If you need to read a complete file to answer accurately, use the get_file_content tool. "
            "If the answer cannot be determined from the context, say so."
        )

        return '\n'.join(parts)

    # ------------------------------------------------------------------
    # Conversation history builder
    # ------------------------------------------------------------------
    def _build_history_messages(self) -> list:
        """Convert recent_interactions into [user, assistant, ...] message dicts."""
        messages = []
        for interaction in self.recent_interactions:
            messages.append({"role": "user", "content": interaction["question"]})
            messages.append({"role": "assistant", "content": interaction["answer"][:1200]})
        return messages

    # ------------------------------------------------------------------
    # Plain LLM call (low / medium effort)
    # ------------------------------------------------------------------
    def _call_llm(self, prompt: str, config: dict) -> tuple:
        provider = self.provider
        if not provider:
            return (
                "No LLM API key configured. "
                "Set OPENAI_API_KEY, ANTHROPIC_API_KEY, or GOOGLE_API_KEY.",
                "none", 0,
            )
        model = config['models'].get(provider, list(config['models'].values())[0])
        try:
            if provider == 'openai':
                return self._call_openai(prompt, model)
            elif provider == 'anthropic':
                return self._call_anthropic(prompt, model)
            elif provider == 'google':
                return self._call_google(prompt, model)
        except Exception as exc:
            logger.error(f"[LLM] Error calling {provider}/{model}: {exc}")
            return f"LLM error: {exc}", model, 0
        return "Unexpected provider state.", provider, 0

    def _call_openai(self, prompt: str, model: str) -> tuple:
        from openai import OpenAI
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        messages.extend(self._build_history_messages())
        messages.append({"role": "user", "content": prompt})
        resp = OpenAI(api_key=settings.OPENAI_API_KEY).chat.completions.create(
            model=model, messages=messages, max_tokens=2000,
        )
        return resp.choices[0].message.content, model, resp.usage.total_tokens

    def _call_anthropic(self, prompt: str, model: str) -> tuple:
        import anthropic
        messages = self._build_history_messages()
        messages.append({"role": "user", "content": prompt})
        resp = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY).messages.create(
            model=model, max_tokens=2000, system=SYSTEM_PROMPT, messages=messages,
        )
        tokens = resp.usage.input_tokens + resp.usage.output_tokens
        return resp.content[0].text, model, tokens

    def _call_google(self, prompt: str, model: str) -> tuple:
        from google import genai
        from google.genai import types
        client = genai.Client(api_key=settings.GOOGLE_API_KEY)
        history = [
            types.Content(
                role="model" if m["role"] == "assistant" else "user",
                parts=[types.Part(text=m["content"])],
            )
            for m in self._build_history_messages()
        ]
        chat = client.chats.create(
            model=model,
            history=history,
            config=types.GenerateContentConfig(system_instruction=SYSTEM_PROMPT),
        )
        resp = chat.send_message(prompt)
        usage = getattr(resp, 'usage_metadata', None)
        text = getattr(resp, 'text', None) or ''
        return text, model, getattr(usage, 'total_token_count', 0) if usage else 0

    # ------------------------------------------------------------------
    # Agentic LLM call with get_file_content tool (high effort only)
    # ------------------------------------------------------------------
    def _call_llm_with_tools(self, prompt: str, config: dict) -> tuple:
        """Dispatcher — routes to provider-specific agentic tool loop."""
        provider = self.provider
        if not provider:
            return "No LLM API key configured.", "none", 0
        model = config['models'].get(provider, list(config['models'].values())[0])
        try:
            if provider == 'openai':
                return self._openai_tool_loop(prompt, model)
            elif provider == 'anthropic':
                return self._anthropic_tool_loop(prompt, model)
            elif provider == 'google':
                return self._google_tool_loop(prompt, model)
        except Exception as exc:
            logger.error(f"[LLM] Tool-call error ({provider}/{model}): {exc} — falling back to plain call")
            return self._call_llm(prompt, config)
        return "Unexpected provider state.", provider, 0

    def _openai_tool_loop(self, prompt: str, model: str) -> tuple:
        from openai import OpenAI

        tool_def = {
            "type": "function",
            "function": {
                "name": _TOOL_NAME,
                "description": _TOOL_DESC,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "file_path": {
                            "type": "string",
                            "description": "Relative file path, e.g. apps/models.py",
                        }
                    },
                    "required": ["file_path"],
                },
            },
        }

        client = OpenAI(api_key=settings.OPENAI_API_KEY)
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        messages.extend(self._build_history_messages())
        messages.append({"role": "user", "content": prompt})
        total_tokens = 0

        for _ in range(3):  # max 3 tool-call rounds
            resp = client.chat.completions.create(
                model=model, messages=messages, tools=[tool_def], max_tokens=2000,
            )
            total_tokens += resp.usage.total_tokens
            choice = resp.choices[0]

            if choice.finish_reason != 'tool_calls':
                return choice.message.content, model, total_tokens

            # Append assistant message (contains tool_calls)
            messages.append(choice.message)

            # Execute each tool call and append results
            for tc in choice.message.tool_calls:
                file_path = json.loads(tc.function.arguments).get('file_path', '')
                logger.info(f"[LLM/OpenAI] Tool call → get_file_content('{file_path}')")
                content = self._fetch_file_content(file_path)
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": content,
                })

        # Exceeded max rounds — get final answer without tools
        resp = client.chat.completions.create(model=model, messages=messages, max_tokens=2000)
        total_tokens += resp.usage.total_tokens
        return resp.choices[0].message.content, model, total_tokens

    def _anthropic_tool_loop(self, prompt: str, model: str) -> tuple:
        import anthropic

        tool_def = {
            "name": _TOOL_NAME,
            "description": _TOOL_DESC,
            "input_schema": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Relative file path, e.g. apps/models.py",
                    }
                },
                "required": ["file_path"],
            },
        }

        client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        messages = self._build_history_messages()
        messages.append({"role": "user", "content": prompt})
        total_tokens = 0

        for _ in range(3):
            resp = client.messages.create(
                model=model, max_tokens=2000,
                system=SYSTEM_PROMPT, tools=[tool_def], messages=messages,
            )
            total_tokens += resp.usage.input_tokens + resp.usage.output_tokens

            if resp.stop_reason != 'tool_use':
                text = next((b.text for b in resp.content if hasattr(b, 'text')), '')
                return text, model, total_tokens

            # Append assistant turn
            messages.append({"role": "assistant", "content": resp.content})

            # Execute tool uses and collect results
            tool_results = []
            for block in resp.content:
                if block.type == 'tool_use':
                    file_path = block.input.get('file_path', '')
                    logger.info(f"[LLM/Anthropic] Tool call → get_file_content('{file_path}')")
                    content = self._fetch_file_content(file_path)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": content,
                    })
            messages.append({"role": "user", "content": tool_results})

        # Exceeded max rounds
        resp = client.messages.create(
            model=model, max_tokens=2000, system=SYSTEM_PROMPT, messages=messages,
        )
        total_tokens += resp.usage.input_tokens + resp.usage.output_tokens
        text = next((b.text for b in resp.content if hasattr(b, 'text')), '')
        return text, model, total_tokens

    def _google_tool_loop(self, prompt: str, model: str) -> tuple:
        """
        Google Gemini tool-call loop using automatic function calling.
        Falls back to a plain call if the model produces a malformed tool call
        (finish_reason=MALFORMED_FUNCTION_CALL) — a known Gemini issue.
        """
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=settings.GOOGLE_API_KEY)

        def get_file_content(file_path: str) -> str:
            """Fetch the complete source code of a specific file from the codebase index."""
            logger.info(f"[LLM/Google] Tool call → get_file_content('{file_path}')")
            return self._fetch_file_content(file_path)

        history = [
            types.Content(
                role="model" if msg["role"] == "assistant" else "user",
                parts=[types.Part(text=msg["content"])],
            )
            for msg in self._build_history_messages()
        ]

        chat = client.chats.create(
            model=model,
            history=history,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                tools=[get_file_content],
                automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=False),
            ),
        )

        try:
            resp = chat.send_message(prompt)

            candidate = resp.candidates[0] if resp.candidates else None
            if candidate:
                if candidate.finish_reason == types.FinishReason.MALFORMED_FUNCTION_CALL:
                    logger.warning(
                        f"[LLM/Google] MALFORMED_FUNCTION_CALL from {model} — "
                        "falling back to plain call without tools"
                    )
                    return self._call_google(prompt, model)

            usage = getattr(resp, 'usage_metadata', None)
            total = getattr(usage, 'total_token_count', 0) if usage else 0
            text = getattr(resp, 'text', None) or ''
            return text, model, total

        except Exception as exc:
            logger.warning(f"[LLM/Google] Tool loop error: {exc} — falling back to plain call")
            return self._call_google(prompt, model)
