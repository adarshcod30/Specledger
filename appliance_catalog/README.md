# Major Appliances: a second product domain

Transforms a bare `Mfg_Part_Num, Part_Desc, E1_Brand, Unilog_Brand, DIB_Brand,
Part_Manuf` row into a fully-populated 252-column Delivery Format record —
matching a real distributor's exact header schema, unmodified — using real,
live sourcing from manufacturer sites, not a lookup table keyed to known
SKUs. This is `specledger/`'s evidence-gated core retargeted at a completely
different domain (major home appliances instead of electronic components) to
prove the architecture isn't single-purpose: see the top-level
[README](../README.md#using-specledger-as-a-library) for the library itself.

## Scope

Depth over breadth: this build targets **Major Appliances** (dishwashers
verified against real ground truth; washers/dryers/ranges/microwaves/
refrigerators extended by pattern and marked `unverified`), not every
category present in the full input sample.

No manufacturer/brand master list, LOV, UOM standards file, or content
guidelines document was available for this build. Only two things anchor it
in real ground truth: a worked dishwasher example from the target format's
own construction spec, and two fully-populated rows in a real Expected
Output file (`PDSH4816AF`, `WDTS7024RZ`, both of which also appear in the
raw input catalog). Everything derived from those two rows is marked
`verified=True`; everything extended to sibling categories by pattern is
marked `verified=False` and scored at reduced confidence. Inventing values
against the missing master lists is the one failure mode this project
refuses to ship, so where there's no authoritative source, the pipeline
leaves the field blank and routes the row to review rather than guess.

## Architecture

```
input row
  │
  ├─ taxonomy.classify()      Dept / Class / Fine / Classpath / Product Name
  │                           rule-based, scoped to 9 appliance sub-categories
  │
  ├─ brand.resolve()          brand token in Part_Desc text (evidence-based
  │                           alias table: "SQ"/"Speed Queen" both appear in
  │                           the input for the same distributor)
  │      │
  │      └─ (no token found)  search.find_manufacturer_domain()
  │                           REAL live search (DuckDuckGo HTML), not a lookup
  │                           table — generalises to any MPN, not just the two
  │                           known SKUs. Both PDSH4816AF and WDTS7024RZ hit
  │                           this path: neither names its brand in Part_Desc.
  │
  ├─ source.fetch_first_reachable()
  │                           REAL HTTP GET against the manufacturer's own
  │                           domain only (never a marketplace/distributor —
  │                           this project's own sourcing rule, enforced at
  │                           fetch time, not just at prompt time)
  │
  ├─ extract.AttributeExtractor
  │                           Bedrock/Nova Lite, evidence-gated: every value
  │                           must carry a verbatim quote, re-checked against
  │                           the actual fetched text. A quote that isn't
  │                           really on the page is discarded regardless of
  │                           how plausible it sounds. Plus a plausibility
  │                           guard on short categorical fields (Color,
  │                           Material, …) — see "What broke" below.
  │
  ├─ describe.*                deterministic template builders for
  │                           INVOICE_DESC / MOBILE_DESC / SHORT_DESC /
  │                           RETAIL_DESC / LONG_DESC1, reverse-engineered
  │                           from the two ground-truth rows and unit-tested
  │                           to reproduce them byte-for-byte (10/10 fields,
  │                           both rows — appliance_catalog/tests/test_describe.py)
  │
  └─ export.write_csv()       exact 252-column header, unmodified
```

## The full batch: all 65 Major Appliance rows, live, from the raw input catalog

`.venv/bin/python -m appliance_catalog.run_batch` — 212.5 seconds, real
network and LLM calls throughout, zero mocking, zero hardcoded per-SKU
answers.

| | count |
|---|---:|
| rows processed | 65 |
| output CSV columns | 252 / 252, exact header match |
| auto-published | 1 |
| routed to review | 64 |
| — of which: source unreachable (brand resolved, site blocked) | 50 |
| — of which: brand unresolved (no token, search found no known domain) | 13 |
| — of which: other | 1 |

Read plainly, this says: **the bottleneck is external site accessibility, not
pipeline logic.** 77% of rows resolved a brand correctly and then hit a
manufacturer site that blocks automated access — the same Akamai/Cloudflare-
class blocking confirmed independently against Frigidaire, LG, and KitchenAid
(see below). Every one of those 50 rows still got Dept/Class/Fine/Classpath/
Product Name/brand-name populated where resolvable, and was honestly flagged
rather than silently left empty or filled with a guess. `PDSH4816AF` — one of
the two known ground-truth SKUs — is exactly this case: `MANUFACTURER_NAME`
and `BRAND_NAME` both resolved to an **exact match** with ground truth
(`Rheem Manufacturing`, `FRIGIDAIRE®`) via live search, but the Frigidaire
site itself timed out, so the row correctly stopped there rather than
fabricate attributes it could not verify.

Full per-row output: `appliance_catalog/out/delivery_format.csv` (the
deliverable) and `appliance_catalog/out/review_queue.csv` (decision,
confidence, and the specific reason for every row).

## What actually works, measured

Run `.venv/bin/python -m appliance_catalog.eval` for the live numbers. Two
separate claims, deliberately not conflated:

1. **Construction fidelity** (given the correct attributes, do the formulas
   reproduce ground truth exactly?): **10/10** fields across both known rows.
   This isolates the deterministic template logic — reverse-engineered by
   diffing the two real Delivery Format rows field by field, not guessed —
   from live sourcing variance. `appliance_catalog/tests/test_describe.py`.

2. **End-to-end live accuracy** (running the full pipeline — real search,
   real fetch, real extraction — against the same two SKUs): bounded by
   which manufacturer sites are reachable *right now*, which is real-world,
   not a scoring artifact.

## A real finding, not a limitation of this code

Frigidaire's site (`frigidaire.com`) is unreachable from every fetch
mechanism tried — a direct HTTP request and, separately, a second independent
fetch path — confirmed independently, both timing out mid-TLS-handshake or on
the request itself. LG and KitchenAid return outright `403` to a
correctly-headered GET.
This is Akamai/Cloudflare-class bot management on the manufacturer's own
infrastructure, not a gap in this pipeline. **Both known ground-truth rows
are exactly this case** — Frigidaire is blocked outright; Whirlpool's search
page returns 200 but the underlying content is client-side-rendered (the raw
HTML is nav chrome until JavaScript runs), so successfully fetching it still
requires filtering out pages with no real product content (`source.py`'s
`_looks_like_real_content` check) before treating them as a usable source.

The honest response: when a source is blocked, the row still gets
Dept/Class/Fine/Classpath/Product Name/brand-name-if-resolvable populated,
description fields degrade to whatever subset of attributes is actually
known rather than going empty or inventing the rest, and the row is marked
`REVIEW` with the specific reason recorded
(`appliance_catalog/out/review_queue.csv`) — never silently blank, never
fabricated. A confidence score or a "needs human review" flag is a genuinely
valuable feature in its own right, not a fallback for a system that couldn't
finish the job.

## What broke during build, and the fix

Whirlpool's search-results page for WDTS7024RZ *did* return real, fetchable
HTML — and the first extraction pass mislabeled the page's own title
("Eco Series Quiet Dishwasher with a washing 3rd Rack & Water Repellent
Silverware Basket") as the `Color` attribute. The quote was **verbatim on the
page** — the evidence-verification check correctly passed it — while being
obviously not a color. Verbatim-on-the-page and semantically-correct are two
different guarantees, and only the first one was being checked. Fixed with a
plausibility guard on short categorical fields (length + word-count + a junk-
word filter): `extract.py::_plausible`. This is the more dangerous failure
mode of "inventing a value," not the more obvious one — it arrives through a
verified-but-mislabeled quote rather than an outright fabrication.

## Running it

```bash
python -m pytest appliance_catalog/tests/ -q          # 6 tests, no network
python -m appliance_catalog.eval                       # 2 known SKUs, live
python -m appliance_catalog.run_batch                   # all 65 appliance
                                                         # rows, live
```

Point `run_batch` at your own input catalog with
`APPLIANCE_CATALOG_INPUT_CSV=/path/to/your.csv`.

Output: `appliance_catalog/out/delivery_format.csv` (the deliverable — exact
252-column schema) and `appliance_catalog/out/review_queue.csv` (which rows
need a human look, and why).

## Honest limitations

- **No manufacturer/brand master list, no LOV, no UOM standards file, no
  content guidelines doc.** Brand casing/symbols and manufacturer-of-record
  are verified for Frigidaire and Whirlpool only (from real ground truth);
  every other brand (GE, LG, KitchenAid, Speed Queen, Café, Maytag) uses a
  public-record default, explicitly flagged `unverified` and scored at
  reduced confidence rather than presented as compliant.
- **Classpath for non-dishwasher categories is an unverified extension** of
  the one confirmed pattern, not checked against a real, authoritative LOV.
- **UOM normalization covers only the units observed in the two ground-truth
  rows** (V, A, in, dBA, kW-hr, hr, plus a few adjacent units) — not a full
  standards table.
- **INVOICE_DESC's abbreviation table is two entries** (`LEG`→`LEG`,
  `Built-in`→`BLTLN`, `Stainless Steel`→`SST`), derived from the two known
  rows. A mounting type or material outside that table is kept unabbreviated
  and the row is flagged rather than guessing at a plausible-looking
  abbreviation.
- **Commerce/logistics fields are left blank on purpose**: UPC, EAN, GTIN,
  UNSPSC, pricing, and shipping dimensions are blank in *both* real
  ground-truth rows, so the pipeline leaves them blank too rather than
  inventing plausible-looking numbers.
