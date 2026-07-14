"""Deterministic extractive summaries for OCR document text."""

from __future__ import annotations

import math
import re
from collections import Counter


NO_SUMMARY_MESSAGE = "No summary available right now for document."

_STOP_WORDS = {
    "a", "an", "and", "are", "as", "at", "be", "been", "before", "by",
    "can", "for", "from", "had", "has", "have", "he", "her", "his", "i",
    "in", "into", "is", "it", "its", "of", "on", "or", "our", "she",
    "that", "the", "their", "them", "there", "they", "this", "to", "was",
    "were", "will", "with", "you", "your",
}
_WORD_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9'/-]*")
_TERMINAL_PATTERN = re.compile(r"[.!?][\"')\]]*$")
_REPEATED_NOISE = re.compile(r"([:._-])\1{3,}")


def _clean_lines(text: str) -> list[str]:
    lines = []
    for raw_line in text.replace("\r", "\n").split("\n"):
        line = " ".join(raw_line.strip().split())
        if not line or _REPEATED_NOISE.search(line):
            continue
        alphanumeric = sum(character.isalnum() for character in line)
        if alphanumeric < 2 or alphanumeric / max(1, len(line)) < 0.35:
            continue
        lines.append(line)
    return lines


def _has_colon_value(line: str) -> bool:
    if ":" not in line:
        return False
    _, value = line.split(":", 1)
    return bool(_WORD_PATTERN.search(value))


def _semantic_units(text: str) -> list[str]:
    """Join OCR line wraps while retaining headings and labelled fields."""
    lines = _clean_lines(text)
    units: list[str] = []
    current = ""
    for line in lines:
        is_field = _has_colon_value(line)
        is_heading = line.endswith(":") and not is_field
        if is_field:
            if current:
                units.append(current)
                current = ""
            units.append(line)
            continue
        if is_heading:
            if current:
                units.append(current)
            current = line
            continue
        current = f"{current} {line}".strip() if current else line
        if _TERMINAL_PATTERN.search(line):
            units.append(current)
            current = ""
    if current:
        units.append(current)

    # A long OCR row may contain multiple ordinary sentences.
    expanded: list[str] = []
    for unit in units:
        pieces = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9])", unit)
        expanded.extend(piece.strip() for piece in pieces if piece.strip())
    return expanded


def _content_words(unit: str) -> list[str]:
    return [
        word.lower()
        for word in _WORD_PATTERN.findall(unit)
        if len(word) > 1 and word.lower() not in _STOP_WORDS
    ]


def summarize_document(text: str | None) -> str:
    """Return up to five source-faithful summary lines.

    Large documents produce four or five extractive lines. Short documents use
    one to three lines. Since complete source units are selected, the summary
    cannot invent facts that were not present in OCR output.
    """
    if not text or not text.strip():
        return ""
    units = _semantic_units(text)
    if not units:
        return ""

    total_words = sum(len(_WORD_PATTERN.findall(unit)) for unit in units)
    if total_words >= 120 or len(units) >= 10:
        target_lines = 5
    elif total_words >= 45 or len(units) >= 6:
        target_lines = 4
    elif total_words >= 25:
        target_lines = min(4, len(units))
    else:
        target_lines = min(3, len(units))
    if len(units) <= target_lines:
        return "\n".join(units)

    document_frequency = Counter()
    unit_words = []
    for unit in units:
        words = _content_words(unit)
        unit_words.append(words)
        document_frequency.update(set(words))
    term_frequency = Counter(word for words in unit_words for word in words)

    scores = []
    for index, words in enumerate(unit_words):
        if not words:
            scores.append((0.0, index))
            continue
        score = 0.0
        for word in words:
            inverse_document_frequency = math.log(
                (1 + len(units)) / (1 + document_frequency[word])
            ) + 1.0
            score += term_frequency[word] * inverse_document_frequency
        score /= math.sqrt(len(words))
        # Preserve some document framing without letting position dominate.
        if index == 0:
            score *= 1.12
        elif index == 1:
            score *= 1.05
        scores.append((score, index))

    selected = sorted(
        index
        for _, index in sorted(scores, reverse=True)[:target_lines]
    )
    return "\n".join(units[index] for index in selected)

