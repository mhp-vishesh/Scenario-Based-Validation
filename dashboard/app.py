"""Scenario-Based Validation Dashboard

Entry point for the Streamlit app. Supports MOCK_MODE for local development.
"""
import os
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

MOCK_MODE = os.environ.get("MOCK_MODE", "0") == "1"


def load_manifest():
    """Load results manifest (mock or real)."""
    import json

    if MOCK_MODE:
        path = Path(__file__).parent / "mock_data" / "manifest.json"
    else:
        path = ROOT / "outputs" / "manifest.json"

    if not path.exists():
        return []
    with open(path) as f:
        return json.load(f)


def main():
    # Sidebar
    st.sidebar.image(str(ROOT / "assets" / "poc_plan_diagram.png"), use_container_width=True)
    st.sidebar.markdown("---")
    st.sidebar.markdown("### Navigation")
    page = st.sidebar.radio(
        "Go to",
        ["Overview", "Failure Gallery", "Export Report"],
        label_visibility="collapsed",
    )

    if MOCK_MODE:
        st.sidebar.warning("Running in MOCK MODE (no GPU)")

    manifest = load_manifest()

    if page == "Overview":
        show_overview(manifest)
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


def show_failures(manifest):
    """Failure gallery with verdicts."""
    st.title("Failure Gallery")
    st.markdown("Review failure cases with automated judge verdicts.")
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
                st.markdown(f"- Failure category: **{verdict.get('failure_category', 'N/A').replace('_', ' ').title()}**")
                st.markdown(f"- Risk score: **{risk}/5**")
                st.markdown("---")
                st.markdown(f"**Rationale:** {verdict['rationale']}")

            # Placeholder for video
            st.info("Video playback would appear here (clip not available in mock mode)")


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
        st.info("PDF export would be generated here (not implemented in mock mode)")


if __name__ == "__main__":
    main()
