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
    'Return ONLY a JSON object: {"lines": [...]} where each element is a verbatim '
    "string exactly as written in the email — one string per item a sales rep would quote. "
    "Keep the text verbatim including leading words like 'and' or 'also'. "
    "Strip parenthetical explanations e.g. '(thats our part number)' and trailing "
    "purpose phrases e.g. 'for the hanger brackets'. "
    "Exclude signatures, greetings, delivery dates, price commentary, quoted reply text. "
    'Return {"lines": []} if nothing to quote.'
)

def _body_hash(body: str) -> str:
    return hashlib.sha256(body.encode()).hexdigest()[:16]

def _load_fixture(body: str) -> list[str] | None:
    path = FIXTURES_DIR / f"{_body_hash(body)}.json"
    if path.exists():
        return json.loads(path.read_text())

    return None

def _save_fixture(body: str, lines: list[str]) -> None:
    path = FIXTURES_DIR / f"{_body_hash(body)}.json"
    path.write_text(json.dumps(lines, ensure_ascii=False, indent=2))

def _call_llm(body: str) -> list[str]:

    groq_key = os.environ.get("GROQ_API_KEY")
    openai_key = os.environ.get("OPENAI_API_KEY")

    if groq_key:
        client = OpenAI(
            api_key=groq_key,
            base_url="https://api.groq.com/openai/v1",
        )
        model = "openai/gpt-oss-120b"
    elif openai_key:
        client = OpenAI(api_key=openai_key)
        model = "gpt-4o-mini"
    else:
        return []

    resp = client.chat.completions.create(
        model=model,
        temperature=0,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": f"Email body: \n\n{body}"},
        ],
    )
    data = json.loads(resp.choices[0].message.content)
    return data.get("lines", [])

def _llm_extract(body: str) -> list[str]:
    cached = _load_fixture(body)
    if cached is not None:
        return cached

    if not os.environ.get("GROQ_API_KEY") and not os.environ.get("OPENAI_API_KEY"):
        return []

    lines = _call_llm(body)
    _save_fixture(body, lines)

    return lines

def extract_lines(parsed: ParsedEmail) -> list[str]:
    if parsed.has_pending_attachment:
        return []
    if _is_not_rfq(parsed):
        return []
    if _is_unresolvable(parsed):
        return []
    if parsed.csv_rows:
        return _lines_from_csv(parsed.csv_rows)

    return _llm_extract(parsed.body)

def extract_all(emails: dict[str, ParsedEmail]) -> dict[str, list[str]]:
    result = {}
    for stem, parsed in emails.items():
        if _is_duplicate(parsed):
            result[stem] = []
        else:
            result[stem] = extract_lines(parsed)

    return result