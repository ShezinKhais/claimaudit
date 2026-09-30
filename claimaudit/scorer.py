"""Score each claim based on how many citations confirm vs challenge it.

The score is the balance of confirming against challenging citations, mapped
onto 0-10 so that an even split sits at 5, plus a bounded bonus for citations
that extend the work. See compute_survival for the exact treatment of neutral
and extending citations.

Verdict bands (the thresholds live in _VERDICT_THRESHOLDS):
  8.0-10  : confirmed
  6.0-8.0 : well-supported
  4.5-6.0 : mixed
  3.0-4.5 : contested
  0-3.0   : challenged

A claim with fewer than min_citations citations scores 5.0 and is reported as
"insufficient data" rather than being placed in a band.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ClaimSurvival:
    claim_text: str
    confirms: int
    challenges: int
    extends: int
    neutral: int
    total: int
    score: float      # 0-10
    verdict: str      # one of _VERDICT_THRESHOLDS' labels, or "insufficient data"


_WEIGHTS = {"confirms": 2.0, "extends": 0.5, "challenges": -2.0, "neutral": 0.0}
# Most a claim can gain from extending citations alone, on the 0-10 scale.
_EXTEND_BONUS = 1.0
_VERDICT_THRESHOLDS = [
    (8.0, "confirmed"),
    (6.0, "well-supported"),
    (4.5, "mixed"),
    (3.0, "contested"),
    (0.0, "challenged"),
]


def compute_survival(
    claim_text: str,
    label_counts: dict[str, int],
    min_citations: int = 5,
) -> ClaimSurvival:
    """Compute survival score for one claim."""
    confirms   = label_counts.get("confirms", 0)
    challenges = label_counts.get("challenges", 0)
    extends    = label_counts.get("extends", 0)
    neutral    = label_counts.get("neutral", 0)
    total      = confirms + challenges + extends + neutral

    if total < min_citations:
        return ClaimSurvival(
            claim_text=claim_text,
            confirms=confirms, challenges=challenges,
            extends=extends, neutral=neutral, total=total,
            score=5.0,
            verdict="insufficient data",
        )

    # The core score is the balance of citations that take a position for or
    # against the claim, with neutral citations pulling it toward the midpoint.
    # Extending citations are excluded from this ratio: they carry less weight
    # than a direct confirmation, so including them in the denominator at full
    # cost made a positively weighted signal lower the score.
    positional  = confirms + challenges + neutral
    if positional == 0:
        normalised = 5.0
    else:
        raw        = _WEIGHTS["confirms"] * confirms + _WEIGHTS["challenges"] * challenges
        # shift so equal confirms/challenges gives a score of 5
        normalised = (raw / (positional * 2.0) + 0.5) * 10

    # Extending work corroborates a claim without directly testing it, so it
    # contributes a bounded bonus that can never reduce the score.
    if total:
        normalised += _EXTEND_BONUS * (extends / total)

    score = max(0.0, min(10.0, normalised))

    verdict = "challenged"
    for threshold, label in _VERDICT_THRESHOLDS:
        if score >= threshold:
            verdict = label
            break

    return ClaimSurvival(
        claim_text=claim_text,
        confirms=confirms, challenges=challenges,
        extends=extends, neutral=neutral, total=total,
        score=round(score, 1),
        verdict=verdict,
    )
