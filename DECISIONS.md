# DECISIONS.md

Roughly 15 hours across the week's evenings. Over the stated budget, and most of the overrun went into measurement rather than features: building a scorer, then chasing differences that turned out to be my scorer disagreeing with itself rather than my matcher being wrong.

## Something in the data that surprised me

E017 is the email where the customer contradicts herself. The subject says `Quote request - 20 ss ball valves 3/4 + hose` and the table in the body says `3/4 ss ball valve, threaded   25`. Same customer, same email, same item, two different quantities. Nothing else in the dev set does this, and I only found it because the answer key wanted `qty: null` on that line and I was working out why my confident 25 was wrong. That reframed the whole quantity problem for me. I had been treating quantity as a parsing problem where the job is to find the number in the string, and the surprise is that the number can be present, unambiguous, correctly parsed, and still be the wrong thing to quote. The signal is not in the line at all. It is in the disagreement between two places in the email. So I added a post-match phase that parses product hints out of the subject using the same normalizer functions I run on body lines, and when subject and body both state a value for quantity, material or size on the same product category and those values differ, I keep the SKU and set `qty: null`. Both sides have to state a value for a conflict to fire, because a missing value on either side is not a conflict, it is just a subject line that did not repeat itself.

## Something in the brief I disagree with

`data/README.md` asks extraction for two things that cannot both be true on a reply.

> Copy the text as written, not normalised.

> A reply that changes an earlier order → the **complete order as the customer now intends it**.

E010 is the test case. Gus writes `make the 1/2 90s 80 not 50, and add 10 of the 1/2 black iron caps, rest stays the same.` Copied as written, that first fragment carries a quantity that is explicitly negated, no material, and a category only recoverable if you know `90s` means 90-degree elbows in this thread. `rest stays the same` is not a line item at all, but it is doing most of the work in the email. The complete order as the customer now intends it is six lines, four of which appear nowhere in E010, and the material `black iron` comes from E003 five days earlier. The second rule requires emitting text the customer never wrote, which the first rule forbids.

I went with the second rule. My extractor uses a separate prompt for follow-ups that receives the parent email's lines as context and returns the complete updated order. `extract` and `run` share that thread handling, so both produce the same six lines for E010 rather than the two fragments a per-email extractor would emit. The reason is that `lines.json` is not only an output, it is the matcher's input, and a matcher that has to reconstruct `black iron` from a thread it cannot see is a matcher I cannot grade in isolation.

The tension shows up somewhere I did not expect, and that is the part I would raise if we only had time for one thing. E003 is not a reply. It never touches the follow-up prompt. And the plain extraction prompt still turned `and 20 of the 3/4″` into `20 of the 3/4″ black iron 90s`, resolving the material from the line above without being asked to. The instruction to produce line items an ISR could quote from pulled harder than the instruction to copy verbatim, because a bare size fragment is not something anyone can quote. That is not a prompt I need to fix. It is the contradiction in the contract surfacing on its own, on an email where no thread logic is running.

I think the right answer is both fields: `raw`, verbatim and auditable, alongside a resolved description the matcher consumes. An ISR reviewing an abstention wants to see what the customer typed. A matcher wants the resolution. Those are different consumers and they should not fight over one string. I built that split, measured it, and reverted it the same evening, because it traded four line-alignment differences for seven without changing a single SKU, and because the format is one string per line so the second field had nowhere to go. That is a change to the contract, not to my code.

## Predicted held-out numbers, and the two kinds of line I expect to lose

Three runs on the dev set, because the pipeline and the two graded commands do not score identically and the gap is informative.

```
run  (extract + match together)          83/86   0 confident wrong   3 alignment pairs
extract then match, my lines             82/86   1 confident wrong   3 alignment pairs
match on your dev/lines.json             83/86   1 confident wrong   2 spurious abstentions
```

The alignment pairs are E003 and E010, described above. Correct SKU, correct quantity, different string, counted once as missing and once as spurious. Against your lines they disappear.

The one confident wrong match is E017, and the reason it appears in the second and third runs but not the first is the disagreement I would raise second. `lines.json` carries the line strings and nothing else. Run end to end, I see the subject contradict the body and return `qty: null`. Graded in isolation, that signal does not exist in the format, and I return 25 confidently. The format makes a class of wrong quote undetectable by construction, and it is the only confident wrong match I have.

For roughly 30 held-out emails I would expect 130 to 160 line items, and I predict **3 to 6 confident wrong matches** and **8 to 15 spurious abstentions**. Abstentions should scale worse, because the design pushes uncertainty toward abstention and the held-out set will contain descriptions my pattern tables have never seen.

**1. An unrecognised qualifier gets silently dropped, and one row survives anyway.** My `_sku_filter` helper narrows candidate rows by a token and falls back to the unfiltered list when the token matches nothing. That fallback is deliberate: returning empty would mean `not_in_catalog`, which claims I do not stock the product when in fact I stock it and just did not understand a word. But the qualifier gets thrown away rather than surfaced. If a customer asks for a flanged brass ball valve and I stock exactly one brass valve, `flanged` matches no SKU, the filter is discarded, one row survives, and I return it confidently. I have quoted a threaded valve to someone who said flanged. On the dev set this never fires with only one survivor, so it costs me nothing here. On held-out it is the first thing I expect to break, and it produces a confident wrong match rather than an abstention, which is the expensive direction. The fix is to record that a filter was discarded and force an abstention when it was, so the system knows the difference between the customer saying nothing and the customer saying something I could not handle.

**2. A novel abbreviation lands on the wrong category pattern, or on none.** `extract_category` is an ordered list of regex-to-category pairs and the first match wins, which makes the ordering load-bearing: `emt_coupling` before `coupling`, `hose_clamp` before `hose`, `hex_cap_screw` before `hex_bolt`. I did not design that ordering up front, I found it. `30 meters of 3/8 push-lok hose` was resolving to `hose_connector`, because my push-lok barb pattern was general enough to swallow the hose itself, which sent it to the `HC-` prefix instead of `HOSE-`. Silent, and only visible because I was reading normalizer output line by line. The ordering is correct for every abbreviation in the dev set, but the dev set is where I learned the abbreviations. A held-out email writing `EMT cplg` either falls through to a more general pattern and gets the wrong prefix, or matches nothing and returns `not_in_catalog`. I expect more of the second, because unfamiliar text usually matches nothing rather than matching the wrong thing. This is the failure mode I would attack first with real inbox volume, because the fix is data rather than design: the patterns are a table, and extending a table is cheap.

## The extraction fork

LLM for extraction, deterministic code for matching. The split is about whether the input space is bounded.

Email prose is unbounded. The dev set alone has free prose, numbered lists, pipe-separated tables, space-aligned tables, an HTML-only body, a CSV attachment, an internal forward, and a reply that modifies an earlier order. You cannot enumerate the formats a customer might use, so a model earns its cost. The catalog is bounded: about 470 SKUs, fully enumerable, and every decision needs to be reproducible, free to run, and to produce a `why` an ISR can check in a second. So matching is regex, table lookups and set filtering, end to end. Cheap checks run before any API call, and every response is cached to a committed fixture so the dev set runs offline. With no key and no fixture, extraction returns an empty list rather than crashing.

The fixture cache is where I was wrong twice, on the same class of mistake. The key was originally a hash of the email body. That collided when the same body was extracted once standalone and once with parent context from a thread: different input to the model, same key. I folded a hash of the parent context in. Then I changed a system prompt and three emails looked broken in ways that had nothing to do with the code I was reading, because the cache was still serving responses generated under the old prompt. Same root cause, second instance. I was keying on the input but not on the function transforming it. The key is now body plus parent context plus prompt, so editing a prompt invalidates the cache automatically. That is the bug I would name if you asked what I learned this week.

## The matcher

The matcher is an evidence ladder. It descends from strongest evidence to weakest, exits the moment it has enough, and abstains when it runs out. Our own SKU appearing literally beats a cross-reference number, which beats attributes parsed out of prose. Tokenisation covers unigrams and bigrams, because competitor part numbers contain spaces and `IP 58899-0336` is invisible to word-boundary splitting. Cross-reference domain scoping is resolved when `xref.csv` loads rather than at lookup time, so the policy lives in one place.

The single most important property is that a missing attribute does not filter. `None` means the customer did not say, not that the field must be null. Get that backwards and every underspecified line filters to zero rows and returns `not_in_catalog`, which destroys the distinction between "we do not stock this" and "I need one more fact from you." That distinction is the entire point of having three abstention reasons instead of one.

Your rule that a unit word is evidence, and its absence when both fit is ambiguity, falls out of that rather than needing code. The catalog carries base-unit and pack-unit SKUs for the same glove and the same hose clamp. `100 nitrile gloves large` names no pack, three rows survive, and the line abstains. `2 dozen nitrile gloves large` names one, and it matches. I did not write a rule for that.

## What I rejected

**Embedding or fuzzy similarity for matching.** The decision I would defend first. Similarity has no concept of a missing attribute. If three materials fit and the customer named none, cosine distance will happily rank them and hand back the top one, which is precisely the case where the correct answer is to not match. Regex fails loudly, by abstaining. Similarity fails silently, by being slightly more confident about one of three wrong answers. A wrong match is a wrong quote a customer receives; an abstention is a line an ISR reviews. I want the failure mode that is visible.

**Auto-substituting discontinued SKUs.** I abstain and put the replacement in `candidates`. The catalog gives me `replaced_by` and it is tempting to just follow it, but a replacement can differ on specs, price or lead time, and the customer asked for the part they asked for. Auto-substitution is a confident wrong match wearing a helpful disguise.

**An agentic loop for matching.** Matching against a 470-row catalog is a filter operation with a decidable answer, so a loop that chooses tools and decides when to stop adds nondeterminism and cost to the one step whose value is being reproducible and free. Where I would use an agent is upstream: an inbox triage layer deciding whether an email needs the RFQ pipeline, needs a human, or needs a reply asking for the attachment that never arrived. That is genuinely open-ended. Matching is not.

## What I know is broken

**Cross-email context does not reach a matcher graded in isolation.** Carry-forward works within an email, so `and 20 of the 3/4″` inherits category and material from the line above it. It does not work across a thread, so E010's first line has nothing to inherit from. Both of my spurious abstentions on your lines are this.

**The xref domain check fails open.** The condition allows a lookup when `domain is None`, but `None` means two different things there. On the xref entry it means not domain-scoped, anyone may use it, which is correct. On the sender it means I could not determine the domain, which is missing information, not permission. As written, an unidentified sender can hit any customer's private cross-reference. Unknown identity should fail closed.

**Only `text/csv` attachments are decoded.** An xlsx or PDF request falls through to `has_pending_attachment` and returns `[]`, which is safe but incomplete: I am telling the ISR to go ask for a file the customer already sent.

**Reel footage is parsed out of the SKU string.** `THHN-12-BLK-500` has 500 feet per reel and I get that by regexing the tail of the identifier. It works because the catalog follows a naming convention, but a suffix or a bundle SKU breaks it silently. That belongs in a catalog column. The same code mutates the parsed line in place during conversion, so the object stops representing what the customer wrote and starts representing what the catalog needs. Nothing downstream reads it today, so it is safe by accident rather than by design.

## What I would do next

1. Track discarded filters and abstain when one was thrown away. Closes the failure mode I expect to cost the most on held-out, and it costs a boolean.
2. Fail closed on unknown sender domains for customer-scoped cross-references.
3. Seed the per-email context from the parent email in a thread, which turns both spurious abstentions into matches and generalises to any follow-up referencing a previous order.