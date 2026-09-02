"""
Offline matcher test suite. Tests match_line() directly — no LLM, no API key needed.
Run from the project root:  python tests/test_matcher.py
"""

from __future__ import annotations
from pathlib import Path
from rfq.matcher import load_matcher

matcher = load_matcher(Path("data"))

PASS = "\033[92mPASS\033[0m"
FAIL = "\033[91mFAIL\033[0m"
INFO = "\033[94mINFO\033[0m"

results = []

def check(label: str, raw: str, *,
          sku: str | None = None,
          abstain: str | None = None,
          qty: float | int | None = ...,
          uom: str | None = ...,
          candidates_include: list[str] | None = None,
          domain: str | None = None):
    r = matcher.match_line(raw, domain=domain)
    ok = True
    notes = []

    if sku is not None:
        if r["sku"] != sku:
            ok = False; notes.append(f"sku: expected {sku!r}, got {r['sku']!r}")
    if abstain is not None:
        if r["abstain"] != abstain:
            ok = False; notes.append(f"abstain: expected {abstain!r}, got {r['abstain']!r}")
    if qty is not ...:
        if r["qty"] != qty:
            ok = False; notes.append(f"qty: expected {qty!r}, got {r['qty']!r}")
    if uom is not ...:
        if r["uom"] != uom:
            ok = False; notes.append(f"uom: expected {uom!r}, got {r['uom']!r}")
    if candidates_include is not None:
        for c in candidates_include:
            if c not in (r.get("candidates") or []):
                ok = False; notes.append(f"candidates missing {c!r}: {r.get('candidates')}")

    tag = PASS if ok else FAIL
    results.append(ok)
    print(f"{tag}  {label}")
    if not ok:
        for n in notes:
            print(f"       {n}")
        print(f"       raw:  {raw}")
        print(f"       got:  sku={r['sku']} abstain={r['abstain']} qty={r['qty']} {r['uom']}  why={r['why']}")
    return r


def info(label: str, raw: str, domain: str | None = None):
    r = matcher.match_line(raw, domain=domain)
    print(f"{INFO}  {label}")
    print(f"       sku={r['sku']} abstain={r['abstain']} qty={r['qty']} {r['uom']}")
    print(f"       candidates={r.get('candidates')}  why={r['why']}")
    return r


print("=" * 70)
print("SECTION 1 — Normalization: decimals, unicode, prime chars")
print("=" * 70)

check("Decimal size 0.750 → 3/4 brass ball valve",
      "6 – 0.750 inch brass ball valves threaded",
      sku="BV-3/4-BR-FNPT", qty=6.0)

check("Unicode fraction ½ in elbow",
      "20 – ½ inch black iron 90 elbows",
      sku="EL90-1/2-BI", qty=20.0)

check("Double-prime ″ as inch marker",
      '10 – 3/4″ black iron tees',
      sku="TEE-3/4-BI", qty=10.0)

check("Metric bolt with decimal pitch — extract_length must skip 'x 1.75', take 'x 40'",
      "60 – M12 x 1.75 x 40 hex bolt class 8.8",
      sku="HB-M12-1.75x40-8.8", qty=60.0)


print()
print("=" * 70)
print("SECTION 2 — Negation stripping")
print("=" * 70)

check("NOT nitrile → leather gloves",
      "6 pair leather gloves large, NOT nitrile",
      sku="GLV-LTH-L", qty=6.0, uom="PR")

check("not galvanized, zinc → ZP hex cap screws (no separator → qty=None is correct)",
      "200 hex cap screws 3/8-16 x 1, not galvanized, zinc",
      sku="HHCS-3/8-16x1-ZP")   # qty not asserted: no separator after 200

check("not brass 90 elbow → black iron",
      "10 – 1/2 inch 90 elbows, not the brass, black iron",
      sku="EL90-1/2-BI", qty=10.0)

check("not small → large nitrile gloves",
      "12 pairs nitrile gloves, NOT small, large",
      sku="GLV-NIT-L", qty=12.0, uom="PR")

info("safety glasses 'not clear' → still ambiguous (SMK or AMB left)",
     "4 safety glasses, not clear")


print()
print("=" * 70)
print("SECTION 3 — Quantity resolution: packs, metric, THHN reels, vague")
print("=" * 70)

check("400 EA hex nuts → 4 BX (pack_qty=100)",
      "400 ea 3/8-16 hex nuts zinc",
      sku="HN-3/8-16-ZP", qty=4, uom="BX")

check("1000 ft THHN → 2 RL (2 × 500ft reels)",
      "1000 ft 12 AWG THHN black",
      sku="THHN-12-BLK-500", qty=2, uom="RL")

check("30 meters push-lok hose → 98.4 FT",
      "30 meters of 1/2 push-lok hose",
      sku="HOSE-1/2-PUSH", qty=98.4, uom="FT")

check("vague 'a couple' → SKU matched but qty=null (vague ≠ abstain)",
      "a couple 3/4 brass ball valves threaded",
      sku="BV-3/4-BR-FNPT", qty=None)   # vague qty → null; SKU is still determinable

check("250 ft THHN — right SKU, qty=null (250 doesn't divide into 500ft reels)",
      "250 ft 10 AWG THHN green",
      sku="THHN-10-GRN-500", qty=None, uom="RL")

check("2 BX lock washers → 2 BX direct (UOM already matches)",
      "2 bx 3/8 lock washers zinc",
      sku="LW-3/8-ZP", qty=2.0, uom="BX")

check("2 dozen nitrile gloves medium → GLV-NIT-M-DZ qty=2 DZ",
      "2 dozen nitrile gloves medium",
      sku="GLV-NIT-M-DZ", qty=2.0, uom="DZ")


print()
print("=" * 70)
print("SECTION 4 — Ambiguity: must abstain, never guess")
print("=" * 70)

check("or-size: 1/2 or 3/4 → ambiguous immediately",
      "20 – 1/2 or 3/4 galv elbows 90",
      abstain="ambiguous")

check("no material on 3/4 90 elbow → ambiguous",
      "6 – 3/4 90 elbows",
      abstain="ambiguous",
      candidates_include=["EL90-3/4-BR", "EL90-3/4-BI"])

info("ball valve no material — catalog has only one active 1-inch ball valve → matches",
     "4 – 1 inch ball valves")   # BV-1-BR-FNPT is only 1-inch active SKU

check("PVC ball valve → not_in_catalog",
      "4 – 3/4 PVC ball valve",
      abstain="not_in_catalog")

check("401 ea hex nuts (not divisible by 100) → qty=null",
      "401 ea 3/8-16 hex nuts zinc",
      sku="HN-3/8-16-ZP", qty=None)


print()
print("=" * 70)
print("SECTION 5 — Discontinued: own SKU and via xref")
print("=" * 70)

check("own discontinued SKU cited → abstain:discontinued with replaced_by",
      "EL90-1/2-GALV x 25",
      abstain="discontinued",
      candidates_include=["EL90-1/2-GV"])

check("legacy xref → discontinued SKU → abstain:discontinued",
      "RL-89466 x 10",        # RL-89466 → EL90-1/2-GALV (discontinued)
      abstain="discontinued",
      candidates_include=["EL90-1/2-GV"])

check("own discontinued HHCS-CD cited → abstain:discontinued",
      "HHCS-1/2-13x2-CD x 100",
      abstain="discontinued",
      candidates_include=["HHCS-1/2-13x2-ZP"])


print()
print("=" * 70)
print("SECTION 6 — xref: domain scoping, competitor bigrams, wrong domain")
print("=" * 70)

check("acme-fab customer xref (correct domain)",
      "AF-04202 x 200",
      sku="HHCS-1/2-13x2-SS", qty=200.0,
      domain="acme-fab.com")

check("acme-fab xref from wrong domain → falls through to attribute match",
      "AF-04202 x 200",
      domain="some-other-company.com")  # no assertion on sku — just info

check("competitor Boltwright single-token xref (any domain)",
      "BW-0081366 x 50",
      sku="HHCS-1/2-13x2-ZP", qty=50.0)

check("competitor IronPeak BIGRAM xref (two-word alt number)",
      "IP 26842-0649 x 20",
      sku="EL90-1/2-BR", qty=20.0)

check("tristate xref from wrong domain → falls through to no category → not_in_catalog",
      "TSM24720 x 10",
      domain="acme-fab.com",   # TSM is scoped to tristate-mechanical.com
      abstain="not_in_catalog") # 'TSM24720' has no category signal → not_in_catalog

check("legacy xref (any domain)",
      "RL-62569 x 15",
      sku="EL90-1/2-BI", qty=15.0)


print()
print("=" * 70)
print("SECTION 7 — Novel / unknown material codes (held-out risk)")
print("=" * 70)

info("GI (galvanized iron) — not in _MATERIAL_PATTERNS → no material extracted",
     "30 – GI nipples 3/4")

info("HDG (hot-dip galvanized) — not in patterns",
     "20 – HDG hex cap screws 3/8-16 x 1")

info("CS (carbon steel) — not in patterns",
     "50 – 1/2 CS hex cap screws 1/2-13 x 2")

info("A2 stainless (IS in patterns)",
     "20 – M12 x 40 hex bolt class A2")

info("THWN alias (IS in patterns)",
     "THWN 12 AWG white 500 ft")

info("ground wire alias (IS in patterns)",
     "10 AWG green ground wire 500 ft")


print()
print("=" * 70)
print("SECTION 8 — Category pattern edge cases")
print("=" * 70)

check("'hex cap' without 'screw' → hex_cap_screw",
      "50 – 3/8-16 x 1 hex cap zinc",
      sku="HHCS-3/8-16x1-ZP", qty=50.0)

check("'90s' shorthand → elbow_90",
      "20 – 1/2 black iron 90s",
      sku="EL90-1/2-BI", qty=20.0)

check("'tees' plural → tee category",
      "10 – 3/4 black iron tees",
      sku="TEE-3/4-BI", qty=10.0)

check("'caps' plural → cap category",
      "10 – 1/2 black iron caps",
      sku="CAP-1/2-BI", qty=10.0)

check("emt_coupling before coupling (ordering matters)",
      "10 – 1/2 emt set screw coupling",
      sku="CPL-EMT-1/2-SS")

check("hose_clamp before hose (ordering matters)",
      "24 – #12 ss hose clamps",
      sku="CLAMP-12-SS", qty=24.0)


print()
print("=" * 70)
print(f"RESULTS: {sum(results)}/{len(results)} passed")
print("=" * 70)
