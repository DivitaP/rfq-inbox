import json
import os
import re
from functools import lru_cache
from pathlib import Path

from langchain_core.tools import tool

from rfq.extractor import _call_llm, _is_not_rfq, _load_fixture
from rfq.parser import ParsedEmail

_FAILURE_MODE = os.environ.get("RFQ_FAILURE_MODE", "")


@lru_cache(maxsize=1)
def _matcher(data_dir: str = "data"):
    from rfq.matcher import load_matcher
    return load_matcher(Path(data_dir))


# ── pipe-table detection ─────────────────────────────────────────────────────
# Matches any line with at least one "|" separator (two non-empty segments).
_PIPE_ROW = re.compile(r'[^\|]+\|[^\|]+')

# ── space-aligned table header detection ─────────────────────────────────────
# Matches lines like "QTY  PART#  DESCRIPTION" or "PART  QTY  DESC".
_SPACE_HDR = re.compile(r'\bQTY\b.*\bPART\b|\bPART\b.*\bQTY\b', re.I)


# ── tools ─────────────────────────────────────────────────────────────────────

@tool
def extract_rfq_cached(email_body: str) -> str:
    """Check the fixture cache for this email body.
    Returns a JSON array of line strings on a cache hit, or the string 'null' on a miss.
    Never calls the LLM and never writes to the cache.
    """
    if _FAILURE_MODE == "always_live":
        return "null"  # simulate cache always missing
    cached = _load_fixture(email_body, None)
    if cached is not None:
        return json.dumps(cached, ensure_ascii=False)
    return "null"


@tool
def extract_rfq_structured(email_body: str) -> str:
    """Try to extract line items from structured table formats without calling the LLM.

    Handles two formats:
      • Pipe-separated tables: 'Part No | Description | Qty'
      • Space-aligned tables with a QTY/PART header row

    Returns a JSON array of verbatim row strings on success, or 'null' if the
    body is unstructured prose that requires LLM extraction.
    """
    lines = email_body.splitlines()

    # ── pipe-separated table ──────────────────────────────────────────────────
    pipe_rows = [l.strip() for l in lines if _PIPE_ROW.search(l.strip())]

    if _FAILURE_MODE == "skip_structured":
        return "null"  # simulate structured parser always failing

    if len(pipe_rows) >= 2:
        data_rows = []
        for row in pipe_rows:
            cells = [c.strip() for c in row.split("|")]
            # A header row has no digit in any cell (e.g. "Part No | Description | Qty")
            is_header = all(not re.search(r"\d", c) for c in cells)
            if not is_header:
                data_rows.append(row)
        if data_rows:
            return json.dumps(data_rows, ensure_ascii=False)

    # ── space-aligned table (QTY / PART# / DESCRIPTION header) ───────────────
    for i, line in enumerate(lines):
        if _SPACE_HDR.search(line):
            data_rows = []
            for data_line in lines[i + 1:]:
                stripped = data_line.strip()
                if not stripped:
                    break
                # Data rows start with a digit (the qty field)
                if re.match(r"^\d", stripped):
                    data_rows.append(stripped)
            if data_rows:
                return json.dumps(data_rows, ensure_ascii=False)

    return "null"


@tool
def extract_rfq_live(email_body: str) -> str:
    """Call the LLM extractor for this email body (cache miss + no structured format).
    Does NOT write to the fixture cache so the cache-miss routing stays stable across runs.
    """
    parsed = ParsedEmail(
        stem="harness",
        sender="",
        date="",
        message_id="",
        in_reply_to="",
        subject="",
        body=email_body,
    )
    if _is_not_rfq(parsed):
        return json.dumps([], ensure_ascii=False)
    lines = _call_llm(email_body)
    return json.dumps(lines, ensure_ascii=False)


@tool
def match_catalog(lines_json: str, domain: str | None = None) -> str:
    """Match extracted RFQ line items against the catalog.
    Returns a JSON array of results.
    """
    from rfq.normalizer import parse_line

    lines = json.loads(lines_json)
    m = _matcher()
    items, email_ctx = [], {}
    for raw in lines:
        item = m.match_line(raw, domain, email_ctx=email_ctx)
        items.append(item)
        if item["sku"]:
            p = parse_line(raw)
            if p.category:
                email_ctx["category"] = p.category
            if p.material:
                email_ctx["material"] = p.material
    return json.dumps(items, ensure_ascii=False)
