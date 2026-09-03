""" Normalizer: raw line string -> structured attributes for catalog matching """

from __future__ import annotations

import re
from dataclasses import dataclass

# unicode / decimal → catalog fraction
_UNICODE_FRACS = {
    "½": "1/2", "¼": "1/4", "¾": "3/4",
    "⅜": "3/8", "⅝": "5/8", "⅞": "7/8",
}

_DECIMAL_FRACS = {
    "0.125": "1/8", "0.250": "1/4", "0.375": "3/8",
    "0.500": "1/2", "0.625": "5/8", "0.750": "3/4",
    "0.875": "7/8",
}

def normalize_text(text: str) -> str:
    for ch, frac in _UNICODE_FRACS.items():
        text = text.replace(ch, frac)
    text = text.replace("″", " in")   # double prime ″ → inch marker
    text = text.replace("′", " ft")   # prime ′ → foot marker
    text = text.replace("”", " in")  # curly right double quote " → inch
    text = text.replace("“", " in")  # curly left double quote " → inch

    def _dec_sub(m: re.Match) -> str:
        return _DECIMAL_FRACS.get(m.group(1), m.group(0))

    text = re.sub(r'\b(0\.\d{3})\b', _dec_sub, text)
    return text

# material

_MATERIAL_PATTERNS = [
    (r'black\s+iron|(?<!\w)bi(?!\w)', "BI"),
    (r'stainless(?:\s+steel)?|(?<!\w)ss(?!\w)|18-8', "SS"),
    (r'galv(?:anized)?|(?<!\w)gv(?!\w)', "GV"),
    (r'zinc(?:\s+plat\w*)?|(?<!\w)zp(?!\w)', "ZP"),
    (r'plain(?:\s+steel)?|(?<!\w)pl(?!\w)', "PL"),
    (r'\bbrass\b|(?<!\w)br(?!\w)', "BR"),
    (r'\bpvc\b', "PVC"),
    (r'class\s*8\.8\b|(?<!\d)8\.8(?!\d)', "8.8"),
    (r'class\s*a2\b|\ba2\b', "A2"),
]

_NEGATION = re.compile(
    r'\b(?:not|no|without|except)\s+(?:the\s+)?(?:\w+(?:\s+\w+)?)',
    re.I,
)

def strip_negations(text: str) -> str:
    return _NEGATION.sub(' ', text)

def extract_material(text: str) -> str | None:
    t = strip_negations(text).lower()

    for pattern, code in _MATERIAL_PATTERNS:
        if re.search(pattern, t):
            return code

    return None

# category

_CATEGORY_PATTERNS = [
    (r'hex\s+cap(?:\s+screw)?|hhcs|(?<!\w)hcs(?!\w)', "hex_cap_screw"),
    (r'hex\s+bolt|(?<!\w)hb(?!\w)', "hex_bolt"),
    (r'hex\s+nut|(?<!\w)hn(?!\w)', "hex_nut"),
    (r'nylock|nyloc', "nylock_nut"),
    (r'flat\s+washer|(?<!\w)fw(?!\w)', "flat_washer"),
    (r'lock\s+washer|(?<!\w)lw(?!\w)', "lock_washer"),
    (r'90.{0,3}elbow|el(?:bow)?\s*90|90\s*°|(?<!\w)ell?\b|(?<!\w)90s\b', "elbow_90"),
    (r'ball\s+valve|(?<!\w)bv(?!\w)', "ball_valve"),
    (r'gate\s+valve', "gate_valve"),
    (r'(?<!\w)tees?\b', "tee"),
    (r'emt\s*set\s*screw\s*coupl|cpl.*emt', "emt_coupling"),
    (r'\bcouplings?\b|(?<!\w)cpl(?!\w)', "coupling"),
    (r'\bnipples?\b|(?<!\w)nip(?!\w)', "nipple"),
    (r'\bunion\b', "union"),
    (r'\bbushings?\b|(?<!\w)bush(?!\w)', "bushing"),
    (r'(?<!\w)caps?\b', "cap"),
    (r'push.?lo[ck]k?\s*barb|hose\s*connector', "hose_connector"),
    (r'hose\s*clamps?|\bclamps?\b', "hose_clamp"),
    (r'\bhose\b', "hose"),
    (r'emt\s*set\s*screw\s*connector|conn.*emt', "emt_connector"),
    (r'emt\s*strap|one\s*hole\s*strap', "emt_strap"),
    (r'\bemt\b', "emt"),
    (r'wire\s*nut', "wire_nut"),
    (r'\bbreakers?\b', "breaker"),
    (r'\bthhn\b|\bthwn\b|\bground\s+wire\b', "thhn_wire"),
    (r'\d\s*sq\b.*box|sq\s*box', "electrical_box"),
    (r'blank\s*cover|sq\s*cover', "electrical_cover"),
    (r'\bgloves?\b', "glove"),
    (r'safety\s*glass', "safety_glasses"),
    (r'hard\s*hat', "hard_hat"),
    (r'shop\s*towel|\btowel\b', "shop_towel"),
    (r'\brags?\b', "rag"),
    (r'\bpadlocks?\b', "padlock"),
    (r'\bshackles?\b', "shackle"),
    (r'duct\s*tape', "duct_tape"),
    (r'ptfe\s*tape', "ptfe_tape"),
    (r'pipe\s*dope', "pipe_dope"),
]

def extract_category(text: str) -> str | None:
    t = text.lower()

    for pattern, cat in _CATEGORY_PATTERNS:
        if re.search(pattern, t):
            return cat

    return None

# quantity

_VAGUE = re.compile(r'\ba\s+couple\b|\ba\s+few\b|\bsome\b', re.I)

_QTY_PATTERNS = [
    (re.compile(r'(\d+(?:\.\d+)?)\s*(?:meters?|m\b)', re.I), "m"),
    (re.compile(r'(\d+(?:\.\d+)?)\s*(?:ft\.?|feet|foot)', re.I), "FT"),
    (re.compile(r'(\d+)\s*(?:reels?|rolls?|rl\b)', re.I), "RL"),
    (re.compile(r'(\d+)\s*(?:boxes?|bx\b)', re.I), "BX"),
    (re.compile(r'(\d+)\s*(?:bags?|bg\b)', re.I), "BG"),
    (re.compile(r'(\d+)\s*(?:cases?|cs\b)', re.I), "CS"),
    (re.compile(r'(\d+)\s*(?:dozens?|dz\b)', re.I), "DZ"),
    (re.compile(r'(\d+)\s*(?:pairs?|pr\b)', re.I), "PR"),
    (re.compile(r'(\d+)\s*(?:pcs?\.?|pieces?|ea\.?|each)', re.I), "EA"),
    (re.compile(r'(\d+)\s*×', re.I), "EA"),
    (re.compile(r'qty\s*:?\s*(\d+)', re.I), "EA"),
    (re.compile(r'\|\s*(\d+)\s*(?:BX|EA|RL|PR|BG|CS)?\s*(?:\||$)', re.I), "EA"),
]

def extract_qty(raw: str) -> tuple[float | None, str | None]:
    if _VAGUE.search(raw):
        return None, None
    raw = re.sub(r'\bnot\s+\d+\b', '', raw, flags=re.I)   # "80 not 50" → 80

    # numbered list "N) count – spec": "1) 100 – hhcs..."
    m = re.match(r'^\d+\)\s*(\d+)\s*[-–]', raw)
    if m:
        return float(m.group(1)), "EA"

    # leading integer with explicit separator takes priority over UOM patterns:
    # "200 – hhcs...", "100,HHCS...", "50 of the...", "4    --  1in PVC conduit 10ft"
    # This prevents "10ft" in trailing length specs from stealing the qty.
    m = re.match(r'^(\d+)\s*(?:[-–,×x]|\s+of\b)', raw)
    if m:
        return float(m.group(1)), "EA"

    # UOM-based patterns (meters, ft, dozens, boxes, etc.)
    for pattern, uom in _QTY_PATTERNS:
        m = pattern.search(raw)
        if m:
            return float(m.group(1)), uom

    # embedded "N of": "add 10 of the...", "and 20 of the..."
    m = re.search(r'\b(\d+)\s+of\b', raw)
    if m:
        return float(m.group(1)), "EA"

    # bare leading integer followed by a letter (not a fraction like "3/4"):
    # "100 hex cap screws" → 100; won't match "3/4 ball valve" (starts with fraction)
    # Only runs when no UOM or leading-separator pattern matched.
    m = re.match(r'^(\d+)\s+(?=[A-Za-z])', raw)
    if m:
        return float(m.group(1)), "EA"

    # trailing number: "3/4 x 1/2 brass bushings, 10" or "EL 90 3/4 BRASS 15"
    m = re.search(r'[\s,]\s*(\d+)\s*$', raw)
    if m:
        return float(m.group(1)), "EA"

    return None, None

# size, thread, length

def extract_size(text: str) -> str | None:
    text = normalize_text(text)
    # metric: M12
    m = re.search(r'\bM(\d+)\b', text, re.I)
    if m:
        return f"M{m.group(1)}"
    # imperial fastener size-thread anchor: "3/8-16" → 3/8 (avoids grabbing length)
    m = re.search(r'\b(\d+/\d+)-\d+\b', text)
    if m:
        return m.group(1)
    # mixed number: 2-1/2
    m = re.search(r'\b(\d+-\d+/\d+)\b', text)
    if m:
        return m.group(1)
    # simple fraction: 1/2
    m = re.search(r'\b(\d+/\d+)\b', text)
    if m:
        return m.group(1)
    # inch suffix: "1-inch", "3/4 in", "1 in", "1in"
    m = re.search(r'\b(\d+/\d+|\d+)[-\s]*(?:inch(?:es)?|in\.?\b)', text, re.I)
    if m:
        return m.group(1)
    return None


def extract_thread(text: str) -> str | None:
    text = normalize_text(text)
    # imperial: 1/2-13
    m = re.search(r'(?:\d+/\d+|\d+-\d+/\d+)-(\d+)(?!\.\d)', text)
    if m:
        return m.group(1)
    # metric explicit: M12 x 1.75
    m = re.search(r'[Mm]\d+\s*[xX]\s*(\d+\.\d+)', text)
    if m:
        return m.group(1)
    return None


def extract_length(text: str) -> str | None:
    text = normalize_text(text)
    # x <length>  e.g. "x 2-1/2" or "x 1"  — (?!\.) avoids grabbing "1" from "x 1.75"
    m = re.search(r'\bx\s+(\d+-\d+/\d+|\d+/\d+|\d+)(?!\.)(?:\b|$)', text, re.I)
    if m:
        return m.group(1)
    return None

# top level parsed line

@dataclass
class ParsedLine:
    raw: str
    qty: float | None
    uom: str | None
    category: str | None
    size: str | None
    material: str | None
    thread: str | None
    length: str | None

def parse_line(raw: str) -> ParsedLine:
    normalized = normalize_text(raw)
    qty, uom = extract_qty(raw)
    return ParsedLine(
        raw=raw,
        qty=qty,
        uom=uom,
        category=extract_category(normalized),
        size=extract_size(normalized),
        material=extract_material(normalized),
        thread=extract_thread(normalized),
        length=extract_length(normalized),
    )