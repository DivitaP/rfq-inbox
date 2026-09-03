# AI_USAGE.md

**Tool:** Claude Code. **Extraction model at runtime:** `openai/gpt-oss-120b` via Groq, `gpt-4o` via OpenAI as fallback.

## How I used it

I wrote the CLI skeleton and the command contract by hand before opening Claude Code ([`9514b33`](../../commit/9514b33)), then spent an hour reading `catalog.csv` and `xref.csv` on their own. That is where the SKU prefix convention showed up, and where I found `SHACKLE-1/2-G` using `GALV` when every other row uses `GV`. I used Claude to check those observations held across all 470 rows rather than the fifty I had scanned.

After that, Claude wrote most of the pattern tables and regex in `normalizer.py` and `matcher.py`. I decided what they had to do and in what order, which is the part that carries the design: category patterns are first-match-wins, so `emt_coupling` must precede `coupling`; size extraction tries fastener diameter before mixed number, or every `3/8-16 x 2-1/2` becomes a 2-1/2 inch screw. That ordering came out of running the normalizer line by line and reading what it produced, not out of a prompt.

Most of my time went into that loop: run, read the output, find the wrong line, work out why, fix it. Generation was the fast part.

I ran every iteration against Groq, which is free, and only switched to the OpenAI key you supplied once the prompts had settled. There was no reason to spend a capped budget on runs I already expected to throw away. The fallback order in `_make_client` reflects that: Groq if `GROQ_API_KEY` is set, OpenAI otherwise, so the same code runs either way and you can point it at your own key without touching anything.

## Caught, rejected, or rewritten

**`cmd_match` was a stub** returning empty line items and never calling the matcher. It ran clean and wrote a well-formed file. Caught it from impossible scores, not from reading the code. [`6916bed`](../../commit/6916bed)

**Attachment regex was `\battach`**, matching `attaching to let you know`. Tightened to `\battached`, same commit as the HTML fallback for emails with no `text/plain` part. [`194c6d3`](../../commit/194c6d3)

**Cross-references were not domain-scoped**, so one customer's private part number could fire on another's email. Also added context carry-forward between lines. [`ec32fa7`](../../commit/ec32fa7)

**Fixture cache collided** on the same body extracted with and without parent context. Folded a context hash into the key. [`ec32fa7`](../../commit/ec32fa7)

**The same cache then served stale responses after a prompt edit**, making three emails look broken in code I had not touched. Same mistake twice: keying on the input but not on the function transforming it. Key now includes a prompt hash. `[COMMIT]`

**The extraction prompt was dropping part numbers** like `AF-04202` and `TSM64072`, which are exactly the tokens the matcher needs for a direct lookup. [`ec32fa7`](../../commit/ec32fa7)

**Two per-category filters whitelisted units.** `_filter_glove` only honoured `PR` and `DZ`, so `4 boxes of nitrile gloves large` had its `BX` discarded and abstained even though the customer named the pack. `[COMMIT]`

**E017's subject and body disagree on quantity.** Pipeline was auto-quoting 25 without seeing that the subject said 20. Added a post-match conflict check. `[COMMIT]`

**Built a `raw`/`resolved` split and reverted it.** Traded four line-alignment differences for seven without changing a SKU. Raised in `DECISIONS.md` as a format change instead. `[COMMIT]` `[COMMIT]`

**`extract` and `run` disagreed on threaded emails.** `run` gave E010 its parent's context, `extract` did not, so the graded command emitted two fragments where the pipeline emitted six lines. Thread handling is now shared. `[COMMIT]`

## Mine

The evidence ladder and the decision to abstain rather than rank. The rule that a missing attribute does not filter, which is what makes underspecified lines come back `ambiguous` instead of `not_in_catalog`. Never auto-substituting a discontinued SKU, never rounding a quantity into a pack it does not divide into. Using a model where the input space is unbounded and deterministic code where it is not. And the measurement that found every bug listed above.