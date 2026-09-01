# data/ — the files, the contract, the grading

```
catalog.csv          the catalog your matcher resolves against
xref.csv             other people's part numbers → our sku
dev/emails/*.eml     the inbox, one RFC-822 file per email (E001.eml …)
dev/lines.json       our extraction of the dev emails — ground truth for part 1, and the
                     matcher input to build on if you skip extraction
dev/answer_key.json  what a careful inside sales rep (ISR) matched each line to — ground truth for part 2
check_format.py      validates the shape of your two output files (it scores nothing)
eml_to_json.py       optional: .eml → JSON. Use it, port it, or ignore it — parsing MIME is not what we grade.
```

A **held-out set** from the same inbox — same catalog, same kinds of customers and quirks,
none of the same strings — is not shipped; your submission is run against it.

## The two commands (this is how we run you, so the shape is mandatory)

```
<your command> extract --emails <dir> --out lines.json
<your command> match   --lines lines.json --out predictions.json
<your command> run     --emails <dir> --out predictions.json      # OPTIONAL: extract → match in one go
```

`extract` and `match` are the contract. `run` is optional — the composition of the other two;
we grade the stages separately, the pipeline is just how the product runs whole.

Check both files with `python check_format.py --lines lines.json --pred predictions.json`
(exit 0 = shape ok; exit 2 names each `email.line.field` that is wrong).

## lines.json — extraction output and matcher input

One JSON object keyed by the `.eml` filename stem; **every email in the input directory must
appear**; the value is the list of **verbatim line-item strings** an ISR would quote from that
email — `[]` when nothing should be:

```json
{"E001": ["50 of the 1/2 brass elbows", "and 20 of the 3/4"], "E002": []}
```

Extraction judgment — these rules are the contract:

- Copy the text as written, not normalised. One sentence yielding several items → one string
  per item (the fragment, or the sentence repeated). Table/CSV/HTML rows → one string per row,
  the cells kept on one line (spaces, commas or ` | ` between cells all work — we align on
  tokens, not punctuation).
- Quoted/forwarded history is context, not new lines. The same request sent twice: **the email
  with the later `Date:` is the duplicate** and gets `[]`. An email whose items live in an
  attached CSV → the attachment's rows. "See attached" with nothing attached → `[]`.
  Signature, price and deadline noise is not a line.
- A reply that changes an earlier order → the **complete order as the customer now intends
  it**; the earlier email keeps its own lines as-of-arrival.

## predictions.json — matching output, same email keys

```json
{
  "E001": {
    "supersedes": null,
    "line_items": [
      {"raw": "20 ea 3/4 brass tee", "qty": 20, "uom": "EA", "sku": "TEE-3/4-BR",
       "why": "exact size+material token match; single candidate"},
      {"raw": "3 - 3/4 pvc unions", "qty": 3, "sku": null, "abstain": "not_in_catalog",
       "why": "no PVC in catalog"}
    ]
  }
}
```

- Required per line: `raw` (the input string), `qty` (number or null), exactly one of
  `sku` / `abstain` (`ambiguous | not_in_catalog | discontinued`), and `why` — one short line
  of evidence a human can check. `abstain: ambiguous` requires `candidates` (≥ 2 skus).
- `confidence` optional and **unscored** — the only way to not commit is to abstain.
- **Quantity rule.** `qty` is in the catalog uom of the matched sku, or set `uom` and we
  convert (`pack_qty` EA→BX; `length` FT→sticks and FT→reel; m→ft × 3.2808). A quantity stated
  in a base unit maps to the base-unit sku; the pack sku is right only when the customer names
  the pack (reel, dozen, box). A unit word is evidence; its absence when both fit is ambiguity.
  Unknown or conflicting quantity → `qty: null`.
- `supersedes` optional (filename stem of the earlier email; only if it is in the inbox). We
  read your lines both as the complete final order and as a delta over that email and keep the
  better reading — if in doubt, emit the complete order.
- **Your matcher must accept any file in the lines.json format.** We grade matching in
  isolation by running `match` on our own extraction of the held-out emails, whether or not
  you built an extractor.

## World facts

- Ridgeline's RFQ inbox is `rfq@ridgeline-supply.example`. Anything **from**
  `@ridgeline-supply.example` is one of our own ISRs — usually forwarding a customer email. For
  such an internal forward the customer is the original sender in the forwarded header, and
  that sender's domain is what scopes `customer:<domain>` cross-references.
- Emails to Ridgeline that are *quotes from a vendor* are not RFQs — nothing to extract.
- Cross-references in `xref.csv` with `source = customer:<domain>` are valid **only** for mail
  from that domain. Competitor and legacy numbers are valid for anyone.
- Quantities in this inbox always divide into whole packs — unless they don't, and then that
  is a question for the customer, not a rounding decision for you (`qty: null`).

## What we grade

**Extraction**: your `lines.json` against ours, paired line-for-line — headline numbers are
**missed lines** and **hallucinated lines** (quoted-thread, signature or noise leakage), then
line recall and precision.

**Matching — graded twice**: once on your lines, once on ours. Headline numbers are
**confident wrong matches** (you named a sku, the right answer was a different sku or an
abstention) and **spurious abstentions** (you abstained where a careful ISR matched —
abstaining on everything shows up here, it is not a safe policy). Then match accuracy, qty
accuracy (within the key's tolerance; `null` must be `null`) and abstain precision/recall.

**The asymmetry, and why those are the headlines:** a wrong match becomes a wrong quote a
customer receives, discovered at the invoice or the receiving dock; an abstention becomes a
slower quote an ISR reviews. Both cost; they do not cost the same.

**`answer_key.json` fields you will see** beyond the schema above: `qty_tol` is a relative
tolerance on `qty` (`0` = exact, `0.05` = ±5 %, `null` = that line's qty is unscored);
`candidates` on an abstaining line lists the skus a careful ISR would put in front of the
customer; line `id`s are `<email>-<n>`. The workflow fields (`classification`, `action`,
`action_accept`, `customer`, `duplicate_of`) are context from the ISR tool this data came
from — they are **not scored** and you do not emit them.
