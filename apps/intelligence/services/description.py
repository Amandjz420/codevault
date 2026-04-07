"""
Lightweight LLM service for generating concise AI descriptions of code entities.

Descriptions are:
- Always ≤ 10 lines (enforced both in prompt and post-processing)
- Generated using the cheapest available LLM provider
- Stored as a separate field from docstring so they are always present

Used during ingestion to enrich ParsedFunction, ParsedClass, and ParsedEndpoint
before they are written to Neo4j and ChromaDB.
"""
import logging
from django.conf import settings

logger = logging.getLogger(__name__)

_MAX_LINES = 10
_MAX_CODE_CHARS = 5000   # keep prompts tiny for speed + cost
_MAX_TOKENS = 500       # ~10 lines of output

# Cheapest model per provider
_CHEAP_MODELS = {
    'openai':    'gpt-4o-mini',
    'anthropic': 'claude-haiku-4-5-20251001',
    'google':    'gemini-3.1-flash-lite-preview',
}


def _get_provider() -> str | None:
    if getattr(settings, 'OPENAI_API_KEY', ''):
        return 'openai'
    if getattr(settings, 'ANTHROPIC_API_KEY', ''):
        return 'anthropic'
    if getattr(settings, 'GOOGLE_API_KEY', ''):
        return 'google'
    return None


def _enforce_limit(text: str) -> str:
    """Hard-cap the description to _MAX_LINES lines."""
    if not text:
        return ''
    lines = text.strip().splitlines()
    return '\n'.join(lines[:_MAX_LINES]).strip()


def _call_llm(provider: str, prompt: str) -> str:
    try:
        if provider == 'openai':
            from openai import OpenAI
            client = OpenAI(api_key=settings.OPENAI_API_KEY)
            resp = client.chat.completions.create(
                model=_CHEAP_MODELS['openai'],
                messages=[{'role': 'user', 'content': prompt}],
                max_tokens=_MAX_TOKENS,
                temperature=0.2,
            )
            return resp.choices[0].message.content or ''

        if provider == 'anthropic':
            import anthropic
            client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
            resp = client.messages.create(
                model=_CHEAP_MODELS['anthropic'],
                max_tokens=_MAX_TOKENS,
                messages=[{'role': 'user', 'content': prompt}],
            )
            return resp.content[0].text if resp.content else ''

        if provider == 'google':
            from google import genai
            from google.genai import types
            client = genai.Client(api_key=settings.GOOGLE_API_KEY)
            resp = client.models.generate_content(
                model=_CHEAP_MODELS['google'],
                contents=prompt,
                config=types.GenerateContentConfig(
                    max_output_tokens=_MAX_TOKENS,
                    temperature=0.2,
                ),
            )
            return resp.text or ''

    except Exception as e:
        logger.warning(f"[DescriptionService] LLM call failed ({provider}): {e}")
    return ''


def _build_prompt(entity_type: str, name: str, file_path: str,
                  code: str = '', docstring: str = '', extra: str = '') -> str:
    parts = [
        f"Describe this {entity_type} in plain English. "
        f"Maximum {_MAX_LINES} lines. Focus on purpose and behavior — not implementation details. "
        f"Output only the description, no labels or headers.\n",
        f"{entity_type.capitalize()}: {name}",
        f"File: {file_path}",
    ]
    if extra:
        parts.append(extra)
    if docstring:
        parts.append(f"Docstring: {docstring[:300]}")
    if code:
        parts.append(f"Code snippet:\n{code[:_MAX_CODE_CHARS]}")
    return '\n'.join(parts)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_description(
    entity_type: str,
    name: str,
    file_path: str,
    code: str = '',
    docstring: str = '',
    extra: str = '',
) -> str:
    """
    Generate a ≤10-line plain-English description for a single code entity.
    Returns empty string if no LLM provider is configured or the call fails.
    """
    provider = _get_provider()
    if not provider:
        return docstring or ''

    prompt = _build_prompt(entity_type, name, file_path, code, docstring, extra)
    raw = _call_llm(provider, prompt)
    return _enforce_limit(raw)


def enrich_parsed_file(parsed_file, file_path: str) -> None:
    """
    Generate AI descriptions for every entity in a ParsedFile, in-place.
    Skips entities whose description is already set.

    Batches all entities for a single file together so callers can
    short-circuit early if no LLM provider is available.
    """
    provider = _get_provider()
    if not provider:
        # No LLM — fall back to docstring as description
        for func in parsed_file.functions:
            if not func.description:
                func.description = func.docstring or ''
        for cls in parsed_file.classes:
            if not cls.description:
                cls.description = cls.docstring or ''
        for ep in parsed_file.endpoints:
            if not ep.description:
                ep.description = ''
        return

    # Functions
    for func in parsed_file.functions:
        if func.description:
            continue
        extra = ''
        if func.parent_class:
            extra = f"Method of class: {func.parent_class}"
        if func.decorators:
            extra += f"\nDecorators: {', '.join(func.decorators)}"
        func.description = generate_description(
            entity_type='function',
            name=func.name,
            file_path=file_path,
            code=func.code,
            docstring=func.docstring or '',
            extra=extra,
        )

    # Classes
    for cls in parsed_file.classes:
        if cls.description:
            continue
        extra = ''
        if cls.bases:
            extra = f"Inherits from: {', '.join(cls.bases)}"
        if cls.is_django_model and cls.fields:
            field_names = [f['name'] for f in cls.fields[:10]]
            extra += f"\nDjango model fields: {', '.join(field_names)}"
        cls.description = generate_description(
            entity_type='class',
            name=cls.name,
            file_path=file_path,
            code=cls.code,
            docstring=cls.docstring or '',
            extra=extra,
        )

    # Endpoints
    for ep in parsed_file.endpoints:
        if ep.description:
            continue
        extra = f"View: {ep.view_name}"
        if ep.http_methods:
            extra += f"\nHTTP methods: {', '.join(ep.http_methods)}"
        ep.description = generate_description(
            entity_type='API endpoint',
            name=ep.url_pattern,
            file_path=file_path,
            extra=extra,
        )


def generate_file_description(
    file_path: str,
    functions: list,
    classes: list,
    endpoints: list,
    raw_content: str = '',
) -> str:
    """
    Generate a ≤10-line plain-English description for an entire source file.
    Summarises the file's purpose based on its entities.
    Returns empty string if no LLM provider is configured or the call fails.
    """
    provider = _get_provider()
    if not provider:
        return ''

    fn_names = [f.name for f in functions[:10]]
    cls_names = [c.name for c in classes[:10]]
    ep_patterns = [e.url_pattern for e in endpoints[:10]]

    parts = [
        f"Describe this file in plain English. "
        f"Maximum {_MAX_LINES} lines. Focus on the file's overall purpose and responsibility. "
        f"Output only the description, no labels or headers.\n",
        f"File: {file_path}",
    ]
    if cls_names:
        parts.append(f"Classes defined: {', '.join(cls_names)}")
    if fn_names:
        parts.append(f"Functions defined: {', '.join(fn_names)}")
    if ep_patterns:
        parts.append(f"API endpoints: {', '.join(ep_patterns)}")
    # For content-only files (markdown, etc.) use the raw text as context
    if raw_content and not fn_names and not cls_names and not ep_patterns:
        parts.append(f"Content preview:\n{raw_content[:_MAX_CODE_CHARS]}")

    prompt = '\n'.join(parts)
    raw = _call_llm(provider, prompt)
    return _enforce_limit(raw)
