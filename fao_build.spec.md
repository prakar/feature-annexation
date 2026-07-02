# Feature Annexation Observatory (FAO) — Build Spec
*Living document. Updated as build progresses. Source for manuscript Appendix C.*

---

## 1. Purpose and Audience

The Feature Annexation Observatory (FAO) is a reference implementation accompanying the paper "Telemetry-Capture Mediated Feature Annexation in Commercial Platform Ecosystems." It provides interactive access to the empirical corpus of 51 verified annexation cases, allowing readers to explore the Feature Annexation Matrix (FAM) profiles, outcome classifications, and evidence trails that underpin the paper's findings.

FAO is designed for multiple audiences simultaneously:
- **Academic readers** verifying the paper's empirical claims and FAM methodology
- **Students** encountering platform economics for the first time
- **Entrepreneurs and founders** assessing their own exposure to Feature Annexation risk
- **Investors** evaluating complementor positioning in platform-governed markets
- **General researchers** from adjacent fields with no prior platform economics background

The tool is deliberately accessible: all display labels use plain-English terminology rather than academic or industry jargon. Where a label diverges from the manuscript's academic term, the correspondence is documented in Section 6 of this spec (the Label Map).

---

## 2. Architecture

**Type:** Streamlit web application (Python backend)
**Data source:** `annexation_evidence.db` (SQLite, 51 events, ~580 evidence rows, 20 investor discourse claims)
**Pipeline scripts:** `verify_events.py`, `score_fam_dimensions.py` (callable from Admin tab)
**Label map:** `labels.yaml` (field-keyed mapping of DB values to display labels)
**Deployment:** [TO BE FILLED — local / Streamlit Cloud / other]
**Theme:** Light (forced via `.streamlit/config.toml`)

---

## 3. Navigation Structure

FAO has three top-level tabs:

### 3.1 Dashboard
*[TO BE FILLED during build — KPI metrics, charts, summary findings]*

Key elements expected:
- Total case count (51)
- Fate distribution chart (bar or donut)
- Zone distribution chart
- FAM dimension score distribution
- Headline finding callout ("53% of annexed complementors pivoted to a niche rather than collapsing")

### 3.2 Annexation Cases
*Primary exploration surface. Replaces internal label "Event Corpus".*

Two-panel layout:
- **Left sidebar (Y-axis — Zone):** Domain filter chips + FAM dimension floor sliders
- **Top bar (X-axis — Fate):** Outcome filter pills (six Fate categories)
- **Active filter strip:** Shows current Fate × Zone intersection as removable pill tags; "Clear all" button
- **Gallery:** Grid of case cards, dynamically filtered by active Fate × Zone × dimension floor selections
- **Hero detail panel:** Opens when a card is selected (see Section 4)
- **Pagination:** Sequential forward/back navigation within the current filtered set; shows "Case N of M in this intersection"

### 3.3 Market Discourse
*Replaces internal label "Investor Discourse." 20 verified investor/analyst claims.*
*[TO BE FILLED — card layout, verification status display, explanatory subhead]*

Planned elements:
- One-line explanatory subhead distinguishing this tab from the main 51-case corpus
- Per-claim card showing platform, claim text, verification result, confidence
- No FAM radar (investor claims are not scored on FAM dimensions)

### 3.4 Run Verification (Admin)
*Pipeline execution tab. Not described in the public-facing manuscript appendix.*
- Provider selector, event ID targeting, live log streaming
- Password gate before any public deployment [TO BE IMPLEMENTED]

---

## 4. Hero Card Layout

Information hierarchy (top to bottom) for a selected annexation case:

1. **Case title** — Platform · Offering (always visible)
2. **Radar plot** — Four FAM dimensions as a Plotly Scatterpolar; shape shows profile, spikiness shows dominance (always visible)
3. **Four dimension bars** — One per FAM dimension; shows absolute score (0–100), tier label, and tier colour (always visible)
4. **Verdict** — "Actual Outcome: [Fate label]" — below dimension bars, always visible but visually subordinate
5. **About this case** — Collapsed by default; click to expand inline (no page navigation)
6. **Evidence sources** — Collapsed by default; click to expand inline; shows source count badge
7. **Framework reasoning** — Collapsed by default; click to expand inline; shows FAM scoring rationale

**Design principle:** A viewer gets the full analytical picture (radar + dimensions + verdict) without reading a single word of prose. Prose is available on demand, not by default.

---

## 5. Filter and Navigation Model

### X-axis (Fate — Outcome)
Six toggle pills in the top bar, one per Fate category. Selecting one narrows the gallery to cases with that outcome. Deselecting returns to all. Multiple selection: [TO BE DECIDED — single-select or multi-select]

### Y-axis (Zone — Domain)
Eight toggle chips in the left sidebar, one per platform domain layer. Selecting one narrows the gallery to cases in that zone.

### Dimension floor sliders (Z-axis refinement)
Four range sliders in the left sidebar, one per FAM dimension. Setting a floor value (e.g. Stopgap Score ≥ 70) removes cases scoring below that threshold from the gallery.

### Active filter strip
Sits between the top bar and the gallery. Shows each active filter as a pill tag:
- Fate filter: accent colour (blue)
- Zone filter: teal
- Dimension floor filters: grey secondary tags
Each pill has an × to remove that filter individually. "Clear all" button on the right.

### Gallery sort order
Default: [TO BE DECIDED — "surprise level" = absolute distance between FAM profile and actual outcome; or by platform name; or by event ID]

### Pagination
Forward/back buttons navigate sequentially through the current filtered set. Count display: "Case N of M in this intersection."

---

## 6. Label Map (Canonical)

This section is the definitive record of all display label decisions. Where a UI label diverges from the manuscript's academic term, both are shown. This map is the source for the manuscript appendix's accessibility rationale.

### 6.1 Fate Categories (Outcome)

| DB value | Academic term (manuscript) | UI display label | Notes |
|---|---|---|---|
| `Repositioning` | Repositioning (Argyres et al. 2023) | **Pivot to Niche** | Plain-English equivalent; manuscript term preserved for citation |
| `Contraction` | Contraction | **Market Narrowing** | "Narrowing" more precise than "reduction" |
| `Compression` | Compression | **Clickthrough Loss** | Mechanically precise; describes the SERP-specific phenomenon |
| `Transformation` | Transformation | **Category Shift** | Avoids "vertical" connotation of alternatives |
| `Survived_No_Clear_Reorganization` | Survived Unchanged | **Survived Unchanged** | DB label is legacy; display label is clean |
| `Contested_Platform_Retreat` | Contested Platform Retreat | **Platform Retreated** | Past tense consistent with other Fate labels |
| `Insufficient_Evidence` | Insufficient Evidence | **Insufficient evidence** | Lowercased second word |

### 6.2 Zone Categories (Domain/Layer)

| DB value | UI display label |
|---|---|
| `AI Tooling` | AI Tooling |
| `Commerce and Infrastructure Layer` | Commerce & Infrastructure |
| `Enterprise Software Layer` | Enterprise Software |
| `Marketplace / Private Label` | Marketplace & Private Label |
| `Media and Attention Layer` | Media & Attention |
| `Mobile OS Utilities` | Mobile OS Utilities |
| `Operating System Layer` | Operating System |
| `Search and Information Layer` | Search & Information |

### 6.3 FAM Dimension Names

| DB field | Academic term (manuscript) | UI display label | Rationale |
|---|---|---|---|
| `fam_implementation_gap` | Implementation Gap | **Stopgap Score** | Captures *why* the offering exists — it fills a gap the platform hasn't closed |
| `fam_replication_feasibility` | Replication Feasibility | **Ease of Replication** | Direct and accurate |
| `fam_telemetry_exposure` | Telemetry Exposure | **Visibility on Platform Radar** | "Radar" evocative and directionally accurate; avoids technical term |
| `fam_integration_pressure` | Integration Pressure | **Native Fit Friction** | "Friction" implies resistance/pressure correctly; "suitability" did not |

### 6.4 FAM Dimension Tier Labels

| Score range | Tier label | Colour |
|---|---|---|
| 75–100 | Annexation Leader | Red |
| 50–74 | Strong Signal | Amber |
| 25–49 | Weak Signal | Teal |
| 0–24 | Negligible | Grey |

**Language note:** Tier labels describe the *strength of the pre-annexation signal on that dimension*, not the platform's causal influence on the outcome. The UI does not claim these dimensions *caused* the outcome; it reports what the profile looked like before annexation occurred.

### 6.5 Confidence (Evidence Quality)

| DB value | UI display label | Notes |
|---|---|---|
| `High` | Good Evidence | Refers to source quality, not outcome severity |
| `Medium` | Medium Evidence | Same |
| `Low` | Low Evidence | Same |

### 6.6 Verification Status

| DB value | UI display label | Notes |
|---|---|---|
| `contradicted` | Contradicts collapse narrative | "Collapse narrative" = original unaudited corpus assumption |
| `verified_consistent` | Consistent with collapse narrative | Same reference point |
| `inconclusive` | Inconclusive | |
| `scored` / `unscored` | — | Internal pipeline state; suppressed from Browse view |

### 6.7 Evidence Source Types

| DB value | UI display label |
|---|---|
| `PD` | Platform documentation |
| `PR` | Product documentation |
| `MR` | Market reporting / press |
| `AR` | Academic / peer-reviewed |
| `CR` | Community / forum |
| `RR` | Regulatory |
| `DS` | Dataset / statistics |
| `VC` | Investor / VC commentary |
| `MR/DS` | Market reporting + dataset *(compound — pending DB split)* |

### 6.8 Evidence Stance

| DB value | UI display label |
|---|---|
| `supports` | Supports |
| `contradicts` | Contradicts |
| `partial` | Partial |

### 6.9 Section / Tab Names

| Internal / old label | UI display label |
|---|---|
| Event Corpus | Annexation Cases |
| Investor Discourse | Market Discourse |
| Browse Corpus | (absorbed into tab label) |
| Run Verification | Run Verification (Admin) |

---

## 7. Accessibility Rationale (for manuscript appendix)

The FAO uses plain-English display labels throughout rather than the academic terminology used in the manuscript. This is a deliberate design decision, not an inconsistency.

The academic terms (Repositioning, Telemetry Exposure, Integration Pressure, etc.) are precise, citable, and load-bearing in the manuscript's theoretical framework. They are preserved exactly in the manuscript and in the underlying database.

The display labels (Pivot to Niche, Visibility on Platform Radar, Native Fit Friction, etc.) are designed for a reader encountering this corpus for the first time without prior grounding in platform economics, strategy research, or industry jargon. The goal is zero uptake friction from language: a reader should be able to navigate the tool and interpret the FAM profiles without consulting a glossary.

The correspondence between academic terms and display labels is documented in full in Section 6 of this spec, and summarised in the manuscript appendix.

---

## 8. Open Items (to be resolved during build)

- [ ] Gallery default sort order — "surprise level" (FAM-outcome discordance) vs platform name vs event ID
- [ ] Fate filter — single-select or multi-select in the top bar pills
- [ ] Investor discourse tab — card layout and explanatory subhead copy
- [ ] Admin tab — password gate implementation before public deployment
- [ ] `MR/DS` compound source type — split at DB level before filter UI is built
- [ ] Dashboard tab — final KPI selection and chart types
- [ ] Deployment target — Streamlit Cloud / local / other
- [ ] Multi-select Fate filter behaviour — does selecting two Fate categories show the union or require both?

---

## 9. What the Manuscript Appendix Will Cover
*(Written after build is locked)*

- FAO purpose and intended audiences
- Navigation overview (three public tabs)
- Hero card walkthrough — how to read the radar, dimension bars, and verdict together
- Label map summary — academic term → display label, with accessibility rationale
- Data provenance — link to DB, pipeline scripts, reproducibility statement
- How to replicate a FAM evaluation using the tool

---
*Last updated: 2026-07-01*
*Status: Pre-build skeleton — open items in Section 8 to be resolved during build*