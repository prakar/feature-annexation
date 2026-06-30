# Investor/Market Discourse Verification Prompt (Appendix A.4 methodology)

Used to verify the 20 rows in the `investor_claims` table. These are harder claims
than the event-verification prompt: they assert that specific *discourse* occurred
(investors/founders publicly citing a platform feature as a deterrent), not just
that a product exists.

---

```
You are verifying one row of an "Investor Chilling" dataset for an academic
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
2. Is there a real, named, dated source discussing this specific case as a
   deterrent to investment or new entry? Generic "platforms are risky" commentary
   does NOT count -- it needs to be about this case.
3. Is there any quantitative or semi-quantitative evidence of funding impact?
   It is fine to come back with "Insufficient_Evidence" here -- that is a more
   honest answer than inventing a number.

Grade every source as: PD, PR, MR, AR, CR, RR, or VC (named VC/investor commentary).

Return ONLY valid JSON, no preamble, no markdown fences:

{
  "discourse_confirmed": true | false | "partial",
  "verified_reputation_signal": "what you actually found, in your own words",
  "verified_investor_learning": "what you actually found",
  "verified_entry_deterrence": "what you actually found",
  "verified_funding_impact": "Low" | "Medium" | "High" | "Insufficient_Evidence",
  "verified_confidence": "High" | "Medium" | "Low",
  "contradicts_original": true | false,
  "sources": [ { "claim_supported": "...", "source_type": "PD|PR|MR|AR|CR|RR|VC",
                 "title": "...", "url": "...", "publication_date": "...",
                 "excerpt_paraphrase": "...", "supports_or_contradicts": "..." } ],
  "notes": "anything a human reviewer should know"
}
```
