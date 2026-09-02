"""Entry point: rfq extract / rfq match / rfq run"""

import argparse
import json
import sys
from pathlib import Path

def cmd_extract(args: argparse.Namespace) -> None:
    """
    this method will scan emails dir for .eml files -> create a dict with each filename stem as a key and empty list as value
    the empty list is a placeholder for extracted line items that will come late
    """

    from rfq.parser import parse_emails_dir
    from rfq.extractor import extract_all

    emails_dir = Path(args.emails)
    if not emails_dir.is_dir():
        sys.exit(f"error: {emails_dir} is not a directory")

    emails = parse_emails_dir(emails_dir)
    result = extract_all(emails)

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

def cmd_run(args: argparse.Namespace) -> None:
    import re
    from rfq.parser import parse_emails_dir
    from rfq.extractor import extract_all
    from rfq.matcher import load_matcher

    emails_dir = Path(args.emails)
    if not emails_dir.is_dir():
        sys.exit(f"error: {emails_dir} is not a directory")

    data_dir = Path(getattr(args, "data", "data"))

    emails = parse_emails_dir(emails_dir)
    lines = extract_all(emails)

    # Build message-id → stem index for thread linking
    msgid_to_stem = {p.message_id: stem for stem, p in emails.items() if p.message_id}

    domains = {}
    customer_emails = {}
    supersedes = {}
    for stem, parsed in emails.items():
        email_addr = parsed.customer_email
        # If sent by a Ridgeline ISR, the real customer is in the forwarded From: header
        if re.search(r'@ridgeline-supply\.example\b', email_addr, re.I):
            fwd = re.search(r'From:\s*.+<(.+@[\w.-]+)>', parsed.body or "", re.I)
            if fwd:
                email_addr = fwd.group(1).lower()
        customer_emails[stem] = email_addr or None
        m = re.search(r'@([\w.-]+)', email_addr)
        domains[stem] = m.group(1).lower() if m else None
        # Thread: does this email reply to another email in the set?
        if parsed.in_reply_to and parsed.in_reply_to in msgid_to_stem:
            supersedes[stem] = msgid_to_stem[parsed.in_reply_to]

    matcher = load_matcher(data_dir)
    result = matcher.match_all(lines, domains=domains, supersedes=supersedes,
                               customer_emails=customer_emails)

    Path(args.out).write_text(json.dumps(result, indent=2, ensure_ascii=False))
    print(f"wrote {len(result)} emails -> {args.out}")

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