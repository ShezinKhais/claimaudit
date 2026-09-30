"""Generate text, JSON, and HTML reports from audit results."""

from __future__ import annotations

import json
from datetime import date
from html import escape
from pathlib import Path

from claimaudit.classifier import AuditResult


# The verdict vocabulary is scorer._VERDICT_THRESHOLDS plus the "insufficient
# data" case the scorer returns when too few citations were classified to judge.
# Listed worst-held first, which is also the order claims are shown in.
_VERDICT_ORDER = [
    "challenged",
    "contested",
    "mixed",
    "well-supported",
    "confirmed",
    "insufficient data",
]

# Each verdict draws in one of the semantic inks. "insufficient data" takes the
# quiet ink because it records an absence of evidence, not a measurement.
_VERDICT_STANCE = {
    "challenged":        "challenge",
    "contested":         "challenge",
    "mixed":             "mixed",
    "well-supported":    "confirm",
    "confirmed":         "confirm",
    "insufficient data": "quiet",
}

_UNSCORED = "insufficient data"

_CSS = """
:root {
  --ground:    #EDEFEA;
  --lift:      #F7F8F5;
  --sink:      #E3E6DF;
  --ink:       #191D1C;
  --ink-mid:   #4E5754;
  --ink-soft:  #7C8683;
  --rule:      #CFD4CC;
  --rule-firm: #A8B0AC;
  --mark:      #1D4E63;
  --mark-soft: #7FA3B2;
  --confirm:   #2F6B4F;
  --challenge: #A33B2A;
  --extend:    #8A6A1F;
  --quiet:     #8C9491;
  --measure:   68ch;
  --sans: ui-sans-serif, "Segoe UI Variable Display", "Segoe UI", Inter,
          system-ui, -apple-system, "Helvetica Neue", Arial, sans-serif;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --ground:    #14171A;
    --lift:      #1C2024;
    --sink:      #0F1215;
    --ink:       #E4E8E6;
    --ink-mid:   #A6AEAB;
    --ink-soft:  #7B8582;
    --rule:      #2E343A;
    --rule-firm: #454D53;
    --mark:      #6FB3CE;
    --mark-soft: #3C6478;
    --confirm:   #6FBE93;
    --challenge: #E08472;
    --extend:    #D9B45C;
    --quiet:     #6E7773;
  }
}
:root[data-theme="dark"] {
  --ground:    #14171A;
  --lift:      #1C2024;
  --sink:      #0F1215;
  --ink:       #E4E8E6;
  --ink-mid:   #A6AEAB;
  --ink-soft:  #7B8582;
  --rule:      #2E343A;
  --rule-firm: #454D53;
  --mark:      #6FB3CE;
  --mark-soft: #3C6478;
  --confirm:   #6FBE93;
  --challenge: #E08472;
  --extend:    #D9B45C;
  --quiet:     #6E7773;
}

* { box-sizing: border-box; }
html { -webkit-text-size-adjust: 100%; }

body {
  margin: 0;
  background: var(--ground);
  color: var(--ink);
  font-family: var(--sans);
  font-size: 15px;
  line-height: 1.6;
}
:focus-visible { outline: 2px solid var(--mark); outline-offset: 2px; }

.sheet { max-width: 1000px; margin: 0 auto; padding: 48px 32px 64px; }
p { margin: 0; }

/* header */
.title {
  font-size: 30px; line-height: 1.15; letter-spacing: -0.02em;
  font-weight: 600; margin: 0;
}
.subject { margin-top: 4px; color: var(--ink-mid); }
.lead { max-width: var(--measure); margin-top: 16px; color: var(--ink-mid); }
.notice {
  margin-top: 16px; padding: 12px; background: var(--lift);
  border: 1px solid var(--rule); max-width: var(--measure);
  font-size: 13.5px; line-height: 1.45; color: var(--ink-mid);
}

.summary {
  display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
  margin: 32px 0 0; padding: 0;
  border-top: 2px solid var(--rule-firm); border-bottom: 1px solid var(--rule);
}
/* The figures sit on one line across the row even when a label above them
   wraps, which it does as soon as the grid drops to two columns. */
.summary > div {
  display: flex; flex-direction: column; padding: 12px 16px 12px 0;
}
.summary dt {
  font-size: 12px; line-height: 1.3; font-weight: 500; color: var(--ink-soft);
}
.summary dd {
  margin: 0; padding-top: 8px; margin-top: auto;
  font-size: 22px; line-height: 1.0; font-weight: 550;
  font-variant-numeric: tabular-nums;
}
.summary dd.text { font-size: 15px; line-height: 1.3; font-weight: 500; }

.tally { margin: 24px 0 0; padding: 0; list-style: none; max-width: 420px; }
.tally-head {
  font-size: 12px; line-height: 1.3; font-weight: 500; color: var(--ink-soft);
  margin-bottom: 4px;
}
.tally-row {
  display: flex; align-items: baseline; gap: 8px;
  padding: 8px 0; border-top: 1px solid var(--rule);
  font-size: 13.5px; line-height: 1.45;
}
.tally-row::before {
  content: ""; flex: 0 0 auto; width: 12px; height: 3px;
  background: var(--row-ink); transform: translateY(-4px);
}
.tally .count {
  margin-left: auto; font-variant-numeric: tabular-nums; color: var(--ink-mid);
}

/* sections */
.stratum { margin-top: 48px; }
.stratum h2 {
  font-size: 17px; line-height: 1.3; font-weight: 600; margin: 0 0 8px;
  padding-bottom: 8px; border-bottom: 2px solid var(--rule-firm);
}
.note {
  max-width: var(--measure); font-size: 13.5px; line-height: 1.45;
  color: var(--ink-mid);
}

/* the two axes, drawn once per section */
.scales {
  display: grid; grid-template-columns: 56px 1fr; gap: 0 12px;
  margin: 24px 0 0; padding-left: 15px;
}
.axis-label {
  font-size: 12px; line-height: 1.3; font-weight: 500; color: var(--ink-soft);
}
.rail { position: relative; width: 48px; height: 10px; margin-top: 8px; }
.rail::before {
  content: ""; position: absolute; left: 0; right: 0; bottom: 0;
  height: 1px; background: var(--rule-firm);
}
.rail-ends {
  display: flex; justify-content: space-between; width: 48px;
  font-size: 12px; line-height: 1.3; color: var(--ink-soft);
  font-variant-numeric: tabular-nums;
}
.tick {
  position: absolute; top: 0; bottom: 0; width: 1px;
  background: var(--row-ink, var(--ink)); margin-left: -0.5px;
}

/* The axis and every bar share the prose measure, so the data column ends
   where the claim text ends and the bars stay comparable to the axis. */
.bar-axis { min-width: 0; max-width: var(--measure); }
.domain { position: relative; height: 10px; margin-top: 8px; }
.domain::before {
  content: ""; position: absolute; left: 0; right: 0; bottom: 0;
  height: 1px; background: var(--rule-firm);
}
.domain span {
  position: absolute; bottom: 0; width: 1px; height: 5px;
  background: var(--rule-firm);
}
.domain .d0   { left: 0; }
.domain .dmid { left: 50%; height: 10px; }
.domain .d1   { right: 0; }
.domain-ends {
  position: relative; display: flex; justify-content: space-between;
  font-size: 12px; line-height: 1.3; color: var(--ink-soft);
  font-variant-numeric: tabular-nums;
}
.domain-ends .mid { position: absolute; left: 50%; transform: translateX(-50%); }

.legend {
  list-style: none; margin: 12px 0 0; padding: 0;
  display: flex; flex-wrap: wrap; gap: 4px 16px;
  font-size: 12px; line-height: 1.3; color: var(--ink-mid);
}
.legend li { display: flex; align-items: center; gap: 6px; }
.legend li::before {
  content: ""; flex: 0 0 auto; width: 12px; height: 3px;
  background: var(--row-ink);
}
.legend .k-neutral::before { height: 1px; }
.caption {
  margin-top: 8px; max-width: var(--measure);
  font-size: 12px; line-height: 1.3; color: var(--ink-soft);
}

/* claim rows */
.claims { list-style: none; margin: 24px 0 0; padding: 0; }
.claim {
  display: grid; grid-template-columns: 56px 1fr; gap: 0 12px;
  padding: 12px 0 16px 12px;
  border-top: 1px solid var(--rule);
  border-left: 3px solid var(--row-ink);
}
.claim:last-child { border-bottom: 1px solid var(--rule); }

.gutter { grid-column: 1; }
.score {
  display: block; font-size: 22px; line-height: 1.0; font-weight: 550;
  font-variant-numeric: tabular-nums;
}
.gutter .rail { margin-top: 8px; height: 8px; }

.body { grid-column: 2; min-width: 0; }
.verdict {
  font-size: 12px; line-height: 1.3; font-weight: 500; color: var(--ink-mid);
}
.claim-text { max-width: var(--measure); margin-top: 4px; }
.source {
  max-width: var(--measure); margin-top: 12px;
  font-size: 13.5px; line-height: 1.45; color: var(--ink-mid);
}
.source .year { font-variant-numeric: tabular-nums; }

/* the diverging evidence bar */
.bar { position: relative; margin-top: 16px; max-width: var(--measure); }
.centre {
  position: absolute; top: 0; bottom: 0; left: 50%;
  width: 1px; margin-left: -0.5px; background: var(--rule-firm);
}
.lane { position: relative; }
.lane-stance { height: 12px; }
.lane-aside { height: 5px; margin-top: 4px; }
.seg { position: absolute; top: 0; min-width: 2px; }
.seg-challenge { right: 50%; height: 12px; background: var(--challenge); }
.seg-confirm   { left: 50%;  height: 12px; background: var(--confirm); }
.seg-extend    { left: 50%;  height: 5px;  background: var(--extend); }
.seg-neutral   { top: 2px;   height: 1px;  background: var(--quiet); }
.counts {
  margin-top: 8px; max-width: var(--measure);
  font-size: 13.5px; line-height: 1.45; color: var(--ink-mid);
  font-variant-numeric: tabular-nums;
}
.silent {
  margin-top: 12px; max-width: var(--measure);
  font-size: 13.5px; line-height: 1.45; color: var(--ink-mid);
}

/* footer */
.provenance {
  margin-top: 48px; padding-top: 12px; border-top: 1px solid var(--rule);
  max-width: var(--measure); font-size: 12px; line-height: 1.3;
  color: var(--ink-soft);
}

.s-confirm   { --row-ink: var(--confirm); }
.s-challenge { --row-ink: var(--challenge); }
.s-mixed     { --row-ink: var(--extend); }
.s-quiet     { --row-ink: var(--quiet); }

@media (max-width: 560px) {
  .sheet { padding: 32px 16px 48px; }
  .title { font-size: 26px; }
  .summary { grid-template-columns: 1fr 1fr; }
  .legend { gap: 4px 12px; }
}
@media (prefers-reduced-motion: reduce) {
  * { transition: none !important; }
}
"""


def _pct(value: float, scale: float) -> str:
    """Half the bar stands for `scale` citations, so both sides share one unit."""
    return f"{(value / scale) * 50.0:.4f}"


def _bar_scale(results: list[AuditResult]) -> int:
    """Widest single side in the whole report, so every bar stays comparable.

    The two lanes are measured together: the stance lane is bounded by the
    larger of confirms and challenges, the lower lane by extends plus neutral.
    """
    widest = 0
    for r in results:
        s = r.survival
        widest = max(widest, s.challenges, s.confirms, s.extends + s.neutral)
    return widest or 1


def _authors(paper) -> str:
    names = [a.name for a in paper.authors[:3] if a.name]
    if not names:
        return ""
    listed = ", ".join(names)
    if len(paper.authors) > 3:
        listed += " et al."
    return listed


def _counts_sentence(survival, n_fetched: int) -> str:
    """Name every count in words, so the bar is not carried by colour alone."""
    parts = []
    for count, word in ((survival.challenges, "challenging"),
                        (survival.confirms,   "confirming"),
                        (survival.extends,    "extending"),
                        (survival.neutral,    "neutral")):
        if count:
            parts.append(f"{count} {word}")
    if not parts:
        return ""
    listed = parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + " and " + parts[-1]
    sentence = f"{listed}, out of {survival.total} citing papers classified."
    if n_fetched and n_fetched != survival.total:
        sentence += f" {n_fetched} were fetched."
    return sentence


def _bar(survival, scale: int, label: str) -> str:
    """Diverging bar: challenges left of centre, confirms right, on one scale."""
    stance = []
    if survival.challenges:
        stance.append(f'<span class="seg seg-challenge" '
                      f'style="width:{_pct(survival.challenges, scale)}%"></span>')
    if survival.confirms:
        stance.append(f'<span class="seg seg-confirm" '
                      f'style="width:{_pct(survival.confirms, scale)}%"></span>')
    aside = []
    if survival.extends:
        aside.append(f'<span class="seg seg-extend" '
                     f'style="width:{_pct(survival.extends, scale)}%"></span>')
    if survival.neutral:
        offset = _pct(survival.extends, scale)
        aside.append(f'<span class="seg seg-neutral" '
                     f'style="left:calc(50% + {offset}%);'
                     f'width:{_pct(survival.neutral, scale)}%"></span>')
    return (
        f'<div class="bar" role="img" aria-label="{escape(label)}">'
        f'<span class="centre"></span>'
        f'<div class="lane lane-stance">{"".join(stance)}</div>'
        f'<div class="lane lane-aside">{"".join(aside)}</div>'
        f'</div>'
    )


def _scales(scale: int, with_score_axis: bool, with_bar_axis: bool,
            with_legend: bool) -> str:
    """Both axes for a section: the gutter score scale and the bar domain.

    The legend and its caption are drawn against the first axis only. Repeating
    them under every section makes the furniture louder than the data.
    """
    if with_score_axis:
        gutter = ('<div>'
                  '<div class="axis-label">survival score</div>'
                  '<div class="rail" aria-hidden="true"></div>'
                  '<div class="rail-ends"><span>0</span><span>10</span></div>'
                  '</div>')
    else:
        gutter = '<div></div>'

    if not with_bar_axis:
        return f'<div class="scales">\n  {gutter}\n  <div></div>\n</div>'

    legend = ""
    if with_legend:
        legend = """
    <ul class="legend">
      <li class="s-challenge">challenging, left of centre</li>
      <li class="s-confirm">confirming, right of centre</li>
      <li class="s-mixed">extending, lower band</li>
      <li class="s-quiet k-neutral">neutral, lower hairline</li>
    </ul>
    <p class="caption">The upper bar is the balance of citations that took a
    position on the claim. The lower marks are the citations that did not:
    extending work builds on the claim without testing it, neutral citations
    only mention it.</p>"""

    return f"""<div class="scales">
  {gutter}
  <div class="bar-axis">
    <div class="axis-label">citing papers, one scale for every bar below</div>
    <div class="domain" aria-hidden="true">
      <span class="d0"></span><span class="dmid"></span><span class="d1"></span>
    </div>
    <div class="domain-ends">
      <span>{scale} challenging</span>
      <span class="mid">0</span>
      <span>{scale} confirming</span>
    </div>{legend}
  </div>
</div>"""


def _claim_row(result: AuditResult, scale: int) -> str:
    s      = result.survival
    stance = _VERDICT_STANCE.get(s.verdict, "quiet")
    scored = s.verdict != _UNSCORED

    if scored:
        gutter = (f'<div class="gutter">'
                  f'<span class="score">{s.score:.1f}</span>'
                  f'<div class="rail"><span class="tick" '
                  f'style="left:{(s.score / 10.0) * 100.0:.2f}%"></span></div>'
                  f'</div>')
    else:
        # The gutter stays empty here on purpose. The scorer returns a
        # placeholder 5.0 below the citation threshold, and drawing that as a
        # measured position would invent a finding the data does not support.
        gutter = '<div class="gutter"></div>'

    counts = _counts_sentence(s, result.n_citations_fetched)
    if s.total:
        evidence = _bar(s, scale, counts) + f'<p class="counts">{counts}</p>'
    elif result.n_citations_fetched:
        evidence = ('<p class="silent">Citing papers were fetched but none could '
                    'be classified, so nothing here tests the claim.</p>')
    else:
        evidence = ('<p class="silent">No citing paper was returned for the '
                    'source paper, so nothing in the record tests this claim '
                    'yet.</p>')

    verdict_line = s.verdict if scored else "not scored, too few citations classified"

    source = escape(result.paper.title)
    authors = _authors(result.paper)
    if authors:
        source += ". " + escape(authors)
    if result.paper.year:
        source += f'. <span class="year">{result.paper.year}</span>'
    source += "."

    return f"""    <li class="claim s-{stance}">
      {gutter}
      <div class="body">
        <p class="verdict">{escape(verdict_line)}</p>
        <p class="claim-text">{escape(s.claim_text)}</p>
        {evidence}
        <p class="source">{source}</p>
      </div>
    </li>"""


def _stratum(heading: str, note: str, results: list[AuditResult],
             scale: int, with_score_axis: bool, with_legend: bool) -> str:
    rows     = "\n".join(_claim_row(r, scale) for r in results)
    has_bars = any(r.survival.total for r in results)
    return f"""<section class="stratum">
  <h2>{escape(heading)}</h2>
  <p class="note">{note}</p>
{_scales(scale, with_score_axis, has_bars, with_legend and has_bars)}
  <ol class="claims">
{rows}
  </ol>
</section>"""


def _header(results: list[AuditResult], title: str, topic: str, demo: bool) -> str:
    subject = (f'<p class="subject">Topic searched: {escape(topic)}</p>'
               if topic else "")
    notice  = ('<p class="notice">Demo mode: these records are the bundled '
               'sample data, not live Semantic Scholar results. The counts are '
               'accurate for that sample and mean nothing beyond it.</p>'
               if demo else "")

    if not results:
        return f"""<header>
  <h1 class="title">{escape(title)}</h1>
{subject}
  <p class="lead">Nothing was scored. What the audit looked for, and what came
  back, is set out below.</p>
{notice}
</header>"""

    n_papers    = len({r.paper.paper_id or r.paper.title for r in results})
    n_citations = sum(r.survival.total for r in results)

    tally_rows = []
    for verdict in _VERDICT_ORDER:
        count = sum(1 for r in results if r.survival.verdict == verdict)
        if count:
            row_stance = _VERDICT_STANCE.get(verdict, "quiet")
            tally_rows.append(f'    <li class="tally-row s-{row_stance}">'
                              f'{escape(verdict)}'
                              f'<span class="count">{count}</span></li>')

    return f"""<header>
  <h1 class="title">{escape(title)}</h1>
{subject}
  <p class="lead">One empirical claim was taken from each abstract that carried
  one, and every paper citing that abstract was read for whether it confirmed,
  challenged, extended or merely mentioned the claim. The bars below show that
  balance. The figure in the left gutter is where the claim sits on a 0 to 10
  survival scale.</p>
{notice}
  <dl class="summary">
    <div><dt>Papers with an extractable claim</dt><dd>{n_papers}</dd></div>
    <div><dt>Claims audited</dt><dd>{len(results)}</dd></div>
    <div><dt>Citing papers classified</dt><dd>{n_citations}</dd></div>
    <div><dt>Audited on</dt>
      <dd class="text">{date.today().strftime("%d %B %Y")}</dd></div>
  </dl>
  <ul class="tally">
    <li class="tally-head">Verdicts</li>
{chr(10).join(tally_rows)}
  </ul>
</header>"""


def _empty_body(topic: str) -> str:
    subject = f" for {escape(topic)}" if topic else ""
    return f"""<section class="stratum">
  <h2>No auditable claim was found</h2>
  <p class="note">The search{subject} returned no abstract containing a sentence
  that ClaimAudit recognises as an empirical claim. Extraction is rule-based: it
  looks for signals such as "we show that", "our results indicate" or "we
  conclude that", so an abstract written without one is skipped even when it
  does make a claim. No claim was scored, so there is nothing to rank here.</p>
</section>"""


def render_html(results: list[AuditResult], title: str = "Claim survival audit",
                output_path: Path = None, topic: str = "",
                demo: bool = False) -> str:
    """Build a self-contained HTML report.

    Claims are ordered by how many citing papers pushed back, then by ascending
    survival score. The score on its own cannot separate a contested claim from
    an ignored one, so the count of papers that actively disputed a claim leads.
    """
    doc_title = f"{title}: {topic}" if topic else title

    if not results:
        body = _empty_body(topic)
    else:
        scale    = _bar_scale(results)
        scored   = [r for r in results if r.survival.verdict != _UNSCORED]
        unscored = [r for r in results if r.survival.verdict == _UNSCORED]
        scored.sort(key=lambda r: (-r.survival.challenges, r.survival.score,
                                   r.paper.title))
        unscored.sort(key=lambda r: (-r.survival.total, r.paper.title))

        parts = []
        if scored:
            plural = "claim" if len(scored) == 1 else "claims"
            parts.append(_stratum(
                "Claims the citing literature engaged with",
                f"{len(scored)} {plural} drew enough classified citations to "
                "score. Most disputed first, then lowest surviving score.",
                scored, scale, with_score_axis=True, with_legend=True,
            ))
        if unscored:
            plural = "claim" if len(unscored) == 1 else "claims"
            parts.append(_stratum(
                "Claims with too little citation evidence to score",
                f"{len(unscored)} {plural} drew fewer citations than this audit "
                "requires before it will judge one. They are listed unscored "
                "rather than scored from thin evidence.",
                unscored, scale, with_score_axis=False,
                with_legend=not scored,
            ))
        body = "\n".join(parts)

    html_doc = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(doc_title)}</title>
<style>{_CSS}</style>
</head>
<body>
<div class="sheet">
{_header(results, title, topic, demo)}
{body}
  <p class="provenance">Papers, citations and citation context text from the
  Semantic Scholar Graph API. Claim extraction and citation classification are
  rule-based pattern matching rather than a trained model, so both carry error:
  read the counts as an indication of where to look, not as a settled result.</p>
</div>
</body>
</html>
"""

    if output_path:
        Path(output_path).write_text(html_doc, encoding="utf-8")
    return html_doc


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
