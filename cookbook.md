# SQL For Data Inspection


    - 1.1 Plain SQL for Full event-by-event summary with outcomes
    SELECT event_id, platform, offering, annexation_event, category_outcome,
        complementor_status, confidence, verification_status
    FROM events ORDER BY event_id;

        - 1.1.1 CLI version
        sqlite3 annexation_evidence.db "SELECT event_id, platform, offering, annexation_event, category_outcome complementor_status, confidence, verification_status FROM events ORDER BY event_id;"

    - 2.1 The headline number: contradiction rate
    SELECT verification_status, count(*) AS n,
        ROUND(100.0 * count(*) / (SELECT count(*) FROM events), 1) AS pct
    FROM events GROUP BY verification_status;

        - 2.1.1 CLI Version
        sqlite3 annexation_evidence.db "SELECT verification_status, count(*) AS n, ROUND(100.0 * count(*) / (SELECT count(*) FROM events), 1) AS pct FROM events GROUP BY verification_status;"


    - 3.1 Outcome-type breakdown (the Stratification finding)

    SELECT category_outcome, count(*) AS n
    FROM events WHERE category_outcome IS NOT NULL
    GROUP BY category_outcome ORDER BY n DESC;

        - 3.1.1 CLI Version
        sqlite3 annexation_evidence.db "SELECT category_outcome, count(*) AS n FROM events WHERE category_outcome IS NOT NULL GROUP BY category_outcome ORDER BY n DESC;"

    - 4.1 Investor claims summary (A4)
    SELECT claim_id, platform, annexation_event, verified_confidence,
        contradicts_original, verification_status
    FROM investor_claims ORDER BY claim_id;

        - 4.1.1 CLI Version
        sqlite3 annexation_evidence.db "SELECT claim_id, platform, annexation_event, verified_confidence, contradicts_original, verification_status FROM investor_claims ORDER BY claim_id;"

    - 5.1 Evidence volume per event (spot the thin ones)
    SELECT e.event_id, e.platform, e.offering, count(ev.evidence_id) AS n_sources
    FROM events e LEFT JOIN evidence ev ON e.event_id = ev.event_id
    GROUP BY e.event_id ORDER BY n_sources ASC;

        - 5.1.1 CLI Version
        sqlite3 annexation_evidence.db "SELECT e.event_id, e.platform, e.offering, count(ev.evidence_id) AS n_sources FROM events e LEFT JOIN evidence ev ON e.event_id = ev.event_id GROUP BY e.event_id ORDER BY n_sources ASC;"

    - 6.1 Every real source URL gathered so far, by case (good for a quick sanity skim)
    SELECT event_id, title, url, source_type, supports_or_contradicts
    FROM evidence WHERE event_id IS NOT NULL ORDER BY event_id;

        - 6.1.1 CLI Version
        sqlite3 annexation_evidence.db "SELECT event_id, title, url, source_type, supports_or_contradicts FROM evidence WHERE event_id IS NOT NULL ORDER BY event_id;"

    - 7.1 All search queries actually run (your literate-programming audit trail)
    SELECT event_id, query, outcome, timestamp FROM search_log ORDER BY timestamp;

        - 7.1.1 CLI Version
        sqlite3 annexation_evidence.db "SELECT event_id, query, outcome, timestamp FROM search_log ORDER BY timestamp;"

    - 8.1 The 2 genuine "matches original narrative" cases (your contrast cases for the write-up)
    SELECT * FROM events WHERE verification_status = 'verified_consistent';

        - 8.1.1 CLI Version
        sqlite3 annexation_evidence.db "SELECT * FROM events WHERE verification_status = 'verified_consistent';"

    - 9.1 Run history / cost-tracking over time
    SELECT * FROM run_log ORDER BY started_at;

        - 9.1.1 CLI Version
        sqlite3 annexation_evidence.db "SELECT * FROM run_log ORDER BY started_at;"

    - 10.1 Full export, events + evidence joined (closest thing to your eventual supplementary-material CSV)
    SELECT e.event_id, e.platform, e.offering, e.category_outcome, e.confidence,
        ev.title, ev.url, ev.source_type, ev.publication_date
    FROM events e LEFT JOIN evidence ev ON e.event_id = ev.event_id
    ORDER BY e.event_id;

        - 10.1.1 CLI Version
        sqlite3 annexation_evidence.db "SELECT e.event_id, e.platform, e.offering, e.category_outcome, e.confidence, ev.title, ev.url, ev.source_type, ev.publication_date FROM events e LEFT JOIN evidence ev ON e.event_id = ev.event_id ORDER BY e.event_id;"
# SQL Update Example
    UPDATE events
    SET verification_status = 'unverified',
        category_outcome = NULL,
        complementor_status = NULL,
        evidence_strength = NULL,
        confidence = NULL,
        contradicts_default_narrative = NULL,
        notes = NULL
    WHERE event_id IN (2, 3);

        - CLI Version:
            sqlite3 annexation_evidence.db "UPDATE events SET verification_status='unverified', category_outcome=NULL, complementor_status=NULL, evidence_strength=NULL, confidence=NULL, contradicts_default_narrative=NULL, notes=NULL WHERE event_id IN (2,3);"