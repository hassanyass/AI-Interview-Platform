"""Bounds for user/profile text included in live LLM prompts."""

MAX_JOB_DESCRIPTION_CHARS = 6000
MAX_PROFILE_CHARS = 6000
MAX_HISTORY_CHARS = 8000
MAX_MESSAGE_CHARS = 1600


def truncate_prompt_text(value: str | None, limit: int) -> str:
    """Keep prompt inputs bounded without changing the stored interview data."""
    if not value:
        return ""
    value = str(value).strip()
    if len(value) <= limit:
        return value
    return value[:limit].rstrip() + "\n[Additional content omitted from this prompt.]"
