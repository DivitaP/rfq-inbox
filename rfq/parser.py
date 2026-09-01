""" MIME parser : .eml -> ParsedEmail """

import csv
import io
import re
from dataclasses import dataclass, field
from email import policy
from email.parser import BytesParser
from pathlib import Path

@dataclass
class ParsedEmail:
    stem: str 
    sender: str
    date: str
    in_reply_to: str
    subject: str
    body: str
    csv_rows: list[list[str]] = field(default_factory=list)
    has_pending_attachment: bool = False

_THREAD_CUT = re.compile(
    r'^On .{5,100}wrote:\s*$',
    re.MULTILINE,
)

def _strip_thread(text: str) -> str:
    m = _THREAD_CUT.search(text)
    if m:
        text = text[: m.start()]

    lines = [l for l in text.splitlines() if not l.startswith(">")]

    return "\n".join(lines).strip()

def _parse_csv(text: str) -> list[list[str]]:
    reader = csv.reader(io.StringIO(text))
    return [row for row in reader if any(cell.strip() for cell in row)]

def parse_eml(path: Path) -> ParsedEmail:
    msg = BytesParser(policy=policy.default).parsebytes(path.read_bytes())

    sender = msg.get("from", "")
    date = msg.get("date", "")
    in_reply_to = msg.get("in-reply-to", "")
    subject = msg.get("subject", "")

    body = ""
    csv_rows = []

    for part in msg.walk():
        if part.is_multipart():
            continue

        ct = part.get_content_type()

        is_attachment = (
            part.get_content_disposition() == "attachment"
            or part.get_filename()
        )

        if is_attachment:
            if ct == "text/csv":
                try:
                    csv_rows = _parse_csv(part.get_content())
                except Exception:
                    pass

        elif ct == "text/plain" and not body:
            try:
                body = part.get_content()
            except Exception:
                body = part.get_payload(decode=True).decode("utf-8", "replace")

    body = _strip_thread(body)

    mentions_attachment = bool(re.search(r'\battach', body, re.IGNORECASE))
    has_pending_attachment = mentions_attachment and not csv_rows

    return ParsedEmail(
        stem = path.stem,
        sender = sender,
        date = date,
        in_reply_to=in_reply_to,
        subject=subject,
        body=body,
        csv_rows=csv_rows,
        has_pending_attachment=has_pending_attachment,
    )

def parse_emails_dir(directory: Path) -> dict[str, ParsedEmail]:
    return {
        path.stem: parse_eml(path)
        for path in sorted(directory.glob("*.eml"))
    }