"""
Feature Annexation Observatory (FAO) -- Streamlit app.

Replaces the original static-HTML/sql.js plan. Streamlit gives a real Python
backend by default, which is what the Admin tab actually needs (running
verify_events.py / verify_investor_claims.py on demand) -- a static page on
GitHub Pages cannot execute Python, full stop, so this architecture is the
correct fix rather than a workaround.

Run with:
    streamlit run app.py

Expects to live in the SAME directory as annexation_evidence.db,
providers.py, verify_events.py, and verify_investor_claims.py -- the flat
repo-root layout already in use, not a separate fao/ subfolder. This file
reads the database directly via sqlite3 (no sql.js, no WASM, no copying the
DB anywhere) and shells out to the existing, already-debugged pipeline
scripts for the Admin actions rather than reimplementing their logic here.
"""

import sqlite3
import subprocess
import sys
import os
import time
from pathlib import Path

import streamlit as st
import pandas as pd
import plotly.graph_objects as go

DB_PATH = Path(__file__).parent / "annexation_evidence.db"

st.set_page_config(page_title="Feature Annexation Observatory", layout="wide")


def render_fam_radar(row):
    """
    Renders the four-axis FAM 'fingerprint' for one event using Plotly's
    Scatterpolar (the standard way to do radar charts in Plotly -- there is
    no dedicated "radar" trace type, Scatterpolar with fill='toself' is the
    documented pattern). Untested live (no network in the environment that
    wrote this), so treat the first real render as the actual test of
    whether the axis labels/closing-the-loop logic look right.
    """
    dims = ["Implementation Gap", "Replication Feasibility", "Telemetry Exposure", "Integration Pressure"]
    values = [
        row["fam_implementation_gap"], row["fam_replication_feasibility"],
        row["fam_telemetry_exposure"], row["fam_integration_pressure"],
    ]
    # Close the loop by repeating the first point -- required for Scatterpolar
    # to render a closed shape rather than an open line.
    fig = go.Figure(data=go.Scatterpolar(
        r=values + [values[0]],
        theta=dims + [dims[0]],
        fill="toself",
        line_color="#4f6df5",
    ))
    fig.update_layout(
        polar=dict(radialaxis=dict(visible=True, range=[0, 100])),
        showlegend=False,
        margin=dict(l=30, r=30, t=20, b=20),
        height=320,
    )
    st.plotly_chart(fig, use_container_width=True)
    if row.get("fam_reasoning"):
        st.caption(row["fam_reasoning"])


# LAYOUT NOTE: Streamlit's default block-container has generous top padding and
# wide vertical gaps between elements, which is why the dashboard's actual
# content started below the fold. This CSS override tightens both without
# touching the theme (colors/fonts stay whatever config.toml sets).
st.markdown("""
<style>
.block-container { padding-top: 1.5rem; padding-bottom: 1rem; }
div[data-testid="stVerticalBlock"] > div { gap: 0.4rem; }
hr { margin: 0.6rem 0; }
h2, h3 { margin-top: 0.3rem; margin-bottom: 0.3rem; }
</style>
""", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# DATA LAYER -- thin, direct sqlite3 access. No ORM, no caching layer beyond
# Streamlit's own @st.cache_data, since the DB is small (under 1MB) and reads
# are cheap. Admin actions that write to the DB call st.cache_data.clear()
# afterward so the Browse tab reflects new results without a manual refresh.
# ---------------------------------------------------------------------------

@st.cache_data
def load_events():
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query("SELECT * FROM events ORDER BY event_id", conn)
    conn.close()
    return df


@st.cache_data
def load_investor_claims():
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query("SELECT * FROM investor_claims ORDER BY claim_id", conn)
    conn.close()
    return df


@st.cache_data
def load_evidence(event_id=None, claim_id=None):
    conn = sqlite3.connect(DB_PATH)
    if event_id is not None:
        df = pd.read_sql_query(
            "SELECT * FROM evidence WHERE event_id = ? ORDER BY evidence_id",
            conn, params=(event_id,)
        )
    elif claim_id is not None:
        # Investor-claim evidence is stored with NULL event_id and the claim_id
        # folded into claim_supported as "[IC-XX] ..." (see verify_investor_claims.py
        # persist_result() for why -- a deliberate choice not to add a third
        # near-duplicate evidence table).
        df = pd.read_sql_query(
            "SELECT * FROM evidence WHERE event_id IS NULL AND claim_supported LIKE ? ORDER BY evidence_id",
            conn, params=(f"[{claim_id}]%",)
        )
    else:
        df = pd.DataFrame()
    conn.close()
    return df


def outcome_badge(outcome, status):
    survive_terms = {"Repositioning", "Survived_No_Clear_Reorganization", "Transformation"}
    decline_terms = {"Contraction", "Compression"}
    if outcome in survive_terms or status == "Survived":
        return f"🟢 {outcome or status}"
    elif outcome in decline_terms or status == "Declined":
        return f"🔴 {outcome or status}"
    else:
        return f"⚪ {outcome or status or 'Unknown'}"


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------

st.title("Feature Annexation Observatory")
st.caption("A read-only, retrospective visualizer for the paper's headline finding and how it varies by domain and platform, plus an Admin tab to extend it.")

st.warning(
    "**Retrospective view only.** Every case here is a documented historical event, "
    "independently verified against real, dated, named sources. This tool makes no "
    "predictions and does not claim to identify which currently-independent offerings "
    "will be annexed next. See the paper's Appendix A for full methodology, including a "
    "known survivorship-bias limitation: this corpus is structurally better at confirming "
    "that a complementor survived than at confirming that one quietly failed.",
    icon="⚠️",
)

tab_dashboard, tab_browse, tab_admin = st.tabs(["📈 Dashboard", "📊 Browse Corpus", "🛠️ Admin: Run Verification"])

# --- BROWSE TAB ---
with tab_browse:
    corpus_choice = st.radio("Dataset", ["Event Corpus (50)", "Investor Discourse (20)"], horizontal=True)

    if corpus_choice.startswith("Event"):
        df = load_events()
        outcomes = sorted(df["category_outcome"].dropna().unique().tolist())
        col1, col2 = st.columns([2, 1])
        with col1:
            search = st.text_input("Search platform, offering, or annexation event")
        with col2:
            outcome_filter = st.selectbox("Filter by outcome", ["All"] + outcomes)

        filtered = df.copy()
        if search:
            mask = (
                filtered["platform"].str.contains(search, case=False, na=False)
                | filtered["offering"].str.contains(search, case=False, na=False)
                | filtered["annexation_event"].str.contains(search, case=False, na=False)
            )
            filtered = filtered[mask]
        if outcome_filter != "All":
            filtered = filtered[filtered["category_outcome"] == outcome_filter]

        st.caption(f"{len(filtered)} of {len(df)} events")

        for _, row in filtered.iterrows():
            with st.expander(f"#{row['event_id']} — {row['platform']} / {row['offering']} → {row['annexation_event']}  {outcome_badge(row['category_outcome'], row['complementor_status'])}"):
                c1, c2, c3 = st.columns(3)
                c1.metric("Outcome", str(row["category_outcome"] or "—").replace("_", " "))
                c2.metric("Complementor", row["complementor_status"] or "Unknown")
                c3.metric("Confidence", row["confidence"] or "—")

                if row["notes"]:
                    st.markdown(f"**Notes:** {row['notes']}")

                fam_dims = ["fam_implementation_gap", "fam_replication_feasibility",
                            "fam_telemetry_exposure", "fam_integration_pressure"]
                if all(pd.notna(row.get(d)) for d in fam_dims):
                    render_fam_radar(row)
                else:
                    st.caption(
                        "FAM fingerprint not yet scored for this case. Run "
                        "`score_fam_dimensions.py` (Admin tab or command line) to populate "
                        "Implementation Gap / Replication Feasibility / Telemetry Exposure / "
                        "Integration Pressure for the full corpus."
                    )

                evidence = load_evidence(event_id=row["event_id"])
                st.markdown(f"**Evidence ({len(evidence)} source{'s' if len(evidence) != 1 else ''})**")
                for _, ev in evidence.iterrows():
                    st.markdown(
                        f"- [{ev['title'] or ev['url']}]({ev['url']})  "
                        f"`[{ev['source_type'] or '?'}]` {ev['publication_date'] or 'undated'} · "
                        f"*{ev['supports_or_contradicts'] or ''}*"
                    )
                    if ev["excerpt_paraphrase"]:
                        st.caption(ev["excerpt_paraphrase"])

    else:
        df = load_investor_claims()
        search = st.text_input("Search platform or annexation event")
        filtered = df.copy()
        if search:
            mask = (
                filtered["platform"].str.contains(search, case=False, na=False)
                | filtered["annexation_event"].str.contains(search, case=False, na=False)
            )
            filtered = filtered[mask]

        st.caption(f"{len(filtered)} of {len(df)} claims")

        for _, row in filtered.iterrows():
            with st.expander(f"{row['claim_id']} — {row['platform']} / {row['annexation_event']}  {outcome_badge(row['verification_status'], None)}"):
                c1, c2 = st.columns(2)
                c1.metric("Funding impact", row["verified_funding_impact"] or "—")
                c2.metric("Confidence", row["verified_confidence"] or "—")

                st.markdown(f"**Reputation signal:** {row['verified_reputation_signal'] or 'No real evidence found'}")
                st.markdown(f"**Investor learning:** {row['verified_investor_learning'] or 'No real evidence found'}")
                st.markdown(f"**Entry deterrence:** {row['verified_entry_deterrence'] or 'No real evidence found'}")
                if row["notes"]:
                    st.markdown(f"**Notes:** {row['notes']}")

                evidence = load_evidence(claim_id=row["claim_id"])
                if len(evidence):
                    st.markdown(f"**Evidence ({len(evidence)} source{'s' if len(evidence) != 1 else ''})**")
                    for _, ev in evidence.iterrows():
                        st.markdown(f"- [{ev['title'] or ev['url']}]({ev['url']})  `[{ev['source_type'] or '?'}]` {ev['publication_date'] or 'undated'}")


# --- DASHBOARD TAB ---
# PHASE A NOTE: everything here uses data the corpus already has (outcome,
# platform, layer/domain, confidence, evidence count). A per-case radar-chart
# "fingerprint" using FAM's four dimensions (Implementation Gap, Replication
# Feasibility, Telemetry Exposure, Integration Pressure) is a real Phase B
# idea, deliberately not built here -- those dimensions are currently only
# scored for 3 worked examples (Appendix B.6), not across all 50 events. This
# tab will need a `fam_scores` table (or four new columns on `events`) before
# a radar view can show real numbers instead of placeholders.
with tab_dashboard:
    import altair as alt

    events_df = load_events()
    total = len(events_df)
    contradicted = (events_df["verification_status"] == "contradicted").sum()
    modal_outcome = events_df["category_outcome"].mode().iloc[0] if not events_df["category_outcome"].dropna().empty else "—"

    @st.cache_data
    def total_evidence_count():
        conn = sqlite3.connect(DB_PATH)
        n = conn.execute("SELECT count(*) FROM evidence").fetchone()[0]
        conn.close()
        return n

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Total events", total)
    k2.metric("Contradict original 'Collapse' label", f"{contradicted}/{total}", f"{contradicted/total:.0%}")
    k3.metric("Modal outcome", modal_outcome.replace("_", " "))
    k4.metric("Evidence sources", total_evidence_count())

    st.divider()

    col_a, col_b = st.columns(2)

    with col_a:
        st.subheader("Outcome by domain (layer)")
        st.caption("Click a bar segment to drill into the underlying cases below.")
        layer_outcome = (
            events_df.dropna(subset=["layer", "category_outcome"])
            .groupby(["layer", "category_outcome"])
            .size()
            .reset_index(name="count")
        )
        if len(layer_outcome):
            # CLICK-TO-FILTER NOTE: this uses Streamlit's chart-selection API
            # (on_select="rerun" + a param-based Altair selection), which is
            # the newest, least-battle-tested piece of anything built this
            # session -- it requires a reasonably recent Streamlit version
            # (1.35+) and I have no way to render-test it live (no network in
            # the environment that wrote this). If clicking does nothing,
            # that's the first thing to check, not the data.
            click_selection = alt.selection_point(fields=["layer", "category_outcome"])
            chart = (
                alt.Chart(layer_outcome)
                .mark_bar()
                .encode(
                    x=alt.X("count:Q", title="Number of cases"),
                    y=alt.Y("layer:N", title=None, sort="-x"),
                    color=alt.Color("category_outcome:N", title="Outcome"),
                    tooltip=["layer", "category_outcome", "count"],
                    opacity=alt.condition(click_selection, alt.value(1.0), alt.value(0.55)),
                )
                .add_params(click_selection)
                .properties(height=320)
            )
            event = st.altair_chart(chart, use_container_width=True, on_select="rerun", key="layer_chart")

            selection = event.get("selection", {}).get("param_1", []) if event else []
            if selection:
                sel = selection[0]
                matched = events_df[
                    (events_df["layer"] == sel.get("layer"))
                    & (events_df["category_outcome"] == sel.get("category_outcome"))
                ]
                st.markdown(f"**{len(matched)} case(s): {sel.get('layer')} → {str(sel.get('category_outcome')).replace('_',' ')}**")
                st.dataframe(
                    matched[["event_id", "platform", "offering", "annexation_event", "confidence"]],
                    hide_index=True, use_container_width=True,
                )
        else:
            st.info("No layer data available to chart.")

    with col_b:
        st.subheader("Outcome by platform")
        st.caption("Which platforms' annexation events skew toward decline vs. repositioning?")
        platform_outcome = (
            events_df.dropna(subset=["platform", "category_outcome"])
            .groupby(["platform", "category_outcome"])
            .size()
            .reset_index(name="count")
        )
        if len(platform_outcome):
            chart2 = (
                alt.Chart(platform_outcome)
                .mark_bar()
                .encode(
                    x=alt.X("count:Q", title="Number of cases"),
                    y=alt.Y("platform:N", title=None, sort="-x"),
                    color=alt.Color("category_outcome:N", title="Outcome", legend=None),
                    tooltip=["platform", "category_outcome", "count"],
                )
                .properties(height=500)
            )
            st.altair_chart(chart2, use_container_width=True)
        else:
            st.info("No platform data available to chart.")

    st.divider()
    st.subheader("Confidence distribution")
    st.caption("How confident is the underlying evidence for each outcome category? Low-confidence outcomes are flagged in Appendix A as needing more scrutiny, not treated as equal to High-confidence ones.")
    conf_outcome = (
        events_df.dropna(subset=["confidence", "category_outcome"])
        .groupby(["category_outcome", "confidence"])
        .size()
        .reset_index(name="count")
    )
    if len(conf_outcome):
        chart3 = (
            alt.Chart(conf_outcome)
            .mark_bar()
            .encode(
                x=alt.X("count:Q", title="Number of cases"),
                y=alt.Y("category_outcome:N", title=None, sort="-x"),
                color=alt.Color("confidence:N", title="Confidence",
                                  scale=alt.Scale(domain=["High", "Medium", "Low"],
                                                   range=["#2e7d32", "#f9a825", "#c62828"])),
                tooltip=["category_outcome", "confidence", "count"],
            )
            .properties(height=280)
        )
        st.altair_chart(chart3, use_container_width=True)

    st.divider()
    st.subheader("Coming next (Phase B, needs new data)")
    st.markdown(
        "- **Per-case FAM radar charts** -- a four-axis 'fingerprint' (Implementation Gap, "
        "Replication Feasibility, Telemetry Exposure, Integration Pressure) for every case. "
        "Currently blocked on scoring all 50 events on these dimensions; only 3 worked "
        "examples are scored today (Appendix B.6).\n"
        "- **Timeline view** -- annexation events plotted by approximate year, once a clean "
        "per-event date field is added (currently only evidence *publication* dates are tracked, "
        "not the annexation event date itself)."
    )



with tab_admin:
    st.subheader("Run verification pipeline")
    st.caption(
        "Shells out to the existing, already-debugged `verify_events.py` / "
        "`verify_investor_claims.py` scripts in this same directory -- this tab does "
        "not reimplement their logic, it just gives them a UI and streams their output."
    )

    # SECRETS BUG NOTE: hasattr(st, "secrets") is always True -- st.secrets exists
    # as an attribute regardless of whether a secrets.toml file is present. The
    # actual error (StreamlitSecretNotFoundError) only fires when you try to USE
    # it (e.g. `in st.secrets`) with no secrets.toml anywhere. A bare try/except
    # is the correct guard here, not a hasattr check.
    def _secret_available(env_var):
        try:
            return env_var in st.secrets
        except Exception:
            return False

    missing_keys = []
    for provider, env_var in [("anthropic", "ANTHROPIC_API_KEY"), ("openai", "OPENAI_API_KEY"),
                                ("gemini", "GOOGLE_API_KEY"), ("grok", "XAI_API_KEY")]:
        if not os.environ.get(env_var) and not _secret_available(env_var):
            missing_keys.append((provider, env_var))
    if missing_keys:
        st.info(
            "API keys detected as missing for: "
            + ", ".join(f"**{p}** (`{v}`)" for p, v in missing_keys)
            + ". Set these as environment variables or in `.streamlit/secrets.toml` "
              "before running a pipeline that needs them."
        )

    pipeline_choice = st.selectbox("Pipeline", [
        "verify_events.py (Event Corpus)",
        "verify_investor_claims.py (Investor Discourse)",
        "score_fam_dimensions.py (FAM Fingerprint scoring -- batched, all 50 at once)",
    ])
    provider = st.selectbox("Provider", ["anthropic", "openai", "gemini", "grok"], index=0,
                             help="anthropic is the most-tested path across this project's development. "
                                  "Run --limit 1 on any other provider before trusting a full batch to it.")
    limit = st.number_input("Limit (rows to process this run; leave at 0 for no limit)", min_value=0, value=5, step=1)
    verbose = st.checkbox("Verbose logging")

    run_clicked = st.button("▶ Run", type="primary")

    if run_clicked:
        # Push any Streamlit-secrets-stored keys into the environment, since the
        # pipeline scripts read os.environ directly (Anthropic(), OpenAI(), etc.
        # SDK clients all default to reading env vars).
        try:
            for env_var in ["ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GOOGLE_API_KEY", "XAI_API_KEY"]:
                if env_var in st.secrets:
                    os.environ[env_var] = st.secrets[env_var]
        except Exception:
            pass  # no secrets.toml present -- fine, env vars are the other valid path

        if pipeline_choice.startswith("verify_events"):
            script = "verify_events.py"
        elif pipeline_choice.startswith("verify_investor_claims"):
            script = "verify_investor_claims.py"
        else:
            script = "score_fam_dimensions.py"

        cmd = [sys.executable, str(Path(__file__).parent / script), "--provider", provider]
        # score_fam_dimensions.py scores all 50 cases in one batched call by
        # design (see its module docstring for why) -- it has no --limit flag.
        if limit > 0 and script != "score_fam_dimensions.py":
            cmd += ["--limit", str(limit)]
        if verbose:
            cmd += ["--verbose"]

        st.write(f"Running: `{' '.join(cmd)}`")
        log_box = st.empty()
        log_lines = []

        process = subprocess.Popen(
            cmd, cwd=Path(__file__).parent,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1,
        )
        for line in process.stdout:
            log_lines.append(line.rstrip())
            # Keep the displayed log bounded so a long run doesn't blow up the page;
            # full output is still in log_lines for the final dump below.
            log_box.code("\n".join(log_lines[-200:]), language="text")

        process.wait()
        st.success(f"Finished with exit code {process.returncode}.")
        load_events.clear()
        load_investor_claims.clear()
        load_evidence.clear()
        st.info("Cache cleared -- switch to the Browse tab to see updated results.")

    st.divider()
    st.subheader("Current corpus status")
    ev_status = load_events().groupby("verification_status").size()
    ic_status = load_investor_claims().groupby("verification_status").size()
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**Event corpus**")
        st.bar_chart(ev_status)
    with c2:
        st.markdown("**Investor claims**")
        st.bar_chart(ic_status)