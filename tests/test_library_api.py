"""Proves the "bring your own catalog" path actually works: a document built
from a plain string (never touching corpus.load_doc), a product class defined
outside schema.py's built-ins, and enrich() called with documents/known_parts
supplied directly. This is the seam an adopting engineer would use to point
the pipeline at their own documents instead of this repo's demo corpus.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from specledger.catalog import InputSKU
from specledger.confidence import ConfidenceModel
from specledger.extract import DETERMINISTIC
from specledger.ingest import IngestedDoc, PageSpan
from specledger.models import DECISION_AUTO, MATCH_EXACT, SourceDoc
from specledger.pipeline import enrich
from specledger.schema import AttributeSpec, ProductClass, register


WIDGET = register(ProductClass(
    key="TEST_WIDGET",
    label="Test Widget",
    attributes=[
        AttributeSpec(
            "voltage_rating", "Voltage Rating", "number", "V",
            required=True, safety_critical=True,
            aliases=("Voltage Rating",),
            plausible_min=1, plausible_max=100,
        ),
    ],
))


def _doc(text: str) -> IngestedDoc:
    src = SourceDoc(
        doc_id="my-own-datasheet", url="", publisher="Acme Corp",
        authority="MFR_DATASHEET", local_path="", sha256="",
        title="Acme Widget-9000 Datasheet", covers=("WIDGET-9000",),
    )
    pages = [PageSpan(page=1, char_start=0, char_end=len(text), width=0, height=0)]
    return IngestedDoc(src, text, pages)


def test_enrich_accepts_caller_supplied_documents():
    doc = _doc("ACME WIDGET-9000\nVoltage Rating: 12 V\n")
    sku = InputSKU("SKU-1", "WIDGET-9000", "Acme Corp",
                   "General purpose test widget", "TEST_WIDGET")

    rec = enrich(sku, model=ConfidenceModel(), extractors=DETERMINISTIC,
                 documents=[doc], known_parts={"WIDGET-9000"})

    assert "voltage_rating" in rec.attributes
    attr = rec.attributes["voltage_rating"]
    assert attr.value == pytest.approx(12.0)
    assert attr.evidence.verified
    assert attr.evidence.match_mode == MATCH_EXACT
    assert attr.decision == DECISION_AUTO


def test_enrich_reports_no_source_when_no_documents_supplied():
    sku = InputSKU("SKU-2", "WIDGET-9000", "Acme Corp",
                   "General purpose test widget", "TEST_WIDGET")
    rec = enrich(sku, model=ConfidenceModel(), extractors=DETERMINISTIC,
                 documents=[], known_parts=set())
    assert rec.attributes == {}
    assert any("no source document" in n for n in rec.notes)


def test_schema_register_rejects_duplicate_key():
    with pytest.raises(ValueError):
        register(ProductClass(key="TEST_WIDGET", label="Duplicate"))
