"""Generate text, JSON, and HTML reports from audit results."""

from __future__ import annotations

import json
from html import escape as _escape
from pathlib import Path

from claimaudit.classifier import AuditResult


_VERDICT_COLORS = {
    "confirmed":        "#4CAF50",
    "well-supported":   "#8BC34A",
    "mixed":            "#FFC107",
    "contested":        "#FF9800",
    "challenged":       "#F44336",
    "insufficient data":"#9E9E9E",
}

_CSS = """
body { background:#0d0d0d; color:#e0e0e0; font-family:sans-serif; padding:2rem; }
h1   { color:#fff; }
.claim-card { border:1px solid #333; border-radius:8px; padding:1.2rem;
              margin:1rem 0; background:#1a1a1a; }
.verdict-badge { display:inline-block; padding:.2rem .7rem; border-radius:12px;
                 color:#000; font-weight:bold; font-size:.85rem; }
.score-bar { height:8px; border-radius:4px; background:#333; margin:.5rem 0; }
.score-fill { height:100%; border-radius:4px; background:#4f8ef7; }
.meta { font-size:.8rem; color:#888; margin-top:.5rem; }
"""


def _verdict_badge(verdict: str) -> str:
    color = _VERDICT_COLORS.get(verdict, "#9E9E9E")
    return f'<span class="verdict-badge" style="background:{color}">{verdict}</span>'


def render_html(results: list[AuditResult], title: str = "ClaimAudit Report",
                output_path: Path = None) -> str:
    """Build a self-contained HTML report.

    Titles, claim text and author names come from the Semantic Scholar API, so
    they are escaped rather than interpolated raw: an abstract containing markup
    would otherwise be parsed as part of the page.
    """
    title = _escape(title)
    cards = []
    for r in results:
        pct  = int(r.survival.score * 10)
        auth = ", ".join(a.name for a in r.paper.authors[:3])
        if len(r.paper.authors) > 3:
            auth += " et al."
        card = f"""
<div class="claim-card">
  <h3>{_escape(r.paper.title)}</h3>
  <p style="font-style:italic">"{_escape(r.survival.claim_text)}"</p>
  {_verdict_badge(r.survival.verdict)}
  <strong style="margin-left:.5rem">{r.survival.score}/10</strong>
  <div class="score-bar"><div class="score-fill" style="width:{pct}%"></div></div>
  <div class="meta">
    {_escape(auth)} | {r.paper.year or "n/a"} |
    Confirms: {r.survival.confirms} |
    Challenges: {r.survival.challenges} |
    Extends: {r.survival.extends} |
    Citations fetched: {r.n_citations_fetched}
  </div>
</div>"""
        cards.append(card)

    html = f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"><title>{title}</title>
<style>{_CSS}</style></head><body>
<h1>{title}</h1>
<p>{len(results)} claims audited</p>
{''.join(cards)}
</body></html>"""

    if output_path:
        Path(output_path).write_text(html, encoding="utf-8")
    return html


def render_text(results: list[AuditResult]) -> str:
    """Plain-text summary of audit results."""
    lines = [f"ClaimAudit - {len(results)} results\n" + "=" * 40]
    for r in results:
        s = r.survival
        lines.append(
            f"\n[{s.verdict.upper()}] {s.score}/10\n"
            f"  Paper : {r.paper.title[:80]}\n"
            f"  Claim : {s.claim_text[:120]}\n"
            f"  Counts: confirms={s.confirms} challenges={s.challenges} "
            f"extends={s.extends} neutral={s.neutral}"
        )
    return "\n".join(lines)


def render_json(results: list[AuditResult]) -> str:
    """Serialise results to JSON string."""
    out = []
    for r in results:
        out.append({
            "paper_id":    r.paper.paper_id,
            "title":       r.paper.title,
            "year":        r.paper.year,
            "claim":       r.survival.claim_text,
            "score":       r.survival.score,
            "verdict":     r.survival.verdict,
            "confirms":    r.survival.confirms,
            "challenges":  r.survival.challenges,
            "extends":     r.survival.extends,
            "neutral":     r.survival.neutral,
            "total":       r.survival.total,
            "n_citations": r.n_citations_fetched,
        })
    return json.dumps(out, indent=2)
