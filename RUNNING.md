# Running this

Python 3.11 or newer. Pure Python, no Linux-specific assumptions, so it runs natively on Windows as well as under WSL or Docker. Everything below assumes you are in the project root.

## Setup

Dependencies and the `rfq` entry point are both declared in `pyproject.toml`, so one command does it:

```bash
pip install -e .
```

That gives you the `rfq` command. If you would rather not install anything, `python3 -m rfq` works the same way everywhere below, as long as the dependencies in `pyproject.toml` are present.

## The short version

```bash
rfq run --emails data/dev/emails --out predictions.json
python3 tests/scorer.py
```

That runs the whole pipeline on the 18 dev emails and scores the output against `data/dev/answer_key.json`. It should take a few seconds and it does not need an API key. More on why in a moment.

## No API key needed for the dev set

Extraction uses an LLM, but every response for the dev set is cached in `rfq/fixtures/` and those fixtures are committed. The cache key is a hash of the email body plus a hash of the prompt, so a cache hit means you are getting exactly the response the committed prompt produced. Running the dev set never touches the network.

If you point the pipeline at emails that are not in the fixtures, it will call the API. Set one of these first:

```bash
export GROQ_API_KEY=...      # uses openai/gpt-oss-120b
export OPENAI_API_KEY=...    # fallback, uses gpt-4o
```

With neither key set and no fixture, extraction returns an empty list rather than crashing. You get an empty result, not a stack trace.

## The three commands

`rfq run` is extract plus match in one pass, and it is the one I would use. The other two exist so each half can be inspected on its own.

**Extract only**

```bash
rfq extract --emails data/dev/emails --out lines.json
```

Writes a dict of email stem to list of line strings. Useful for checking what the extractor pulled out before any matching happens.

**Match only**

```bash
rfq match --lines lines.json --out predictions.json
```

Takes the output of `extract` and runs it through the matcher. Deterministic, no network, no API key.

**Both**

```bash
rfq run --emails data/dev/emails --out predictions.json
```

`run` does more than chaining the other two. It builds the thread graph from the `Message-ID` and `In-Reply-To` headers, processes parents before children so a follow-up email can see the order it is modifying, resolves the real customer domain on emails an ISR forwarded, and carries category and material context forward across lines within an email. `extract` followed by `match` skips all of that.

Both commands take `--data DIR` if `catalog.csv` and `xref.csv` live somewhere other than `data/`.

## Scoring

```bash
python3 tests/scorer.py
```

Defaults to `predictions.json` against `data/dev/answer_key.json`. Override either:

```bash
python3 tests/scorer.py --pred my.json --key my_key.json
python3 tests/scorer.py --verbose          # show the emails that scored clean too
```

Output looks like this:

```
=================================================================
LINE ITEMS : 82/86 correct  |  0 wrong  |  4 missing  |  4 spurious
CLASSIFY   : 18/18
ACTION     : 18/18
=================================================================
```

**Wrong** is the number I care about most. It means a line matched to the key but returned the wrong SKU or the wrong quantity, which is a bad quote reaching a customer. It is zero.

**Missing** and **spurious** come in pairs and are almost always the same line item counted twice. The scorer aligns a prediction to a key entry by normalizing the raw string, so when my extracted text differs from the key's text the entry shows up as missing on one side and spurious on the other even though the SKU and quantity are identical. The four remaining are two line items in E003 and E010. Both have the correct SKU. I wrote up why in README.md rather than tuning the scorer's normalizer until the number moved, because that would be optimizing the measurement instead of the system.

## Running on your own emails

```bash
rfq run --emails path/to/your/emails --out predictions.json
```

Set an API key first, since none of those bodies will be in the fixtures. Fixtures are written as the run goes, so a second run over the same emails is free and reproducible.

To force a clean re-extraction, delete the fixtures:

```bash
rm -rf rfq/fixtures && mkdir rfq/fixtures
```

You only need this if you change a prompt, and even then the prompt hash in the cache key handles it for you. The manual delete is for when you want to confirm the committed fixtures actually reproduce from the committed prompt.

## Output shape

```json
{
  "E003": {
    "classification": "rfq",
    "action": "auto_quote",
    "customer": "harborworks.example",
    "customer_email": "dan@harborworks.example",
    "supersedes": null,
    "superseded_by": "E010",
    "duplicate_of": null,
    "line_items": [
      {
        "raw": "50 - 1/2 inch black iron 90 elbows",
        "qty": 50,
        "uom": "EA",
        "sku": "EL90-1/2-BI",
        "abstain": null,
        "candidates": [],
        "why": "single match on elbow_90, 1/2, BI"
      }
    ]
  }
}
```

Every line item carries a `why`, including the ones that matched cleanly. An ISR reviewing an abstention can see which candidates survived and what was missing, and an ISR spot-checking a confident match can see which attributes drove it. That was the point of keeping matching deterministic.

`classification` is one of `rfq`, `not_rfq`, `duplicate`, `needs_attachment`. `action` is one of `auto_quote`, `ask_customer`, `escalate`, `ignore`. `abstain` is `null` on a match, otherwise `ambiguous`, `not_in_catalog`, or `discontinued`.

## Layout

```
rfq/
  cli.py          extract / match / run, thread ordering, classification, action
  parser.py       .eml to ParsedEmail: MIME, HTML tables, CSV attachments, quoted history
  extractor.py    LLM extraction and the fixture cache
  normalizer.py   line string to structured attributes, all regex
  matcher.py      structured attributes to SKU or abstention
  fixtures/       cached LLM responses, keyed by body hash plus prompt hash
data/
  catalog.csv     the SKUs
  xref.csv        competitor, legacy and customer part numbers
  dev/emails/     18 dev emails
  dev/answer_key.json
tests/
  scorer.py
```

## If something goes wrong

**`error: data/dev/emails is not a directory`** means the path is wrong. All paths are relative to where you are running from, not to the package.

**`error: catalog.csv not found in data`** means `--data` is pointing somewhere without the CSVs.

**Every line comes back empty** usually means the fixtures are missing and no API key is set. Check `ls rfq/fixtures | wc -l`, which should show a file per dev email body.

**The score dropped after a code change** is worth checking against the fixtures before assuming the matcher broke. If you changed a prompt, the cache key changed with it and the next run re-extracts, which is the intended behaviour but it does mean the run is no longer offline.