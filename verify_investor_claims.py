#!/usr/bin/env python3
"""
Investor Chilling Dataset (A4) — discourse/sentiment verification pipeline.

WHY THIS IS A SEPARATE SCRIPT FROM verify_events.py, NOT A SHARED ONE:
A1's claims were existence/survival claims -- "did this app exist, does it
still exist" -- which are binary and checkable against a clean fact. A4's
claims are softer: "did ecosystem participants actually talk about this as
platform risk," "did investors actually cite it as a deterrent." Those need
a different verification standard (does real, dated discourse exist using
this framing, not just is the underlying fact true) and a different output
shape. Rather than overload one schema with two different kinds of claims,
this is its own table (investor_claims) and its own prompt, but it reuses
every piece of engineering already debugged in verify_events.py: streaming
with heartbeat logging, the max_uses search cap, the pause_turn continuation
loop, and the robust preamble-tolerant JSON extraction. None of those are
claim-type-specific; all of them were bugs found by actually running the
other pipeline, and they'd reappear here unchanged if skipped.

Requirements:
    pip install -r requirements.txt

Environment (set whichever provider(s) you plan to use):
    export ANTHROPIC_API_KEY=sk-ant-...
    export OPENAI_API_KEY=sk-...
    export GOOGLE_API_KEY=...
    export XAI_API_KEY=...

Usage:
    python verify_investor_claims.py                              # process all unverified, anthropic
    python verify_investor_claims.py --provider openai --limit 1  # test a new provider on one row first
    python verify_investor_claims.py --provider gemini
    python verify_investor_claims.py --provider grok
    python verify_investor_claims.py --claim-id IC-M3              # reprocess one row
    python verify_investor_claims.py --status
"""

import sqlite3
import json
import time
import sys
import argparse
import datetime
import logging
import providers

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
    stream=sys.stdout,
)
log = logging.getLogger("investor_claims_pipeline")

DB_PATH = "annexation_evidence.db"
MODEL = providers.DEFAULT_MODELS["anthropic"]
PROVIDER = "anthropic"

VERIFICATION_PROMPT_TEMPLATE = """You are verifying one row of an "Investor Chilling" dataset for an academic
platform-economics paper on Feature Annexation. Unlike a simple fact-check, this
dataset makes DISCOURSE claims -- not "did X happen" but "did people (investors,
founders, journalists) actually talk about X in a specific way."

CASE TO VERIFY:
  Platform: {platform}
  Annexation Event: {annexation_event}
  Original (UNVERIFIED, narrative-assigned, no citations) claims to check:
    - Reputation Signal claimed: {orig_reputation_signal}
    - Investor Learning claimed: {orig_investor_learning}
    - Entry Deterrence claimed: {orig_entry_deterrence}
    - Funding Impact claimed: {orig_funding_impact}

Your task: use web search to find REAL, dated, named, URL-backed evidence of
whether this discourse actually happened -- not whether it's plausible that it
could have. Specifically look for:

1. Did a named term or phrase (e.g. "Sherlocking," "Google Risk," "framework risk")
   actually get used in press, blog posts, VC commentary, or founder statements
   about THIS specific platform/event? Find an actual instance, not just that the
   general concept of platform risk exists in the abstract.
2. Is there a real, named, dated source (an article, a VC's blog post, a founder's
   public statement, a pitch deck leak, an academic paper) discussing this
   specific case as a deterrent to investment or new entry? Generic "platforms
   are risky" commentary does NOT count -- it needs to be about this case.
3. Is there any quantitative or semi-quantitative evidence of funding impact
   (e.g. a sector report showing reduced VC investment in a category after a
   specific annexation event)? This is the hardest claim in the dataset to
   verify and it is fine to come back with "Insufficient_Evidence" here --
   that is a more honest answer than inventing a number.

IMPORTANT: a prior audit of a SIBLING dataset in this same corpus (A1, the event
corpus) found that self-assigned "High confidence" labels were attached to claims
that turned out to be false on inspection (e.g. a claimed "category collapse" where
the product in question is still sold commercially today). Apply that same
skepticism here -- do not let a claim's specificity or confident phrasing
substitute for an actual source you found.

Grade every source as: PD (platform documentation), PR (product documentation),
MR (market reporting / press), AR (academic), CR (community/forum), RR (regulatory),
VC (named VC/investor commentary -- a new category specific to this dataset).

Return ONLY valid JSON, no preamble, no markdown fences, matching exactly this shape:

{{
  "discourse_confirmed": true | false | "partial",
  "verified_reputation_signal": "what you actually found, in your own words, or 'No real evidence found for the claimed signal'",
  "verified_investor_learning": "what you actually found, or 'No real evidence found'",
  "verified_entry_deterrence": "what you actually found, or 'No real evidence found'",
  "verified_funding_impact": "Low" | "Medium" | "High" | "Insufficient_Evidence",
  "verified_confidence": "High" | "Medium" | "Low",
  "contradicts_original": true | false,
  "sources": [
    {{
      "claim_supported": "short description",
      "source_type": "PD|PR|MR|AR|CR|RR|VC",
      "title": "exact title",
      "url": "exact url",
      "publication_date": "YYYY-MM-DD or best available, or 'undated'",
      "excerpt_paraphrase": "your own words, NOT a verbatim quote",
      "supports_or_contradicts": "supports" | "contradicts" | "partial"
    }}
  ],
  "notes": "anything a human reviewer should know"
}}
"""


def get_unverified_claims(conn, limit=None, specific_id=None):
    c = conn.cursor()
    if specific_id is not None:
        c.execute("""SELECT claim_id, platform, annexation_event, orig_reputation_signal,
                            orig_investor_learning, orig_entry_deterrence, orig_funding_impact
                     FROM investor_claims WHERE claim_id=?""", (specific_id,))
    else:
        q = """SELECT claim_id, platform, annexation_event, orig_reputation_signal,
                      orig_investor_learning, orig_entry_deterrence, orig_funding_impact
               FROM investor_claims
               WHERE verification_status IN ('unverified', 'failed')
               ORDER BY claim_id"""
        if limit:
            q += f" LIMIT {int(limit)}"
        c.execute(q)
    return c.fetchall()


def verify_one_claim(client, platform, annexation_event, orig_rep, orig_inv, orig_deter, orig_fund, verbose=False):
    """
    Dispatches to the active provider's caller (providers.CALLERS[PROVIDER]) --
    same dispatch pattern as verify_events.py's verify_one_event(), kept
    consistent across both scripts deliberately so a fix to providers.py
    benefits both pipelines at once rather than needing to be applied twice.
    """
    prompt = VERIFICATION_PROMPT_TEMPLATE.format(
        platform=platform, annexation_event=annexation_event,
        orig_reputation_signal=orig_rep, orig_investor_learning=orig_inv,
        orig_entry_deterrence=orig_deter, orig_funding_impact=orig_fund,
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


def persist_result(conn, claim_id, result):
    c = conn.cursor()
    contradicts = bool(result.get("contradicts_original"))
    discourse = result.get("discourse_confirmed")

    # STATUS LOGIC FIX: a prior version of this function used
    # `elif contradicts or discourse is False: status = "contradicted"`,
    # which incorrectly treated "we didn't find clean evidence the discourse
    # happened" (discourse_confirmed=False) as equivalent to "we found
    # evidence that actively contradicts the original row"
    # (contradicts_original=True). Those are different findings -- the first
    # is an evidentiary gap, the second is a positive disagreement -- and
    # conflating them produced a real discrepancy in practice: a live run
    # printed "contradicted: 6" in the status summary but only listed 4 rows
    # under "Claims contradicted by real evidence," because print_status()
    # correctly filters on contradicts_original=1 while this function was
    # marking two evidentiary-gap rows (IC-G3, IC-G4) as 'contradicted' even
    # though their own contradicts_original value was False. Fixed by making
    # contradicts_original the only thing that can produce 'contradicted'.
    if contradicts:
        status = "contradicted"
    elif discourse is True:
        status = "verified_consistent"
    else:
        status = "inconclusive"  # discourse_confirmed False/partial, but no positive contradiction found

    c.execute("""UPDATE investor_claims SET
                    verified_reputation_signal=?, verified_investor_learning=?,
                    verified_entry_deterrence=?, verified_funding_impact=?,
                    verified_confidence=?, contradicts_original=?, verification_status=?, notes=?
                 WHERE claim_id=?""",
              (result.get("verified_reputation_signal"), result.get("verified_investor_learning"),
               result.get("verified_entry_deterrence"), result.get("verified_funding_impact"),
               result.get("verified_confidence"), 1 if contradicts else 0, status,
               result.get("notes"), claim_id))

    # Reuse the same evidence table as A1's pipeline -- it's already keyed
    # loosely (event_id), so we store investor-claims evidence with a NULL
    # event_id and the claim_id folded into claim_supported for traceability,
    # rather than creating a third near-duplicate evidence table.
    today = datetime.date.today().isoformat()
    for src in result.get("sources", []):
        c.execute("""INSERT INTO evidence
                        (event_id, claim_supported, source_type, title, url,
                         publication_date, retrieved_date, excerpt_paraphrase,
                         supports_or_contradicts, notes)
                     VALUES (NULL,?,?,?,?,?,?,?,?,?)""",
                  (f"[{claim_id}] {src.get('claim_supported')}", src.get("source_type"),
                   src.get("title"), src.get("url"), src.get("publication_date"),
                   today, src.get("excerpt_paraphrase"), src.get("supports_or_contradicts"), None))

    conn.commit()


def print_status(conn):
    c = conn.cursor()
    rows = c.execute("SELECT verification_status, count(*) FROM investor_claims GROUP BY verification_status").fetchall()
    total = c.execute("SELECT count(*) FROM investor_claims").fetchone()[0]
    print(f"Total investor_claims rows: {total}")
    for status, n in rows:
        print(f"  {status}: {n}")
    contradictions = c.execute(
        "SELECT claim_id, platform, annexation_event FROM investor_claims WHERE contradicts_original=1"
    ).fetchall()
    if contradictions:
        print(f"\nClaims contradicted by real evidence ({len(contradictions)}):")
        for row in contradictions:
            print(f"  {row[0]}: {row[1]} -> {row[2]}")


def main():
    global MODEL, PROVIDER

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--claim-id", type=str, default=None)
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--sleep", type=float, default=2.0)
    parser.add_argument("--provider", choices=["anthropic", "openai", "gemini", "grok"], default="anthropic",
                         help="Which API to spend against. anthropic is the only path confirmed against a "
                              "live API so far -- run --limit 1 on a new provider before trusting a full batch.")
    parser.add_argument("--model", type=str, default=None,
                         help="Override the default model for the chosen provider. Defaults: "
                              + ", ".join(f"{k}={v}" for k, v in providers.DEFAULT_MODELS.items()))
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    if args.verbose:
        log.setLevel(logging.DEBUG)

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
        log.info("NOTE: this provider path has not been confirmed against a live API yet -- "
                  "treat this run as the real first test. If it breaks, the traceback plus a look at "
                  "providers.py's call_%s() function is the fastest way to fix it.", PROVIDER)
    client = None  # providers.py constructs its own client per-provider

    claims = get_unverified_claims(conn, limit=args.limit, specific_id=args.claim_id)
    log.info("Found %d claim(s) to process this run.", len(claims))
    if not claims:
        log.info("Nothing to do. Run with --status to see progress.")
        return

    succeeded, failed = 0, 0
    run_start = time.monotonic()

    for idx, (claim_id, platform, annexation_event, orig_rep, orig_inv, orig_deter, orig_fund) in enumerate(claims, start=1):
        log.info("=" * 70)
        log.info("Claim %d/%d (%s) -- %.1fs elapsed", idx, len(claims), claim_id, time.monotonic() - run_start)
        log.info("  Platform: %s | Event: %s", platform, annexation_event)

        try:
            result = verify_one_claim(client, platform, annexation_event, orig_rep, orig_inv, orig_deter, orig_fund,
                                       verbose=args.verbose)
            persist_result(conn, claim_id, result)
            log.info("  RESULT: discourse_confirmed=%s | contradicts_original=%s | confidence=%s",
                      result.get("discourse_confirmed"), result.get("contradicts_original"),
                      result.get("verified_confidence"))
            succeeded += 1
        except Exception as e:
            log.error("  FAILED: %s: %s", type(e).__name__, e)
            conn.execute("UPDATE investor_claims SET verification_status='failed', notes=? WHERE claim_id=?",
                         (f"Automated pass failed ({type(e).__name__}): {e}", claim_id))
            conn.commit()
            failed += 1

        if idx < len(claims):
            log.info("  Sleeping %.1fs before next claim...", args.sleep)
            time.sleep(args.sleep)

    log.info("=" * 70)
    log.info("Run complete. Succeeded: %d, Failed: %d.", succeeded, failed)
    print_status(conn)


if __name__ == "__main__":
    main()