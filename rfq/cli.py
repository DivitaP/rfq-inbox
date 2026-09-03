"""Entry point: rfq extract / rfq match / rfq run"""

import argparse
import json
import re
import sys
import time
from pathlib import Path

def _extract_threaded(emails: dict) -> dict[str, list[str]]:
    """Extract lines for every email, giving follow-ups their parent's lines as context.

    Same thread handling cmd_run does, so `extract` and `run` produce identical
    lines.json for a threaded inbox.
    """
    from rfq.extractor import extract_lines, _is_duplicate

    msgid_to_stem = {p.message_id: stem for stem, p in emails.items() if p.message_id}
    supersedes: dict[str, str] = {}
    for stem, parsed in emails.items():
        if parsed.in_reply_to and parsed.in_reply_to in msgid_to_stem:
            supersedes[stem] = msgid_to_stem[parsed.in_reply_to]

    # parents before children; date strings aren't reliably sortable as text
    order, remaining = [], set(emails)
    while remaining:
        ready = sorted(s for s in remaining if supersedes.get(s) not in remaining)
        if not ready:
            order.extend(sorted(remaining))   # cycle guard
            break
        order.extend(ready)
        remaining -= set(ready)

    result: dict[str, list[str]] = {}
    for stem in order:
        parsed = emails[stem]
        if _is_duplicate(parsed):
            result[stem] = []
            continue
        parent = supersedes.get(stem)
        parent_context = None
        if parent and result.get(parent):
            parent_context = [{"raw": r} for r in result[parent]]
        result[stem] = extract_lines(parsed, parent_context=parent_context)

    return {stem: result[stem] for stem in emails}   # restore input key order

def cmd_extract(args: argparse.Namespace) -> None:
    """Scan a directory of .eml files and write the extracted line items per email.

    Follow-up emails are extracted after the email they reply to, with the parent's
    lines passed as context, so a reply like "rest stays the same" resolves to the
    complete order rather than the fragment the customer typed.
    """
    from rfq.parser import parse_emails_dir

    emails_dir = Path(args.emails)
    if not emails_dir.is_dir():
        sys.exit(f"error: {emails_dir} is not a directory")

    emails = parse_emails_dir(emails_dir)
    result = _extract_threaded(emails)

    Path(args.out).write_text(json.dumps(result, indent=2, ensure_ascii=False))
    print(f"wrote {len(result)} emails -> {args.out}")

def cmd_match(args: argparse.Namespace) -> None:
    from rfq.matcher import load_matcher

    lines_path = Path(args.lines)
    if not lines_path.exists():
        sys.exit(f"error: {lines_path} not found")

    data_dir = Path(getattr(args, "data", "data"))
    if not (data_dir / "catalog.csv").exists():
        sys.exit(f"error: catalog.csv not found in {data_dir}")

    lines = json.loads(lines_path.read_text(encoding="utf-8"))
    matcher = load_matcher(data_dir)
    result = matcher.match_all(lines)

    Path(args.out).write_text(json.dumps(result, indent=2, ensure_ascii=False))
    print(f"wrote {len(result)} emails -> {args.out}")

def _classify(parsed) -> str:
    from rfq.extractor import _is_not_rfq, _is_duplicate
    if _is_not_rfq(parsed):
        return "not_rfq"
    if parsed.has_pending_attachment:
        return "needs_attachment"
    if _is_duplicate(parsed):
        return "duplicate"
    return "rfq"

def _parse_subject_hints(subject: str) -> list[dict]:
    """Extract product hints from the subject line.

    Splits on '+', ',', '&' to get per-product phrases, then runs the same
    normalizer functions used on body lines. Only 1-3 digit integers are
    treated as qty candidates — longer numbers are likely PO/job references.
    """
    from rfq.normalizer import extract_category, extract_material, extract_size
    hints = []
    for chunk in re.split(r'[+,&]', subject):
        chunk = chunk.strip()
        cat = extract_category(chunk)
        if not cat:
            continue
        mat = extract_material(chunk)
        size = extract_size(chunk)
        qty = None
        m = re.search(r'(?<![/\d])\b(\d{1,3})\b(?![/\d])', chunk)
        if m:
            qty = float(m.group(1))
        hints.append({"category": cat, "qty": qty, "material": mat, "size": size})
    return hints


def _conflicted_line_indices(subject: str, raw_lines: list[str]) -> set[int]:
    """Return the indices of raw_lines whose attributes conflict with subject hints.

    A conflict is: subject specifies a value for qty / material / size AND the
    body line specifies a *different* non-None value for that same attribute on
    the same product category. Both sides must have a value for a conflict to
    fire — a missing value on either side is not a conflict.
    """
    from rfq.normalizer import extract_category, extract_material, extract_size, extract_qty
    hints = _parse_subject_hints(subject)
    if not hints:
        return set()
    conflicted: set[int] = set()
    for i, line in enumerate(raw_lines):
        cat = extract_category(line)
        if not cat:
            continue
        matching = [h for h in hints if h["category"] == cat]
        if not matching:
            continue
        hint = matching[0]
        line_qty, _ = extract_qty(line)
        line_mat = extract_material(line)
        line_size = extract_size(line)
        if hint["qty"] is not None and line_qty is not None and hint["qty"] != line_qty:
            conflicted.add(i)
        elif hint["material"] is not None and line_mat is not None and hint["material"] != line_mat:
            conflicted.add(i)
        elif hint["size"] is not None and line_size is not None and hint["size"] != line_size:
            conflicted.add(i)
    return conflicted


def _action(classification: str, items: list) -> str:
    if classification in ("not_rfq", "duplicate"):
        return "ignore"
    if classification == "needs_attachment":
        return "ask_customer"
    if not items:
        return "escalate"
    if any(p.get("abstain") == "discontinued" for p in items):
        return "ask_customer"
    if any(p.get("qty") is None and p.get("sku") is not None for p in items):
        return "ask_customer"
    if any(p.get("abstain") in ("ambiguous", "not_in_catalog") for p in items):
        return "escalate"
    return "auto_quote"

def cmd_run(args: argparse.Namespace) -> None:
    import re
    from rfq.parser import parse_emails_dir
    from rfq.extractor import extract_all, extract_lines, _is_duplicate
    from rfq.matcher import load_matcher

    _t0 = time.time()
    emails_dir = Path(args.emails)
    if not emails_dir.is_dir():
        sys.exit(f"error: {emails_dir} is not a directory")

    data_dir = Path(getattr(args, "data", "data"))

    emails = parse_emails_dir(emails_dir)

    # Build thread graph from email headers
    msgid_to_stem = {p.message_id: stem for stem, p in emails.items() if p.message_id}

    domains: dict[str, str | None] = {}
    customer_emails: dict[str, str | None] = {}
    supersedes: dict[str, str] = {}  # child → parent

    for stem, parsed in emails.items():
        email_addr = parsed.customer_email
        if re.search(r'@ridgeline-supply\.example\b', email_addr, re.I):
            fwd = re.search(r'From:\s*.+<(.+@[\w.-]+)>', parsed.body or "", re.I)
            if fwd:
                email_addr = fwd.group(1).lower()
        customer_emails[stem] = email_addr or None
        m = re.search(r'@([\w.-]+)', email_addr)
        domains[stem] = m.group(1).lower() if m else None
        if parsed.in_reply_to and parsed.in_reply_to in msgid_to_stem:
            supersedes[stem] = msgid_to_stem[parsed.in_reply_to]

    # inverse: parent → child
    superseded_by: dict[str, str] = {old: new for new, old in supersedes.items()}

    threaded: set[str] = set(supersedes) | set(superseded_by)
    independent: dict[str, object] = {s: p for s, p in emails.items() if s not in threaded}

    matcher = load_matcher(data_dir)
    result: dict = {}

    def _match_with_ctx(raw_lines, domain):
        """Match items in order, carrying category/material context forward."""
        from rfq.normalizer import parse_line as _pl
        items, email_ctx = [], {}
        for r in raw_lines:
            item = matcher.match_line(r, domain, email_ctx=email_ctx)
            items.append(item)
            if item["sku"]:
                p = _pl(r)
                if p.category:
                    email_ctx["category"] = p.category
                if p.material:
                    email_ctx["material"] = p.material
        return items

    # Batch-process emails with no thread relationship (current behaviour, unchanged)
    for stem, raw_lines in extract_all(independent).items():
        parsed = emails[stem]
        domain = domains.get(stem)
        items = _match_with_ctx(raw_lines, domain)
        for i in _conflicted_line_indices(parsed.subject, raw_lines):
            if i < len(items) and items[i].get("sku"):
                items[i] = dict(items[i])
                items[i]["qty"] = None
                items[i]["uom"] = None
        cl = _classify(parsed)
        result[stem] = {
            "classification": cl,
            "action": _action(cl, items),
            "customer": domain,
            "customer_email": customer_emails.get(stem),
            "supersedes": None,
            "superseded_by": None,
            "duplicate_of": None,
            "line_items": items,
        }

    # Process threaded emails in topological order: parents before children.
    # Build order via graph walk — date strings aren't reliably sortable as text.
    def _topo(nodes: set[str], parents: dict[str, str]) -> list[str]:
        order, remaining = [], set(nodes)
        while remaining:
            ready = sorted(s for s in remaining if parents.get(s) not in remaining)
            if not ready:
                break  # cycle guard (shouldn't occur in email threads)
            order.extend(ready)
            remaining -= set(ready)
        return order

    matched_cache: dict[str, list] = {}  # stem → matched items, used as context for children

    for stem in _topo(threaded, supersedes):
        parsed = emails[stem]
        domain = domains.get(stem)
        parent_stem = supersedes.get(stem)
        parent_context = None
        if parent_stem and matched_cache.get(parent_stem):
            parent_context = [{"raw": p["raw"]} for p in matched_cache[parent_stem]]

        raw_lines = extract_lines(parsed, parent_context=parent_context)
        items = _match_with_ctx(raw_lines, domain)
        for i in _conflicted_line_indices(parsed.subject, raw_lines):
            if i < len(items) and items[i].get("sku"):
                items[i] = dict(items[i])
                items[i]["qty"] = None
                items[i]["uom"] = None
        matched_cache[stem] = items

        cl = _classify(parsed)
        if stem in superseded_by:
            result[stem] = {
                "classification": cl,
                "action": _action(cl, items),
                "customer": domain,
                "customer_email": customer_emails.get(stem),
                "supersedes": supersedes.get(stem),
                "superseded_by": superseded_by[stem],
                "duplicate_of": None,
                "line_items": items,
            }
        else:
            result[stem] = {
                "classification": cl,
                "action": _action(cl, items),
                "customer": domain,
                "customer_email": customer_emails.get(stem),
                "supersedes": supersedes.get(stem),
                "superseded_by": None,
                "duplicate_of": None,
                "line_items": items,
            }

    Path(args.out).write_text(json.dumps(result, indent=2, ensure_ascii=False))
    elapsed = time.time() - _t0
    print(f"wrote {len(result)} emails -> {args.out}  ({elapsed:.2f}s)")

def main() -> None:
    parser = argparse.ArgumentParser(prog="rfq")
    sub = parser.add_subparsers(dest="command", required=True)

    p_extract = sub.add_parser("extract", help="Email dir -> lines.json")
    p_extract.add_argument("--emails", required=True, metavar="DIR")
    p_extract.add_argument("--out", required=True, metavar="FILE")

    p_match = sub.add_parser("match", help="lines.json -> predictions.json")
    p_match.add_argument("--lines", required=True, metavar="FILE")
    p_match.add_argument("--out", required=True, metavar="FILE")
    p_match.add_argument("--data", default="data", metavar="DIR",
                         help="directory containing catalog.csv and xref.csv (default: data)")

    p_run = sub.add_parser("run", help="Email dir -> predictions.json (extract + match)")
    p_run.add_argument("--emails", required=True, metavar="DIR")
    p_run.add_argument("--out", required=True, metavar="FILE")
    p_run.add_argument("--data", default="data", metavar="DIR",
                         help="directory containing catalog.csv and xref.csv (default: data)")

    args = parser.parse_args()
    {"extract": cmd_extract, "match": cmd_match, "run": cmd_run}[args.command](args)

if __name__ == "__main__":
    main()