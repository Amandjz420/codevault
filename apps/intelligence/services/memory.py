"""
Memory service: generates and updates rolling project summaries using LLM.

Two update triggers:
  1. Query-based  — called after every MEMORY_UPDATE_EVERY queries logged for a project.
                    Reads recent Q&A pairs and synthesises them into an updated summary.
  2. Ingestion-based — called after each ingestion completes.
                       Updates the summary to reflect code changes, preserving prior context.
"""
import logging
from django.conf import settings

logger = logging.getLogger(__name__)

# How many new queries must accumulate before a memory refresh is triggered
MEMORY_UPDATE_EVERY = 5

_SUMMARY_SYSTEM_PROMPT = """\
You are a technical memory assistant for a codebase intelligence system.
Your task is to maintain a concise, structured summary of what has been learned about a
codebase through developer queries and code changes.

The summary will be injected into future query prompts so the AI can answer questions faster
and with richer context. Write for an AI reader, not a human — be dense, precise, and structured.
Omit pleasantries. Use bullet points and short sections. Maximum 600 words."""


# --------------------------------------------------------------------------- #
#  Internal LLM helper                                                         #
# --------------------------------------------------------------------------- #

def _get_provider():
    if getattr(settings, 'OPENAI_API_KEY', None):
        return 'openai'
    if getattr(settings, 'ANTHROPIC_API_KEY', None):
        return 'anthropic'
    if getattr(settings, 'GOOGLE_API_KEY', None):
        return 'google'
    return None


def _call_llm(prompt: str) -> str:
    """Call the cheapest/fastest available LLM to produce a summary."""
    provider = _get_provider()
    if not provider:
        logger.warning('[MemoryService] No LLM provider configured — skipping summary.')
        return ''

    try:
        if provider == 'openai':
            from openai import OpenAI
            client = OpenAI(api_key=settings.OPENAI_API_KEY)
            resp = client.chat.completions.create(
                model='gpt-4o-mini',
                messages=[
                    {'role': 'system', 'content': _SUMMARY_SYSTEM_PROMPT},
                    {'role': 'user', 'content': prompt},
                ],
                max_tokens=900,
            )
            return resp.choices[0].message.content.strip()

        elif provider == 'anthropic':
            import anthropic
            client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
            resp = client.messages.create(
                model='claude-haiku-20240307',
                max_tokens=900,
                system=_SUMMARY_SYSTEM_PROMPT,
                messages=[{'role': 'user', 'content': prompt}],
            )
            return resp.content[0].text.strip()

        elif provider == 'google':
            import google.generativeai as genai
            genai.configure(api_key=settings.GOOGLE_API_KEY)
            m = genai.GenerativeModel(
                'gemini-3.1-flash-lite-preview',
                system_instruction=_SUMMARY_SYSTEM_PROMPT,
            )
            resp = m.generate_content(prompt)
            return resp.text.strip()

    except Exception as exc:
        logger.error(f'[MemoryService] LLM call failed: {exc}')
        return ''


# --------------------------------------------------------------------------- #
#  Public API                                                                  #
# --------------------------------------------------------------------------- #

def update_memory_from_queries(project_id: int) -> None:
    """
    Regenerate the project memory summary from recent Q&A pairs.

    Reads the last 20 QueryLog entries and asks the LLM to produce an updated
    summary, merging any existing memory with new insights.
    """
    from apps.projects.models import Project
    from apps.intelligence.models import QueryLog, ProjectMemory

    project = Project.objects.get(id=project_id)
    memory, _ = ProjectMemory.objects.get_or_create(project=project)

    recent_logs = list(
        QueryLog.objects.filter(project=project)
        .order_by('-created_at')[:20]
    )
    if not recent_logs:
        return

    # Present in chronological order so the LLM sees the conversation arc
    qa_text = '\n\n'.join(
        f'Q: {log.question}\nA: {log.answer[:600]}'
        for log in reversed(recent_logs)
    )

    prompt = '\n'.join([
        f'Project name: {project.name}',
        f'Primary language: {project.language}',
        '',
        '## Existing memory summary',
        memory.summary or '(no previous summary)',
        '',
        '## Recent developer queries and answers (oldest → newest)',
        qa_text,
        '',
        '## Task',
        'Update the memory summary based on the queries above.',
        'Highlight: recurring topics, key components referenced, patterns found, open questions.',
        'Merge new insights with the existing summary; drop outdated or redundant points.',
    ])

    new_summary = _call_llm(prompt)
    if new_summary:
        memory.summary = new_summary
        memory.queries_since_update = 0
        memory.save()
        logger.info(f'[MemoryService] Query-based memory updated for "{project.name}"')


def update_memory_from_ingestion(project_id: int, changed_files: list, stats: dict) -> None:
    """
    Update project memory after a code ingestion completes.

    Incorporates which files changed and ingestion statistics into the existing
    summary so future queries are aware of recent code evolution.
    """
    from apps.projects.models import Project
    from apps.intelligence.models import ProjectMemory

    project = Project.objects.get(id=project_id)
    memory, _ = ProjectMemory.objects.get_or_create(project=project)

    # Nothing to do if there's no memory yet and no files changed
    if not memory.summary and not changed_files:
        return

    files_processed = stats.get('processed', 0)
    files_skipped = stats.get('skipped', 0)
    errors = stats.get('errors', 0)

    file_list = '\n'.join(f'  - {f}' for f in changed_files[:40])
    if len(changed_files) > 40:
        file_list += f'\n  … and {len(changed_files) - 40} more files'
    if not file_list:
        file_list = '  (full re-index — no specific file list available)'

    prompt = '\n'.join([
        f'Project name: {project.name}',
        f'Primary language: {project.language}',
        '',
        '## Current memory summary',
        memory.summary or '(no previous summary)',
        '',
        '## Code ingestion just completed',
        f'  - Files processed (new/changed): {files_processed}',
        f'  - Files skipped (unchanged):     {files_skipped}',
        f'  - Errors:                         {errors}',
        '',
        '## Changed / added files',
        file_list,
        '',
        '## Task',
        'Update the memory summary to reflect these code changes.',
        'Note which areas of the codebase were modified.',
        'Preserve still-relevant context from the previous summary.',
        'Flag any implications the changes may have for open questions from past queries.',
    ])

    new_summary = _call_llm(prompt)
    if new_summary:
        memory.summary = new_summary
        memory.save()
        logger.info(f'[MemoryService] Ingestion-based memory updated for "{project.name}"')
