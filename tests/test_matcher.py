"""Tests for citation stance classification and HTML reporting."""

from html import escape

import pytest

from claimaudit.scholar import CitationContext, Paper, Author
from claimaudit.matcher import classify_citation, aggregate_labels, match_citations
from claimaudit.scorer import compute_survival
from claimaudit.classifier import AuditResult
from claimaudit.extractor import ClaimSentence
from claimaudit.reporter import render_html


def _ctx(text="", intents=(), influential=False):
    return CitationContext(
        paper_id="p1", title="Citing paper", year=2021,
        intents=list(intents), is_influential=influential, context_text=text,
    )


def _relation(text, **kw):
    return classify_citation(_ctx(text, **kw)).relation


class TestQuestionIsNotAlwaysAChallenge:
    """"question" as a noun is ordinary neutral prose in a citation.

    The bare stem used to match it, and because challenges take precedence over
    confirms, a citation that plainly agreed was recorded as challenging.
    """

    def test_resolving_a_question_while_confirming_is_a_confirmation(self):
        assert _relation(
            "This work confirms the earlier finding and resolves a "
            "longstanding question in the field."
        ) == "confirms"

    def test_addressing_a_question_is_not_a_challenge(self):
        assert _relation("The study addresses the question of scale.") == "neutral"

    def test_research_question_phrasing_is_not_a_challenge(self):
        assert _relation("Our research question follows from this.") == "neutral"

    def test_open_question_phrasing_is_not_a_challenge(self):
        assert _relation("It remains an open question in the field.") == "neutral"

    @pytest.mark.parametrize("text", [
        "Later work questions the validity of this result.",
        "Recent work questions the result reported here.",
        "They question whether the effect is real.",
        "Subsequent work questioned the assumption.",
        "A follow-up study is questioning the mechanism.",
        "These findings call into question the original claim.",
    ])
    def test_the_verb_sense_is_still_a_challenge(self, text):
        assert _relation(text) == "challenges"


class TestStanceLexicons:
    def test_plain_confirmation(self):
        assert _relation("Our results confirm the original finding.") == "confirms"

    def test_plain_challenge(self):
        assert _relation("These data contradict the original finding.") == "challenges"

    def test_challenge_wins_when_both_lexicons_fire(self):
        assert _relation("We could not replicate or support this result.") == "challenges"

    def test_inconsistent_does_not_read_as_consistent(self):
        assert _relation("The results are inconsistent with the claim.") == "challenges"

    def test_extension(self):
        assert _relation("We build on this approach and extend it.") == "extends"

    def test_no_signal_is_neutral(self):
        assert _relation("The method was introduced in prior work.") == "neutral"

    def test_intents_are_the_fallback_when_there_is_no_context(self):
        assert _relation("", intents=["result"], influential=True) == "confirms"
        assert _relation("", intents=["result"]) == "extends"
        assert _relation("", intents=["background"]) == "neutral"


class TestAggregate:
    def test_counts_every_label(self):
        counts = aggregate_labels(match_citations([
            _ctx("this confirms the finding"),
            _ctx("this contradicts the finding"),
            _ctx("we build on this work"),
            _ctx("the method was described here"),
        ]))
        assert counts == {"confirms": 1, "challenges": 1, "extends": 1, "neutral": 1}


class TestVerdictBands:
    """The bands the module docstring advertises must be the ones it applies."""

    @pytest.mark.parametrize("confirms,challenges,expected", [
        (10, 0, "confirmed"),
        (0, 10, "challenged"),
        (5, 5, "mixed"),
    ])
    def test_bands(self, confirms, challenges, expected):
        counts = {"confirms": confirms, "challenges": challenges,
                  "extends": 0, "neutral": 0}
        assert compute_survival("a claim", counts, min_citations=5).verdict == expected

    def test_too_few_citations_is_insufficient_data(self):
        counts = {"confirms": 1, "challenges": 0, "extends": 0, "neutral": 0}
        result = compute_survival("a claim", counts, min_citations=5)
        assert result.verdict == "insufficient data"
        assert result.score == 5.0


class TestHtmlEscaping:
    """Titles and abstracts come from the API and must not become markup."""

    def _result(self, title, claim, author):
        paper = Paper(paper_id="p", title=title, abstract="", year=2020,
                      authors=[Author(name=author)], citation_count=5)
        counts = {"confirms": 5, "challenges": 0, "extends": 0, "neutral": 0}
        return AuditResult(
            paper=paper,
            claim=ClaimSentence(text=claim, signal="we show", confidence=0.7),
            survival=compute_survival(claim, counts, min_citations=1),
            n_citations_fetched=5,
        )

    def test_markup_in_api_text_is_escaped(self):
        page = render_html([self._result(
            "<script>alert(1)</script> A Study",
            "<img src=x onerror=alert(2)>",
            "Smith & Jones",
        )])
        assert "<script>alert(1)</script>" not in page
        assert "<img src=x onerror=alert(2)>" not in page
        assert escape("<script>alert(1)</script> A Study") in page

    def test_report_title_is_escaped(self):
        page = render_html([], title="<script>alert(3)</script>")
        assert "<script>alert(3)</script>" not in page

    def test_ordinary_text_still_renders(self):
        page = render_html([self._result("A Study", "We show that X.", "Smith J")])
        assert "A Study" in page
        assert "We show that X." in page
