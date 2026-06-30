# Event Verification Prompt (Appendix A methodology)

This is the canonical prompt used to verify each of the 50 events in the corpus
(`events` table). It was run against multiple LLM providers (Anthropic, Grok)
via the `providers.py` abstraction in the companion pipeline repository.

Fork this repository, swap the model/provider, and re-run this exact prompt
against any case to see whether your results converge with ours.

---

```
You are conducting a provenance verification pass for one row of an
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

PART 2 — OUTCOME CHECK
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

{
  "mechanism_verified": true | false | "insufficient_evidence",
  "category_outcome": "Repositioning" | "Contraction" | "Compression" | "Transformation" | "Survived_No_Clear_Reorganization" | "Insufficient_Evidence",
  "complementor_status": "Survived" | "Declined" | "Emerging" | "Unknown",
  "confidence": "High" | "Medium" | "Low",
  "evidence_strength": "High" | "Medium" | "Low",
  "contradicts_typical_collapse_narrative": true | false,
  "sources": [
    {
      "claim_supported": "short description of what this source supports",
      "source_type": "PD|PR|MR|AR|CR|RR|DS",
      "title": "exact title",
      "url": "exact url",
      "publication_date": "YYYY-MM-DD or best available, or 'undated'",
      "excerpt_paraphrase": "your own words, NOT a verbatim quote, summarizing what it says",
      "supports_or_contradicts": "supports" | "contradicts" | "partial"
    }
  ],
  "notes": "anything a human reviewer should know, including any contradiction with the dramatic/default narrative"
}
```

Note: `category_outcome` values were updated from an earlier version of this prompt
that used the term "Stratification." The corpus and prompt now use "Repositioning"
(Argyres, Nickerson, & Ozalp, 2023) throughout, per a terminology correction made
during manuscript review. If you fork this and see older notes/commit history
referencing "Stratification," that is the same construct under its prior name.
