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
    """
    this method reads lines.json and for each email creates valud predictions structure
    """
    lines_path = Path(args.lines)
    if not lines_path.exists():
        sys.exit(f"error: {lines_path} not found")

    lines = json.loads(lines_path.read_text(encoding="utf-8"))

    result = {}
    for email_id, raw_lines in lines.items():
        result[email_id] = {
            "supersedes": None,
            "line_items": [],
        }

    Path(args.out).write_text(json.dumps(result, indent=2, ensure_ascii=False))
    print(f"wrote {len(result)} emails -> {args.out}")

def cmd_run(args: argparse.Namespace) -> None:
    """
    composes the 2 methods above
    writes a temp file for the intermediate lines, calls extract then match, cleans up the temp file
    """
    import tempfile, os

    with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as tmp:
        tmp_lines = tmp.name

    try:
        extract_args = argparse.Namespace(emails=args.emails, out=tmp_lines)
        cmd_extract(extract_args)

        match_args = argparse.Namespace(lines=tmp_lines, out=args.out)
        cmd_match(match_args)
    finally:
        os.unlink(tmp_lines)

def main() -> None:
    parser = argparse.ArgumentParser(prog="rfq")
    sub = parser.add_subparsers(dest="command", required=True)

    p_extract = sub.add_parser("extract", help="Email dir -> lines.json")
    p_extract.add_argument("--emails", required=True, metavar="DIR")
    p_extract.add_argument("--out", required=True, metavar="FILE")

    p_match = sub.add_parser("match", help="lines.json -> predictions.json")
    p_match.add_argument("--lines", required=True, metavar="FILE")
    p_match.add_argument("--out", required=True, metavar="FILE")

    p_run = sub.add_parser("run", help="Email dir -> predictions.json (extract + match)")
    p_run.add_argument("--emails", required=True, metavar="DIR")
    p_run.add_argument("--out", required=True, metavar="FILE")

    args = parser.parse_args()
    {"extract": cmd_extract, "match": cmd_match, "run": cmd_run}[args.command](args)

if __name__ == "__main__":
    main()