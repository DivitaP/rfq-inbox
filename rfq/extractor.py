""" Extractor: ParsedEmail -> list[line strings (accurate)] """

from __future__ import annotations
import hashlib
import json
import os
import re
from pathlib import Path
from openai import OpenAI

from rfq.parser import ParsedEmail

FIXTURES_DIR = Path(__file__).parent / "fixtures"
FIXTURES_DIR.mkdir(exist_ok=True)

_VENDOR_SIGNALS = re.compile(
    r'unit\s+price|fob\s+\w|valid\s+\d+\s+days|quote\s*#\s*\w',
    re.IGNORECASE,
)

_UNRESOLVABLE = re.compile(
    r'\bsame\s+as\s+(po|order|p\.o\.)\b',
    re.IGNORECASE,
)

_RESEND = re.compile(r'\bresend\b', re.IGNORECASE)

def _is_not_rfq(parsed: ParsedEmail) -> bool:
    matches = _VENDOR_SIGNALS.findall(parsed.body)
    return len(matches) >= 2

def _is_unresolvable(parsed: ParsedEmail) -> bool:
    return bool(_UNRESOLVABLE.search(parsed.body))

def _is_duplicate(parsed: ParsedEmail) -> bool:
    return bool(_RESEND.search(parsed.subject))

def _lines_from_csv(rows: list[list[str]]) -> list[str]:
    lines = []
    for row in rows:
        if not row:
            continue
        if not re.match(r'^\d', row[0].strip()):
            continue
        lines.append(",".join(cell.strip() for cell in row))

    return lines

_SYSTEM = (
    "You extract line items from RFQ email bodies for an industrial distributor. "
    'Return ONLY a JSON object: {"lines": [...]} where each element is one string per '
    "item a sales rep would quote. "
    "Preserve each line as close to verbatim as the customer wrote it — keep part numbers, "
    "customer/vendor reference codes (e.g. 'AF-04202', 'RL-77981', 'NF/27937/567'), "
    "pipe separators, and embedded quantity notation like 'qty N'. "
    "Preserve vague quantity words exactly as written (e.g. 'a couple of', 'a few', 'some') "
    "— do not replace them with a number or drop them. "
    "For pipe-separated tables (code | description | qty), include each data row verbatim. "
    "For space-aligned tables (columns separated by multiple spaces), include each data row verbatim. "
    "Strip trailing purpose phrases (e.g. 'for the hanger brackets'). "
    "Exclude signatures, greetings, delivery dates, price preferences, quoted reply text. "
    'Return {"lines": []} if nothing to quote.'
)

_SYSTEM_DELTA = (
    "You extract line items from an RFQ follow-up email for an industrial distributor. "
    "The customer's PREVIOUS order is listed below as context — these are the raw customer "
    "lines from their original email. Their new email modifies the order.\n"
    'Return ONLY a JSON object: {"lines": [...]} containing the COMPLETE updated order — '
    "every item that should now be quoted. "
    "For changed items: write a clear, matchable description using the previous order for "
    "context (e.g. '80 – 1/2 inch black iron 90 elbows' not 'make the 1/2 90s 80 not 50'). "
    "For unchanged items: copy the customer line from the previous order exactly as shown. "
    "For new items: use the text as written in the follow-up. "
    'Return {"lines": []} only if the follow-up contains no quotable items at all.'
)

def _body_hash(body: str) -> str:
    return hashlib.sha256(body.encode()).hexdigest()[:16]

def _context_hash(parent_context: list[dict]) -> str:
    s = json.dumps(parent_context, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(s.encode()).hexdigest()[:8]

_PROMPT_VERSION = hashlib.sha256((_SYSTEM + _SYSTEM_DELTA).encode()).hexdigest()[:8]

def _fixture_key(body: str, parent_context) -> str:
    key = f"{_body_hash(body)}_{_PROMPT_VERSION}"
    if parent_context:
        key += f"_{_context_hash(parent_context)}"
    return key

def _load_fixture(body: str, parent_context: list[dict] | None = None) -> list[str] | None:
    path = FIXTURES_DIR / f"{_fixture_key(body, parent_context)}.json"
    if path.exists():
        return json.loads(path.read_text())
    return None

def _save_fixture(body: str, lines: list[str], parent_context: list[dict] | None = None) -> None:
    path = FIXTURES_DIR / f"{_fixture_key(body, parent_context)}.json"
    path.write_text(json.dumps(lines, ensure_ascii=False, indent=2))

def _make_client():
    groq_key = os.environ.get("GROQ_API_KEY")
    openai_key = os.environ.get("OPENAI_API_KEY")
    if groq_key:
        return OpenAI(api_key=groq_key, base_url="https://api.groq.com/openai/v1"), "openai/gpt-oss-120b"
    if openai_key:
        return OpenAI(api_key=openai_key), "gpt-4o"
    return None, None

def _call_llm(body: str) -> list[str]:
    client, model = _make_client()
    if not client:
        return []
    resp = client.chat.completions.create(
        model=model,
        temperature=0,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": f"Email body:\n\n{body}"},
        ],
    )
    data = json.loads(resp.choices[0].message.content)
    return data.get("lines", [])

def _call_llm_delta(body: str, parent_context: list[dict]) -> list[str]:
    client, model = _make_client()
    if not client:
        return []
    # Show only customer text — no SKU annotations so the LLM doesn't copy them verbatim
    prev = "\n".join(f"- {p['raw']}" for p in parent_context)
    resp = client.chat.completions.create(
        model=model,
        temperature=0,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": _SYSTEM_DELTA},
            {"role": "user", "content": f"Previous order:\n{prev}\n\nFollow-up email:\n{body}"},
        ],
    )
    data = json.loads(resp.choices[0].message.content)
    return data.get("lines", [])

def _llm_extract(body: str, parent_context: list[dict] | None = None) -> list[str]:
    cached = _load_fixture(body, parent_context)
    if cached is not None:
        return cached

    if not os.environ.get("GROQ_API_KEY") and not os.environ.get("OPENAI_API_KEY"):
        return []

    lines = _call_llm_delta(body, parent_context) if parent_context else _call_llm(body)
    _save_fixture(body, lines, parent_context)
    return lines

def extract_lines(parsed: ParsedEmail, parent_context: list[dict] | None = None) -> list[str]:
    if parsed.has_pending_attachment:
        return []
    if _is_not_rfq(parsed):
        return []
    if _is_unresolvable(parsed):
        return []
    if parsed.csv_rows:
        return _lines_from_csv(parsed.csv_rows)
    return _llm_extract(parsed.body, parent_context)

def extract_all(emails: dict[str, ParsedEmail]) -> dict[str, list[str]]:
    result = {}
    for stem, parsed in emails.items():
        if _is_duplicate(parsed):
            result[stem] = []
        else:
            result[stem] = extract_lines(parsed)

    return result