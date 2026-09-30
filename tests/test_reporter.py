"""Tests for the HTML report, which nothing else covers (no network required)."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

from claimaudit.classifier import AuditResult
from claimaudit.extractor import ClaimSentence
from claimaudit.reporter import _bar_scale, render_html, render_json, render_text
from claimaudit.scholar import Author, Paper
from claimaudit.scorer import compute_survival


def _result(counts, fetched, title="A paper", claim="We show that X holds.",
            min_citations=5):
    paper = Paper(paper_id=title, title=title, abstract="", year=2020,
                  authors=[Author("A. Author")])
    return AuditResult(
        paper=paper,
        claim=ClaimSentence(text=claim, signal="we show", confidence=0.7),
        survival=compute_survival(claim, counts, min_citations),
        n_citations_fetched=fetched,
    )


CONTESTED = {"confirms": 3, "challenges": 9, "extends": 1, "neutral": 2}
SUPPORTED = {"confirms": 7, "challenges": 1, "extends": 0, "neutral": 1}


class TestRenderHtml:
    def test_document_is_self_contained(self):
        html = render_html([_result(SUPPORTED, 9)])
        assert html.startswith("<!DOCTYPE html>")
        # A report that reaches the network is not a single portable file.
        for remote in ("http://", "https://", "<script", "<img", "@import"):
            assert remote not in html

    def test_no_hex_outside_the_token_blocks(self):
        html = render_html([_result(SUPPORTED, 9)])
        css   = html.split("<style>")[1].split("</style>")[0]
        # Everything after the last token block must name variables, not colours.
        tail  = css.split(":root[data-theme=\"dark\"]")[1].split("}", 1)[1]
        assert "#" not in tail

    def test_diverging_bar_replaces_the_progress_bar(self):
        html = render_html([_result(CONTESTED, 15)])
        assert "seg-challenge" in html and "seg-confirm" in html
        assert "score-fill" not in html and "verdict-badge" not in html

    def test_bars_share_one_scale_across_the_report(self):
        results = [_result(CONTESTED, 15, title="A"), _result(SUPPORTED, 9, title="B")]
        # 9 challenges is the widest single side anywhere in the report.
        assert _bar_scale(results) == 9
        html = render_html(results)
        # The widest side reaches exactly half the bar, and the axis says so.
        assert "width:50.0000%" in html
        assert "9 challenging" in html and "9 confirming" in html

    def test_counts_are_named_in_words_as_well_as_ink(self):
        html = render_html([_result(CONTESTED, 15)])
        assert "9 challenging, 3 confirming, 1 extending and 2 neutral" in html

    def test_unscored_claim_gets_no_score_mark(self):
        """The scorer's placeholder 5.0 must not be drawn as a measured value."""
        html = render_html([_result({"confirms": 1, "challenges": 1}, 2)])
        assert "not scored" in html
        assert 'class="tick"' not in html
        assert "5.0" not in html

    def test_claim_with_no_citations_says_so(self):
        html = render_html([_result({}, 0)])
        assert "No citing paper was returned" in html

    def test_empty_report_says_what_was_looked_for(self):
        html = render_html([], topic="graphene batteries")
        assert "No auditable claim was found" in html
        assert "graphene batteries" in html
        assert "claim" in html

    def test_markup_in_content_is_escaped(self):
        html = render_html([_result(SUPPORTED, 9, title="<b>Title</b>",
                                    claim='We show that "a" < "b".')])
        assert "<b>Title</b>" not in html
        assert "&lt;b&gt;Title&lt;/b&gt;" in html

    def test_most_disputed_claim_leads(self):
        results = [_result(SUPPORTED, 9, title="Supported"),
                   _result(CONTESTED, 15, title="Contested")]
        html = render_html(results)
        assert html.index("Contested") < html.index("Supported")

    def test_demo_run_is_labelled_as_sample_data(self):
        html = render_html([_result(SUPPORTED, 9)], demo=True)
        assert "Demo mode" in html

    def test_writes_the_file(self, tmp_path):
        out = tmp_path / "report.html"
        html = render_html([_result(SUPPORTED, 9)], output_path=out)
        assert out.read_text(encoding="utf-8") == html


class TestOtherRenderersUnchanged:
    def test_text_report_shape(self):
        text = render_text([_result(CONTESTED, 15)])
        assert "ClaimAudit - 1 results" in text
        assert "confirms=3 challenges=9 extends=1 neutral=2" in text

    def test_json_report_keys(self):
        import json
        rows = json.loads(render_json([_result(CONTESTED, 15)]))
        assert rows[0]["challenges"] == 9
        assert rows[0]["n_citations"] == 15
        assert set(rows[0]) == {
            "paper_id", "title", "year", "claim", "score", "verdict",
            "confirms", "challenges", "extends", "neutral", "total",
            "n_citations",
        }
