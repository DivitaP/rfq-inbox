""" Matcher: raw line item string -> predictions.json entry """

from __future__ import annotations

import csv
import re
from pathlib import Path

from rfq.normalizer import parse_line, strip_negations

# (catalog_category, sku_prefix) per normalizer category
_FILTER: dict[str, tuple[str, str]] = {
    "hex_cap_screw":    ("hex_cap_screw",    "HHCS-"),
    "hex_bolt":         ("hex_bolt_metric",  "HB-"),
    "hex_nut":          ("hex_nut",          "HN-"),
    "nylock_nut":       ("hex_nut",          "NL-"),
    "flat_washer":      ("flat_washer",      "FW-"),
    "lock_washer":      ("lock_washer",      "LW-"),
    "elbow_90":         ("pipe_fitting",     "EL90-"),
    "ball_valve":       ("ball_valve",       "BV-"),
    "gate_valve":       ("ball_valve",       "GV-"),
    "tee":              ("pipe_fitting",     "TEE-"),
    "coupling":         ("pipe_fitting",     "CPL-"),
    "nipple":           ("pipe_fitting",     "NIP-"),
    "union":            ("pipe_fitting",     "UNION-"),
    "bushing":          ("pipe_fitting",     "BUSH-"),
    "cap":              ("pipe_fitting",     "CAP-"),
    "hose_connector":   ("hose",            "HC-"),
    "hose":             ("hose",            "HOSE-"),
    "hose_clamp":       ("hose",            "CLAMP-"),
    "emt_connector":    ("electrical",      "CONN-EMT-"),
    "emt_coupling":     ("electrical",      "CPL-EMT-"),
    "emt_strap":        ("electrical",      "STRAP-EMT-"),
    "emt":              ("electrical",      "EMT-"),
    "wire_nut":         ("electrical",      "WN-"),
    "breaker":          ("electrical",      "CB-"),
    "thhn_wire":        ("electrical",      "THHN-"),
    "electrical_box":   ("electrical",      "BOX-"),
    "electrical_cover": ("electrical",      "COVER-"),
    "glove":            ("safety",         "GLV-"),
    "safety_glasses":   ("safety",         "SG-"),
    "hard_hat":         ("safety",         "HH-"),
    "shop_towel":       ("misc",           "TOWEL-"),
    "rag":              ("misc",           "RAG-"),
    "padlock":          ("misc",           "PADLOCK-"),
    "shackle":          ("misc",           "SHACKLE-"),
    "duct_tape":        ("misc",           "TAPE-DUCT-"),
    "ptfe_tape":        ("misc",           "TAPE-PTFE-"),
    "pipe_dope":        ("misc",           "PIPE-DOPE-"),
}

# Special attribute extractors (for categories normalizer doesn't cover) 
_THHN_GAUGE = re.compile(r'\b(\d{1,2})\s*awg\b', re.I)
_THHN_REEL  = re.compile(r"\b(\d{3,})\s*(?:'|ft\b|foot|feet)", re.I)
_THHN_COLOR = [
    (re.compile(r'\bblack\b',  re.I), "BLK"),
    (re.compile(r'\bwhite\b',  re.I), "WHT"),
    (re.compile(r'\bred\b',    re.I), "RED"),
    (re.compile(r'\bblue\b',   re.I), "BLU"),
    (re.compile(r'\bgreen\b',  re.I), "GRN"),
    (re.compile(r'\byellow\b', re.I), "YEL"),
    (re.compile(r'\bgray\b',   re.I), "GRY"),
]

def _thhn_attrs(raw: str) -> dict:
    clean = strip_negations(raw)
    gauge = m.group(1) if (m := _THHN_GAUGE.search(clean)) else None
    reel  = m.group(1) if (m := _THHN_REEL.search(raw))    else None  # reel footage can't be negated
    color = next((c for p, c in _THHN_COLOR if p.search(clean)), None)
    return {"gauge": gauge, "color": color, "reel": reel}

_CB_AMPS   = re.compile(r'\b(\d+)\s*a\b', re.I)
_CB_POLES  = re.compile(r'\b(\d+)\s*(?:p\b|pole)', re.I)
_CB_SINGLE = re.compile(r'\bsingle[\s-]?pole\b', re.I)

def _breaker_attrs(raw: str) -> dict:
    amps  = m.group(1) if (m := _CB_AMPS.search(raw))  else None
    poles = "1" if _CB_SINGLE.search(raw) else (m.group(1) if (m := _CB_POLES.search(raw)) else None)
    return {"amps": amps, "poles": poles}

_GLV_MAT  = [(re.compile(r'\bnitrile\b', re.I), "NIT"),
              (re.compile(r'\bleather\b', re.I), "LTH")]
_GLV_SIZE = [(re.compile(r'\bextra\s*large\b|\bXL\b', re.I), "XL"),
              (re.compile(r'\blarge\b|\bL\b(?!\w)',    re.I), "L"),
              (re.compile(r'\bmedium\b|\bM\b(?!\w)',   re.I), "M"),
              (re.compile(r'\bsmall\b|\bS\b(?!\w)',    re.I), "S")]

def _glove_attrs(raw: str) -> dict:
    clean = strip_negations(raw)
    mat  = next((c for p, c in _GLV_MAT  if p.search(clean)), None)
    size = next((s for p, s in _GLV_SIZE if p.search(clean)), None)
    return {"mat": mat, "size": size}

_SG_TINT = [(re.compile(r'\bclear\b', re.I), "CLR"),
             (re.compile(r'\bsmoke\b', re.I), "SMK"),
             (re.compile(r'\bamber\b', re.I), "AMB")]

def _sg_attrs(raw: str) -> dict:
    clean = strip_negations(raw)
    tint = next((c for p, c in _SG_TINT if p.search(clean)), None)
    return {"tint": tint}

_CLAMP_NUM = re.compile(r'#(\d+)')

_HOSE_PUSH = re.compile(r'\bpush\b|\blok\b', re.I)
_HOSE_AIR  = re.compile(r'\bair\b', re.I)

_BUSH_SIZE = re.compile(r'\b(\d+/\d+)\s*x\s*(\d+/\d+)\b'
                         r'|\b(\d+)\s*x\s*(\d+/\d+)\b')

def _bushing_size(raw: str) -> str | None:
    m = _BUSH_SIZE.search(raw)
    if not m:
        return None
    if m.group(1):
        return f"{m.group(1)}x{m.group(2)}"
    return f"{m.group(3)}x{m.group(4)}"

# ── per-category extra-filter functions ──────────────────────────────────────
# Each takes (rows, raw, uom) → filtered rows.
# To add a new category: write a function, add it to _EXTRA_FILTERS below.

_BV_FNPT = re.compile(r'\bfnpt\b|\bnpt\b|\bthreaded\b', re.I)
_BV_SWT  = re.compile(r'\bswt\b|\bsweat\b|\bsolder\b',  re.I)
_HH_YEL  = re.compile(r'\byellow\b', re.I)
_HH_WHT  = re.compile(r'\bwhite\b',  re.I)
_4SQ     = re.compile(r'\b4\s*sq\b', re.I)
_BOX_DEP = re.compile(r'\b(\d+-\d+/\d+|\d+/\d+)\s*(?:deep|dp\b)', re.I)

def _sku_filter(rows: list[dict], token: str) -> list[dict]:
    """Keep rows whose SKU contains token; fall back to all rows if none match."""
    filtered = [r for r in rows if token in r["sku"]]
    return filtered or rows

def _uom_filter(rows: list[dict], uom: str | None) -> list[dict]:
    """Keep rows matching catalog UOM; fall back to all rows if uom is None."""
    if uom is None:
        return rows
    filtered = [r for r in rows if r["uom"] == uom]
    return filtered or rows

def _filter_hose(rows, raw, uom):
    if _HOSE_PUSH.search(raw):
        rows = _sku_filter(rows, "-PUSH")
    elif _HOSE_AIR.search(raw):
        rows = _sku_filter(rows, "-AIR")
    if uom == "RL":
        rows = [r for r in rows if r["uom"] == "RL"]
    elif uom in ("m", "FT"):
        rows = [r for r in rows if r["uom"] == "FT"]
    return rows

def _filter_thhn(rows, raw, uom):
    a = _thhn_attrs(raw)
    if a["gauge"]:
        rows = [r for r in rows if f"-{a['gauge']}-" in r["sku"]]
    if a["color"]:
        rows = [r for r in rows if f"-{a['color']}-" in r["sku"]
                or r["sku"].endswith(f"-{a['color']}")]
    if a["reel"]:
        # fall back to all rows if footage doesn't match a catalog reel size
        rows = _sku_filter(rows, f"-{a['reel']}")
    return rows

def _filter_breaker(rows, raw, uom):
    a = _breaker_attrs(raw)
    if a["amps"]:
        rows = [r for r in rows if f"-{a['amps']}A-" in r["sku"]]
    if a["poles"]:
        rows = [r for r in rows if r["sku"].endswith(f"-{a['poles']}P")]
    return rows

def _filter_glove(rows, raw, uom):
    a = _glove_attrs(raw)
    if a["mat"]:
        rows = [r for r in rows if f"-{a['mat']}-" in r["sku"]]
    if a["size"]:
        rows = [r for r in rows if r["sku"].endswith(f"-{a['size']}")
                or f"-{a['size']}-" in r["sku"]]
    rows = _uom_filter(rows, uom if uom in ("PR", "DZ") else None)
    return rows

def _filter_sg(rows, raw, uom):
    a = _sg_attrs(raw)
    if a["tint"]:
        rows = [r for r in rows if r["sku"].endswith(f"-{a['tint']}")
                or f"-{a['tint']}-" in r["sku"]]
    return rows

def _filter_hose_clamp(rows, raw, uom):
    m = _CLAMP_NUM.search(raw)
    if m:
        rows = [r for r in rows if r["size"] == f"#{m.group(1)}"]
    return rows

def _filter_ball_valve(rows, raw, uom):
    if _BV_FNPT.search(raw):
        rows = _sku_filter(rows, "FNPT")
    elif _BV_SWT.search(raw):
        rows = _sku_filter(rows, "SWT")
    return rows

def _filter_hard_hat(rows, raw, uom):
    if _HH_YEL.search(raw):
        rows = _sku_filter(rows, "-YEL")
    elif _HH_WHT.search(raw):
        rows = _sku_filter(rows, "-WHT")
    return rows

def _filter_shop_towel(rows, raw, uom):
    return _uom_filter(rows, uom if uom in ("RL", "CS") else None)

def _filter_elec_box(rows, raw, uom):
    if _4SQ.search(raw):
        rows = _sku_filter(rows, "4SQ")
    m = _BOX_DEP.search(raw)
    if m:
        rows = _sku_filter(rows, m.group(1))
    return rows

# Registry: category → filter function.  Add new categories here.
_EXTRA_FILTERS: dict[str, object] = {
    "hose":          _filter_hose,
    "thhn_wire":     _filter_thhn,
    "breaker":       _filter_breaker,
    "glove":         _filter_glove,
    "safety_glasses":_filter_sg,
    "hose_clamp":    _filter_hose_clamp,
    "ball_valve":    _filter_ball_valve,
    "hard_hat":      _filter_hard_hat,
    "shop_towel":    _filter_shop_towel,
    "electrical_box":_filter_elec_box,
}

class Matcher:
    def __init__(self, catalog_path: Path, xref_path: Path):
        self._catalog = self._load_catalog(catalog_path)
        self._sku_index = {r["sku"]: r for r in self._catalog}
        self._xref = self._load_xref(xref_path)

    def _load_catalog(self, path: Path) -> list[dict]:
        with open(path, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        for r in rows:
            if r["material"] == "GALV":   # normalize inconsistent catalog code
                r["material"] = "GV"
        return rows

    def _load_xref(self, path: Path) -> dict:
        index: dict = {}
        with open(path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                src = row["source"]
                # Only customer-scoped xrefs are domain-restricted.
                # Competitor and legacy numbers are usable by any customer.
                if src.startswith("customer:"):
                    domain = src.split(":", 1)[1]
                else:
                    domain = None
                index[row["alt_number"]] = {"sku": row["sku"], "domain": domain}
        return index

    def _tokenize(self, raw: str) -> list[str]:
        parts = re.split(r"[|,;]", raw)
        tokens: list[str] = []

        for p in parts:
            words = p.split()

            for w in words:
                tokens.append(w.strip(".,()[]"))

            for i in range(len(words)-1):
                tokens.append(
                    f"{words[i].strip('.,()[]')} {words[i+1].strip('.,()[]')}"
                )

        return tokens

    def _own_sku(self, tokens: list[str]) -> dict | None:
        for t in tokens:
            row = self._sku_index.get(t) or self._sku_index.get(t.upper())

            if row:
                return row

        return None

    def _xref_hit(self, tokens: list[str], domain: str | None) -> str | None:
        for t in tokens:
            entry = self._xref.get(t)
            if entry:
                # domain=None means no info — allow all; otherwise enforce scope
                if domain is None or entry["domain"] is None or entry["domain"] == domain:
                    return entry["sku"]

        return None

    def _catalog_candidates(self, parsed, raw: str) -> list[dict]:
        if not parsed.category:
            return []

        entry = _FILTER.get(parsed.category)
        if not entry:
            return []

        cat_cat, sku_prefix = entry

        size = parsed.size
        if parsed.category == "bushing":
            size = _bushing_size(raw) or size
        if parsed.category == "electrical_box":
            size = None  # depth ("2-1/8") gets extracted as size; don't filter on it

        results = []
        for row in self._catalog:
            if row["category"] != cat_cat:
                continue
            if not row["sku"].startswith(sku_prefix):
                continue
            if size and row["size"] != size:
                continue
            if parsed.material and row["material"] != parsed.material:
                continue
            if parsed.thread and row["thread"] != parsed.thread:
                continue
            if parsed.length and row["length"] and row["length"] != parsed.length:
                continue
            results.append(row)

        return self._extra_filter(parsed.category, results, raw, parsed.uom)

    def _extra_filter(self, cat: str, rows: list[dict], raw: str, uom: str | None) -> list[dict]:
        fn = _EXTRA_FILTERS.get(cat)
        return fn(rows, raw, uom) if fn else rows

    def _resolve_qty(self, parsed, row: dict) -> tuple:
        cat_uom = row["uom"]
        pack_qty = int(row["pack_qty"] or 1)
        cust_qty = parsed.qty
        cust_uom = parsed.uom

        if cust_qty is None:
            return None, cat_uom

        if cust_uom == "m" and cat_uom == "FT":
            return round(cust_qty * 3.2808, 1), "FT"

        if cust_uom == cat_uom:
            return cust_qty, cat_uom

        # EA (or no uom) → pack unit
        if cust_uom in ("EA", None) and cat_uom not in ("EA", "FT", "RL", "m"):
            converted = cust_qty / pack_qty
            if converted == int(converted):
                return int(converted), cat_uom
            return None, cat_uom

        return cust_qty, cat_uom

    _OR_SIZE = re.compile(r'\b(\d+/\d+|\d+-\d+/\d+)\s+or\s+(\d+/\d+|\d+-\d+/\d+|\d+)\b', re.I)

    def match_line(self, raw: str, domain: str | None = None,
                   email_ctx: dict | None = None) -> dict:
        # "1/2 or 3/4 threaded, whichever..." — customer stated alternative sizes
        if self._OR_SIZE.search(raw):
            parsed = parse_line(raw)
            # collect candidates with size filter disabled
            parsed_no_size = parse_line(raw)
            parsed_no_size.size = None
            candidates = [r["sku"] for r in self._catalog_candidates(parsed_no_size, raw)
                          if r["status"] == "active"]
            return {
                "raw": raw,
                "qty": parsed.qty,
                "uom": None,
                "sku": None,
                "abstain": "ambiguous",
                "candidates": candidates,
                "why": "customer stated alternative sizes (or)",
            }

        parsed = parse_line(raw)

        # For "4 30A 2-pole breakers" / "3 12AWG THHN..." the leading count is qty
        if parsed.qty is None and parsed.category in ("breaker", "thhn_wire"):
            m = re.match(r'^(\d+)\s+', raw)
            if m:
                parsed.qty = float(m.group(1))
                parsed.uom = "EA"

        tokens = self._tokenize(raw)

        # 1. direct own-SKU (handles customer citing our discontinued number)
        own = self._own_sku(tokens)

        if own:
            if own["status"] == "discontinued":
                return {
                    "raw": raw,
                    "qty": parsed.qty,
                    "uom": own["uom"],
                    "sku": None,
                    "abstain": "discontinued",
                    "candidates": [own["replaced_by"]] if own["replaced_by"] else [],
                    "why": f"customer cited discontinued SKU {own['sku']}",
                }
            qty, uom = self._resolve_qty(parsed, own)
            return {
                "raw": raw,
                "qty": qty,
                "uom": uom,
                "sku": own["sku"],
                "abstain": None,
                "candidates": [],
                "why": "direct sku match",
            }

        # 2. xref (customer / competitor / legacy cross-reference)
        xref_sku = self._xref_hit(tokens, domain)

        if xref_sku:
            xrow = self._sku_index.get(xref_sku)
            if xrow:
                if xrow["status"] == "discontinued":
                    return {
                        "raw": raw, 
                        "qty": parsed.qty, 
                        "uom": xrow["uom"],
                        "sku": None, 
                        "abstain": "discontinued",
                        "candidates": [xrow["replaced_by"]] if xrow["replaced_by"] else [],
                        "why": f"xref maps to discontinued {xref_sku}",
                    }

                qty, uom = self._resolve_qty(parsed, xrow)
                return {
                    "raw": raw, 
                    "qty": qty, 
                    "uom": uom,
                    "sku": xref_sku, 
                    "abstain": None, 
                    "candidates": [],
                    "why": "xref lookup match"
                }

        # 3. attribute-based catalog filtering
        candidates = self._catalog_candidates(parsed, raw)
        active = [r for r in candidates if r["status"] == "active"]
        disc   = [r for r in candidates if r["status"] == "discontinued"]

        if len(active) == 1:
            # THHN: customer quotes footage ("500 ft"), but catalog sells whole reels
            if parsed.category == "thhn_wire" and parsed.uom == "FT" and parsed.qty:
                m = re.search(r'-(\d+)$', active[0]["sku"])
                if m:
                    reel_ft = int(m.group(1))
                    n = parsed.qty / reel_ft
                    if n == int(n):
                        parsed.qty = int(n)
                    else:
                        parsed.qty = None
                    parsed.uom = "RL"
            qty, uom = self._resolve_qty(parsed, active[0])
            attrs = ", ".join(filter(None, [
                parsed.category, parsed.size, parsed.material,
                parsed.thread, parsed.length
            ]))
            return {
                "raw": raw, 
                "qty": qty, 
                "uom": uom,
                "sku": active[0]["sku"], 
                "abstain": None, 
                "candidates": [],
                "why": f"single match on {attrs}"
            }

        if len(active) > 1:
            return {
                "raw": raw, 
                "qty": parsed.qty, 
                "uom": None,
                "sku": None, 
                "abstain": "ambiguous",
                "candidates": [r["sku"] for r in active],
                "why": f"{len(active)} candidates; need more attributes"
            }

        if len(disc) == 1 and not active:
            return {
                "raw": raw,
                "qty": parsed.qty,
                "uom": disc[0]["uom"],
                "sku": None,
                "abstain": "discontinued",
                "candidates": [disc[0]["replaced_by"]] if disc[0]["replaced_by"] else [],
                "why": f"only match is discontinued {disc[0]['sku']}"
            }

        # Inherit category/material from previous items in the same email when the
        # current raw has only a size (e.g. "20 of the 3/4″" after "1/2 black iron 90s").
        if email_ctx and not parsed.category:
            inherited = False
            if email_ctx.get("category"):
                parsed.category = email_ctx["category"]
                inherited = True
            if email_ctx.get("material") and not parsed.material:
                parsed.material = email_ctx["material"]
                inherited = True
            if inherited:
                candidates = self._catalog_candidates(parsed, raw)
                active = [r for r in candidates if r["status"] == "active"]
                if len(active) == 1:
                    qty, uom = self._resolve_qty(parsed, active[0])
                    return {
                        "raw": raw, "qty": qty, "uom": uom,
                        "sku": active[0]["sku"], "abstain": None, "candidates": [],
                        "why": f"email-context match ({parsed.category}/{parsed.material})"
                    }

        return {
            "raw": raw,
            "qty": parsed.qty,
            "uom": None,
            "sku": None,
            "abstain": "not_in_catalog",
            "candidates": [],
            "why": f"no match for {parsed.category or 'unknown category'}"
        }

    def match_all(
            self,
            lines: dict[str, list[str]],
            domains: dict[str, str] | None = None,
            supersedes: dict[str, str | None] | None = None,
            customer_emails: dict[str, str | None] | None = None,
    ) -> dict:
        sup = supersedes or {}
        # inverse map: old_stem -> new_stem that supersedes it
        superseded_by: dict[str, str] = {old: new for new, old in sup.items() if old}

        result = {}
        for stem, raw_lines in lines.items():
            domain = (domains or {}).get(stem)
            cust = (customer_emails or {}).get(stem)
            items = [self.match_line(r, domain) for r in raw_lines]
            result[stem] = {
                "supersedes": sup.get(stem),
                "superseded_by": superseded_by.get(stem),
                "customer_email": cust,
                "line_items": items,
            }

        return result


def load_matcher(data_dir: Path) -> Matcher:
    return Matcher(
        catalog_path=data_dir / "catalog.csv",
        xref_path=data_dir / "xref.csv",
    )