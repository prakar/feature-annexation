"""
Feature Annexation Observatory (FAO) — v4 Streamlit app.
Changes from v3:
- Header banner: title + descriptor
- Footer: GitHub link, paper attribution, corpus version
- Admin: API key setup instructions
- Feature Gap Degree label (was Stopgap Score)
- Tier labels: Mature / Developing / Emerging / Nascent
- Verdict box: badge removed, text only
- Notes: paragraph breaks rendered
- st.popover dimension tooltips in hero modal
- "How to read this" collapsible on Annexation Cases tab
- DB connection error handling
- Mini radar axis: "Gap Degree" (was "Stopgap")
Run:  streamlit run app.py
"""

import sqlite3, subprocess, sys, os, re, math
from pathlib import Path

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import yaml

ROOT      = Path(__file__).parent
DB_PATH   = ROOT / "annexation_evidence.db"
YAML_PATH = ROOT / "labels.yaml"

CORPUS_VERSION = "v1.0 · June 2026 · 51 cases"
GITHUB_URL     = "https://github.com/prakar/feature-annexation"
PAPER_CITATION = (
    "Reference implementation accompanying "
    "\u2018Telemetry-Capture Mediated Feature Annexation in Commercial Platform Ecosystems\u2019 "
    "by Prasanna Karmarkar \u2014 submitted for peer review."
)

st.set_page_config(
    page_title="Feature Annexation Observatory",
    page_icon="\U0001f52d",
    layout="wide",
    initial_sidebar_state="collapsed",
)

FATE_ACCENT = "#6366F1"
ZONE_ACCENT = "#6366F1"
DIM_ACCENT  = "#94A3B8"

st.markdown(f"""
<style>
.block-container {{ padding-top:3rem !important; padding-bottom:1rem !important; }}

/* ── Primary buttons: indigo (not Streamlit red) ────────────────────────── */
button[kind="primary"] {{
    background-color: {FATE_ACCENT} !important;
    border-color: {FATE_ACCENT} !important;
    color: #FFFFFF !important;
}}
button[kind="primary"]:hover {{
    background-color: #4F46E5 !important;
    border-color: #4F46E5 !important;
}}

/* ── Solid secondary buttons ─────────────────────────────────────────────── */
button[kind="secondary"] {{
    background-color: #F1F5F9 !important;
    border: 1.5px solid #CBD5E1 !important;
    color: #334155 !important;
    font-weight: 500 !important;
}}
button[kind="secondary"]:hover {{
    background-color: #E2E8F0 !important;
    border-color: #94A3B8 !important;
    color: #1E293B !important;
}}

/* ── X-axis Fate bar ─────────────────────────────────────────────────────── */
.fate-bar {{
    background: #EEEEFF;
    border-left: 4px solid {FATE_ACCENT};
    padding: 10px 14px 8px;
}}
.fate-bar-label {{
    font-size:13px; font-weight:700; color:{FATE_ACCENT};
    letter-spacing:0.3px; margin-bottom:6px;
}}

/* ── Y-axis Zone sidebar ─────────────────────────────────────────────────── */
.zone-header {{
    background: #ECFDF5;
    border-left: 4px solid {ZONE_ACCENT};
    padding: 8px 10px 6px; margin-bottom:8px;
}}
.zone-header-label {{
    font-size:13px; font-weight:700; color:{ZONE_ACCENT};
}}

/* ── Dimension floor ─────────────────────────────────────────────────────── */
.dim-header {{
    border-left: 4px solid {DIM_ACCENT};
    padding: 6px 10px; margin: 12px 0 8px; background:#F8FAFC;
}}
.dim-header-label {{ font-size:12px; font-weight:600; color:#64748B; }}
.dim-header-sub   {{ font-size:10px; color:#B0BAC9; margin-top:1px; }}

/* ── Filter tags ─────────────────────────────────────────────────────────── */
.filter-tag {{
    display:inline-flex; align-items:center; gap:4px;
    padding:3px 10px 3px 12px; border-radius:20px;
    font-size:11px; font-weight:500; margin:2px;
}}
.filter-tag-fate {{ background:#EEF2FF; color:{FATE_ACCENT}; border:1px solid #A5B4FC; }}
.filter-tag-zone {{ background:#F0FDF4; color:{ZONE_ACCENT}; border:1px solid #6EE7B7; }}
.filter-tag-dim  {{ background:#F8FAFC; color:#64748B;       border:1px solid #CBD5E1; }}

/* ── Fate badge chips ────────────────────────────────────────────────────── */
.badge {{ display:inline-block; padding:2px 9px; border-radius:10px; font-size:11px; font-weight:500; white-space:nowrap; }}
.badge-pivot    {{ background:#DCFCE7; color:#166534; }}
.badge-loss     {{ background:#FEE2E2; color:#991B1B; }}
.badge-narrow   {{ background:#FEF3C7; color:#92400E; }}
.badge-shift    {{ background:#EDE9FE; color:#4C1D95; }}
.badge-survived {{ background:#F1F5F9; color:#475569; }}
.badge-retreat  {{ background:#FFF7ED; color:#9A3412; }}
.badge-insuff   {{ background:#F8FAFC; color:#94A3B8; border:1px solid #E2E8F0; }}

/* ── Verdict box ─────────────────────────────────────────────────────────── */
.verdict-box {{
    padding:12px 16px; background:#F8FAFC;
    border-radius:10px; border:1px solid #E2E8F0; margin-top:12px;
}}
.verdict-label {{ font-size:12px; color:#94A3B8; text-transform:uppercase; letter-spacing:0.5px; }}
.verdict-value {{ font-size:20px; font-weight:700; color:#1E293B; margin-top:4px; }}

/* ── Source badge ────────────────────────────────────────────────────────── */
.src-badge {{
    display:inline-block; padding:1px 7px; border-radius:8px;
    font-size:9px; font-weight:600; white-space:nowrap;
}}

/* ── Footer ──────────────────────────────────────────────────────────────── */
.fao-footer {{
    margin-top: 32px;
    padding: 14px 0 8px;
    border-top: 1px solid #E2E8F0;
    font-size: 11px;
    color: #94A3B8;
    line-height: 1.6;
    text-align: center;
}}
.fao-footer a {{ color: #6366F1; text-decoration: none; }}
.fao-footer a:hover {{ text-decoration: underline; }}

/* ── How to read callout ─────────────────────────────────────────────────── */
.how-to-read {{
    background:#F0F4FF; border:1px solid #C7D2FE;
    border-radius:8px; padding:12px 16px; font-size:12px;
    color:#3730A3; margin-bottom:10px; line-height:1.6;
}}
</style>
""", unsafe_allow_html=True)


# ── Label system ──────────────────────────────────────────────────────────────
@st.cache_data
def load_labels():
    try:
        with open(YAML_PATH) as f:
            return yaml.safe_load(f)
    except Exception:
        return {}

def humanise(s):
    if not s: return "\u2014"
    return str(s).replace("_"," ").title()

def friendly_name(field, raw_value):
    labels = load_labels()
    return labels.get(field, {}).get(str(raw_value), humanise(raw_value))

FATE_LABELS = {
    "Repositioning":                   ("Pivot to Niche",       "badge-pivot"),
    "Compression":                     ("Clickthrough Loss",     "badge-loss"),
    "Contraction":                     ("Market Narrowing",      "badge-narrow"),
    "Transformation":                  ("Category Shift",        "badge-shift"),
    "Survived_No_Clear_Reorganization":("Survived Unchanged",    "badge-survived"),
    "Contested_Platform_Retreat":      ("Platform Retreated",    "badge-retreat"),
    "Insufficient_Evidence":           ("Insufficient evidence", "badge-insuff"),
}

ZONE_LABELS = {
    "AI Tooling":                       "AI Tooling",
    "Commerce and Infrastructure Layer":"Commerce & Infrastructure",
    "Enterprise Software Layer":        "Enterprise Software",
    "Marketplace / Private Label":      "Marketplace & Private Label",
    "Media and Attention Layer":        "Media & Attention",
    "Mobile OS Utilities":              "Mobile OS Utilities",
    "Operating System Layer":           "Operating System",
    "Search and Information Layer":     "Search & Information",
}

FAM_DIMS = {
    "fam_implementation_gap":      "Feature Gap Degree",
    "fam_replication_feasibility": "Ease of Replication",
    "fam_telemetry_exposure":      "Visibility on Platform Radar",
    "fam_integration_pressure":    "Native Fit Friction",
}

FAM_TOOLTIPS = {
    "fam_implementation_gap": (
        "Feature Gap Degree\n\n"
        "How significant was the platform gap this offering filled?\n\n"
        "Mature (75\u2013100): the platform had not built this capability at all \u2014 "
        "the offering existed entirely because the platform hadn\u2019t.\n"
        "Developing (50\u201374): the platform had a partial native equivalent "
        "but the offering filled a meaningful remaining gap.\n"
        "Emerging (25\u201349): the platform had reasonable native coverage; "
        "the offering\u2019s gap rationale was partial.\n"
        "Nascent (0\u201324): the platform already provided this capability natively; "
        "the offering\u2019s value came from something else."
    ),
    "fam_replication_feasibility": (
        "Ease of Replication\n\n"
        "How easily could the platform reproduce this capability natively?\n\n"
        "Mature (75\u2013100): trivially replicable using existing platform infrastructure \u2014 "
        "no new technology required.\n"
        "Developing (50\u201374): replicable with moderate engineering effort; "
        "some new capability needed.\n"
        "Emerging (25\u201349): replication required significant new investment "
        "or capability acquisition.\n"
        "Nascent (0\u201324): the platform would need to enter a genuinely new market "
        "to replicate this."
    ),
    "fam_telemetry_exposure": (
        "Visibility on Platform Radar\n\n"
        "How visible was usage of this offering to the platform through its own telemetry?\n\n"
        "Mature (75\u2013100): the platform could observe demand directly \u2014 "
        "via API calls, search queries, in-app signals, or marketplace data.\n"
        "Developing (50\u201374): the platform had reasonable but incomplete visibility "
        "into usage patterns.\n"
        "Emerging (25\u201349): usage was partially visible; the platform had indirect signals.\n"
        "Nascent (0\u201324): usage was largely invisible to the platform \u2014 "
        "activity occurred outside platform-mediated infrastructure."
    ),
    "fam_integration_pressure": (
        "Native Fit Friction\n\n"
        "How much structural resistance exists to the platform absorbing this natively?\n\n"
        "Mature (75\u2013100): fits naturally into the platform\u2019s existing architecture "
        "and user flows \u2014 integration would simplify the user experience.\n"
        "Developing (50\u201374): a reasonable fit with some structural adaptation required.\n"
        "Emerging (25\u201349): meaningful friction \u2014 native integration would require "
        "the platform to extend its architecture.\n"
        "Nascent (0\u201324): the platform would need to enter a categorically different "
        "domain to absorb this natively."
    ),
}

OUTCOME_RGBA = {
    "Repositioning":                   ("rgba(34,197,94,0.18)",  "#22C55E"),
    "Survived_No_Clear_Reorganization":("rgba(100,116,139,0.15)","#64748B"),
    "Contested_Platform_Retreat":      ("rgba(249,115,22,0.18)", "#F97316"),
    "Transformation":                  ("rgba(168,85,247,0.18)", "#A855F7"),
    "Compression":                     ("rgba(239,68,68,0.18)",  "#EF4444"),
    "Contraction":                     ("rgba(245,158,11,0.18)", "#F59E0B"),
    "Insufficient_Evidence":           ("rgba(203,213,225,0.15)","#CBD5E1"),
}

SRC_COLOURS = {
    "PD":("1D4ED8","DBEAFE"), "PR":("1D4ED8","DBEAFE"),
    "MR":("92400E","FEF3C7"), "AR":("166534","DCFCE7"),
    "CR":("4C1D95","EDE9FE"), "RR":("991B1B","FEE2E2"),
    "DS":("0F766E","CCFBF1"), "VC":("9A3412","FFF7ED"),
}

def tier_label(score):
    """Returns (label, text_colour, bg_colour) based on absolute score.
    Labels describe maturity of annexation conditions, not alarm level.
    Nascent → Emerging → Developing → Mature
    """
    if score is None: return ("\u2014","#94A3B8","#F1F5F9")
    s = float(score)
    if s >= 75: return ("Mature",     "#059669","#DCFCE7")
    if s >= 50: return ("Developing", "#0284C7","#E0F2FE")
    if s >= 25: return ("Emerging",   "#D97706","#FEF3C7")
    return             ("Nascent",    "#94A3B8","#F1F5F9")

def fate_badge_html(outcome):
    label, cls = FATE_LABELS.get(outcome,(humanise(outcome),"badge-insuff"))
    return f'<span class="badge {cls}">{label}</span>'

def confidence_badge_html(row):
    """Badge showing Annexation Confidence for gallery cards."""
    label, tc, bg, _ = fam_signal(row)
    return f'<span style="display:inline-block;padding:2px 9px;border-radius:10px;font-size:11px;font-weight:600;background:{bg};color:{tc};white-space:nowrap">{label} confidence</span>'

def src_badge_html(code):
    tc, bg = SRC_COLOURS.get(str(code).upper().strip(),("475569","F1F5F9"))
    label  = friendly_name("source_type", code)
    return f'<span class="src-badge" style="background:#{bg};color:#{tc}">{label}</span>'

def render_notes(raw):
    """Format pipeline notes for display: paragraph breaks, clean up tags."""
    if not raw: return "No narrative notes recorded."
    text = re.sub(r'\[RECLASSIFIED[^\]]*\]','',str(raw)).strip()
    # Split on double newline or PART N — markers
    text = re.sub(r'(PART\s+\d+\s*\u2014)', r'<br><br><strong>\1</strong>', text)
    text = text.replace('\n\n','<br><br>').replace('\n','<br>')
    return text


# ── Data layer ────────────────────────────────────────────────────────────────
def db_ok():
    return DB_PATH.exists()

@st.cache_data
def load_events():
    conn = sqlite3.connect(DB_PATH)
    df   = pd.read_sql_query("SELECT * FROM events ORDER BY event_id", conn)
    conn.close()
    return df

@st.cache_data
def load_investor_claims():
    conn = sqlite3.connect(DB_PATH)
    df   = pd.read_sql_query("SELECT * FROM investor_claims ORDER BY claim_id", conn)
    conn.close()
    return df

@st.cache_data
def load_evidence_for_event(event_id):
    conn = sqlite3.connect(DB_PATH)
    df   = pd.read_sql_query(
        "SELECT * FROM evidence WHERE event_id=? ORDER BY supports_or_contradicts, evidence_id",
        conn, params=(int(event_id),)
    )
    conn.close()
    return df

@st.cache_data
def total_evidence_count():
    conn = sqlite3.connect(DB_PATH)
    n    = conn.execute("SELECT count(*) FROM evidence WHERE event_id IS NOT NULL").fetchone()[0]
    conn.close()
    return n


# ── Radar (Plotly, hero) ──────────────────────────────────────────────────────
def render_radar(row, height=260, conf_rgba=None):
    dim_keys  = list(FAM_DIMS.keys())
    dim_names = list(FAM_DIMS.values())
    values    = [float(row.get(k) or 0) for k in dim_keys]
    if conf_rgba:
        fill_rgba, line_hex = conf_rgba
    else:
        outcome = str(row.get("category_outcome",""))
        fill_rgba, line_hex = OUTCOME_RGBA.get(outcome,("rgba(99,102,241,0.18)","#6366F1"))
    fig = go.Figure(go.Scatterpolar(
        r=values+[values[0]], theta=dim_names+[dim_names[0]],
        fill="toself", fillcolor=fill_rgba,
        line=dict(color=line_hex, width=2),
        hovertemplate="%{theta}: %{r}<extra></extra>",
    ))
    fig.update_layout(
        polar=dict(
            radialaxis=dict(visible=True, range=[0,100],
                            tickfont=dict(size=9), gridcolor="#E2E8F0",
                            tickvals=[25,50,75,100]),
            angularaxis=dict(
                tickfont=dict(size=11, color="#475569"),
                categoryorder="array",
                categoryarray=dim_names,
                direction="counterclockwise",
                rotation=90,
            ),
            bgcolor="#FAFAFA",
        ),
        showlegend=False,
        margin=dict(l=60,r=60,t=20,b=20),
        height=height,
        paper_bgcolor="rgba(0,0,0,0)",
    )
    return fig


# ── Mini radar (SVG, gallery cards) ──────────────────────────────────────────
def mini_radar_html(row):
    dim_keys = list(FAM_DIMS.keys())
    values   = [float(row.get(k) or 0)/100.0 for k in dim_keys]
    # Colour by confidence, not outcome
    conf     = row.get("_conf","Unscored")
    conf_map = {"High":("#059669","#05966930"),"Medium":("#D97706","#D9770630"),
                "Low":("#64748B","#64748B25"),"Unscored":("#CBD5E1","#CBD5E120")}
    line_hex, fill_hex = conf_map.get(conf,("#6366F1","#6366F130"))
    cx,cy,r  = 46,46,34
    angles   = [math.pi/2 + 2*math.pi*i/4 for i in range(4)]
    rings = "".join(
        f'<polygon points="{" ".join(f"{cx+math.cos(a)*r*p:.1f},{cy-math.sin(a)*r*p:.1f}" for a in angles)}" fill="none" stroke="#E2E8F0" stroke-width="0.8"/>'
        for p in [0.33,0.66,1.0]
    )
    axlines = "".join(
        f'<line x1="{cx}" y1="{cy}" x2="{cx+math.cos(a)*r:.1f}" y2="{cy-math.sin(a)*r:.1f}" stroke="#E2E8F0" stroke-width="0.8"/>'
        for a in angles
    )
    pts  = " ".join(f"{cx+math.cos(angles[i])*r*values[i]:.1f},{cy-math.sin(angles[i])*r*values[i]:.1f}" for i in range(4))
    poly = f'<polygon points="{pts}" fill="{fill_hex}" stroke="{line_hex}" stroke-width="1.8"/>'
    # "Gap Degree" replaces "Stopgap" on mini radar
    short = ["Gap Degree","Replication","Visibility","Friction"]
    lbls  = "".join(
        f'<text x="{cx+math.cos(angles[i])*(r+13):.0f}" y="{cy-math.sin(angles[i])*(r+13):.0f}" text-anchor="middle" dominant-baseline="middle" font-size="7.5" fill="#94A3B8" font-family="sans-serif">{short[i]}</text>'
        for i in range(4)
    )
    return (f'<div style="background:#F8FAFC;border:1px solid #E2E8F0;border-radius:8px;margin:6px 0">'
            f'<svg width="92" height="92" viewBox="0 0 92 92" style="display:block;margin:0 auto">'
            f'{rings}{axlines}{poly}{lbls}</svg></div>')


# ── Dimension bars HTML ───────────────────────────────────────────────────────
def dim_bars_html(row, compact=False):
    bar_colours = {"Mature":"#059669","Developing":"#0284C7",
                   "Emerging":"#D97706","Nascent":"#CBD5E1"}
    html = '<div style="display:grid;gap:5px;margin-top:6px">'
    for key, name in FAM_DIMS.items():
        val   = row.get(key)
        score = float(val) if val is not None else 0.0
        tlabel,tc,tbg = tier_label(val)
        bar_c = bar_colours.get(tlabel, "#CBD5E1")
        fs = "10px" if not compact else "9.5px"
        html += f"""
        <div style="display:grid;grid-template-columns:1fr 90px;align-items:center;gap:6px">
          <div>
            <div style="font-size:{fs};color:#64748B;margin-bottom:2px">{name} · {int(score)}</div>
            <div style="height:4px;background:#F1F5F9;border-radius:2px;overflow:hidden">
              <div style="width:{score}%;height:100%;background:{bar_c};border-radius:2px"></div>
            </div>
          </div>
          <span style="font-size:11px;padding:3px 8px;border-radius:8px;background:{tbg};color:{tc};font-weight:600;text-align:center;white-space:nowrap">{tlabel}</span>
        </div>"""
    return html + "</div>"


def fam_signal(row):
    """Compute Annexation Confidence from the four FAM dimension scores.
    Returns (label, colour, bg_colour, interpretation_text).
    label is a single word: High / Medium / Low.
    """
    scores = [float(row.get(k) or 0) for k in FAM_DIMS.keys()]
    valid  = [s for s in scores if s > 0]
    if not valid:
        return ("Unscored", "#94A3B8", "#F1F5F9",
                "FAM dimensions have not been scored for this case.")
    avg = sum(valid) / len(valid)
    if avg >= 65:
        return (
            "High",
            "#059669", "#DCFCE7",
            f"Pre-annexation FAM avg: {avg:.0f}/100. "
            "All or most dimensions showed high structural readability. "
            "The framework would have flagged this as a clear annexation candidate."
        )
    if avg >= 40:
        return (
            "Medium",
            "#D97706", "#FEF3C7",
            f"Pre-annexation FAM avg: {avg:.0f}/100. "
            "Some dimensions showed meaningful structural readability, others did not. "
            "The framework would have flagged this with caveats."
        )
    return (
        "Low",
        "#475569", "#F1F5F9",
        f"Pre-annexation FAM avg: {avg:.0f}/100. "
        "Most dimensions showed low structural readability. "
        "This annexation was not strongly predicted by the FAM framework — "
        "the mechanism may differ from telemetry-capture reimplementation."
    )


# ── @st.dialog — case detail modal ───────────────────────────────────────────
@st.dialog("Case Detail", width="large")
def show_case_detail(row):
    outcome     = str(row.get("category_outcome",""))
    fate_disp,_ = FATE_LABELS.get(outcome,(humanise(outcome),""))
    sig_label, sig_tc, sig_bg, sig_text = fam_signal(row)
    _conf_rgba_map = {
        "High":     ("rgba(5,150,105,0.18)",  "#059669"),
        "Medium":   ("rgba(217,119,6,0.18)",  "#D97706"),
        "Low":      ("rgba(100,116,139,0.15)","#64748B"),
    }
    _radar_rgba = _conf_rgba_map.get(sig_label)
    zone_disp   = ZONE_LABELS.get(row['layer'], row['layer'] or '\u2014')
    ev_quality  = friendly_name("confidence", row.get("confidence"))

    left, right = st.columns([1,1], gap="large")

    with left:
        # ── Annexation Confidence — PRIMARY VERDICT at top ────────────────────
        st.markdown(f"""
        <div style="padding:14px 16px;border-radius:10px;
                    background:{sig_bg};border:1.5px solid {sig_tc}44;margin-bottom:16px">
          <div style="font-size:10px;font-weight:700;color:{sig_tc};text-transform:uppercase;
                      letter-spacing:0.6px;margin-bottom:4px">Annexation Confidence</div>
          <div style="font-size:26px;font-weight:900;color:{sig_tc};margin-bottom:6px;
                      line-height:1">{sig_label}</div>
          <div style="font-size:12px;color:#475569;line-height:1.6">{sig_text}</div>
        </div>""", unsafe_allow_html=True)

        # ── Case title + quiet annexed note ───────────────────────────────────
        st.markdown(f"""
        <div style="font-size:20px;font-weight:800;color:#1E293B;margin-bottom:2px">
          {row['platform']} · {row['offering']}
        </div>
        <div style="font-size:12px;color:#94A3B8;margin-bottom:14px">
          {zone_disp}
          <span style="margin-left:8px;font-style:italic;color:#CBD5E1">(annexed product)</span>
        </div>

        <div style="font-size:11px;font-weight:700;color:#6366F1;text-transform:uppercase;
                    letter-spacing:0.6px;margin-bottom:4px">Pre-Annexation FAM Profile</div>
        <div style="font-size:11px;color:#94A3B8;margin-bottom:8px">
          Retrospective snapshot \u2014 structural readability <em>before</em> the platform acted
        </div>""", unsafe_allow_html=True)

        st.plotly_chart(render_radar(row, height=220, conf_rgba=_radar_rgba),
                        use_container_width=True,
                        key=f"dlg_radar_{row['event_id']}")

        # Dimension bars with popovers
        _bar_colours = {"Mature":"#059669","Developing":"#0284C7",
                        "Emerging":"#D97706","Nascent":"#CBD5E1"}
        for key, name in FAM_DIMS.items():
            val   = row.get(key)
            score = float(val) if val is not None else 0.0
            tlabel,tc,tbg = tier_label(val)
            bar_c = _bar_colours.get(tlabel, "#CBD5E1")
            dcol, icol = st.columns([8,1], gap="small")
            with dcol:
                st.markdown(f"""
                <div style="display:grid;grid-template-columns:1fr 90px;align-items:center;gap:6px;margin-bottom:2px">
                  <div>
                    <div style="font-size:13px;color:#64748B;margin-bottom:3px">{name} · {int(score)}</div>
                    <div style="height:6px;background:#F1F5F9;border-radius:3px;overflow:hidden">
                      <div style="width:{score}%;height:100%;background:{bar_c};border-radius:3px"></div>
                    </div>
                  </div>
                  <span style="font-size:11px;padding:3px 8px;border-radius:8px;background:{tbg};
                               color:{tc};font-weight:600;text-align:center;white-space:nowrap">{tlabel}</span>
                </div>""", unsafe_allow_html=True)
            with icol:
                with st.popover("\u2139\ufe0f"):
                    st.markdown(FAM_TOOLTIPS[key])

        # ── Fate after annexation — demoted secondary ─────────────────────────
        st.markdown(f"""
        <div style="margin-top:12px;padding:10px 14px;border-radius:8px;
                    background:#F8FAFC;border:1px solid #E2E8F0">
          <div style="font-size:10px;color:#94A3B8;text-transform:uppercase;
                      letter-spacing:0.5px;margin-bottom:3px">
            Fate after annexation
            <span style="font-size:9px;font-style:italic;font-weight:400;
                         text-transform:none;letter-spacing:0">
              \u2014 not predicted by this framework
            </span>
          </div>
          <div style="font-size:15px;font-weight:600;color:#64748B">{fate_disp}</div>
          <div style="font-size:11px;color:#94A3B8;margin-top:4px">
            Evidence quality: {ev_quality}
          </div>
        </div>""", unsafe_allow_html=True)

    with right:
        with st.expander("\U0001f4c4 About this case", expanded=False):
            st.markdown(
                f'<div style="font-size:14px;color:#475569;line-height:1.8">'
                f'{render_notes(row.get("notes"))}</div>',
                unsafe_allow_html=True
            )
        with st.expander("\U0001f9e0 Framework reasoning", expanded=False):
            reasoning = str(row.get("fam_reasoning") or "No FAM reasoning recorded.")
            st.markdown(
                f'<div style="font-size:14px;color:#475569;line-height:1.8">{reasoning}</div>',
                unsafe_allow_html=True
            )
        evidence = load_evidence_for_event(row["event_id"])
        n_ev     = len(evidence)
        with st.expander(f"\U0001f517 Evidence sources ({n_ev})", expanded=False):
            stance_colour = {"supports":"#059669","contradicts":"#DC2626","partial":"#D97706"}
            for _, ev in evidence.iterrows():
                code    = str(ev.get("source_type") or "?").strip()
                stance  = str(ev.get("supports_or_contradicts") or "").lower()
                sc      = stance_colour.get(stance,"#94A3B8")
                title   = ev.get("title") or ev.get("url") or "Untitled"
                url     = ev.get("url") or ""
                date    = ev.get("publication_date") or "undated"
                excerpt = ev.get("excerpt_paraphrase") or ""
                link    = (f'<a href="{url}" target="_blank" style="color:#3730A3;text-decoration:none">{title}</a>'
                           if url else title)
                st.markdown(f"""
                <div style="padding:8px 10px;background:#F8FAFC;border-radius:8px;
                            border:1px solid #E2E8F0;margin-bottom:6px;font-size:13px">
                  <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:8px">
                    <span style="flex:1">{link}</span>
                    {src_badge_html(code)}
                  </div>
                  <div style="color:#94A3B8;font-size:12px;margin-top:4px">
                    {date}
                    <span style="margin-left:8px;color:{sc};font-weight:600;font-size:11px">
                      {stance.title() if stance else ""}
                    </span>
                  </div>
                  {'<div style="color:#64748B;font-size:12px;margin-top:5px;font-style:italic">'+excerpt+'</div>' if excerpt else ''}
                </div>""", unsafe_allow_html=True)


# ── Footer helper ─────────────────────────────────────────────────────────────
def render_footer():
    st.markdown(f"""
    <div class="fao-footer">
      <div style="font-size:12px;color:#64748B;margin-bottom:6px">
        An interactive corpus explorer for platform annexation research —
        51 verified cases of platform-native features displacing third-party complementors.
        Retrospective only &nbsp;·&nbsp; No predictions.
      </div>
      {PAPER_CITATION}<br>
      Corpus: {CORPUS_VERSION} &nbsp;·&nbsp;
      <a href="{GITHUB_URL}" target="_blank">Source on GitHub</a>
    </div>""", unsafe_allow_html=True)


# ── Header banner ─────────────────────────────────────────────────────────────
# ── Header ───────────────────────────────────────────────────────────────────
st.markdown(
    '<h2 style="color:#312E81;font-weight:800;letter-spacing:-0.5px;margin:0 0 4px">'
    '\U0001f52d Feature Annexation Observatory</h2>'
    '<p style="color:#94A3B8;font-size:12px;margin:0 0 12px">51-case retrospective corpus &nbsp;·&nbsp; '
    'No predictions &nbsp;·&nbsp; v1.0 · June 2026</p>',
    unsafe_allow_html=True
)

# ── DB check ──────────────────────────────────────────────────────────────────
if not db_ok():
    st.error(
        f"**Corpus database not found.**  \n"
        f"Expected `annexation_evidence.db` in `{ROOT}`.  \n"
        f"If you\u2019ve just cloned the repo, download the database from the "
        f"[GitHub releases page]({GITHUB_URL}/releases) and place it in the repo root."
    )
    st.stop()

tab_cases, tab_dashboard, tab_discourse, tab_admin = st.tabs([
    "\U0001f50e Annexation Cases",
    "\U0001f4ca Dashboard",
    "\U0001f4ac Investors on Annexation Risk",
    "\u2699\ufe0f Run Verification",
])


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 1 — ANNEXATION CASES
# ═══════════════════════════════════════════════════════════════════════════════
with tab_cases:
    df_all = load_events()

    # Pre-compute confidence for every row once
    def get_conf(row):
        scores = [float(row.get(k) or 0) for k in FAM_DIMS.keys()]
        valid  = [s for s in scores if s > 0]
        if not valid: return "Unscored"
        avg = sum(valid)/len(valid)
        if avg >= 65: return "High"
        if avg >= 40: return "Medium"
        return "Low"

    df_all["_conf"] = df_all.apply(get_conf, axis=1)

    # Confidence buckets for X-axis
    CONF_LEVELS  = ["High", "Medium", "Low"]
    CONF_DISPLAY = {"High":"High Confidence","Medium":"Medium Confidence","Low":"Low Confidence"}
    CONF_COLOURS = {"High":"#059669","Medium":"#D97706","Low":"#475569"}
    CONF_BG      = {"High":"#DCFCE7","Medium":"#FEF3C7","Low":"#F1F5F9"}

    # Radar polygon colours keyed to confidence (not outcome/fate)
    CONF_RGBA = {
        "High":     ("rgba(5,150,105,0.18)",  "#059669"),
        "Medium":   ("rgba(217,119,6,0.18)",  "#D97706"),
        "Low":      ("rgba(100,116,139,0.15)","#64748B"),
        "Unscored": ("rgba(203,213,225,0.15)","#CBD5E1"),
    }

    for k,v in [
        ("active_conf","High"),   # default: High confidence
        ("active_zone",None),
        ("dim_floors",{k:0 for k in FAM_DIMS}),
        ("gallery_page",0),
    ]:
        if k not in st.session_state:
            st.session_state[k] = v

    # How to read this
    with st.expander("\U0001f4a1 How to read this tool", expanded=False):
        st.markdown("""<div class="how-to-read">
        <strong>Every case in this corpus is a confirmed annexation</strong> —
        a platform that shipped a native feature previously served by a third-party complementor.
        Annexation is not in question; it already happened.<br><br>
        <strong>What the framework measures:</strong> How readable was this annexation
        <em>before</em> it happened? The four FAM dimensions score the pre-annexation
        structural conditions. The <strong>Annexation Confidence</strong> badge summarises
        how strongly those conditions signalled that annexation would occur.<br><br>
        <strong>The four dimensions:</strong><br>
        \u2022 <strong>Feature Gap Degree</strong> \u2014 how significant was the platform gap this offering filled?<br>
        \u2022 <strong>Ease of Replication</strong> \u2014 how easily could the platform copy this natively?<br>
        \u2022 <strong>Visibility on Platform Radar</strong> \u2014 how visible was usage to the platform\u2019s own telemetry?<br>
        \u2022 <strong>Native Fit Friction</strong> \u2014 how naturally did this fit into the platform\u2019s architecture?<br><br>
        <strong>Filter by Confidence \u2192</strong> and <strong>Zone \u2193</strong> to navigate the corpus.
        High-confidence cases are the framework\u2019s strongest retrospective reads.
        Low-confidence cases are the corpus\u2019s edge cases \u2014 annexations the framework
        did not strongly predict, often using a different mechanism than telemetry-capture reimplementation.<br><br>
        <em>All FAM scores are retrospective \u2014 scored knowing annexation occurred.
        The framework reports structural readability; it does not claim to have predicted these events in real time.</em>
        </div>""", unsafe_allow_html=True)

    # ── X-axis: Annexation Confidence pills ──────────────────────────────────
    conf_counts = df_all["_conf"].value_counts().to_dict()
    st.markdown('<div class="fate-bar"><div class="fate-bar-label">ANNEXATION CONFIDENCE \u2192</div>',
                unsafe_allow_html=True)
    conf_cols = st.columns(len(CONF_LEVELS)+1, gap="small")
    for i, level in enumerate(CONF_LEVELS):
        count     = conf_counts.get(level, 0)
        is_active = st.session_state.active_conf == level
        disp      = CONF_DISPLAY[level]
        if conf_cols[i].button(
            f"{'✓ ' if is_active else ''}{disp} {count}",
            key=f"conf_{level}",
            type="primary" if is_active else "secondary",
            use_container_width=True,
        ):
            st.session_state.active_conf  = None if is_active else level
            st.session_state.gallery_page = 0
            st.rerun()
    if conf_cols[len(CONF_LEVELS)].button("All cases", key="conf_clear",
                                          type="primary" if st.session_state.active_conf is None else "secondary",
                                          use_container_width=True):
        st.session_state.active_conf  = None
        st.session_state.gallery_page = 0
        st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)

    sidebar_col, main_col = st.columns([1,3], gap="medium")

    with sidebar_col:
        st.markdown('<div class="zone-header"><div class="zone-header-label">ZONE \u2195</div></div>',
                    unsafe_allow_html=True)
        for db_zone, zone_label in ZONE_LABELS.items():
            is_active = st.session_state.active_zone == db_zone
            if st.button(
                f"{'✓ ' if is_active else ''}{zone_label}",
                key=f"zone_{db_zone}",
                type="primary" if is_active else "secondary",
                use_container_width=True,
            ):
                st.session_state.active_zone  = None if is_active else db_zone
                st.session_state.gallery_page = 0
                st.rerun()
        if st.session_state.active_zone:
            if st.button("\u21a9 All zones",key="zone_clear",use_container_width=True):
                st.session_state.active_zone  = None
                st.session_state.gallery_page = 0
                st.rerun()

        st.markdown("""<div class="dim-header">
          <div class="dim-header-label">Adjust Dimension Floor</div>
          <div class="dim-header-sub">Show only cases scoring above a threshold</div>
        </div>""", unsafe_allow_html=True)

        for key, name in FAM_DIMS.items():
            new_val = st.slider(name, 0, 100,
                                st.session_state.dim_floors[key],
                                step=5, key=f"slider_{key}")
            if new_val != st.session_state.dim_floors[key]:
                st.session_state.dim_floors[key] = new_val
                st.session_state.gallery_page     = 0
        if any(v > 0 for v in st.session_state.dim_floors.values()):
            if st.button("\u21a9 Reset all floors",key="dim_reset",use_container_width=True):
                st.session_state.dim_floors   = {k:0 for k in FAM_DIMS}
                st.session_state.gallery_page = 0
                st.rerun()

    with main_col:
        filtered = df_all.copy()
        if st.session_state.active_conf:
            filtered = filtered[filtered["_conf"] == st.session_state.active_conf]
        if st.session_state.active_zone:
            filtered = filtered[filtered["layer"] == st.session_state.active_zone]
        for key, floor in st.session_state.dim_floors.items():
            if floor > 0:
                filtered = filtered[filtered[key].fillna(0) >= floor]
        filtered = filtered.reset_index(drop=True)
        n = len(filtered)

        tags_html  = ""
        any_filter = False
        if st.session_state.active_conf:
            tc = CONF_COLOURS.get(st.session_state.active_conf, "#475569")
            bg = CONF_BG.get(st.session_state.active_conf, "#F1F5F9")
            tags_html += (f'<span class="filter-tag" style="background:{bg};color:{tc};'
                          f'border:1px solid {tc}44">'
                          f'Confidence: {st.session_state.active_conf}</span>')
            any_filter = True
        if st.session_state.active_zone:
            zl = ZONE_LABELS.get(st.session_state.active_zone, st.session_state.active_zone)
            tags_html += f'<span class="filter-tag filter-tag-zone">Zone: {zl}</span>'
            any_filter = True
        for key, floor in st.session_state.dim_floors.items():
            if floor > 0:
                tags_html += f'<span class="filter-tag filter-tag-dim">{FAM_DIMS[key]} \u2265 {floor}</span>'
                any_filter = True

        suffix = " of 51 total" if any_filter else ""
        st.markdown(
            f'<div style="padding:6px 0 8px;display:flex;align-items:center;flex-wrap:wrap;gap:4px">'
            f'<span style="font-size:11px;color:#64748B;margin-right:4px">'
            f'Showing <strong>{n}</strong> case{"s" if n!=1 else ""}{suffix}</span>'
            f'{tags_html}</div>',
            unsafe_allow_html=True
        )

        if n == 0:
            st.markdown("""
            <div style="padding:40px;text-align:center;background:#F8FAFC;border-radius:12px;
                        border:1px dashed #CBD5E1;margin:8px 0">
              <div style="font-size:32px;margin-bottom:8px">\U0001f50d</div>
              <div style="font-size:15px;font-weight:600;color:#475569;margin-bottom:4px">
                No cases match this intersection
              </div>
              <div style="font-size:12px;color:#94A3B8">
                Try a different Confidence level or Zone, or reset the dimension floors.
              </div>
            </div>""", unsafe_allow_html=True)
        else:
            CARDS_PER_PAGE = 6
            total_pages = max(1,(n+CARDS_PER_PAGE-1)//CARDS_PER_PAGE)
            page        = min(st.session_state.gallery_page, total_pages-1)
            page_df     = filtered.iloc[page*CARDS_PER_PAGE:(page+1)*CARDS_PER_PAGE]

            gcols = st.columns(3, gap="small")
            for i,(_,row) in enumerate(page_df.iterrows()):
                with gcols[i%3]:
                    st.markdown(f"""
                    <div style="background:#FFFFFF;border:1px solid #E2E8F0;border-radius:12px;
                                padding:14px;margin-bottom:4px">
                      <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:4px">
                        <div>
                          <div style="font-size:12px;font-weight:700;color:#1E293B">{row['platform']}</div>
                          <div style="font-size:11px;color:#64748B">{row['offering']}</div>
                        </div>
                        {confidence_badge_html(row)}
                      </div>
                      {mini_radar_html(row)}
                      {dim_bars_html(row, compact=True)}
                    </div>""", unsafe_allow_html=True)
                    if st.button("View details",key=f"card_{row['event_id']}",
                                 use_container_width=True):
                        show_case_detail(row)

            if total_pages > 1:
                p1,p2,p3 = st.columns([1,2,1])
                with p1:
                    if page > 0 and st.button("\u2190 Prev",key="prev_page"):
                        st.session_state.gallery_page = page-1
                        st.rerun()
                with p2:
                    s,e = page*CARDS_PER_PAGE+1, min((page+1)*CARDS_PER_PAGE,n)
                    st.markdown(
                        f'<p style="text-align:center;font-size:11px;color:#94A3B8;padding-top:6px">'
                        f'Showing {s}\u2013{e} of {n} cases \u00b7 Page {page+1}/{total_pages}</p>',
                        unsafe_allow_html=True
                    )
                with p3:
                    if page < total_pages-1 and st.button("Next \u2192",key="next_page"):
                        st.session_state.gallery_page = page+1
                        st.rerun()

    render_footer()


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 2 — DASHBOARD
# ═══════════════════════════════════════════════════════════════════════════════
with tab_dashboard:
    import altair as alt

    ev = load_events()

    # Compute confidence for all rows
    def _get_conf(row):
        scores = [float(row.get(k) or 0) for k in FAM_DIMS.keys()]
        valid  = [s for s in scores if s > 0]
        if not valid: return "Unscored"
        avg = sum(valid)/len(valid)
        if avg >= 65: return "High"
        if avg >= 40: return "Medium"
        return "Low"
    ev["_conf"] = ev.apply(_get_conf, axis=1)

    total    = len(ev)
    n_high   = (ev["_conf"]=="High").sum()
    n_mod    = (ev["_conf"]=="Medium").sum()
    n_low    = (ev["_conf"]=="Low").sum()
    n_contra = (ev["verification_status"]=="postFA-collapseContradicted").sum()

    # ── Primary KPIs ─────────────────────────────────────────────────────────
    st.markdown(f"""
    <div style="padding:14px 20px;background:linear-gradient(135deg,#F0FDF4,#DCFCE7);
                border-radius:10px;border:1px solid #86EFAC;margin-bottom:16px">
      <div style="font-size:11px;font-weight:700;color:#059669;text-transform:uppercase;
                  letter-spacing:0.6px;margin-bottom:8px">Annexation Confidence Distribution — Primary Finding</div>
      <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:16px">
        <div>
          <div style="font-size:28px;font-weight:900;color:#059669">{n_high}</div>
          <div style="font-size:12px;color:#047857;font-weight:600">High Confidence</div>
          <div style="font-size:11px;color:#6EE7B7">{n_high/total:.0%} of corpus</div>
        </div>
        <div>
          <div style="font-size:28px;font-weight:900;color:#D97706">{n_mod}</div>
          <div style="font-size:12px;color:#B45309;font-weight:600">Medium Confidence</div>
          <div style="font-size:11px;color:#B45309">{n_mod/total:.0%} of corpus</div>
        </div>
        <div>
          <div style="font-size:28px;font-weight:900;color:#475569">{n_low}</div>
          <div style="font-size:12px;color:#334155;font-weight:600">Low Confidence</div>
          <div style="font-size:11px;color:#94A3B8">{n_low/total:.0%} — mechanism variant</div>
        </div>
        <div>
          <div style="font-size:28px;font-weight:900;color:#1E293B">{total}</div>
          <div style="font-size:12px;color:#475569;font-weight:600">Total Cases</div>
          <div style="font-size:11px;color:#94A3B8">{total_evidence_count()} evidence sources</div>
        </div>
      </div>
    </div>""", unsafe_allow_html=True)

    st.caption(f"49/51 cases contradict the original \u2018Collapse\u2019 narrative \u00b7 "
               f"Framework called {n_high} annexations clearly ({n_high/total:.0%})")

    st.divider()

    # ── Confidence by Zone and Platform ──────────────────────────────────────
    ev_c = ev.copy()
    ev_c["Confidence"] = ev_c["_conf"].map(
        lambda x: {"High":"High Confidence","Medium":"Medium Confidence",
                   "Low":"Low Confidence"}.get(x,x)
    )
    ev_c["Zone"] = ev_c["layer"].map(lambda x: ZONE_LABELS.get(x, x or "Unknown"))

    conf_domain  = ["High Confidence","Medium Confidence","Low Confidence"]
    conf_colours = ["#059669","#D97706","#94A3B8"]

    ca, cb = st.columns(2)
    with ca:
        st.subheader("Annexation Confidence by Zone")
        lf = ev_c.dropna(subset=["Zone","Confidence"]).groupby(["Zone","Confidence"]).size().reset_index(name="n")
        st.altair_chart(
            alt.Chart(lf).mark_bar().encode(
                x=alt.X("n:Q",title="Cases"),
                y=alt.Y("Zone:N",title=None,sort="-x"),
                color=alt.Color("Confidence:N",title="Confidence",
                    scale=alt.Scale(domain=conf_domain,range=conf_colours)),
                tooltip=["Zone","Confidence","n"],
            ).properties(height=300), use_container_width=True
        )
    with cb:
        st.subheader("Annexation Confidence by Platform")
        pf = ev_c.dropna(subset=["platform","Confidence"]).groupby(["platform","Confidence"]).size().reset_index(name="n")
        st.altair_chart(
            alt.Chart(pf).mark_bar().encode(
                x=alt.X("n:Q",title="Cases"),
                y=alt.Y("platform:N",title=None,sort="-x"),
                color=alt.Color("Confidence:N",title=None,legend=None,
                    scale=alt.Scale(domain=conf_domain,range=conf_colours)),
                tooltip=["platform","Confidence","n"],
            ).properties(height=400), use_container_width=True
        )

    st.divider()
    st.subheader("Pre-annexation FAM dimension distributions")
    st.caption("Scores reflect structural readability before the platform acted. "
               "Higher = conditions were more mature for annexation on that dimension.")
    dcols = st.columns(4)
    for i,(key,name) in enumerate(FAM_DIMS.items()):
        with dcols[i]:
            scores = ev[key].dropna()
            if len(scores):
                fh = go.Figure(go.Histogram(x=scores,nbinsx=10,marker_color="#059669",opacity=0.75))
                fh.update_layout(
                    title=dict(text=name,font=dict(size=10)),
                    xaxis=dict(range=[0,100],title=None,tickfont=dict(size=9)),
                    yaxis=dict(title=None,tickfont=dict(size=9)),
                    margin=dict(l=10,r=10,t=28,b=10),
                    height=150,bargap=0.1,paper_bgcolor="rgba(0,0,0,0)",
                )
                st.plotly_chart(fh,use_container_width=True,key=f"hist_{key}")
                st.caption(f"avg {scores.mean():.0f} \u00b7 min {scores.min():.0f} \u00b7 max {scores.max():.0f}")

    # Fate distribution demoted to supplementary
    with st.expander("Complementor outcomes after annexation (supplementary — not the framework\u2019s primary claim)"):
        st.caption("What happened to the complementor after annexation. "
                   "This is distinct from the framework\u2019s annexation confidence prediction.")
        ev_f = ev.copy()
        ev_f["Fate"] = ev_f["category_outcome"].map(lambda x: FATE_LABELS.get(x,(humanise(x),""))[0])
        ev_f["Zone"] = ev_f["layer"].map(lambda x: ZONE_LABELS.get(x, x or "Unknown"))
        all_fates   = [v[0] for v in FATE_LABELS.values()]
        all_colours_f = ["#22C55E","#EF4444","#F59E0B","#A855F7","#94A3B8","#F97316","#CBD5E1"]
        fa, fb = st.columns(2)
        with fa:
            lf2 = ev_f.dropna(subset=["Zone","Fate"]).groupby(["Zone","Fate"]).size().reset_index(name="n")
            st.altair_chart(
                alt.Chart(lf2).mark_bar().encode(
                    x=alt.X("n:Q",title="Cases"),
                    y=alt.Y("Zone:N",title=None,sort="-x"),
                    color=alt.Color("Fate:N",title="Fate",
                        scale=alt.Scale(domain=all_fates,range=all_colours_f)),
                    tooltip=["Zone","Fate","n"],
                ).properties(height=260,title="Fate by Zone"), use_container_width=True
            )
        with fb:
            pf2 = ev_f.dropna(subset=["platform","Fate"]).groupby(["platform","Fate"]).size().reset_index(name="n")
            st.altair_chart(
                alt.Chart(pf2).mark_bar().encode(
                    x=alt.X("n:Q",title="Cases"),
                    y=alt.Y("platform:N",title=None,sort="-x"),
                    color=alt.Color("Fate:N",title=None,legend=None,
                        scale=alt.Scale(domain=all_fates,range=all_colours_f)),
                    tooltip=["platform","Fate","n"],
                ).properties(height=340,title="Fate by Platform"), use_container_width=True
            )

    st.divider()
    st.markdown("""
    <div style="padding:12px 16px;background:#FFF7ED;border-radius:8px;
                border:1px solid #FED7AA;font-size:12px;color:#92400E">
    <strong>Retrospective view only.</strong> Every case is a documented historical event,
    independently verified against real, dated, named sources. FAM scores reflect structural
    position <em>before</em> annexation. This tool makes no predictions. See Appendix A
    of the accompanying paper for full methodology and limitations.
    </div>""", unsafe_allow_html=True)
    render_footer()


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 3 — MARKET DISCOURSE
# ═══════════════════════════════════════════════════════════════════════════════

@st.dialog("Discourse Analysis", width="large")
def show_discourse_detail(row):
    vstatus = str(row.get("verification_status") or "")
    vc      = {"contradicted":"#DC2626","inconclusive":"#D97706","confirmed":"#059669"}.get(vstatus,"#94A3B8")
    vdisp   = friendly_name("investor_verification_status", vstatus)
    funding = friendly_name("investor_funding_impact", row.get("verified_funding_impact"))
    vconf   = friendly_name("investor_confidence", row.get("verified_confidence"))

    st.markdown(f"""
    <div style="font-size:18px;font-weight:800;color:#1E293B;margin-bottom:2px">
      {row['platform']} · {row['annexation_event']}
    </div>
    <div style="font-size:11px;color:#94A3B8;margin-bottom:14px">{row['claim_id']}</div>
    <div style="display:flex;gap:10px;margin-bottom:16px;flex-wrap:wrap">
      <span style="padding:3px 10px;border-radius:20px;font-size:12px;font-weight:600;
                   background:{vc}22;color:{vc};border:1px solid {vc}44">{vdisp}</span>
      <span style="padding:3px 10px;border-radius:20px;font-size:12px;color:#475569;
                   background:#F1F5F9;border:1px solid #E2E8F0">{funding}</span>
      <span style="padding:3px 10px;border-radius:20px;font-size:12px;color:#94A3B8;
                   background:#F8FAFC;border:1px solid #E2E8F0">{vconf}</span>
    </div>""", unsafe_allow_html=True)

    for field, label, icon in [
        ("verified_reputation_signal",  "Reputation signal",  "📣"),
        ("verified_investor_learning",  "Investor learning",  "📚"),
        ("verified_entry_deterrence",   "Entry deterrence",   "🚧"),
    ]:
        val = row.get(field)
        if val and str(val).strip() and str(val).lower() not in ("none","nan","—"):
            st.markdown(f"**{icon} {label}**")
            st.markdown(f'<div style="font-size:13px;color:#475569;line-height:1.7;'
                        f'padding:10px 14px;background:#F8FAFC;border-radius:8px;'
                        f'border:1px solid #E2E8F0;margin-bottom:10px">{val}</div>',
                        unsafe_allow_html=True)
    if row.get("notes"):
        st.markdown("**📋 Verification notes**")
        st.markdown(f'<div style="font-size:12px;color:#64748B;line-height:1.7;'
                    f'padding:10px 14px;background:#F8FAFC;border-radius:8px;'
                    f'border:1px solid #E2E8F0">{row["notes"]}</div>',
                    unsafe_allow_html=True)


with tab_discourse:
    st.markdown("""
    <div style="padding:10px 14px;background:#F0FDF4;border-radius:8px;
                border:1px solid #86EFAC;font-size:12px;color:#166534;margin-bottom:12px">
    20 public investor and analyst claims examining the same annexation events from a different
    angle: did investors and analysts actually price annexation risk into their decisions?
    <br><br>
    The framework shows that the structural conditions were often readable in advance. This tab
    asks whether the people whose job it is to price risk \u2014 VCs, analysts, press \u2014
    treated annexation as a real signal or background noise. The finding is striking: even where
    structural readability was high, documented investor response is thin. Annexation risk was
    talked about more than it was acted on. That gap \u2014 between a readable structural signal
    and a market that did not price it \u2014 is arguably the most commercially actionable finding
    in this corpus.
    </div>""", unsafe_allow_html=True)

    claims_df = load_investor_claims()

    # Filters
    fc1, fc2 = st.columns([2,1], gap="medium")
    with fc1:
        search = st.text_input("Search platform or event",
                               placeholder="e.g. Google, Apple, funding\u2026",
                               key="discourse_search", label_visibility="collapsed")
    with fc2:
        vstatus_opts = ["All"] + sorted(claims_df["verification_status"].dropna().unique().tolist())
        vstatus_filter = st.selectbox("Status", vstatus_opts, key="discourse_vstatus",
                                      label_visibility="collapsed")

    filtered_claims = claims_df.copy()
    if search:
        mask = (
            filtered_claims["platform"].str.contains(search,case=False,na=False)
            | filtered_claims["annexation_event"].str.contains(search,case=False,na=False)
            | filtered_claims["notes"].fillna("").str.contains(search,case=False)
        )
        filtered_claims = filtered_claims[mask]
    if vstatus_filter != "All":
        filtered_claims = filtered_claims[filtered_claims["verification_status"]==vstatus_filter]

    st.caption(f"Showing {len(filtered_claims)} of 20 claims")

    # Card grid — 3 columns
    DISC_VSTATUS_COLOUR = {
        "contradicted": ("#DC2626","#FEE2E2"),
        "inconclusive": ("#D97706","#FEF3C7"),
        "confirmed":    ("#059669","#DCFCE7"),
    }
    dcols = st.columns(3, gap="small")
    for i, (_, row) in enumerate(filtered_claims.iterrows()):
        with dcols[i % 3]:
            vstatus = str(row.get("verification_status") or "")
            vdisp   = friendly_name("investor_verification_status", vstatus)
            tc, bg  = DISC_VSTATUS_COLOUR.get(vstatus, ("#94A3B8","#F1F5F9"))

            # Bubble up the most informative field
            key_finding = ""
            for f in ["verified_reputation_signal","verified_investor_learning","verified_entry_deterrence"]:
                val = row.get(f)
                if val and str(val).strip() and str(val).lower() not in ("none","nan","—"):
                    key_finding = str(val)[:160] + ("…" if len(str(val)) > 160 else "")
                    break

            st.markdown(f"""
            <div style="background:#FFFFFF;border:1px solid #E2E8F0;border-radius:12px;
                        padding:14px;margin-bottom:4px;min-height:160px">
              <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:8px">
                <div>
                  <div style="font-size:12px;font-weight:700;color:#1E293B">{row['platform']}</div>
                  <div style="font-size:11px;color:#64748B">{row['annexation_event']}</div>
                </div>
                <span style="font-size:10px;padding:2px 8px;border-radius:10px;font-weight:600;
                             background:{bg};color:{tc};white-space:nowrap">{vdisp}</span>
              </div>
              <div style="font-size:11px;color:#64748B;line-height:1.5;font-style:italic">
                {key_finding if key_finding else '<span style="color:#CBD5E1">No key finding recorded</span>'}
              </div>
            </div>""", unsafe_allow_html=True)

            if st.button("Read full analysis", key=f"disc_{row['claim_id']}",
                         use_container_width=True):
                show_discourse_detail(row)

    render_footer()


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 4 — ADMIN
# ═══════════════════════════════════════════════════════════════════════════════
with tab_admin:
    st.subheader("Run verification pipeline")
    st.caption("Shells out to pipeline scripts in this directory. Streams live output.")

    st.info(
        "**API key setup:**  \n"
        "Pipeline scripts require a provider API key.  \n"
        "\u2022 **Local / Codespace:** `export XAI_API_KEY=...` in your terminal before running Streamlit.  \n"
        "\u2022 **Render:** Add the key under *Environment \u2192 Add Environment Variable* in your service dashboard.  \n"
        "\u2022 **Streamlit Cloud:** Add to `.streamlit/secrets.toml` as `XAI_API_KEY = \"...\"`  \n"
        "The recommended provider is **grok** (`XAI_API_KEY`). "
        "Anthropic, OpenAI, and Gemini are also supported."
    )

    def _secret_available(env_var):
        try: return env_var in st.secrets
        except Exception: return False

    detected = [p for p,v in [
        ("grok","XAI_API_KEY"),("anthropic","ANTHROPIC_API_KEY"),
        ("openai","OPENAI_API_KEY"),("gemini","GOOGLE_API_KEY"),
    ] if os.environ.get(v) or _secret_available(v)]
    if detected:
        st.success(f"Keys detected for: {', '.join(detected)}")

    pipeline = st.selectbox("Pipeline",[
        "verify_events.py","verify_investor_claims.py","score_fam_dimensions.py",
    ])
    provider  = st.selectbox("Provider",["grok","anthropic","openai","gemini"],index=0)
    limit     = st.number_input("Limit (0 = no limit)",min_value=0,value=5,step=1)
    event_id  = st.number_input("Force specific event_id (0 = ignore)",min_value=0,value=0,step=1)
    verbose   = st.checkbox("Verbose logging")

    if st.button("\u25b6 Run", type="primary"):
        try:
            for ev_key in ["ANTHROPIC_API_KEY","OPENAI_API_KEY","GOOGLE_API_KEY","XAI_API_KEY"]:
                if ev_key in st.secrets: os.environ[ev_key] = st.secrets[ev_key]
        except Exception: pass
        cmd = [sys.executable, str(ROOT/pipeline),"--provider",provider]
        if limit > 0 and pipeline != "score_fam_dimensions.py":
            cmd += ["--limit",str(limit)]
        if event_id > 0:
            cmd += ["--event-id",str(event_id)]
        if verbose:
            cmd += ["--verbose"]
        st.code(" ".join(cmd))
        log_box,log_lines = st.empty(),[]
        proc = subprocess.Popen(cmd,cwd=ROOT,
            stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
            text=True,bufsize=1)
        for line in proc.stdout:
            log_lines.append(line.rstrip())
            log_box.code("\n".join(log_lines[-200:]),language="text")
        proc.wait()
        st.success(f"Finished \u2014 exit code {proc.returncode}")
        load_events.clear()
        load_investor_claims.clear()
        load_evidence_for_event.clear()

    st.divider()
    st.subheader("Corpus status")
    sv = load_events()
    c1,c2 = st.columns(2)
    with c1:
        st.markdown("**Fate distribution**")
        st.bar_chart(sv["category_outcome"].value_counts().rename(
            index=lambda x: FATE_LABELS.get(x,(humanise(x),""))[0]
        ))
    with c2:
        st.markdown("**Verification status**")
        st.bar_chart(sv["verification_status"].value_counts())
    render_footer()