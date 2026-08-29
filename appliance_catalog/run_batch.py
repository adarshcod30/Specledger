"""Batch runner: a raw catalog input -> Major Appliances rows -> full 252-column
Delivery Format CSV, plus a companion review-queue CSV.

Run: .venv/bin/python -m appliance_catalog.run_batch
Point it at your own input with APPLIANCE_CATALOG_INPUT_CSV=/path/to/input.csv
"""
from __future__ import annotations

import csv
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from appliance_catalog.export import write_csv, write_review_log             # noqa: E402
from appliance_catalog.extract import AttributeExtractor                     # noqa: E402
from appliance_catalog.pipeline import InputRow, run_row                     # noqa: E402
from appliance_catalog.taxonomy import classify                               # noqa: E402

INPUT_CSV = os.environ.get("APPLIANCE_CATALOG_INPUT_CSV",
                            "appliance_catalog/data/sample_input.csv")
OUT_CSV = "appliance_catalog/out/delivery_format.csv"
REVIEW_CSV = "appliance_catalog/out/review_queue.csv"

NON_APPLIANCE_MANUF_EXCLUDE = {"Milwaukee Accessory (4031)", "Black & Decker/dewlt (2585)"}


def load_appliance_rows() -> list[InputRow]:
    rows = []
    with open(INPUT_CSV, newline="", encoding="utf-8") as f:
        for raw in csv.DictReader(f):
            if raw["Part_Manuf"] in NON_APPLIANCE_MANUF_EXCLUDE:
                continue
            if not classify(raw["Part_Desc"]):
                continue
            rows.append(InputRow(
                mfg_part_num=raw["Mfg_Part_Num"], part_desc=raw["Part_Desc"],
                e1_brand=raw["E1_Brand"], unilog_brand=raw["Unilog_Brand"],
                dib_brand=raw["DIB_Brand"], part_manuf=raw["Part_Manuf"]))
    return rows


def main():
    rows = load_appliance_rows()
    print(f"{len(rows)} Major Appliances rows identified in the 1000-item input")
    extractor = AttributeExtractor()
    outputs = []
    log_rows = []
    t0 = time.time()
    for i, row in enumerate(rows, 1):
        try:
            out = run_row(row, extractor=extractor)
        except Exception as e:
            from appliance_catalog.pipeline import OutputRow
            out = OutputRow()
            out.set("Mfg_Part_Num", row.mfg_part_num)
            out.set("Part_Desc", row.part_desc)
            out.reasons.append(f"pipeline error: {type(e).__name__}: {e}")
        outputs.append(out)
        log_rows.append((row.mfg_part_num, out))
        elapsed = time.time() - t0
        print(f"[{i:3d}/{len(rows)}] {row.mfg_part_num:16s} "
              f"decision={out.decision:12s} conf={out.confidence:.2f} "
              f"({elapsed:6.1f}s elapsed)", flush=True)

    write_csv(outputs, OUT_CSV)
    write_review_log(log_rows, REVIEW_CSV)

    n_auto = sum(1 for o in outputs if o.decision == "AUTO_PUBLISH")
    print(f"\n{len(outputs)} rows written to {OUT_CSV}")
    print(f"{n_auto} auto-published, {len(outputs)-n_auto} routed to review "
          f"({REVIEW_CSV})")
    print(f"total time: {time.time()-t0:.1f}s")


if __name__ == "__main__":
    main()
