"""Match extracted claims to citation contexts and classify the relationship."""

from __future__ import annotations

import re
from dataclasses import dataclass

from claimaudit.scholar import CitationContext


# Each verb stem accepts its inflected forms; matching only the bare stem
# would miss the way citations are actually written ("contradicts", "supported").
_CONFIRM_PATTERNS = re.compile(
    r'\b(confirm(s|ed|ing)?|support(s|ed|ing)?|consistent with|agree(s|d|ing)?|'
    r'validat(e|es|ed|ing)|replicat(e|es|ed|ing)|'
    r'in line with|corroborat(e|es|ed|ing)|consistent|verif(y|ies|ied))\b',
    re.I
)
_CHALLENGE_PATTERNS = re.compile(
    r'\b(contradict(s|ed|ing)?|challeng(e|es|ed|ing)|disput(e|es|ed|ing)|'
    r'refut(e|es|ed|ing)|contrary|inconsistent|fails? to replicate|'
    r'not (support(s|ed)?|consistent|replicat(e|ed))|'
    # "question" only in its verb sense, which a following "the" or "whether"
    # marks. The bare stem also matched the noun, which is ordinary neutral
    # prose in a citation ("resolves a longstanding question", "addresses the
    # question of scale"), and because challenges take precedence over confirms
    # it turned citations that plainly agreed into challenges.
    r'question(s|ed|ing)? (the|whether)|call(s|ed)? into question|'
    r'undermin(e|es|ed|ing)|conflict(s|ed|ing)?)\b',
    re.I
)
_EXTEND_PATTERNS = re.compile(
    r'\b(build(s|ing)? on|extend(s|ed|ing)?|generaliz(e|es|ed|ing)|'
    r'appl(y|ies|ied) to|expand(s|ed|ing)?|further|beyond|improv(e|es|ed|ing) upon)\b',
    re.I
)


@dataclass
class MatchResult:
    citation: CitationContext
    relation: str    # "confirms" | "challenges" | "extends" | "neutral"
    confidence: float


def classify_citation(ctx: CitationContext) -> MatchResult:
    """
    Classify how a citing paper relates to the source claim.

    The citation context text is authoritative when present, because it states
    whether the citing work agreed or disagreed. Semantic Scholar's structured
    intents (result, methodology, background) describe where a paper is cited,
    not the stance: a paper that refutes a claim in its results section still
    carries a "result" intent. Intents are therefore only a fallback for when
    no context text is available.
    """
    text = ctx.context_text
    if text:
        challenge_m = _CHALLENGE_PATTERNS.search(text)
        confirm_m   = _CONFIRM_PATTERNS.search(text)
        extend_m    = _EXTEND_PATTERNS.search(text)

        # A sentence may contain both a confirming stem and a negation of it
        # ("could not replicate", "do not support"). The explicit challenge
        # lexicon (contradict, refute, dispute, inconsistent) is the stronger
        # signal, so challenges take precedence when both fire.
        if challenge_m:
            return MatchResult(ctx, "challenges", 0.75)
        if confirm_m:
            return MatchResult(ctx, "confirms", 0.75)
        if extend_m:
            return MatchResult(ctx, "extends", 0.65)
        return MatchResult(ctx, "neutral", 0.5)

    # No context text: fall back to the structured intent.
    intents = [i.lower() for i in ctx.intents]
    if "result" in intents or "methodology" in intents:
        if ctx.is_influential:
            return MatchResult(ctx, "confirms", 0.8)
        return MatchResult(ctx, "extends", 0.65)
    return MatchResult(ctx, "neutral", 0.5)


def match_citations(citations: list[CitationContext]) -> list[MatchResult]:
    """Classify all citations for a paper."""
    return [classify_citation(c) for c in citations]


def aggregate_labels(results: list[MatchResult]) -> dict[str, int]:
    """Count each relation label across all citation matches."""
    counts: dict[str, int] = {"confirms": 0, "challenges": 0, "extends": 0, "neutral": 0}
    for r in results:
        counts[r.relation] = counts.get(r.relation, 0) + 1
    return counts
