# Feature Annexation — Evidence Verification Package

## What this is

A decontaminated, resumable pipeline to backfill real, citable evidence into the
Feature Annexation event corpus, replacing self-assigned "Collapse / High Confidence"
style labels that were checked and found to be unreliable.

## What's in the box

- `annexation_evidence.db` — SQLite database, pre-populated with all 50 events from
  the original corpus's "Platform Absorption Dataset v0.2" (the Core Cases + OS +
  Search + Enterprise + Media + Commerce layers). This event/offering/platform layer
  is treated as the trusted superset — it was not found to be hallucinated in the
  spot checks run so far.
- `verify_events.py` — the pipeline script. Calls the Anthropic API with the
  server-side `web_search` tool to verify each event's mechanism and outcome,
  grades source quality, and writes results back to the DB.
- `README.md` — this file.

## What was deliberately deleted, and why

Four columns — `category_outcome`, `complementor_status`, `evidence_strength`,
`confidence` — had their **contents** wiped (schema kept, values set to NULL) before
packaging. Two independent spot-checks during the audit session found that this
specific layer of the original corpus was not just unsourced but **actively wrong**:

- WinZip was coded "Collapse" / "Declined" — but WinZip is still sold and updated today.
- Flashlight apps were coded "Collapse" / "Declined" — but flashlight apps are still
  actively published, updated, and reviewed today.

Both contradicted by directly checkable, dated, real sources within minutes of
looking. The pattern suggests these columns were assigned by narrative plausibility
("platform shipped a feature -> incumbent must have died") rather than by checking
anything. They are not trustworthy in their current state, and rather than try to
"fix" them piecemeal, the decision was to null them out entirely and rebuild from
verified evidence only.

The `cic_score` / `poc_score` / `ic_score` / `af_score` / `pdr_score` columns (from
the "Platform Absorption Dataset v0.2" framework — Complementor Innovation Cost,
Platform Observation Cost, etc.) were **not** wiped, because they weren't
contradicted by evidence in the same way — but be aware they are independently
weak: every single one of the 50 rows in the source has `poc_score = 1`, with zero
variance across wildly different platforms and capabilities, which is itself a sign
these were typed in rather than measured. Treat them as illustrative, not validated,
until/unless a separate audit pass addresses them specifically.

## How the pipeline works

1. Reads events with `verification_status IN ('unverified', 'failed')`.
2. For each one, sends a structured prompt to Claude (via the Anthropic API) with
   the `web_search` tool enabled. The prompt explicitly instructs the model to:
   - find dated, named, URL-backed sources, not category labels;
   - check survival/death status as an open question, not an assumption — this is
     the exact failure mode that produced the WinZip and Flashlight errors;
   - grade every source's tier (PD/PR/MR/AR/CR/RR/DS) honestly;
   - flag explicitly when a finding contradicts the "platform shipped competing
     feature -> complementor died" default narrative.
3. Parses the JSON response and writes outcome fields + evidence rows + a search
   log entry back into the DB.
4. Marks each event `verified`, `contradicted`, `inconclusive`, or `failed` so a
   second run only retries what didn't finish — safe to interrupt at any point.

## Running it on GitHub Codespaces

```bash
pip install anthropic
export ANTHROPIC_API_KEY=sk-ant-...

# Check current state (no API calls, free):
python verify_events.py --status

# Process a small batch first to sanity-check output quality:
python verify_events.py --limit 5

# Review what came back (see "Reviewing output" below), then continue:
python verify_events.py --limit 45

# Or just keep running with no --limit until everything is processed;
# it's safe to Ctrl+C and restart at any point.
python verify_events.py
```

## Reviewing output

After any run, inspect results directly:

```bash
sqlite3 annexation_evidence.db "SELECT event_id, platform, offering, category_outcome, confidence, verification_status FROM events;"

sqlite3 annexation_evidence.db "SELECT * FROM events WHERE verification_status='contradicted';"

sqlite3 annexation_evidence.db "SELECT * FROM evidence WHERE event_id=16;"
```

**Do not treat the model's automated grading as final.** It is the same kind of
judgment call that got the original corpus's outcome columns wrong in the first
place — the prompt is designed to reduce that risk (by explicitly requiring evidence
of survival/death rather than assuming it), but a second human pass over anything
marked `verified` with `confidence: High` is still warranted before it goes in a
manuscript, especially for any row whose outcome supports a key claim in the paper
(e.g. anything cited in §4 or §5 / Platform Utility Paradox).

## Why Anthropic API + `web_search` tool instead of SerpAPI / Bing / Google CSE

You already have an Anthropic key; this avoids standing up a second vendor
relationship, a second billing account, and a second API surface to learn. The
`web_search` tool returns results already attached to a model call that can reason
about them in the same step (grade source tier, paraphrase, flag contradictions),
rather than returning raw search-engine JSON that you'd then need a separate model
call to interpret anyway. There's no capability SerpAPI/Bing/Google CSE would add
here that matters more than that simplicity, for this specific task.

## Known limitations

- This pipeline depends on the model's web search actually finding good sources.
  For genuinely obscure or very recent cases (e.g. AI-ecosystem rows: LangChain,
  MCP wrappers, routing frameworks), expect more `inconclusive` results — that's
  an honest outcome, not a bug.
- Rate limits: the `--sleep` flag and `--limit` flag exist specifically so you can
  throttle yourself rather than getting throttled. Start small.
- The script does not deduplicate or cross-check against the original corpus's A2
  (Temporal/Telemetry), A3 (Ecosystem Reorganization), A4 (Investor) or A5
  (Typology) datasets, which contain overlapping but not identically-keyed claims
  about the same events. That cross-referencing is a separate pass.
