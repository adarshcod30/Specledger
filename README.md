# SpecLedger

**Chain of custody for AI-generated product data.** Every attribute SpecLedger
publishes traces to a highlighted sentence in a real source document, carries a
calibrated confidence score, and auto-publishes only when it is provably safe
to. Where a value can't be verified, the system says so and routes it to a
human — instead of guessing and hoping.

<p>
<img alt="tests" src="https://img.shields.io/badge/tests-48%20passing-158a4a?style=flat-square">
<img alt="python" src="https://img.shields.io/badge/python-3.13-2563eb?style=flat-square">
<img alt="llm" src="https://img.shields.io/badge/LLM-Amazon%20Nova%20Lite%20(Bedrock)-0891b2?style=flat-square">
<img alt="license" src="https://img.shields.io/badge/license-MIT-8b93a1?style=flat-square">
<img alt="status" src="https://img.shields.io/badge/status-runs%20locally-b45309?style=flat-square">
</p>

Team **Unisol**.

---

## Table of contents

- [The problem, in one real example](#the-problem-in-one-real-example)
- [Why this repo has two projects in it](#why-this-repo-has-two-projects-in-it)
- [Part 1 — SpecLedger: verifiable product intelligence](#part-1--specledger-verifiable-product-intelligence)
  - [Architecture](#architecture)
  - [What each piece does, and why it exists](#what-each-piece-does-and-why-it-exists)
  - [How the LLM fits in — and why the architecture doesn't depend on it](#how-the-llm-fits-in--and-why-the-architecture-doesnt-depend-on-it)
  - [Results, measured](#results-measured)
  - [The Review Cockpit](#the-review-cockpit)
- [Part 2 — UniHack: product intelligence for Major Appliances](#part-2--unihack-product-intelligence-for-major-appliances)
- [Tech stack](#tech-stack)
- [Environment variables and keys](#environment-variables-and-keys)
- [Data map — every file and what's in it](#data-map--every-file-and-whats-in-it)
- [API reference](#api-reference)
- [Setup and running it](#setup-and-running-it)
- [Testing](#testing)
- [Deployment](#deployment)
- [Honest limitations](#honest-limitations)
- [Repository layout](#repository-layout)
- [License](#license)

---

## The problem, in one real example

Vishay's rectifier datasheet tabulates seven part numbers in one row:

```
PARAMETER                              SYMBOL  1N4001 1N4002 1N4003 1N4004 1N4005 1N4006 1N4007  UNIT
Maximum repetitive peak reverse voltage VRRM    50     100    200    400    600    800    1000    V
```

Flattened to text — which is what every naive "read the PDF, ask an LLM"
pipeline does — the part numbers and their values land in **separate rows**.
Get the column wrong and you publish `1000 V` for a `1N4001`, a part rated
`50 V`. Someone puts it on a 600 V rail. It fails short.

That is not a hypothetical. It is in the datasheet this repository actually
downloads and processes. Industrial distributors manage millions of SKUs like
this — cryptic descriptions, scattered manufacturer PDFs, specs that are
safety-critical if wrong — and the review labor to catch every mistake by hand
doesn't scale. **SpecLedger is the layer that decides which AI-generated
values are safe to publish unreviewed, and proves it with a citation.**

## Why this repo has two projects in it

| | **SpecLedger** (repo root) | **UniHack module** (`unihack/`) |
|---|---|---|
| What it is | The core architecture: evidence-gated extraction, source arbitration, calibrated confidence, selective abstention | A real submission to Unilog's UniHack challenge, built by retargeting SpecLedger's proven backend at a different domain |
| Domain | Electronic components (rectifier diodes, linear regulators) | Major home appliances (dishwashers, washers, dryers, ranges…) |
| Sourcing | Pre-fetched manufacturer PDF datasheets (Vishay, Diodes Inc, Texas Instruments) | **Live** web sourcing — real-time search + fetch against manufacturer sites, at run time |
| Output | A Review Cockpit web app + audit trail in SQLite | A 252-column CSV matching Unilog's exact Delivery Format schema |
| Ground truth | A 98-label gold set, hand-transcribed from the same PDFs | 2 fully-populated real rows from Unilog's own Expected Output file |

`unihack/extract.py` imports directly from `specledger/llm.py` — the two
projects share one Bedrock/Nova Lite credential path and one evidence-gate
contract. See [How things connect](#how-the-llm-fits-in--and-why-the-architecture-doesnt-depend-on-it).

---

## Part 1 — SpecLedger: verifiable product intelligence

### Architecture

```
sparse SKU (mpn + brand + one marketing line)
  │
  ├─ 1  INGEST         PDF → text with exact character offsets + page map
  │                    (PyMuPDF). Same char-offset model works for any plain
  │                    text source — HTML included, which is what unihack/
  │                    reuses it for.
  │
  ├─ 2  SEGMENT        Datasheets have canonical sections, and each has
  │                    authority over different claims. Absolute Maximum
  │                    Ratings states ratings; Electrical Characteristics
  │                    states TEST CONDITIONS that look identical but aren't;
  │                    Typical Characteristics is graphs and authorizes
  │                    nothing at all.
  │
  ├─ 3  EXTRACT        A panel of strategies, each required to emit a
  │     │              verbatim quote:
  │     ├─ table_column   resolves WHICH COLUMN of a series table belongs
  │     │                 to this exact part — defeats the trap above
  │     ├─ range           two-ended ranges; unit must come from the
  │     │                 document, never assumed from the schema
  │     ├─ inline_spec     label/value lines, dimension-guarded
  │     └─ llm              Amazon Nova Lite via AWS Bedrock, same contract
  │                         (self-consistency sampled, k=3 by default)
  │
  ├─ 4  VERIFY         Every quote is re-checked against the actual document
  │                    bytes. Not found → the value is FABRICATED and is
  │                    dropped, full stop, regardless of how confident the
  │                    model sounded. Guards: sibling-part contamination,
  │                    graph-axis rejection, section authority.
  │
  ├─ 5  NORMALIZE      Pint. "100mA" and "0.1A" become one comparable number.
  │
  ├─ 6  ARBITRATE      Cluster candidate values across sources; weight by
  │                    evidence quality, source authority, and brand match —
  │                    never by raw vote count. Cross-manufacturer
  │                    disagreement is escalated to a human, never silently
  │                    resolved in either direction.
  │
  ├─ 7  RULES          Physics as a free validator: surge current must
  │                    exceed continuous current, Vin_max must exceed
  │                    Vout_max, Tmin must be below Tmax.
  │
  ├─ 8  CALIBRATE      Logistic regression over 11 evidence features →
  │                    P(correct). Threshold chosen to hit a target
  │                    precision floor on OUT-OF-FOLD predictions (not
  │                    in-sample, which would overstate confidence) →
  │                    AUTO_PUBLISH / REVIEW / REJECT. Safety-critical
  │                    attributes get a stricter floor by a monotonicity
  │                    constraint, not by hoping the data supports one.
  │
  └─ 9  PUBLISH        Commerce payload + schema.org JSON-LD + a full audit
                       trail in SQLite (every decision, every reviewer
                       action, timestamped).
```

### What each piece does, and why it exists

| Module | Responsibility | Why it's a separate module |
|---|---|---|
| `specledger/corpus.py` | Pins the 7 real vendor-datasheet URLs + SHA-256 hashes, fetches them, detects if a vendor silently revises a PDF | Datasheets are copyrighted — never vendored into git, always fetched fresh and hash-verified |
| `specledger/ingest.py` | PDF → text with exact character offsets, page rendering for evidence highlighting | Two jobs deliberately split from `verify.py`: offsets *prove* a quote is real; rendering just *shows* it — mixing them makes both fragile |
| `specledger/sections.py` | Classifies which datasheet section a span of text came from (Absolute Maximum Ratings vs. a graph's axis labels vs. a test condition) | Without this, a naive extractor reads a **test condition** ("TJ = 100°C") as if it were the part's rated maximum — a real bug this project caught and fixed mid-build |
| `specledger/extract.py` | Deterministic strategies: series-table column resolution, two-ended ranges, inline label/value pairs | Precision-first by construction — every strategy is allowed to abstain, and abstention is never penalized |
| `specledger/llm.py` | Amazon Bedrock (Nova Lite) / direct Anthropic API backend, self-consistency sampling | The LLM is a candidate *generator*, not an oracle — this module's job ends the moment it hands a quote to `verify.py` |
| `specledger/verify.py` | The evidence gate: exact / normalized / relocated / not-found matching against the real document bytes | This is the one module every other module answers to. A value that fails here never reaches the catalog |
| `specledger/normalize.py` | Unit conversion (Pint) and enum canonicalization | "100mA" and "0.1A" must compare as equal, or arbitration can't cluster them |
| `specledger/arbitrate.py` | Multi-source conflict resolution, weighted by evidence strength and manufacturer authority | Ballot-stuffing guard: the same regex matching 8 times in one PDF is not 8 independent confirmations |
| `specledger/rules.py` | Cross-attribute physics checks | A free validator that costs nothing and catches internally-inconsistent values no single-field check would see |
| `specledger/confidence.py` | Logistic regression calibrator, conformal thresholding, out-of-fold scoring | The number that actually decides AUTO_PUBLISH vs. REVIEW — the entire economic case for this system lives here |
| `specledger/pipeline.py` | Orchestrates ingest → extract → verify → normalize → arbitrate → rules → calibrate for one SKU | The one place that knows the full order of operations |
| `specledger/publish.py` | Commerce payload + schema.org JSON-LD + "AI-search readiness" scoring | Only `AUTO_PUBLISH` attributes are ever emitted here — by construction, not by convention |
| `specledger/store.py` | SQLite persistence + append-only audit trail | Chosen over Postgres deliberately: a judge (or you) must be able to clone and run this with zero infrastructure |
| `api/main.py` | FastAPI service: 10 endpoints, background catalog warm-up | Enrichment with a live LLM in the panel can take minutes — this runs in a background thread at boot so the first request is never a silent multi-minute hang |
| `web/index.html` | The Review Cockpit — single static file, zero build step, zero JS framework | A reviewer needs to go from a published number to the sentence that justifies it in one click, or the whole "traceable output" claim is just a slogan |

### How the LLM fits in — and why the architecture doesn't depend on it

`specledger/llm.py` talks to **Amazon Nova Lite over AWS Bedrock's Converse
API** by default (an `SPECLEDGER_LLM_BACKEND=anthropic` fallback exists for
local development). Two design decisions matter more than the model choice
itself:

1. **The LLM is a candidate generator, never an oracle.** It proposes a value
   and a verbatim quote; `verify.py` re-checks that quote against the actual
   document bytes before anything downstream ever sees it. A fabricated
   citation — however fluent — contributes nothing. This was tested directly:
   `tests/test_bedrock_contract.py` proves that a model returning a
   correctly-typed, schema-valid value with an **invented** citation produces
   a candidate that is never usable.

2. **Self-consistency is measured, not assumed.** Each extraction is sampled
   `k=3` times at non-zero temperature; agreement across samples becomes a
   calibrator feature (`self_consistency`). This is real uncertainty signal —
   unlike a model's own stated confidence, which research shows is badly
   calibrated (Expected Calibration Error up to 0.61 on open-ended tasks).

Because the confidence model's 11 features describe the *evidence*
(match quality, source authority, agreeing-source count, self-consistency…)
rather than which model produced it, swapping Nova Lite for Claude or a pure
regex panel doesn't invalidate anything the calibrator learned. `unihack/`
proves this in practice — it reuses the exact same `specledger/llm.py`
backend for a completely different domain, with zero duplicated credential or
retry logic (`BedrockBackend.call()` accepts an optional system prompt and
tool schema override specifically so a second domain could share it).

### Results, measured

Run `make eval` to reproduce. Measured on **12 SKUs across 7 real vendor
datasheets** (Vishay, Diodes Incorporated, Texas Instruments), graded against
**98 hand-transcribed labels** — read directly from the source PDFs, never
from memory. Both arms below run the identical inputs and documents.

| metric | naive extraction | SpecLedger |
|---|---:|---:|
| coverage | 92.9% | 92.9% |
| auto-publish rate | 100% | 80.0% |
| **precision on published** | **69.2%** | **98.7%** |
| **safety-critical precision** | **81.3%** | **100%** |
| **wrong values published** | **28** | **1** |
| queued for human review | 0 | 19 |
| calibration error (ECE) | 0.308 | 0.037 |

The naive arm publishes everything it finds — which is what "just call an
LLM" looks like in production. 28 wrong specs shipped, no signal about which
ones. SpecLedger's lower auto-publish rate is the system doing its job, not a
regression: naive's 100% is the absence of a check, not a strength.

**Risk–coverage frontier** — the knob a distributor actually turns:

| threshold | coverage | precision |
|---:|---:|---:|
| 0.00 | 100% | 94.7% |
| 0.46 | 95.8% | 98.9% |
| 0.90 | 94.7% | 98.9% |
| 0.95 | 83.2% | 98.7% |
| 0.98 | 13.7% | 92.3% |

One error is disclosed on purpose, not tuned away: `REG-LM1117-TI`'s
`package` field reads `TO-252`, present in the source document but not among
the part's actually-offered packages. `make eval` prints it every run. Trust
comes from what a system admits, not just what it claims.

### The Review Cockpit

`web/index.html` — a single static file, no build step, no JS framework,
served directly by FastAPI at `/`.

- **Catalog** — every SKU, its published/total attribute ratio, an
  AI-search-readiness gauge, and a full attribute list with color-coded
  confidence bars. Click any attribute to see the **exact source sentence**
  that justifies it, with a rendered PDF page and a highlighted span.
- **Review queue** — items ranked by `risk = uncertainty × safety weight ×
  conflict weight`, so a reviewer with one hour spends it where a wrong value
  does the most damage, not on whatever arrived first.
- **Evaluation** — the table and risk-coverage chart above, generated live
  from `eval/out/metrics.json`, plus the learned calibrator feature weights
  as a bar chart.
- A **Help** modal explains the 4-step pipeline and every badge in plain
  language, for a reviewer who's never seen the tool before.

The UI is light-themed by design: reviewers use this tool for extended
periods against printed and on-screen documents side by side, and a dark
interface fights that use case rather than serving it. Elevation is
communicated with shadows, not glow, and every section (Catalog / Record /
Evidence, or Queue / Evidence) is a clearly bounded card so the three-way
split stays legible even on a laptop-sized viewport. Below 1150px the layout
gracefully re-stacks instead of clipping.

---

## Part 2 — UniHack: product intelligence for Major Appliances

Unilog's actual UniHack brief: given a bare `Mfg_Part_Num, Part_Desc,
E1_Brand, Unilog_Brand, DIB_Brand, Part_Manuf` row, produce a fully-populated
**252-column** Delivery Format record — the exact schema Unilog uses
internally, header names unmodified.

Full writeup, architecture diagram, and every measured number:
**[unihack/README.md](unihack/README.md)**.

The short version: construction formulas for every description field
(`INVOICE_DESC`, `MOBILE_DESC`, `SHORT_DESC`, `LONG_DESC1`, `RETAIL_DESC`)
were reverse-engineered by diffing two real ground-truth rows field by
field — not guessed — and verified to reproduce them **10/10 exact
byte-for-byte** (`unihack/tests/test_describe.py`). The pipeline is
genuinely dynamic: real live search resolves a brand when none is named in
the input text, real HTTP fetches hit the manufacturer's own domain only
(never a marketplace or distributor, per the brief's sourcing rule), and a
real Bedrock/Nova Lite pass extracts attributes under the identical
evidence-gate contract as SpecLedger. Run across all 65 Major Appliance rows
in the real 1,000-item input in 212.5 seconds: `unihack/out/delivery_format.csv`.

A genuine, externally-verified finding from that run: 50 of 65 rows resolved
a brand correctly and then hit a manufacturer site running bot-management
that blocks automated access outright (confirmed independently against
Frigidaire, LG, and KitchenAid, via direct HTTP *and* separately via a
different fetch mechanism). Those rows are honestly routed to review with the
specific reason recorded — never left silently blank, never fabricated.

---

## Tech stack

| Layer | Choice | Why |
|---|---|---|
| Language | Python 3.13 | |
| API | FastAPI + Uvicorn | Async-friendly, typed, minimal ceremony |
| PDF parsing | PyMuPDF (`pymupdf`) | Gives character-level bounding boxes — span highlighting in the UI is nearly free |
| Units | Pint | Don't hand-roll unit conversion; industrial specs use five spellings for one unit |
| HTTP client | httpx | Used for both PDF fetches and, in `unihack/`, live HTML fetches |
| LLM (primary) | Amazon Nova Lite via **AWS Bedrock** (`boto3`) | Cost-efficient, and the same account already used elsewhere on this team |
| LLM (fallback) | Anthropic API (`anthropic`) | Local-dev path when Bedrock isn't configured |
| ML | scikit-learn (`LogisticRegression`), numpy, pandas | The whole confidence model is ~200 lines and outperforms trusting a model's self-reported confidence |
| Storage | SQLite (via `sqlite3`) | Zero-infrastructure — a judge clones the repo and runs it, no server to provision |
| Validation | Pydantic | Request/response models in the API layer |
| Config | `python-dotenv` | `.env` → `os.environ`, gitignored |
| Testing | pytest | 48 tests, 1.4s wall clock, hermetic (see [Testing](#testing)) |
| Frontend | Vanilla HTML/CSS/JS, one file, no framework, no build step | The deliverable has to run with `make run` and nothing else |
| Live search (`unihack/`) | DuckDuckGo's HTML endpoint, no API key | Resolves a brand's manufacturer domain from a bare model number at run time — not a lookup table |

## Environment variables and keys

Copy `.env.example` to `.env`. **Every value is optional** — SpecLedger and
the `unihack` module both run fully offline on the deterministic extractors
with zero configuration; credentials only switch on the LLM extractor, which
joins the panel and raises recall under the identical evidence-verification
contract as everything else.

| Variable | Default | What it controls |
|---|---|---|
| `SPECLEDGER_LLM_BACKEND` | `bedrock` | `bedrock` talks to Nova Lite via AWS; `anthropic` uses the direct API instead |
| `AWS_ACCESS_KEY_ID` | — | AWS credential (Bedrock backend only) |
| `AWS_SECRET_ACCESS_KEY` | — | AWS credential (Bedrock backend only) |
| `AWS_SESSION_TOKEN` | — | Only needed for temporary/STS credentials |
| `AWS_REGION` | `us-east-1` | Must be a region where Bedrock + the chosen model are enabled |
| `SPECLEDGER_BEDROCK_MODEL` | `us.amazon.nova-lite-v1:0` | Nova Lite needs a **region-prefixed inference profile** for on-demand invocation — the bare foundation-model ID throws `ValidationException` |
| `ANTHROPIC_API_KEY` | — | Only used when `SPECLEDGER_LLM_BACKEND=anthropic` |
| `SPECLEDGER_MODEL` | `claude-sonnet-4-5` | Model ID for the Anthropic fallback path |
| `SPECLEDGER_LLM_SAMPLES` | `3` | Independent samples per extraction; agreement feeds the calibrator as `self_consistency`. `1` disables it |
| `SPECLEDGER_TARGET_PRECISION` | `0.98` | The precision floor the calibrator solves for on general attributes |
| `SPECLEDGER_TARGET_PRECISION_SAFETY` | `0.99` | Stricter floor for safety-critical attributes, enforced by a monotonicity constraint (never lower than the general floor) |

No API keys, secrets, or `.env` files are committed anywhere in this repo —
verify with `git log -p -- .env` (empty) and `.gitignore` (`.env` is listed
explicitly).

## Data map — every file and what's in it

```
data/
├── gold/gold.json          98 labels, 12 SKUs — hand-transcribed from the
│                           real source PDFs, frozen, never trained on. Every
│                           value in eval/out/metrics.json is graded against
│                           this file.
├── cache/*.text.json       Ingested PDF text + char-offset page map, one per
│                           datasheet — regenerable via `make fetch`, not the
│                           source of truth (the PDFs and their pinned SHA-256
│                           in corpus.py are).
├── corpus.lock.json        SHA-256 of every fetched datasheet. If a vendor
│                           silently revises a PDF, this is how you'd know.
├── confidence_model.json   The trained logistic-regression calibrator:
│                           coefficients, thresholds, out-of-fold metrics.
│                           Regenerated by `make eval`; a stale copy (wrong
│                           feature count) is detected and safely ignored —
│                           see confidence.py's schema-validation guard.
└── specledger.db           SQLite: enriched records, attributes, and a full
                            append-only audit trail of reviewer actions.
                            Created on first `make run`, gitignored.

eval/out/metrics.json       The full evaluation output the Review Cockpit's
                            "Evaluation" tab renders live — arm comparison,
                            risk-coverage curve, feature weights, disclosed
                            errors. Regenerated by `make eval`.

unihack/data/output_header.py   The exact 252-column Delivery Format header,
                                 parsed once from Unilog's real Expected
                                 Output file and never hand-edited — the
                                 single source of truth for column order.

unihack/out/
├── delivery_format.csv     The actual deliverable: 65 rows × 252 columns,
│                           header names unmodified, from a live run against
│                           the real 1,000-item input.
└── review_queue.csv        Companion file: decision, confidence, and the
                            specific reason for every row that didn't
                            auto-publish.
```

## API reference

`api/main.py`, served at `http://127.0.0.1:8077` via `make run`.

| Method | Path | Returns |
|---|---|---|
| `GET` | `/` | The Review Cockpit (`web/index.html`) |
| `GET` | `/api/ready` | `{ready, llm_extractor}` — cheap, never blocks; the cockpit polls this during warm-up |
| `GET` | `/api/health` | Full catalog stats, calibration metrics, LLM backend status, resolved fresh on every call |
| `GET` | `/api/records` | Every SKU with published/total ratio and readiness score |
| `GET` | `/api/records/{sku}` | Full attribute breakdown for one SKU, including per-candidate quarantine reasons |
| `GET` | `/api/queue` | The review queue, sorted by risk score |
| `GET` | `/api/evidence/{sku}/{attribute}.png` | The source PDF page, rendered with the supporting sentence highlighted |
| `GET` | `/api/publish/{sku}` | Commerce payload + schema.org JSON-LD + AI-search readiness for one SKU |
| `POST` | `/api/review` | Accept / reject / correct one attribute — writes to the audit trail |
| `GET` | `/api/metrics` | The full `eval/out/metrics.json`, for the Evaluation tab |

## Setup and running it

```bash
git clone https://github.com/adarshcod30/Unisol.git
cd Unisol
make setup      # venv + pip install -r requirements.txt
make fetch      # downloads 7 real datasheets (~10 MB) from vendor sites,
                 # SHA-256 pinned in specledger/corpus.py
make eval       # fits the calibrator, prints and writes eval/out/metrics.json
make run        # starts the Review Cockpit at http://127.0.0.1:8077
```

Or all at once: `make demo` (setup → fetch → eval → test → run).

The server opens its port immediately and warms the catalog in a background
thread; the cockpit shows a real loading state until it's ready instead of
hanging silently. With no LLM credentials this takes seconds. With Bedrock or
Anthropic configured, the LLM extractor joins the panel and — because
self-consistency sampling means real API calls per attribute — the first
warm-up can take a few minutes on the full catalog. One-time cost per server
start, not per request.

Other targets: `make llm-check` (verifies the configured backend end-to-end
against a live column-resolution trap, credentials masked in the output),
`make clean` (clears generated data, keeps fetched PDFs), `make reset` (also
re-fetches everything from scratch).

For the UniHack module specifically:

```bash
.venv/bin/python -m pytest unihack/tests/ -q   # 6 tests, no network
.venv/bin/python -m unihack.eval                # 2 known SKUs, live sourcing
.venv/bin/python -m unihack.run_batch            # all 65 rows, live, ~3.5 min
```

## Testing

```
tests/                                42 tests — SpecLedger
├── test_evidence_gate.py             6   the central claim: a fabricated
│                                          citation is never publishable
├── test_variant_traps.py             11  the real series-table and
│                                          sibling-contamination traps
├── test_provenance_and_units.py      8   section authority, unit handling,
│                                          the stale-calibrator-model guard
├── test_pipeline.py                  7   end-to-end invariants across every
│                                          record
└── test_bedrock_contract.py          10  the Bedrock/Nova Lite integration,
                                           proven without live credentials
                                           via simulated Converse responses

unihack/tests/test_describe.py        6 tests — every description formula
                                       reproduces real ground truth exactly
```

**48 tests, 1.4 seconds, zero network calls** — even the Bedrock contract
tests run hermetically. This mattered in practice: adding live AWS
credentials to `.env` once silently made the pipeline tests start making real
network calls (294s instead of 1.3s), because `enrich()` defaulted to the
full extraction panel regardless of caller. Fixed by adding an explicit
`extractors=` override and pinning every test to the deterministic-only path,
plus a regression test (`test_pipeline_tests_never_call_the_real_network`)
asserting the LLM path is never touched from there — a test suite's speed and
cost must not depend on what happens to be sitting in `.env`.

```bash
make test
# or directly:
.venv/bin/python -m pytest tests/ unihack/tests/ -q
```

## Deployment

**Not currently deployed to a public URL — runs locally via `make run`.**
There's no Dockerfile, `render.yaml`, `fly.toml`, or similar in this repo
yet; the FastAPI service is a standard ASGI app and would deploy cleanly to
Render, Fly.io, Railway, or an EC2/Lightsail instance with `uvicorn` behind a
reverse proxy — none of that has been done. If a live demo is needed for
judging, the fastest path is `uvicorn api.main:app --host 0.0.0.0 --port
$PORT` on any of the above.

**GitHub repository "About" panel** — this README is edited via the
Claude Code CLI, which doesn't have GitHub API/`gh` credentials to update the
repo sidebar (description, website link, topics) directly. Paste this in at
[github.com/adarshcod30/Unisol](https://github.com/adarshcod30/Unisol) → the
gear icon next to "About":

> **Description:** Chain of custody for AI-generated product data — evidence-gated extraction, calibrated confidence, and selective abstention for industrial product intelligence.
> **Topics:** `ai`, `llm`, `product-intelligence`, `data-enrichment`, `fastapi`, `aws-bedrock`, `evidence-verification`, `human-in-the-loop`

## Honest limitations

- **The gold set is 98 labels over 12 SKUs.** That's enough to measure real
  precision, not enough to *certify* 99% — one high-scoring error caps
  achievable coverage at roughly 1% at that target, which is why the default
  floor is 98% and the full risk-coverage frontier is published rather than a
  single flattering number.
- **One disclosed error survives**: `REG-LM1117-TI`'s `package` field. Left
  in `make eval`'s output on purpose rather than tuned away.
- **`is_conflicting` learned a positive calibrator weight** — wrong-signed, a
  small-sample artifact. Harmless today because `decide()` gates on conflict
  unconditionally regardless of the learned weight, but it needs a
  monotonicity constraint at a larger sample size.
- **Two SpecLedger product classes** (rectifier diodes, linear regulators).
  The schema registry is the extension point — adding a class is additive,
  not a rewrite.
- **SQLite, not Postgres.** Deliberate, for a project a judge or reviewer
  must be able to clone and run with zero infrastructure.
- **`unihack/`'s brand styling and manufacturer-of-record data is verified
  for Frigidaire and Whirlpool only** (from real ground truth); every other
  brand uses a public-record default, explicitly flagged `unverified` in the
  output rather than presented as compliant. No manufacturer/brand master
  list, LOV, UOM standards file, or content-guidelines document was provided
  for that build — see [unihack/README.md](unihack/README.md) for the full
  accounting of what that does and doesn't let the pipeline verify.
- **No public deployment yet** — see [Deployment](#deployment).

## Repository layout

```
Unisol/
├── specledger/              core architecture — see the module table above
│   ├── corpus.py, ingest.py, sections.py, extract.py, llm.py, verify.py,
│   │   normalize.py, arbitrate.py, rules.py, confidence.py, pipeline.py,
│   │   publish.py, store.py, schema.py, catalog.py, models.py, config.py
│   └── __init__.py
├── api/main.py               FastAPI service, 10 endpoints
├── web/index.html            Review Cockpit — single file, no build step
├── eval/run_eval.py           naive-vs-SpecLedger evaluation harness
├── data/                      gold set, cache, corpus lock, SQLite DB
├── tests/                     42 tests
├── unihack/                    the UniHack competition submission
│   ├── taxonomy.py, brand.py, search.py, source.py, extract.py,
│   │   describe.py, uom.py, schema.py, pipeline.py, export.py,
│   │   run_batch.py, eval.py
│   ├── data/output_header.py   the 252-column schema
│   ├── out/                    delivery_format.csv, review_queue.csv
│   ├── tests/test_describe.py  6 tests
│   └── README.md                full UniHack writeup
├── requirements.txt
├── Makefile
├── .env.example
└── README.md                  this file
```

## License

[MIT](LICENSE) — see the LICENSE file.
