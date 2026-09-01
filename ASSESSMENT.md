# The RFQ Inbox — a one-week problem

> Read *The situation*, then the eighteen dev emails, then come back for the rest. This document
> is short on purpose: most of what matters here is *your* judgment, not ours.

## The situation

You have just joined **Ridgeline Industrial Supply**, a distributor of fasteners, pipe fittings,
valves, hose, and electrical parts. Ridgeline's inside sales reps (ISRs) spend most of their day
doing one thing: reading **request-for-quote (RFQ) emails** from customers, working out which
catalog items the customer actually means, and typing up a quote.

That sounds simple. It isn't. Customers describe the same part a dozen ways — in their units,
their part numbers, their shorthand, none of which are ours. They reply to old threads. They
forward things with the whole history underneath. Some of what lands in the inbox isn't a
request at all. And every mis-read line becomes a wrong quote, which costs far more than a slow
one.

The job has exactly two halves, and they are this assessment:

1. **Extract** — from a real email, get the list of things the customer is actually asking
   for, as they wrote them.
2. **Match** — for each of those, decide which catalog item it is. Or decide that you can't.

**You have until the weekend to show us how you would start.** The eighteen dev emails are the
real brief.

## What you are given

```
data/
  README.md            the contract: file formats, the two commands, how we grade
  catalog.csv          Ridgeline's catalog (~470 SKUs: size / material / thread / length, uom + pack qty, price, status + replaced_by)
  xref.csv             known cross-references: customer, competitor and legacy part numbers → sku
  eml_to_json.py       optional helper that turns any .eml into JSON — use it, port it, or ignore it
  check_format.py      validates your output files' shape (it does not score anything)
  dev/
    emails/*.eml       18 inbox emails (mostly plain text, one HTML-only, one with a CSV attachment)
    lines.json         our extraction of those 18 emails — the ground truth for part 1
    answer_key.json    what a careful ISR matched each line to — the ground truth for part 2
```

There is also a **held-out set** of ~30 emails from the same inbox — the same kinds of
customers and the same kinds of surprises, none of the same strings. We run your submission
against it. Work that passes the dev set by fitting it will not survive that; work built from
understanding why the dev set is hard will.

The data is synthetic. No real company, customer, or person is in it.

## Part 1 — Extraction: email in, line items out

`extract --emails <dir> --out lines.json`: for every email, extract the verbatim strings an ISR would
quote from — and nothing else. What counts as a line is defined in `data/README.md`; the
emails are the exam. `dev/lines.json` is our extraction of the dev set — your ground truth.

How you get there — and what it costs you — is your call. It's one of the decisions we'll be
reading about in `DECISIONS.md`. And if you can't get there: take `dev/lines.json` as your
matcher input and go straight to part 2. Part 1 scores as not attempted; part 2 is graded in
isolation either way.

## Part 2 — Matching: line item in, catalog SKU out (or a refusal)

`match --lines lines.json --out predictions.json`: for each extracted string, the catalog SKU —
with the quantity in that SKU's unit of measure — or an explicit abstention (`ambiguous`,
`not_in_catalog`, `discontinued`) with the candidates and a one-line `why`.

This is the half we care most about, and it is a **design** problem, not a string-similarity
problem. There is no library call that knows `½"`, `.5 in` and `0.500` are the same size, that
a customer's part number isn't yours, that "2 boxes" of a thing sold by the hundred isn't 2,
or that when three materials fit and the customer named none, the right answer is to *not*
match. How you structure the catalog, what you normalize, when you use `xref.csv`, where you
put the line between "close enough" and "ask a human" — that's the assessment.

- A confident wrong match and an abstention have very different costs: one is a wrong quote a
  customer receives, the other is a slower quote an ISR reviews. Does your matcher know that?
- How do you *measure* a matcher? We ship no scorer — deciding what to count is part of the
  problem. `dev/answer_key.json` is your ground truth; we run our own scorer on the held-out
  set, and its two headline numbers are **confident wrong matches** and **spurious
  abstentions**. Build your own measurement and show us the numbers that drove your decisions.
- You may use an LLM here too, same rules — though we'd want to hear why, and what it costs
  per line.

**Your matcher must accept any file in the `lines.json` format.** That's how we grade part 2 in
isolation: we run *your* matcher on *our* extraction of the held-out emails. A weak extractor
can't sink a good matcher — and a good extractor can't carry a weak one.

## Optional: the pipeline, end to end

The two stages above are the assessment — everything in this section is extra, welcome, and
never required. If you like, wire the stages together:

```
run --emails <dir> --out predictions.json      # extract → match: raw inbox in, SKUs and quantities out
```

It's one composition line, and it's how the product runs whole: an email goes in, a quote-ready
list of catalog SKUs with quantities comes out. We grade the two stages, not the wiring.
**Also optional:** a simple
page or CLI view that walks one email through the pipeline — raw email → extracted lines →
matched SKU and qty. Zero penalty for skipping it, and we don't score polish; build it only if
it helps you see your own system.

**Also optional: an agentic take.** If a fixed extract→match pipeline feels rigid to you, you
may build `run` as a small **agent** instead — a bounded loop that reads an email, decides
which tools to use (extract, catalog search, xref lookup) and when to stop, and emits the same
`predictions.json`. Same grading either way; it can only help, never hurt. If you go this way:
bound its steps and cost, keep a per-decision trace we can read, and compare it against a plain
pipeline on your own eval. And if you'd rather just *describe* the agent you would build —
tools, stopping rule, forbidden actions — a paragraph in `DECISIONS.md` is welcome too.

## Rules

- **Time.** The package arrives Monday evening, 31 Aug; submission is due **Saturday 5 Sep,
  end of day (23:59 CST)** — and the moment you're done is the moment to send it: we review
  immediately and schedule third/final round interviews accordingly. So, earlier submissions get scheduled
  earlier. Please note that any final-round interviews that are not conducted this week will be scheduled for Tuesday, 9/8. We expect **8–12 hours of work** spread over the week's evenings and grade for that
  budget. Past 16 hours: stop and write. Tell us in `DECISIONS.md` roughly how long you spent.
  If this week doesn't work for you, say so and we'll move the window.
- **Stack.** Anything that runs for us: we run submissions on **Windows — natively, in Docker,
  or under WSL** — with Python 3.11+, Node 20 and Docker available. If your stack assumes
  Linux, ship a Dockerfile; either way, say what we need in `RUNNING.md`.
- **AI tools are allowed, expected, and disclosed.** Use Claude Code, Cursor, Copilot — whatever
  you use for real work. We are evaluating *your* decisions, so `AI_USAGE.md` tells us how you
  used them — and every claim that you rejected, rewrote, or fixed something must point at a
  commit where we can see it. Keep your tool's session history; we may ask to see it.
- **If you use an LLM — allowed anywhere — calls must be replayable.** We send an **OpenAI API
  key with a USD 20 cap** along with this package; read it from `OPENAI_API_KEY` (tell us the
  model in `RUNNING.md`). On the dev set your submission must run with **no key present** —
  record or cache responses and commit the fixtures. On the held-out set we run it with our own
  key; if the key is missing or a call fails, degrade gracefully (your deterministic behaviour,
  or an empty result with a note) — never crash. Prefer your own key or another provider?
  Fine — same rules, at your own cost.
- **Don't fit the dev set.** The held-out set has the same *kinds* of surprises, not the same strings.

## What to hand in

A git repository (zipped or shared — see *Logistics*; no GitHub needed) containing:

1. **The code**, with a `RUNNING.md` that gets us from unzip to the two commands (`extract`,
   `match`) in one setup step — plus `run` if you wired the pipeline. The commands must take
   the input and output paths as arguments, exactly as written in `data/README.md`, because we
   run them unchanged on files you have not seen.
2. **Your outputs on dev**: `lines.json` (if you built an extractor) and `predictions.json`,
   regenerated by those commands.
3. **`DECISIONS.md`** — at most two pages, with these three headed sections **required**:
   - *Something in the data that surprised you* — one paragraph.
   - *Something in this brief or the README you disagree with, and what you did about it.* We
     mean it; the README is not gospel.
   - *Your predicted held-out numbers, and the two kinds of line you expect to lose.* We will
     compare.
   Plus whatever else belongs in a design memo: the extraction fork and why, the matcher
   design, what you rejected, what you know is broken, what you'd do next. Be specific to
   *this* data — the sentence we want to read looks like "the customer's numbering scheme
   collides with ours on two digits, so…".
4. **`AI_USAGE.md`** — at most one page, as above.
5. **A screen recording, five minutes or less** — you, walking us through what you built and
   the decisions you took: one email end-to-end through both commands, then the two decisions
   you'd defend first and why. Link it in `RUNNING.md` (Loom/Drive is fine) or commit the file
   (keep the repo under 50 MB). Production value is worth nothing; a phone pointed at your
   screen is fine.
6. **Commit history as it happened** — zip your project folder *including the `.git`
   directory*; we read the history. Don't squash or tidy it for us; starting from your own
   template is fine if the first commit message says so.

## How we read it

We run both commands on the held-out set **before we read a word you wrote** — your extractor
on the raw emails, and your matcher twice: on your lines and on ours. Then `DECISIONS.md`, your
recording, the code, the commits, `AI_USAGE.md`. Then a 60-minute conversation where you show
us the two emails you find most interesting, predict what your pipeline will do on an email
you've never seen before we run it, defend two decisions, and change something live (any tools
you like — we watch where you look first and what test you name).

If you skip extraction and build your matcher on `dev/lines.json`, part 1 scores as not
attempted; part 2 is graded in isolation either way. Two pages that name three real properties
of this data beat a feature you rushed.

## Logistics

- **Submit:** email your zip (the project folder including `.git`, LLM fixtures committed) to
  **chad@firstdistributors.com** and **vikyath@firstdistributors.com** — or, if it's too big
  for email, put the zip and the recording on Google Drive and send us the link. Code and
  recording both. No GitHub needed.
- **Your code stays yours.** We use it only to evaluate you and delete it when the process ends.
- **Questions:** the same two addresses. We reply within a few hours between 09:00 and 21:00
  CST on weekdays. We answer questions about the data and the format; we won't tell you what
  to build.
- **Timeline:** we review over the weekend and hold the 60-minute conversations on **Monday 7
  and Tuesday 8 Sep**. The earlier you submit, the earlier you're scheduled.
