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
import argparse
import datetime
from anthropic import Anthropic

DB_PATH = "annexation_evidence.db"
MODEL = "claude-sonnet-4-6"

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
    c = conn.cursor()
    if specific_id is not None:
        c.execute("SELECT event_id, platform, offering, annexation_event FROM events WHERE event_id=?", (specific_id,))
    else:
        q = """SELECT event_id, platform, offering, annexation_event FROM events
               WHERE verification_status IN ('unverified', 'failed')
               ORDER BY event_id"""
        if limit:
            q += f" LIMIT {int(limit)}"
        c.execute(q)
    return c.fetchall()


def verify_one_event(client, event_id, platform, offering, annexation_event):
    prompt = VERIFICATION_PROMPT_TEMPLATE.format(
        platform=platform, offering=offering, annexation_event=annexation_event
    )
    response = client.messages.create(
        model=MODEL,
        max_tokens=4000,
        messages=[{"role": "user", "content": prompt}],
        tools=[{"type": "web_search_20250305", "name": "web_search"}],
    )
    # Concatenate all text blocks (search results produce multiple blocks)
    text_parts = [block.text for block in response.content if getattr(block, "type", None) == "text"]
    full_text = "\n".join(text_parts).strip()

    # Strip accidental code fences if the model adds them despite instructions
    if full_text.startswith("```"):
        full_text = full_text.strip("`")
        if full_text.lower().startswith("json"):
            full_text = full_text[4:].strip()

    return json.loads(full_text)


def persist_result(conn, event_id, result):
    c = conn.cursor()
    today = datetime.date.today().isoformat()

    mech = result.get("mechanism_verified")
    status = "verified" if mech is True else ("contradicted" if result.get("contradicts_typical_collapse_narrative") else "inconclusive")

    c.execute("""UPDATE events SET
                    category_outcome=?, complementor_status=?, evidence_strength=?,
                    confidence=?, verification_status=?, notes=?
                 WHERE event_id=?""",
              (result.get("category_outcome"), result.get("complementor_status"),
               result.get("evidence_strength"), result.get("confidence"),
               status, result.get("notes"), event_id))

    for src in result.get("sources", []):
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


def print_status(conn):
    c = conn.cursor()
    rows = c.execute("SELECT verification_status, count(*) FROM events GROUP BY verification_status").fetchall()
    total = c.execute("SELECT count(*) FROM events").fetchone()[0]
    print(f"Total events: {total}")
    for status, n in rows:
        print(f"  {status}: {n}")
    contradictions = c.execute(
        "SELECT event_id, platform, offering, annexation_event FROM events WHERE verification_status='contradicted'"
    ).fetchall()
    if contradictions:
        print("\nConfirmed contradictions of the original 'Collapse'-style narrative:")
        for row in contradictions:
            print(f"  #{row[0]}: {row[1]} / {row[2]} -> {row[3]}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None, help="Max number of events to process this run")
    parser.add_argument("--event-id", type=int, default=None, help="Reprocess a single event by ID")
    parser.add_argument("--status", action="store_true", help="Print progress and exit, no API calls")
    parser.add_argument("--sleep", type=float, default=2.0, help="Seconds to sleep between API calls (rate-limit courtesy)")
    args = parser.parse_args()

    conn = sqlite3.connect(DB_PATH)

    if args.status:
        print_status(conn)
        return

    client = Anthropic()  # reads ANTHROPIC_API_KEY from environment

    events = get_unverified_events(conn, limit=args.limit, specific_id=args.event_id)
    print(f"Processing {len(events)} event(s)...")

    succeeded, failed = 0, 0
    run_start = datetime.datetime.utcnow().isoformat()

    for event_id, platform, offering, annexation_event in events:
        print(f"\n[{event_id}] {platform} / {offering} -> {annexation_event}")
        try:
            result = verify_one_event(client, event_id, platform, offering, annexation_event)
            persist_result(conn, event_id, result)
            print(f"  -> status={result.get('mechanism_verified')} outcome={result.get('category_outcome')} "
                  f"contradicts_default_narrative={result.get('contradicts_typical_collapse_narrative')}")
            succeeded += 1
        except Exception as e:
            print(f"  -> FAILED: {e}")
            conn.execute("UPDATE events SET verification_status='failed', notes=? WHERE event_id=?",
                         (f"Automated pass failed: {e}", event_id))
            conn.commit()
            failed += 1
        time.sleep(args.sleep)

    conn.execute("""INSERT INTO run_log (started_at, finished_at, events_processed, events_succeeded, events_failed, notes)
                     VALUES (?,?,?,?,?,?)""",
                 (run_start, datetime.datetime.utcnow().isoformat(), len(events), succeeded, failed, None))
    conn.commit()

    print(f"\nDone. Succeeded: {succeeded}, Failed: {failed}")
    print_status(conn)


if __name__ == "__main__":
    main()
