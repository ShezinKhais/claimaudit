# ClaimAudit

Tracks how well the empirical claims in a research paper hold up over time. Given a research topic, it searches Semantic Scholar, extracts quantitative and causal claims from paper abstracts, finds the citing papers, and classifies each citation as confirming, challenging, or extending the original claim. The result is a per-claim survival report.

Claim extraction and citation classification are rule-based, using signal-word and marker-phrase patterns rather than a trained model. Built to explore text pipelines on academic writing and to think about how scientific consensus forms (or doesn't) after publication.

---

## How it works

1. Claims are extracted from paper abstracts using regex signal patterns for quantitative, comparative, and causal language
2. Citing papers, and the context text of each citation, are retrieved from Semantic Scholar
3. Each citation context is classified as confirms / challenges / extends / neutral using marker-phrase patterns
4. A survival score (0-10) is computed per claim from the balance of confirming and challenging citations; extending citations add a small bounded bonus and neutral citations pull the score toward the midpoint

---

## Usage

```bash
pip install -r requirements.txt

# Try it offline with bundled sample data (no network or API key needed)
python -m claimaudit.cli "graphene batteries" --demo

# Audit a topic against live data from Semantic Scholar
python -m claimaudit.cli "graphene batteries"

# Fetch more papers, filter by year, and write both reports
python -m claimaudit.cli "perovskite solar cells" --papers 20 --from-year 2015 \n    --html report.html --json report.json

# Require more citations before a claim is scored at all
python -m claimaudit.cli "graphene batteries" --demo --min-cites 10
```

Each claim is scored 0-10 from the balance of citing papers that confirm,
challenge, or extend it, with a verdict label (confirmed / well-supported /
mixed / contested / challenged).

### Live data and rate limits

Live queries use the Semantic Scholar API. Its free tier throttles
unauthenticated traffic heavily, so requests without a key are often
rate-limited. For live use, request a free API key from Semantic Scholar and
provide it via the `SEMANTIC_SCHOLAR_API_KEY` environment variable (or
`--api-key`). Without a key, use `--demo` to run against the bundled sample
data.

---

## The report

`--html` writes a single self-contained page. It fetches nothing, so it can be
opened from disk, committed, or served as a static file.

Each claim is one row. The figure in the left gutter is its survival score on a
0 to 10 scale shared by every row, so the rows can be read against each other
rather than only against themselves. Beside it the citations are drawn as a
balance: those that took a position on the claim form the upper bar, challenging
to the left of centre and confirming to the right, and the citations that took
no position sit below it, extending work on one band and bare mentions on a
hairline. Every bar is on one scale, stated above the set.

Each row also writes its counts out in words, so nothing on the page depends on
reading a drawing. Claims are ordered most disputed first, then by lowest score.

Running with `--demo` says so on the page itself, because a report that looks
identical whether or not it touched real data is a report that will eventually
be mistaken for one.

---

## Limitations

Claim extraction and citation classification are regex rules over abstract and
citation-context text. There is no model behind either, and the score inherits
every weakness of both.

**The score saturates at the top of its range.** It is the balance of confirming
against challenging citations mapped onto 0 to 10, and the mapping produces
values above 10 that are then clamped. A claim reaches a flat 10 as soon as it
has roughly three times as many confirmations as challenges, so 8 confirmations
against 2 challenges scores exactly the same as 10 against none. The bundled
demo shows this directly: its top claim has 4 confirming and 1 challenging
citation and is reported as 10.0, confirmed. Read the counts beside the score,
not the score alone; the report prints them for this reason.

**A claim is one sentence from an abstract.** Whatever the paper actually
established lives in the results section, which is not fetched. An abstract
sentence is a summary written to be persuasive, and the claim recovered from it
can be stronger or vaguer than what was shown.

**The classifier does not handle negation, and gets these backwards.** It looks
for marker phrases without checking whether they were negated, so a citation
saying "we failed to replicate their finding" is counted as *confirming*, on the
strength of the word "replicate", and so is "we did not confirm the original
observation". In the other direction, "our results are not inconsistent with
Smith et al." is counted as *challenging*. These are not edge cases; retractions
and failed replications are written in exactly this register, which is the
worst possible place for the error to fall.

**Classification reads the citation context, not the citing paper.** Semantic
Scholar returns a short snippet around each citation. A paper that spends a
section dismantling a claim but cites it once in neutral language is counted as
neutral.

**Coverage is whatever Semantic Scholar has.** Citation contexts are missing for
a large share of citations, especially for papers behind paywalls, so `total` is
the number of citations that could be classified rather than the number that
exist. A claim with few contexts is reported as insufficient data rather than
scored, which is the right call but means absence of coverage and absence of
engagement look similar from outside.

---

## Testing

Install the dependencies and run the suite:

```bash
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt pytest   # Linux/macOS: .venv/bin/pip
.venv/Scripts/python -m pytest -v
```

Exercise the CLI directly with `python -m claimaudit.cli --help`.

---

## Project structure

```
claimaudit/
├── claimaudit/
│   ├── extractor.py    # regex-based claim extraction from abstracts
│   ├── scholar.py      # Semantic Scholar Graph API client (+ demo data)
│   ├── matcher.py      # citation-relation classification (confirms/challenges/extends)
│   ├── classifier.py   # audit pipeline: search, extract, classify, score
│   ├── scorer.py       # survival score computation and verdict thresholds
│   ├── reporter.py     # HTML and JSON output
│   ├── demo_data.py    # bundled sample data for --demo
│   └── cli.py
└── tests/
    ├── test_classifier.py
    ├── test_matcher.py
    ├── test_reporter.py
    ├── test_demo.py
    └── test_scorer.py
```

---

## Stack

Python 3.10, Requests, Typer, Rich. No third-party ML or PDF libraries;
claim extraction and citation classification are rule-based.

An API key is optional but recommended: Semantic Scholar's free tier throttles
unauthenticated traffic, so live runs without a key are often rate-limited.
Use `--demo` to run offline against the bundled sample data.
