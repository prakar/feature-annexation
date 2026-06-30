# Feature Annexation Observatory (FAO)

A Streamlit app for browsing the Feature Annexation evidence corpus, plus the
verification pipeline scripts that built it. Everything lives in one flat
directory on purpose -- this repo grew incrementally during the paper's own
audit process, and the pipeline scripts (`verify_events.py`,
`verify_investor_claims.py`) and the data they produce (`annexation_evidence.db`)
need to stay next to each other rather than split across folders, since the
scripts resolve the database path relative to their own location.

## Repository structure (flat, by design)

```
annexation_evidence.db        -- the full evidence corpus (CC-BY, see LICENSE-DATA)
providers.py                  -- provider-agnostic LLM dispatch (Anthropic/OpenAI/Gemini/Grok)
verify_events.py              -- resumable verification pipeline, Event Corpus (50 cases)
verify_investor_claims.py     -- resumable verification pipeline, Investor Discourse (20 claims)
app.py                        -- Streamlit app: Browse tab + Admin tab (NEW)
requirements.txt
cookbook.md                   -- process notes from building the corpus
LICENSE                       -- MIT (code)
LICENSE-DATA                  -- CC-BY (database, evidence corpus, prompts)
prompts/
  event_verification_prompt.md       -- canonical prompt used by verify_events.py
  investor_discourse_prompt.md       -- canonical prompt used by verify_investor_claims.py
```

## Running the app

```bash
pip install -r requirements.txt
streamlit run app.py
```

Two tabs:

- **Browse Corpus** -- read-only viewer over the 50 events and 20 investor-discourse
  claims, with the full evidence trail (source, URL, date, supports/contradicts)
  for every case. This is the retrospective, public-facing view.
- **Admin: Run Verification** -- a UI over `verify_events.py` and
  `verify_investor_claims.py`. Lets you pick a provider, a row limit, and run
  the pipeline directly, with live-streamed log output. This does **not**
  reimplement the pipeline logic -- it shells out to the same scripts you'd
  run from the command line, so command-line and Admin-tab runs stay
  identical and the scripts remain independently runnable and testable.

Why Streamlit rather than the originally-planned static HTML/GitHub-Pages
page: the Admin tab needs to *execute Python on demand* (run a verification
pass when a researcher clicks a button), which a static page fundamentally
cannot do -- there's no server. Streamlit gives a real backend by default
without standing up a separate Flask layer.

## API keys

The pipeline scripts read provider API keys from environment variables
(`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GOOGLE_API_KEY`, `XAI_API_KEY`),
exactly as before. If you deploy this app (e.g. on Streamlit Community Cloud
or Render, the same way the companion "fluttering sail" app for a different
paper was deployed), set these via that platform's secrets mechanism --
`app.py` checks `st.secrets` and copies any keys found there into the
environment before launching a pipeline run, so either approach works
locally or deployed.

## Command-line usage (unchanged, still fully supported)

Everything that worked before this app existed still works exactly the same way:

```bash
python verify_events.py --provider grok --limit 5
python verify_events.py --status
python verify_investor_claims.py --provider anthropic
```

The Admin tab is an additional way to trigger these, not a replacement for
running them directly -- useful if you want to script a larger batch job
outside the browser, or just prefer the terminal.

## Forking and re-running verification with a different model

This is the actual point of externalizing the prompts in `prompts/`: if you
think a result is wrong, you can check, cheaply. Swap `--provider` and
compare. If your re-run produces a different outcome than ours for the same
case, that disagreement is itself a useful, citable finding.

## A known limitation, stated up front

This corpus is **better at confirming that a complementor survived than at
confirming that one quietly failed without public announcement** (see the
paper's Appendix A.7.1 and Section 5.7, grounded in Denrell's 2003 work on
undersampling of organizational failure). The near-absence of clean
"annexed and did not reposition" cases in this dataset should be read as a
structural blind spot in retrospective, web-search-based research, not as
evidence that such cases are rare. Locating and verifying that cohort is
identified as necessary future work, not completed here.

## Licensing

- Code (`app.py`, `providers.py`, `verify_events.py`, `verify_investor_claims.py`):
  MIT License (see `LICENSE`).
- Data (`annexation_evidence.db`, `prompts/`): CC-BY (see `LICENSE-DATA`) --
  attribution required, otherwise free to use, fork, and extend.

## Roadmap (not yet built)

- Predictive scoring is an explicitly deferred, open question -- see the
  paper's Appendix B.7 before pursuing this; it is future work, not a
  missing feature of the current app.
- A second dataset for the related-but-distinct "Extraction Annexation"
  phenomenon is being developed as a separate research thread and may
  eventually become a third tab here.
- Admin-tab authentication / access control: right now anyone who can reach
  the deployed app can trigger a pipeline run (and spend your API budget).
  Fine for local/Codespace use; needs a password gate or IP restriction
  before any public deployment.
