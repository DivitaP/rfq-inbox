"""
Score predictions.json against data/dev/answer_key.json.

Usage:
    python rfq/scorer.py                              # uses predictions.json + data/dev/answer_key.json
    python rfq/scorer.py --pred my.json               # custom predictions file
    python rfq/scorer.py --pred my.json --key k.json  # custom key
    python rfq/scorer.py --verbose                    # show all details even when clean
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


# ---------------------------------------------------------------------------
# Raw-string normalisation for lenient matching
# ---------------------------------------------------------------------------

def _norm(s: str) -> str:
    s = re.sub(r'^\d+\)\s*', '', s.strip())                    # strip "N) " numbered-list prefix
    s = re.sub(r'^(?:and|also|plus|add|or)\s+', '', s, flags=re.I)  # strip leading discourse
    s = re.sub(r'\bqty\s*:?\s*', '', s, flags=re.I)            # strip embedded "qty" marker
    s = re.sub(r'\s*\([^)]*\)', '', s)                          # strip parenthetical notes
    s = re.sub(r'\s+', ' ', s)                                  # collapse whitespace
    return s.lower().strip()


# ---------------------------------------------------------------------------
# Per-line scorer
# ---------------------------------------------------------------------------

class LineResult:
    def __init__(self, eid: str, verdict: str, key_item: dict, pred_item: dict | None,
                 notes: list[str]):
        self.eid = eid
        self.verdict = verdict          # "correct" | "wrong" | "missing" | "spurious"
        self.key_item = key_item
        self.pred_item = pred_item
        self.notes = notes

    def __str__(self) -> str:
        ki = self.key_item
        pi = self.pred_item
        raw = (ki or pi or {}).get('raw', '')[:55]
        if self.verdict == 'correct':
            return f"  CORRECT  [{ki['sku'] or ki['abstain']}]  {raw}"
        if self.verdict == 'wrong':
            return f"  WRONG    {' | '.join(self.notes)}  raw={raw}"
        if self.verdict == 'missing':
            return f"  MISSING  key={ki['sku'] or ki['abstain']}  raw={raw}"
        return f"  SPURIOUS sku={pi['sku'] or pi['abstain']}  raw={raw}"


# ---------------------------------------------------------------------------
# Email-level scorer
# ---------------------------------------------------------------------------

class EmailResult:
    def __init__(self, eid: str, key_email: dict, pred_email: dict):
        self.eid = eid
        self.key_email = key_email
        self.pred_email = pred_email
        self.line_results: list[LineResult] = []

        self.classification_ok = (
            pred_email.get('classification') == key_email.get('classification')
        )
        self.action_ok = (
            pred_email.get('action') == key_email.get('action')
        )

    def add(self, r: LineResult):
        self.line_results.append(r)

    @property
    def correct(self):   return [r for r in self.line_results if r.verdict == 'correct']
    @property
    def wrong(self):     return [r for r in self.line_results if r.verdict == 'wrong']
    @property
    def missing(self):   return [r for r in self.line_results if r.verdict == 'missing']
    @property
    def spurious(self):  return [r for r in self.line_results if r.verdict == 'spurious']

    def summary(self) -> str:
        cl_sym  = '✓' if self.classification_ok else '✗'
        act_sym = '✓' if self.action_ok else '✗'
        return (
            f"{self.eid}  "
            f"class={cl_sym}({self.pred_email.get('classification','?')})  "
            f"action={act_sym}({self.pred_email.get('action','?')})  "
            f"lines: {len(self.correct)}✓ {len(self.wrong)}✗ "
            f"{len(self.missing)} miss {len(self.spurious)} spur"
        )


# ---------------------------------------------------------------------------
# Main scorer
# ---------------------------------------------------------------------------

class Scorer:
    def __init__(self, key_path: Path, pred_path: Path):
        self.key_data  = json.loads(key_path.read_text(encoding='utf-8'))['emails']
        self.pred_data = json.loads(pred_path.read_text(encoding='utf-8'))
        self.email_results: list[EmailResult] = []

    def run(self) -> 'Scorer':
        for eid, ke in sorted(self.key_data.items()):
            pe = self.pred_data.get(eid, {})
            er = EmailResult(eid, ke, pe)

            pred_by_norm = {_norm(p['raw']): p for p in pe.get('line_items', [])}
            matched_norms: set[str] = set()

            for ki in ke.get('line_items', []):
                nk = _norm(ki['raw'])
                p  = pred_by_norm.get(nk)

                if p is None:
                    er.add(LineResult(eid, 'missing', ki, None, []))
                    continue

                matched_norms.add(nk)

                sku_ok  = (ki['sku'] == p['sku']) and (ki['abstain'] == p['abstain'])
                k_qty   = ki['qty']
                tol     = ki.get('qty_tol', 0) or 0
                p_qty   = p['qty']

                if k_qty is None:
                    qty_ok = (p_qty is None)
                elif p_qty is None:
                    qty_ok = False
                else:
                    qty_ok = abs(p_qty - k_qty) <= tol

                if sku_ok and qty_ok:
                    er.add(LineResult(eid, 'correct', ki, p, []))
                else:
                    notes = []
                    if not sku_ok:
                        notes.append(
                            f"sku: key={ki['sku'] or ki['abstain']} "
                            f"got={p['sku'] or p['abstain']}"
                        )
                    if not qty_ok:
                        notes.append(f"qty: key={k_qty} got={p_qty}")
                    er.add(LineResult(eid, 'wrong', ki, p, notes))

            for p in pe.get('line_items', []):
                if _norm(p['raw']) not in matched_norms:
                    er.add(LineResult(eid, 'spurious', {}, p, []))

            self.email_results.append(er)
        return self

    # ------------------------------------------------------------------
    # Aggregates
    # ------------------------------------------------------------------

    @property
    def total_key_lines(self) -> int:
        return sum(len(er.correct) + len(er.wrong) + len(er.missing)
                   for er in self.email_results)

    @property
    def correct(self) -> int:
        return sum(len(er.correct) for er in self.email_results)

    @property
    def wrong(self) -> int:
        return sum(len(er.wrong) for er in self.email_results)

    @property
    def missing(self) -> int:
        return sum(len(er.missing) for er in self.email_results)

    @property
    def spurious(self) -> int:
        return sum(len(er.spurious) for er in self.email_results)

    @property
    def classify_correct(self) -> int:
        return sum(1 for er in self.email_results if er.classification_ok)

    @property
    def action_correct(self) -> int:
        return sum(1 for er in self.email_results if er.action_ok)

    def report(self, verbose: bool = False) -> str:
        n = len(self.email_results)
        lines = [
            '=' * 65,
            f"LINE ITEMS : {self.correct}/{self.total_key_lines} correct"
            f"  |  {self.wrong} wrong"
            f"  |  {self.missing} missing"
            f"  |  {self.spurious} spurious",
            f"CLASSIFY   : {self.classify_correct}/{n}",
            f"ACTION     : {self.action_correct}/{n}",
            '=' * 65,
        ]

        for er in self.email_results:
            has_issues = (
                er.wrong or er.missing or er.spurious
                or not er.classification_ok or not er.action_ok
            )
            if verbose or has_issues:
                lines.append('')
                lines.append(er.summary())
                if not er.classification_ok:
                    lines.append(
                        f"    classification: key={er.key_email.get('classification')} "
                        f"got={er.pred_email.get('classification')}"
                    )
                if not er.action_ok:
                    lines.append(
                        f"    action: key={er.key_email.get('action')} "
                        f"got={er.pred_email.get('action')}"
                    )
                for r in er.wrong + er.missing + er.spurious:
                    lines.append(f"  {str(r)}")

        return '\n'.join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--pred', default='predictions.json',
                    help='predictions file (default: predictions.json)')
    ap.add_argument('--key',  default='data/dev/answer_key.json',
                    help='answer key file (default: data/dev/answer_key.json)')
    ap.add_argument('--verbose', '-v', action='store_true',
                    help='show correct emails too')
    a = ap.parse_args(argv)

    scorer = Scorer(Path(a.key), Path(a.pred)).run()
    print(scorer.report(verbose=a.verbose))


if __name__ == '__main__':
    main()
