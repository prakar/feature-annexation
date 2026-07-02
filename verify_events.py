#!/usr/bin/env python3
"""
Feature Annexation corpus — evidence verification pipeline.

Run on GitHub Codespaces. Resumable: re-running this script skips events
already marked 'verified' or 'contradicted', and retries 'unverified' or
'failed' ones. Safe to interrupt (Ctrl+C, Codespace restart, rate limit)
and resume.

Requirements:
    pip install anthropic

Environment:
    export ANTHROPIC_API_KEY=sk-ant-...

Usage:
    python verify_events.py                 # process all unverified events
    python verify_events.py --limit 10      # process only 10 this run (rate-limit friendly)
    python verify_events.py --event-id 7    # reprocess one specific event
    python verify_events.py --status        # print progress summary, no API calls
"""

import sqlite3
import json
import time
import sys
import argparse
import datetime
import logging
import providers

# ---------------------------------------------------------------------------
# WHY LOGGING IS SET UP THE WAY IT IS
# ---------------------------------------------------------------------------
# The original complaint that produced this revision was: "the process is
# waiting long on the CLI so I can't tell [what it's doing]." That's a
# visibility problem, not a correctness problem -- the script was silent
# during the slow part (the network round-trip to Claude + its web searches,
# which can easily take 10-60 seconds per event), so it *looked* hung even
# when it wasn't.
#
# The fix is to log at every state transition, with timestamps and elapsed
# time, and to flush stdout immediately rather than letting Python buffer it
# (which is its own classic cause of "nothing is printing" on a slow CLI).
# We use Python's `logging` module rather than bare `print()` so that every
# line gets a wall-clock timestamp for free, and so verbosity is a single
# knob (--verbose) rather than something you'd need to hand-edit print
# statements to change.

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
    stream=sys.stdout,
)
log = logging.getLogger("feature_annexation_pipeline")

DB_PATH = "annexation_evidence.db"
# MULTI-PROVIDER NOTE: model selection now goes through providers.py's
# DEFAULT_MODELS dict, keyed by --provider. The MODEL constant below is kept
# only as the value actually used for a given run (set in main()), so the
# rest of this file (which references MODEL in log lines and the search_log
# table) doesn't need to change throughout.
MODEL = providers.DEFAULT_MODELS["anthropic"]
PROVIDER = "anthropic"


# This is the grading rubric / prompt template referenced as "the exact prompt"
# in the conversation that produced this pipeline. It encodes the same judgment
# discipline used manually earlier in the session: grade source tier honestly,
# explicitly mark contradictions rather than burying them, never inflate
# confidence, and require a real dated/named/URL'd source -- not a category label.
VERIFICATION_PROMPT_TEMPLATE = """You are conducting a provenance verification pass for one row of an
academic research dataset on "Feature Annexation" (the incorporation of independently
validated third-party functionality into native platform capability).

CASE TO VERIFY:
  Platform: {platform}
  Offering / Complementor: {offering}
  Claimed Annexation Event: {annexation_event}

Your task has two parts. Use web search to investigate both.

PART 1 — MECHANISM CHECK
Find real, dated, named, URL-backed evidence that:
  (a) the independent offering existed and had some adoption/validation BEFORE the
      platform's native capability shipped, and
  (b) the platform did in fact ship a native capability that substantially overlaps
      with what the offering provided.
Only primary sources (official platform docs/blogs/release notes), or named, dated
independent press / academic / regulatory sources count as real evidence. Marketing
blogs from vendors with a commercial interest in the topic are weak tier -- usable,
but must be labeled as such, not treated as equivalent to a primary source.

PART 2 — OUTCOME CHECK (this is the part the existing corpus got wrong before)
Do NOT assume the complementor declined, shrank, or "lost" just because the platform
shipped a competing feature. Actively search for whether the complementor/category:
  - still exists / is still sold or actively maintained (check for this explicitly,
    it is the single most common false-positive failure mode in this corpus), or
  - genuinely declined/shut down/was acquired (find a dated source saying so), or
  - the evidence is genuinely insufficient to say either way.

Grade EVERY source you find as one of: PD (platform documentation), PR (product
documentation), MR (market reporting / press), AR (academic), CR (community/forum),
RR (regulatory), DS (dataset/stats). Do not invent a source you have not actually
retrieved a URL for.

Return ONLY valid JSON, no preamble, no markdown fences, matching exactly this shape:

{{
  "mechanism_verified": true | false | "insufficient_evidence",
  "category_outcome": "Collapse" | "Contraction" | "Compression" | "Transformation" | "Stratification" | "Survived_No_Clear_Reorganization" | "Insufficient_Evidence",
  "complementor_status": "Survived" | "Declined" | "Emerging" | "Unknown",
  "confidence": "High" | "Medium" | "Low",
  "evidence_strength": "High" | "Medium" | "Low",
  "contradicts_typical_collapse_narrative": true | false,
  "sources": [
    {{
      "claim_supported": "short description of what this source supports",
      "source_type": "PD|PR|MR|AR|CR|RR|DS",
      "title": "exact title",
      "url": "exact url",
      "publication_date": "YYYY-MM-DD or best available, or 'undated'",
      "excerpt_paraphrase": "your own words, NOT a verbatim quote, summarizing what it says",
      "supports_or_contradicts": "supports" | "contradicts" | "partial"
    }}
  ],
  "notes": "anything a human reviewer should know, including any contradiction with the dramatic/default narrative"
}}
"""


def get_unverified_events(conn, limit=None, specific_id=None):
    """
    Decide which rows still need work.

    Resumability lives entirely in this one query: any event whose
    verification_status is still 'unverified' (never attempted) or 'failed'
    (attempted but errored, e.g. a malformed JSON response or a dropped
    connection) is fair game to retry. Anything 'verified', 'contradicted',
    or 'inconclusive' is left alone -- those are *results*, not problems to
    retry, even if you personally disagree with the result later (that's a
    job for a human review pass over the evidence table, not for re-running
    the search).
    """
    c = conn.cursor()
    if specific_id is not None:
        log.debug("Querying for a single specific event_id=%s (forced reprocess).", specific_id)
        c.execute("SELECT event_id, platform, offering, annexation_event FROM events WHERE event_id=?", (specific_id,))
    else:
        q = """SELECT event_id, platform, offering, annexation_event FROM events
               WHERE verification_status IN ('unverified', 'failed')
               ORDER BY event_id"""
        if limit:
            q += f" LIMIT {int(limit)}"
        log.debug("Querying for unverified/failed events. SQL: %s", " ".join(q.split()))
        c.execute(q)
    return c.fetchall()


def verify_one_event(client, event_id, platform, offering, annexation_event, verbose=False):
    """
    Dispatches to the active provider's caller (providers.CALLERS[PROVIDER]).
    `client` is unused for non-anthropic providers (kept as a parameter for
    call-site compatibility) -- each provider function in providers.py
    constructs its own client internally, since each SDK has a different
    client shape and auth mechanism.
    """
    prompt = VERIFICATION_PROMPT_TEMPLATE.format(
        platform=platform, offering=offering, annexation_event=annexation_event
    )

    log.info("  Sending request to %s via %s (this typically takes 10-90s; logging progress as it happens)...",
              MODEL, PROVIDER)
    call_start = time.monotonic()

    caller = providers.CALLERS[PROVIDER]
    full_text, search_count, stop_reason, input_tokens, output_tokens = caller(
        prompt, MODEL, verbose=verbose
    )

    total_elapsed = time.monotonic() - call_start
    log.info("  [%.1fs] Response complete. stop_reason=%s | %d web search(es) (best-effort count) run, "
              "%d input/%d output tokens.",
              total_elapsed, stop_reason, search_count, input_tokens, output_tokens)

    return providers.extract_json(full_text)

PROTECTED_OUTCOMES = {'Contested_Platform_Retreat'}

def persist_result(conn, event_id, result):
    """
    Write one event's verification result to disk and commit immediately.

    CONTRADICTS_DEFAULT_NARRATIVE BUG NOTE: an earlier version of this function
    computed verification_status as 'verified' whenever mechanism_verified was
    True, falling back to 'contradicted' only otherwise -- which meant that
    whenever a case had BOTH mechanism_verified=True AND
    contradicts_typical_collapse_narrative=True (the common case -- confirming
    the mechanism is usually the easy part, and most complementors turned out
    to survive), the contradiction got silently swallowed into 'verified'. On
    a real 38-event run this caused 34 genuine contradictions to be miscounted
    as plain 'verified' results, undercounting the actual finding by more than
    10x (3 reported vs. 37 actual). Fixed by giving contradiction its own
    column rather than overloading one status field with two independent
    facts.
    """
    c = conn.cursor()
    today = datetime.date.today().isoformat()

    mech = result.get("mechanism_verified")
    contradicts = bool(result.get("contradicts_typical_collapse_narrative"))

    if mech is not True:
        status = "inconclusive"
    elif contradicts:
        status = "contradicted"
    else:
        status = "verified_consistent"  # mechanism confirmed AND outcome matches the original dramatic label

    log.debug("  Computed verification_status='%s' from mechanism_verified=%r, contradicts_flag=%r",
              status, mech, contradicts)
    
    # Preserve manually-assigned category_outcomes the pipeline cannot derive.
    existing = c.execute("SELECT category_outcome FROM events WHERE event_id=?", (event_id,)).fetchone()
    existing_outcome = existing[0] if existing else None
    if existing_outcome in PROTECTED_OUTCOMES:
        final_outcome = existing_outcome
        log.info("  Preserving protected category_outcome=%r for event %d.", existing_outcome, event_id)
    else:
        final_outcome = result.get("category_outcome")

    c.execute("""UPDATE events SET
                    category_outcome=?, complementor_status=?, evidence_strength=?,
                    confidence=?, verification_status=?, contradicts_default_narrative=?, notes=?
                 WHERE event_id=?""",
              (result.get("category_outcome"), result.get("complementor_status"),
               result.get("evidence_strength"), result.get("confidence"),
               status, 1 if contradicts else 0, result.get("notes"), event_id))

    sources = result.get("sources", [])
    log.info("  Persisting %d source(s) to the evidence table.", len(sources))
    for i, src in enumerate(sources, start=1):
        log.debug("    source %d/%d: [%s] %s (%s)",
                  i, len(sources), src.get("source_type"), src.get("title"), src.get("url"))
        c.execute("""INSERT INTO evidence
                        (event_id, claim_supported, source_type, title, url,
                         publication_date, retrieved_date, excerpt_paraphrase,
                         supports_or_contradicts, notes)
                     VALUES (?,?,?,?,?,?,?,?,?,?)""",
                  (event_id, src.get("claim_supported"), src.get("source_type"),
                   src.get("title"), src.get("url"), src.get("publication_date"),
                   today, src.get("excerpt_paraphrase"), src.get("supports_or_contradicts"),
                   None))

    c.execute("""INSERT INTO search_log (event_id, query, step_purpose, outcome, model_used, timestamp)
                 VALUES (?,?,?,?,?,?)""",
              (event_id, "[automated verification pass]", "mechanism + outcome verification",
               status, MODEL, today))

    conn.commit()
    log.debug("  Committed to %s.", DB_PATH)


def print_status(conn):
    """
    A pure read-only summary -- no API calls, instant, safe to run as often
    as you like just to reassure yourself the process is making progress
    without interrupting it. Run this from a *second* terminal while the
    main run is going, since SQLite handles concurrent readers fine even
    while one writer is committing.
    """
    c = conn.cursor()
    rows = c.execute("SELECT verification_status, count(*) FROM events GROUP BY verification_status").fetchall()
    total = c.execute("SELECT count(*) FROM events").fetchone()[0]
    print(f"Total events: {total}")
    for status, n in rows:
        print(f"  {status}: {n}")
    contradictions = c.execute(
        "SELECT event_id, platform, offering, annexation_event FROM events WHERE contradicts_default_narrative=1"
    ).fetchall()
    if contradictions:
        print(f"\nConfirmed contradictions of the original 'Collapse'-style narrative ({len(contradictions)}):")
        for row in contradictions:
            print(f"  #{row[0]}: {row[1]} / {row[2]} -> {row[3]}")
    
        print("\nOutcome distribution:")
        outcome_rows = c.execute(
            "SELECT category_outcome, count(*) FROM events GROUP BY category_outcome ORDER BY count(*) DESC"
        ).fetchall()
        for outcome, n in outcome_rows:
            print(f"  {outcome}: {n}")




def main():
    global MODEL, PROVIDER

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=None, help="Max number of events to process this run")
    parser.add_argument("--event-id", type=int, default=None, help="Reprocess a single event by ID")
    parser.add_argument("--status", action="store_true", help="Print progress and exit, no API calls")
    parser.add_argument("--sleep", type=float, default=2.0, help="Seconds to sleep between API calls (rate-limit courtesy)")
    parser.add_argument("--provider", choices=["anthropic", "openai", "gemini", "grok"], default="anthropic",
                         help="Which API to spend against. anthropic is the only path that's been run "
                              "against a live API in this project so far -- the other three were written "
                              "against current docs but not live-tested (see providers.py docstring). "
                              "Run --limit 1 on a new provider before trusting a full batch to it.")
    parser.add_argument("--model", type=str, default=None,
                         help="Override the default model for the chosen provider. Defaults: "
                              + ", ".join(f"{k}={v}" for k, v in providers.DEFAULT_MODELS.items()))
    parser.add_argument("--verbose", action="store_true",
                         help="Also log token-streaming heartbeats and SQL queries (DEBUG level). "
                              "Use this if you want maximum visibility into exactly what's happening "
                              "while you wait.")
    args = parser.parse_args()

    if args.verbose:
        log.setLevel(logging.DEBUG)
        log.debug("Verbose mode on: you will see streaming heartbeats and raw SQL.")

    PROVIDER = args.provider
    MODEL = args.model or providers.DEFAULT_MODELS[PROVIDER]

    log.info("Connecting to %s", DB_PATH)
    conn = sqlite3.connect(DB_PATH)

    if args.status:
        print_status(conn)
        return

    log.info("Using provider=%s, model=%s. Reading %s from environment.",
              PROVIDER, MODEL, providers.REQUIRED_ENV_VAR[PROVIDER])
    if PROVIDER != "anthropic":
        log.info("NOTE: this provider path has not been run against a live API by the author of this "
                  "script -- treat this run as the real first test. If it breaks, the error message "
                  "and a quick look at providers.py's call_%s() function is the fastest way to fix it.",
                  PROVIDER)
    client = None  # providers.py constructs its own client per-provider; kept for call-site compatibility

    events = get_unverified_events(conn, limit=args.limit, specific_id=args.event_id)
    log.info("Found %d event(s) to process this run.", len(events))
    if not events:
        log.info("Nothing to do. Run with --status to see overall progress, "
                 "or --event-id N to force-reprocess a specific row.")
        return

    succeeded, failed = 0, 0
    run_start_wall = datetime.datetime.now(datetime.timezone.utc)
    run_start_mono = time.monotonic()

    for idx, (event_id, platform, offering, annexation_event) in enumerate(events, start=1):
        elapsed_total = time.monotonic() - run_start_mono
        log.info("=" * 70)
        log.info("Event %d/%d (id=%s) -- %.1fs elapsed in this run so far",
                  idx, len(events), event_id, elapsed_total)
        log.info("  Platform: %s | Offering: %s | Claimed event: %s", platform, offering, annexation_event)

        try:
            event_start = time.monotonic()
            result = verify_one_event(client, event_id, platform, offering, annexation_event, verbose=args.verbose)
            persist_result(conn, event_id, result)
            event_elapsed = time.monotonic() - event_start

            log.info("  RESULT: mechanism_verified=%s | category_outcome=%s | confidence=%s | "
                      "contradicts_default_narrative=%s | (%.1fs)",
                      result.get("mechanism_verified"), result.get("category_outcome"),
                      result.get("confidence"), result.get("contradicts_typical_collapse_narrative"),
                      event_elapsed)
            succeeded += 1

        except json.JSONDecodeError as e:
            # Specifically distinguished from other exceptions because it has
            # a specific likely cause (model didn't follow the "JSON only"
            # instruction) and a specific fix (just retry -- it's nondeterministic).
            log.error("  FAILED (could not parse model output as JSON): %s", e)
            conn.execute("UPDATE events SET verification_status='failed', notes=? WHERE event_id=?",
                         (f"JSON parse error on automated pass: {e}", event_id))
            conn.commit()
            failed += 1

        except Exception as e:
            log.error("  FAILED: %s: %s", type(e).__name__, e)
            conn.execute("UPDATE events SET verification_status='failed', notes=? WHERE event_id=?",
                         (f"Automated pass failed ({type(e).__name__}): {e}", event_id))
            conn.commit()
            failed += 1

        if idx < len(events):
            log.info("  Sleeping %.1fs before next event (rate-limit courtesy)...", args.sleep)
            time.sleep(args.sleep)

    total_elapsed = time.monotonic() - run_start_mono
    conn.execute("""INSERT INTO run_log (started_at, finished_at, events_processed, events_succeeded, events_failed, notes)
                     VALUES (?,?,?,?,?,?)""",
                 (run_start_wall.isoformat(), datetime.datetime.now(datetime.timezone.utc).isoformat(),
                  len(events), succeeded, failed, None))
    conn.commit()

    log.info("=" * 70)
    log.info("Run complete in %.1fs. Succeeded: %d, Failed: %d.", total_elapsed, succeeded, failed)
    print_status(conn)


if __name__ == "__main__":
    main()