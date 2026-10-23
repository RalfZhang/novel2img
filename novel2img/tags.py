"""Clean up the Danbooru-style tag prompts written by the LLM.

Small models often squash a whole sentence into one "tag" ("her_hair_is_long_and_silver").
Such tags are split at connecting words, and pieces that are still too long are dropped.
"""
from __future__ import annotations

import re

MAX_TAG_WORDS = 4

# Words that give away a sentence squashed into a tag, even a short one.
_SENTENCE_WORDS = frozenset(
    "her his their them with that which is are was were be been the an and or but while when "
    "between extremely very".split()
)
# Where squashed sentences are split (connecting words plus prepositions).
_SPLIT_RE = re.compile(
    r"\b(?:and|or|with|of|that|which|her|his|their|them|from|on|in|to|while|when|between|"
    r"because|as|but|is|are|was|were|the|an|extremely|very)\b"
)
# Filler words removed from the pieces after splitting.
_FILLER_WORDS = _SENTENCE_WORDS | {"a", "to", "from", "on", "in"}


def split_tags(prompt: str) -> list[str]:
    """Split a comma-separated prompt into stripped, non-empty tags."""
    return [tag.strip() for tag in prompt.split(",") if tag.strip()]


def sanitize_tag(tag: str) -> list[str]:
    """Normalize one tag to lower-case words separated by single spaces.

    A tag that reads like a sentence is split into short tags, and pieces longer than
    ``MAX_TAG_WORDS`` words are dropped. Returns zero or more tags.
    """
    words = [w for w in re.split(r"[\s_\-]+", tag.strip().strip(",;。.").lower()) if w]
    # Short tags without sentence words pass unchanged ("from above", "on bed", …).
    if len(words) <= MAX_TAG_WORDS and not any(w in _SENTENCE_WORDS for w in words):
        return [" ".join(words)] if words else []
    tags = []
    for piece in _SPLIT_RE.split(" ".join(words)):
        piece_words = [w for w in piece.split() if w not in _FILLER_WORDS]
        if 1 <= len(piece_words) <= MAX_TAG_WORDS:
            tags.append(" ".join(piece_words))
    return tags


def sanitize_prompt(prompt: str) -> str:
    """Sanitize every tag of a comma-separated prompt and drop duplicates, keeping the order."""
    seen = set()
    result = []
    for raw in split_tags(prompt):
        for tag in sanitize_tag(raw):
            if tag not in seen:
                seen.add(tag)
                result.append(tag)
    return ", ".join(result)
