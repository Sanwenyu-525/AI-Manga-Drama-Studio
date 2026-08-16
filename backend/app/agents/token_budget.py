"""TokenBudget (P7-T006): character budget with truncation strategy.

ContextResolver must never exceed a fixed size before an LLM call. This module
enforces a character budget (tokens are estimated; char-per-token ~1 for CJK)
with a head/tail retention strategy: the most relevant prefix and suffix are kept,
the middle elided with a marker.
"""

from __future__ import annotations

# Rough budget defaults (characters). A conservative 4096-token prompt with ~1 char/token.
DEFAULT_PROMPT_BUDGET_CHARS = 4096
HEAD_KEEP_RATIO = 0.5
TAIL_KEEP_RATIO = 0.5
ELISION_MARKER = "...[truncated]..."


class TokenBudget:
    """Character-based budget guard used by ContextResolver (P7-T006)."""

    def __init__(self, max_chars: int = DEFAULT_PROMPT_BUDGET_CHARS) -> None:
        self.max_chars = max_chars

    def truncate(self, text: str) -> str:
        """Truncate a single text block to the full budget (head + tail retention)."""
        return truncate_text(text, self.max_chars)

    def fit(self, parts: list[str]) -> list[str]:
        """Best-effort pack many parts under the budget: keep head parts whole,
        elide tail parts beyond the cap; each part itself is truncated at need."""
        budget = self.max_chars
        out: list[str] = []
        for i, part in enumerate(parts):
            if not part:
                out.append("")
                continue
            if i > 0 and budget <= 0:
                out.append(ELISION_MARKER)
                continue
            budget_for_part = max(1, min(budget, budget))
            trimmed = truncate_text(part, min(budget_for_part, len(part)))
            out.append(trimmed)
            budget -= len(trimmed)
        return out


def truncate_text(text: str, max_chars: int) -> str:
    """Keep the head + tail of a block, eliding the middle (P7-T006).

    The result (head + marker + tail) never exceeds max_chars: the marker length is
    subtracted from the split so the total stays within budget.
    """
    if len(text) <= max_chars:
        return text
    avail = max_chars - len(ELISION_MARKER)
    if avail <= 0:
        return text[:max_chars]
    head = int(avail * HEAD_KEEP_RATIO)
    tail = avail - head
    return text[:head] + ELISION_MARKER + text[-tail:]
