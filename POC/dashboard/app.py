"""Scenario-Based Validation Dashboard

Entry point for the Streamlit app.
"""
import sys
from pathlib import Path

import streamlit as st

# Add src to path for imports
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

st.set_page_config(
    page_title="Scenario-Based Validation",
    page_icon="🚗",
    layout="wide",
    initial_sidebar_state="expanded",
)


def load_manifest():
    """Load results manifest."""
    import json

    path = ROOT / "outputs" / "manifest.json"

    if not path.exists():
        return []
    with open(path) as f:
        return json.load(f)


def outputs_dir() -> Path:
    """Base directory the manifest's relative paths resolve against."""
    return ROOT / "outputs"


def resolve_output(rel_path):
    """Resolve a manifest relative path (clip / keyframe) to an absolute file."""
    if not rel_path:
        return None
    p = outputs_dir() / rel_path
    return p if p.exists() else None


SIDEBAR_CSS = """
<style>
/* Sidebar container */
section[data-testid="stSidebar"] {
    background: #fafbfc;
    border-right: 1px solid #e8eaed;
}
section[data-testid="stSidebar"] > div {
    padding-top: 1.2rem;
}

/* Brand header */
.sb-brand {
    padding: 0.2rem 0.4rem 1rem 0.4rem;
}
.sb-logo {
    display: flex;
    align-items: center;
    gap: 0.55rem;
}
.sb-logo-mark {
    width: 6px;
    height: 26px;
    border-radius: 3px;
    background: #76b900;
    flex: 0 0 auto;
}
.sb-logo-text {
    font-size: 1.12rem;
    font-weight: 700;
    letter-spacing: 0.2px;
    color: #1a1d24;
    line-height: 1.1;
}
.sb-logo-text span {
    color: #76b900;
}
.sb-brand-sub {
    font-size: 0.78rem;
    color: #6b7280;
    margin: 0.4rem 0 0 0.05rem;
}

/* Section label */
.sb-section {
    font-size: 0.72rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 1px;
    color: #9aa1ad;
    margin: 0.6rem 0.4rem 0.4rem 0.4rem;
}

/* Divider */
.sb-divider {
    height: 1px;
    background: #e8eaed;
    border: none;
    margin: 0.6rem 0;
}

/* Navigation radio as nav items */
section[data-testid="stSidebar"] div[role="radiogroup"] {
    gap: 0.25rem;
}
section[data-testid="stSidebar"] div[role="radiogroup"] label {
    display: flex;
    align-items: center;
    padding: 0.55rem 0.75rem;
    border-radius: 8px;
    cursor: pointer;
    border-left: 3px solid transparent;
    transition: all 0.15s ease;
    color: #4b5563;
    font-size: 0.9rem;
    font-weight: 500;
}
 section[data-testid="stSidebar"] div[role="radiogroup"] label:hover {
    background: #f0f2f5;
    color: #1a1d24;
}
 section[data-testid="stSidebar"] div[role="radiogroup"] label:has(input:checked) {
    background: rgba(118, 185, 0, 0.10);
    border-left: 3px solid #76b900;
    color: #1a1d24;
    font-weight: 600;
}
/* Hide the default radio dot */
section[data-testid="stSidebar"] div[role="radiogroup"] label > div:first-child {
    display: none;
}
</style>
"""


def main():
    st.markdown(SIDEBAR_CSS, unsafe_allow_html=True)

    # Sidebar
    st.sidebar.markdown(
        '<div class="sb-brand">'
        '<div class="sb-logo">'
        '<div class="sb-logo-mark"></div>'
        '<div class="sb-logo-text">NVIDIA <span>Cosmos</span></div>'
        '</div>'
        '<p class="sb-brand-sub">World Foundation Models for ADAS validation</p>'
        '</div>',
        unsafe_allow_html=True,
    )
    st.sidebar.markdown('<hr class="sb-divider">', unsafe_allow_html=True)
    st.sidebar.markdown('<p class="sb-section">Navigation</p>', unsafe_allow_html=True)
    page = st.sidebar.radio(
        "Go to",
        ["Overview", "Clip Review", "Failure Gallery", "Export Report"],
        label_visibility="collapsed",
    )

    manifest = load_manifest()

    if page == "Overview":
        show_overview(manifest)
    elif page == "Clip Review":
        show_clips(manifest)
    elif page == "Failure Gallery":
        show_failures(manifest)
    else:
        show_export(manifest)


def show_overview(manifest):
    """Metrics and coverage heatmap."""
    import pandas as pd
    import plotly.express as px
    import plotly.graph_objects as go

    st.title("Scenario-Based Validation")
    st.markdown("Synthetic scenario generation and automated safety validation for ADAS.")
    st.markdown("---")

    # Top metrics
    total = len(manifest)
    failures = [m for m in manifest if not m["validation"]["verdict"]["hazard_detected_in_time"]
                or not m["validation"]["verdict"]["action_safe"]]
    passes = total - len(failures)
    avg_realism = sum(m["validation"]["realism_score"] for m in manifest) / total if total else 0
    failure_categories = {}
    for m in failures:
        cat = m["validation"]["verdict"].get("failure_category") or "unknown"
        failure_categories[cat] = failure_categories.get(cat, 0) + 1

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Scenarios", total)
    col2.metric("Passed", passes, delta=f"{100*passes/total:.0f}%" if total else "0%")
    col3.metric("Failures Found", len(failures), delta=f"{100*len(failures)/total:.0f}%" if total else "0%", delta_color="inverse")
    col4.metric("Avg Realism Score", f"{avg_realism:.2f}")

    st.markdown("---")

    # Coverage heatmap
    st.subheader("Coverage Heatmap: Weather vs Lighting")

    weather_vals = ["clear", "rain", "fog", "snow"]
    lighting_vals = ["day", "dusk", "night", "low_sun_glare", "tunnel_transition"]

    # Build matrix
    matrix = []
    for w in weather_vals:
        row = []
        for l in lighting_vals:
            count = sum(
                1 for m in manifest
                if m["scenario"]["weather"] == w and m["scenario"]["lighting"] == l
            )
            fail_count = sum(
                1 for m in manifest
                if m["scenario"]["weather"] == w and m["scenario"]["lighting"] == l
                and (not m["validation"]["verdict"]["hazard_detected_in_time"]
                     or not m["validation"]["verdict"]["action_safe"])
            )
            # Encode as failure rate (0 to 1), or -1 if no coverage
            if count == 0:
                row.append(-0.1)  # No coverage
            else:
                row.append(fail_count / count)
        matrix.append(row)

    fig = go.Figure(data=go.Heatmap(
        z=matrix,
        x=lighting_vals,
        y=weather_vals,
        colorscale=[
            [0, "#e8f5e9"],      # 0% failure - green
            [0.25, "#fff9c4"],   # 25% - yellow
            [0.5, "#ffcc80"],    # 50% - orange
            [0.75, "#ef9a9a"],   # 75% - red
            [1.0, "#c62828"],    # 100% - dark red
        ],
        zmin=0,
        zmax=1,
        text=[[f"{v*100:.0f}%" if v >= 0 else "No data" for v in row] for row in matrix],
        texttemplate="%{text}",
        textfont={"size": 12},
        hovertemplate="Weather: %{y}<br>Lighting: %{x}<br>Failure rate: %{text}<extra></extra>",
        colorbar=dict(title="Failure Rate", tickformat=".0%"),
    ))
    fig.update_layout(
        height=350,
        margin=dict(l=20, r=20, t=30, b=20),
        xaxis_title="Lighting",
        yaxis_title="Weather",
    )
    st.plotly_chart(fig, use_container_width=True)

    # Failure categories breakdown
    col_left, col_right = st.columns(2)

    with col_left:
        st.subheader("Failure Categories")
        if failure_categories:
            df_cat = pd.DataFrame([
                {"Category": k.replace("_", " ").title(), "Count": v}
                for k, v in failure_categories.items()
            ])
            fig_cat = px.pie(df_cat, names="Category", values="Count", hole=0.4,
                             color_discrete_sequence=px.colors.qualitative.Set2)
            fig_cat.update_layout(height=300, margin=dict(l=20, r=20, t=30, b=20))
            st.plotly_chart(fig_cat, use_container_width=True)
        else:
            st.info("No failures detected.")

    with col_right:
        st.subheader("Risk Score Distribution")
        risk_scores = [m["validation"]["verdict"]["risk_score"] for m in manifest]
        df_risk = pd.DataFrame({"Risk Score": risk_scores})
        fig_risk = px.histogram(df_risk, x="Risk Score", nbins=5, range_x=[0.5, 5.5],
                                 color_discrete_sequence=["#5C8A1B"])
        fig_risk.update_layout(
            height=300,
            margin=dict(l=20, r=20, t=30, b=20),
            xaxis=dict(tickmode="linear", tick0=1, dtick=1),
            yaxis_title="Count",
            bargap=0.1,
        )
        st.plotly_chart(fig_risk, use_container_width=True)

    # Results table
    st.markdown("---")
    st.subheader("All Scenarios")

    df = pd.DataFrame([
        {
            "Clip ID": m["clip_id"],
            "Weather": m["scenario"]["weather"],
            "Lighting": m["scenario"]["lighting"],
            "Actor": ", ".join(m["scenario"]["actors"]),
            "Behaviour": m["scenario"]["behaviour"].replace("_", " ").title(),
            "Pass": "Yes" if (m["validation"]["verdict"]["hazard_detected_in_time"]
                             and m["validation"]["verdict"]["action_safe"]) else "No",
            "Risk": m["validation"]["verdict"]["risk_score"],
            "Realism": f"{m['validation']['realism_score']:.2f}",
        }
        for m in manifest
    ])

    st.dataframe(
        df.style.applymap(
            lambda v: "background-color: #ffcdd2" if v == "No" else "",
            subset=["Pass"]
        ),
        use_container_width=True,
        height=400,
    )


def _verdict_badge(verdict):
    """Return a short pass/fail label and colour for a verdict."""
    ok = verdict.get("hazard_detected_in_time") and verdict.get("action_safe")
    return ("PASS", "#2e7d32") if ok else ("FAIL", "#c62828")


def render_clip_detail(entry):
    """Render one clip: video, YOLO feedback, and the judge verdict."""
    scenario = entry.get("scenario", {})
    val = entry.get("validation", {}) or {}
    verdict = val.get("verdict", {}) or {}
    sut = val.get("sut_summary", {}) or {}
    gen = entry.get("generation", {}) or {}

    label, color = _verdict_badge(verdict)
    st.markdown(
        f"<span style='background:{color};color:white;padding:2px 10px;"
        f"border-radius:4px;font-weight:600'>{label}</span>"
        f"&nbsp;&nbsp;<code>{entry.get('clip_id','')}</code>",
        unsafe_allow_html=True,
    )

    scen_line = " · ".join(
        str(scenario.get(k, "")) for k in ("weather", "lighting", "behaviour", "geometry") if scenario.get(k)
    )
    actors = ", ".join(scenario.get("actors", []))
    st.caption(f"{scen_line}  |  actors: {actors}")
    if gen.get("prompt"):
        st.caption(f"Generation prompt: {gen['prompt']}")

    model = str(gen.get("model", ""))
    is_preview = "preview" in model.lower() or "seed-transform" in model.lower()

    col_v, col_y = st.columns(2)

    with col_v:
        st.markdown("**Generated clip**")
        clip = resolve_output(val.get("clip_path"))
        if clip:
            st.video(str(clip))
        else:
            st.info("Clip not available.")
        if is_preview:
            st.warning(
                "Local preview: the seed footage has only a weather and lighting "
                "transform applied. The scenario actor described in the prompt "
                "(for example the pedestrian) is not present. Actors are "
                "synthesized only when Cosmos Predict runs on the GPU."
            )
        else:
            st.caption(f"Generated by: {model}")

    with col_y:
        st.markdown("**YOLO v8 (system under test)**")
        keyframe = resolve_output(val.get("yolo_keyframe"))
        if keyframe:
            st.image(str(keyframe), use_column_width=True, caption="Detections on a sample frame")
        counts = sut.get("class_counts", {})
        if counts:
            st.markdown(
                "Detected: "
                + ", ".join(f"{k} ({v})" for k, v in sorted(counts.items(), key=lambda x: -x[1]))
            )
        cols = st.columns(3)
        cols[0].metric("Action", str(sut.get("action", "n/a")))
        cols[1].metric("Hazards", sut.get("total_hazards", 0))
        df = sut.get("detection_frame")
        cols[2].metric("First hazard frame", "none" if df is None else df)

    st.markdown("**Cosmos Reason verdict**")
    v1, v2, v3, v4 = st.columns(4)
    v1.metric("Hazard in time", "Yes" if verdict.get("hazard_detected_in_time") else "No")
    v2.metric("Action safe", "Yes" if verdict.get("action_safe") else "No")
    cat = verdict.get("failure_category")
    v3.metric("Failure category", (cat or "none").replace("_", " ").title())
    v4.metric("Risk", f"{verdict.get('risk_score', '-')}/5")
    if verdict.get("rationale"):
        st.markdown(f"**Rationale:** {verdict['rationale']}")


def render_legend():
    """Explain every metric shown on the clip and failure pages."""
    with st.expander("What do these numbers mean? (legend)"):
        st.markdown(
            "**Generated clip** is produced by Cosmos Predict2.5 from a short seed "
            "window plus the scenario prompt. The caption under it shows the exact "
            "prompt used.\n\n"
            "**YOLO v8 (system under test)** is the perception model being validated. "
            "It runs on the generated frames."
        )
        st.markdown("**YOLO metrics**")
        st.markdown(
            "- **Detected: car (123), truck (67), person (8)**: total number of "
            "detections per class, summed across all sampled frames of the clip. "
            "It is not a count of unique objects. A car visible in 120 frames counts "
            "about 120 times, so the number shows how persistently each class appears.\n"
            "- **Action**: the driving decision. `brake` if a hazard appears early, "
            "`late_brake` if it appears only in the last 30% of the clip, `maintain` "
            "if no hazard is found.\n"
            "- **Hazards**: how many times a hazard-class object was detected across "
            "frames. Only `person`, `bicycle`, and `motorcycle` count as hazards. "
            "Cars and trucks do not.\n"
            "- **First hazard frame**: the frame index where a hazard first appeared."
        )
        st.markdown("**Cosmos Reason verdict (the judge grading the SUT)**")
        st.markdown(
            "- **Hazard in time**: did the SUT detect the hazard early enough to react "
            "safely? `No` means the detection was too late.\n"
            "- **Action safe**: was the chosen action (for example braking) appropriate?\n"
            "- **Failure category**: a label for the type of failure. `Unknown` means "
            "the judge flagged a problem but did not assign a named category.\n"
            "- **Risk**: severity from 1 (low) to 5 (high).\n"
            "- **Realism score**: 0 to 1, from frame-quality metrics on the generated "
            "clip (temporal consistency, sharpness, motion smoothness, lighting).\n"
            "- **Rationale**: the judge's written reasoning."
        )


def show_clips(manifest):
    """Per-clip review: video, YOLO feedback, judge verdict for every clip."""
    st.title("Clip Review")
    st.markdown("Each generated clip with its YOLO detections and the Cosmos Reason verdict.")
    render_legend()
    st.markdown("---")

    if not manifest:
        st.info("No clips found. Run scripts/run_demo.py to generate results.")
        return

    for i, entry in enumerate(manifest):
        render_clip_detail(entry)
        if i < len(manifest) - 1:
            st.markdown("---")


def show_failures(manifest):
    """Failure gallery with verdicts."""
    st.title("Failure Gallery")
    st.markdown("Review failure cases with automated judge verdicts.")
    render_legend()
    st.markdown("---")

    failures = [m for m in manifest if not m["validation"]["verdict"]["hazard_detected_in_time"]
                or not m["validation"]["verdict"]["action_safe"]]

    if not failures:
        st.success("No failures detected in this run.")
        return

    # Filter
    categories = list(set(m["validation"]["verdict"].get("failure_category", "unknown") for m in failures))
    selected_cat = st.selectbox("Filter by failure category", ["All"] + categories)

    if selected_cat != "All":
        failures = [m for m in failures if m["validation"]["verdict"].get("failure_category") == selected_cat]

    for m in failures:
        verdict = m["validation"]["verdict"]
        risk = verdict["risk_score"]
        risk_color = "#c62828" if risk >= 4 else "#ff9800" if risk >= 3 else "#ffc107"

        with st.expander(f"**{m['clip_id']}** | Risk: {risk}/5", expanded=False):
            col1, col2 = st.columns([1, 2])

            with col1:
                st.markdown("**Scenario**")
                st.markdown(f"- Weather: {m['scenario']['weather']}")
                st.markdown(f"- Lighting: {m['scenario']['lighting']}")
                st.markdown(f"- Actor: {', '.join(m['scenario']['actors'])}")
                st.markdown(f"- Behaviour: {m['scenario']['behaviour'].replace('_', ' ')}")
                st.markdown(f"- Geometry: {m['scenario']['geometry'].replace('_', ' ')}")
                st.markdown(f"- Realism score: {m['validation']['realism_score']:.2f}")

            with col2:
                st.markdown("**Judge Verdict**")
                st.markdown(f"- Hazard detected in time: {'Yes' if verdict['hazard_detected_in_time'] else 'No'}")
                st.markdown(f"- Action safe: {'Yes' if verdict['action_safe'] else 'No'}")
                st.markdown(f"- Failure category: **{(verdict.get('failure_category') or 'none').replace('_', ' ').title()}**")
                st.markdown(f"- Risk score: **{risk}/5**")
                st.markdown("---")
                st.markdown(f"**Rationale:** {verdict['rationale']}")

            # Generated clip and YOLO detections, when available
            val = m.get("validation", {}) or {}
            clip = resolve_output(val.get("clip_path"))
            keyframe = resolve_output(val.get("yolo_keyframe"))
            if clip or keyframe:
                mcol1, mcol2 = st.columns(2)
                with mcol1:
                    if clip:
                        st.markdown("**Generated clip**")
                        st.video(str(clip))
                        gen = m.get("generation", {}) or {}
                        if gen.get("prompt"):
                            st.caption(f"Generation: {gen['prompt']}")
                with mcol2:
                    if keyframe:
                        st.markdown("**YOLO detections**")
                        st.image(str(keyframe), use_column_width=True)
                        counts = (val.get("sut_summary") or {}).get("class_counts", {})
                        if counts:
                            st.caption(
                                "Detected: "
                                + ", ".join(f"{k} ({v})" for k, v in sorted(counts.items(), key=lambda x: -x[1]))
                            )
            else:
                st.info("No clip available for this scenario.")


def show_export(manifest):
    """Export validation report."""
    st.title("Export Validation Report")
    st.markdown("Generate a SOTIF / ISO 26262 aligned one-page validation summary.")
    st.markdown("---")

    total = len(manifest)
    failures = [m for m in manifest if not m["validation"]["verdict"]["hazard_detected_in_time"]
                or not m["validation"]["verdict"]["action_safe"]]

    st.markdown(f"**Total scenarios:** {total}")
    st.markdown(f"**Failures found:** {len(failures)}")
    st.markdown(f"**Pass rate:** {100 * (total - len(failures)) / total:.1f}%" if total else "N/A")

    st.markdown("---")

    st.markdown("### Report Preview")
    st.markdown("""
    **Scenario-Based Validation Report**

    | Metric | Value |
    |--------|-------|
    | Total scenarios generated | {} |
    | Scenarios passed | {} |
    | Scenarios failed | {} |
    | New failure modes discovered | {} |
    | Average realism score | {:.2f} |

    **Failure categories:**
    """.format(
        total,
        total - len(failures),
        len(failures),
        len(set(m["validation"]["verdict"].get("failure_category") for m in failures if m["validation"]["verdict"].get("failure_category"))),
        sum(m["validation"]["realism_score"] for m in manifest) / total if total else 0,
    ))

    cats = {}
    for m in failures:
        cat = m["validation"]["verdict"].get("failure_category") or "unknown"
        cats[cat] = cats.get(cat, 0) + 1
    for cat, count in cats.items():
        st.markdown(f"- {cat.replace('_', ' ').title()}: {count}")

    st.markdown("---")

    if st.button("Download PDF Report", type="primary"):
        st.info("PDF export is not implemented yet.")


if __name__ == "__main__":
    main()
