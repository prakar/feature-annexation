#!/usr/bin/env python3
"""
FAM (Feature Annexation Matrix) dimension scoring pipeline.

Scores all 50 events in the corpus on the four real FAM dimensions
(Implementation Gap, Replication Feasibility, Telemetry Exposure,
Integration Pressure -- see Appendix B.2) on the paper's actual 0-100
anchored scale. This is what unlocks the per-case radar "fingerprint" view
in the Dashboard -- currently only 3 worked examples (Appendix B.6) have
real scores; this script extends that to the full corpus.

FRAMING NOTE, same as the now-removed cost-score re-estimation script: this
is an ESTIMATION pass, not a fact-verification pass. There is no source to
web-search for "what is LangChain's Replication Feasibility score." What
CAN be checked is whether the scoring shows real, theory-grounded variance
across the corpus rather than collapsing to the same value for every case --
which is exactly the failure mode the original CIC/POC/IC/AF/PDR cost scores
had (Platform Observation Cost scored "1" for all 50 rows, with zero
variance). This script is deliberately batched -- all 50 cases in ONE
prompt -- so the model has the whole distribution in view and can't repeat
that mistake without it being immediately visible in the output.

Requirements:
    pip install -r requirements.txt

Usage:
    python score_fam_dimensions.py --provider grok
    python score_fam_dimensions.py --status
"""

import sqlite3
import sys
import time
import argparse
import logging
import providers

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
    stream=sys.stdout,
)
log = logging.getLogger("fam_scoring_pipeline")

DB_PATH = "annexation_evidence.db"
MODEL = providers.DEFAULT_MODELS["anthropic"]
PROVIDER = "anthropic"

PROMPT_TEMPLATE = """You are scoring {n} Feature Annexation cases on the Feature Annexation
Matrix (FAM), exactly as defined in this paper's Appendix B.2. This is an ESTIMATION task --
there is no source to look up for "what is X's Replication Feasibility score." Your job is to
produce CONSISTENT, COMPARATIVE, DIFFERENTIATED scores across the whole set below, using the
real anchor definitions given, not to score each case in isolation.

A prior attempt at a DIFFERENT scoring exercise on this same corpus (an earlier, since-removed
cost-proxy framework) produced degenerate output: one dimension was scored identically for
all 50 cases regardless of how different the cases were, because each row was scored alone
with no comparative anchor. Do not repeat that failure. Every dimension below MUST show real
variance across this set of 50 cases.

DIMENSIONS AND ANCHORS (0-100 scale; use the full range, not just the five anchor points):

IMPLEMENTATION GAP -- "to what extent does the offering exist because the platform has not yet
implemented functionality users reasonably expect natively?"
  0 = Independent Value Creation (e.g. a premium physical product, unrelated to any platform gap)
  25 = Adjacent Capability (extends platform functionality, not an obvious omission)
  50 = Supplemental Capability (fills a useful gap, but native support isn't expected)
  75 = Apparent Platform Omission (many users would expect this natively)
  100 = Pure Platform Omission (exists almost entirely because of an obvious missing native feature)

REPLICATION FEASIBILITY -- "how easily can the platform reproduce this using assets it already
controls?"
  0 = Extremely Difficult (needs assets the platform doesn't have: proprietary data, physical
      logistics, regulatory licenses, specialized infrastructure)
  25 = Difficult (needs substantial new assets/expertise)
  50 = Moderate (platform has some prerequisites, meaningful effort remains)
  75 = Easy (most requirements already exist within the platform)
  100 = Trivial (mostly logic/configuration/orchestration/interface design)

TELEMETRY EXPOSURE -- "how much can the platform observe adoption/demand/validation signals for
this offering?"
  0 = Opaque (platform has little/no visibility into usage)
  25 = Weak Visibility (only indirect market signals: reviews, press, search visibility)
  50 = Partial Visibility (platform controls distribution but not runtime behavior)
  75 = Strong Visibility (platform hosts execution or critical interactions)
  100 = Full Visibility (platform directly mediates/routes/records/analyzes usage)

INTEGRATION PRESSURE -- "how much would users benefit if this became a native capability?"
  0 = Independence Is Valuable (users specifically value that it stays independent)
  25 = Mild Benefit (convenient but not transformative if native)
  50 = Noticeable Benefit (users would appreciate it, but tolerate separation)
  75 = Strong Benefit (users frequently express wanting native support)
  100 = Overwhelming Benefit (independent existence is experienced mainly as friction)

CASES (id | platform | offering | annexation event):
{case_list}

Return ONLY valid JSON, no preamble, no markdown fences: a JSON array, one element per case,
SAME ORDER as given above:

[
  {{
    "event_id": <int>,
    "implementation_gap": <0-100>,
    "replication_feasibility": <0-100>,
    "telemetry_exposure": <0-100>,
    "integration_pressure": <0-100>,
    "reasoning": "one or two sentences justifying these scores RELATIVE TO OTHER CASES in this set, not in isolation"
  }},
  ...
]
"""


def get_all_events(conn):
    c = conn.cursor()
    return c.execute("SELECT event_id, platform, offering, annexation_event FROM events ORDER BY event_id").fetchall()


def score_all(events, verbose=False):
    case_list = "\n".join(
        f"{eid} | {platform} | {offering} | {annexation_event}"
        for eid, platform, offering, annexation_event in events
    )
    prompt = PROMPT_TEMPLATE.format(n=len(events), case_list=case_list)

    log.info("Sending all %d cases in one batched request to %s via %s "
              "(comparative scoring needs the whole set in context at once)...",
              len(events), MODEL, PROVIDER)
    call_start = time.monotonic()

    caller = providers.CALLERS[PROVIDER]
    full_text, search_count, stop_reason, input_tokens, output_tokens = caller(prompt, MODEL, verbose=verbose)

    elapsed = time.monotonic() - call_start
    log.info("[%.1fs] Response complete. stop_reason=%s | %d input/%d output tokens.",
              elapsed, stop_reason, input_tokens, output_tokens)

    parsed = providers.extract_json(full_text)
    if not isinstance(parsed, list):
        raise RuntimeError(f"Expected a JSON array, got {type(parsed)}")
    return parsed


def persist_results(conn, results):
    c = conn.cursor()
    for r in results:
        c.execute("""UPDATE events SET
                        fam_implementation_gap=?, fam_replication_feasibility=?,
                        fam_telemetry_exposure=?, fam_integration_pressure=?,
                        fam_reasoning=?, fam_scoring_status='scored'
                     WHERE event_id=?""",
                  (r.get("implementation_gap"), r.get("replication_feasibility"),
                   r.get("telemetry_exposure"), r.get("integration_pressure"),
                   r.get("reasoning"), r.get("event_id")))
    conn.commit()


def print_status(conn):
    c = conn.cursor()
    print(c.execute("SELECT fam_scoring_status, count(*) FROM events GROUP BY fam_scoring_status").fetchall())
    print()
    for dim in ["fam_implementation_gap", "fam_replication_feasibility", "fam_telemetry_exposure", "fam_integration_pressure"]:
        rows = c.execute(f"SELECT MIN({dim}), MAX({dim}), AVG({dim}) FROM events WHERE {dim} IS NOT NULL").fetchone()
        print(f"  {dim}: min={rows[0]} max={rows[1]} avg={rows[2]:.1f}" if rows[0] is not None else f"  {dim}: no data yet")


def main():
    global MODEL, PROVIDER
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider", choices=["anthropic", "openai", "gemini", "grok"], default="anthropic")
    parser.add_argument("--model", type=str, default=None)
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    if args.verbose:
        log.setLevel(logging.DEBUG)

    PROVIDER = args.provider
    MODEL = args.model or providers.DEFAULT_MODELS[PROVIDER]

    conn = sqlite3.connect(DB_PATH)

    if args.status:
        print_status(conn)
        return

    log.info("Using provider=%s, model=%s.", PROVIDER, MODEL)
    events = get_all_events(conn)
    log.info("Scoring all %d events in one batched call.", len(events))

    try:
        results = score_all(events, verbose=args.verbose)
        persist_results(conn, results)
        log.info("Persisted %d scored rows.", len(results))
    except Exception as e:
        log.error("FAILED: %s: %s", type(e).__name__, e)
        return

    print_status(conn)


if __name__ == "__main__":
    main()