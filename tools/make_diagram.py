"""Render a clean, presentation-ready diagram of the POC plan.

Output: assets/poc_plan_diagram.png (high resolution, 16:9).
"""
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.font_manager as fm
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

# ---------------------------------------------------------------- palette
NAVY = "#1F2A44"
INK = "#2B3447"
MUTE = "#5B6577"
LINE = "#D6DBE3"
CARD = "#FFFFFF"
CANVAS = "#FFFFFF"
BAND = "#F4F6F9"

PHASE = [
    {"key": "P1", "title": "1  Provision & Store", "accent": "#3B5275"},
    {"key": "P2", "title": "2  Generate Scenarios", "accent": "#5C8A1B"},
    {"key": "P3", "title": "3  Validate", "accent": "#2C6E7F"},
    {"key": "P4", "title": "4  Present", "accent": "#B5852A"},
]

# pick a clean sans serif if available
for cand in ("Helvetica Neue", "Helvetica", "Arial", "DejaVu Sans"):
    if any(cand == f.name for f in fm.fontManager.ttflist):
        plt.rcParams["font.family"] = cand
        break

fig, ax = plt.subplots(figsize=(14.0, 7.875), dpi=220)
fig.patch.set_facecolor(CANVAS)
ax.set_xlim(0, 100)
ax.set_ylim(0, 100)
ax.axis("off")


def rounded(x, y, w, h, fc, ec, lw=1.0, rad=0.025, z=2):
    p = FancyBboxPatch(
        (x, y),
        w,
        h,
        boxstyle=f"round,pad=0,rounding_size={rad*100}",
        mutation_aspect=h / w if w else 1,
        facecolor=fc,
        edgecolor=ec,
        linewidth=lw,
        zorder=z,
    )
    ax.add_patch(p)
    return p


def card(x, y, w, h, title, sub, accent):
    # subtle shadow
    rounded(x + 0.35, y - 0.5, w, h, "#E9ECF1", "#E9ECF1", lw=0, rad=0.03, z=1)
    rounded(x, y, w, h, CARD, LINE, lw=1.1, rad=0.03, z=2)
    # accent bar on the left (clean thin tab)
    ax.add_patch(
        plt.Rectangle(
            (x + 0.55, y + 0.9),
            0.55,
            h - 1.8,
            facecolor=accent,
            edgecolor=accent,
            zorder=3,
        )
    )
    ax.text(
        x + 2.0,
        y + h - 1.7,
        title,
        fontsize=10.2,
        color=INK,
        fontweight="bold",
        va="top",
        ha="left",
        zorder=4,
    )
    ax.text(
        x + 2.0,
        y + h - 4.0,
        sub,
        fontsize=8.1,
        color=MUTE,
        va="top",
        ha="left",
        zorder=4,
    )


def arrow(x1, y1, x2, y2, color=NAVY, lw=1.8, style="-|>", dashed=False, rad=0.0):
    a = FancyArrowPatch(
        (x1, y1),
        (x2, y2),
        arrowstyle=style,
        mutation_scale=13,
        linewidth=lw,
        color=color,
        connectionstyle=f"arc3,rad={rad}",
        linestyle="--" if dashed else "-",
        zorder=5,
    )
    ax.add_patch(a)


# ---------------------------------------------------------------- title
ax.text(2.5, 96.5, "Scenario-Based Validation POC", fontsize=20, color=NAVY, fontweight="bold", va="top")
ax.text(2.5, 91.6, "NVIDIA Cosmos on AWS  |  closed-loop synthetic scenario generation and automated safety validation",
        fontsize=10.5, color=MUTE, va="top")
ax.plot([2.5, 97.5], [89.2, 89.2], color=LINE, lw=1.2)

# ---------------------------------------------------------------- phase bands
band_top, band_bot = 86.5, 39.0
xs = [2.5, 26.5, 50.5, 74.5]
bw = 23.0
for i, ph in enumerate(PHASE):
    x = xs[i]
    rounded(x, band_bot, bw, band_top - band_bot, BAND, BAND, lw=0, rad=0.015, z=0)
    # header chip
    rounded(x, band_top - 4.2, bw, 4.2, ph["accent"], ph["accent"], lw=0, rad=0.03, z=2)
    ax.text(x + bw / 2, band_top - 2.1, ph["title"], color="white", fontsize=11.5,
            fontweight="bold", ha="center", va="center", zorder=3)

# ---------------------------------------------------------------- cards
ch = 8.6  # card height
gap = 1.6
cw = bw - 3.0


def col_cards(x, items, accent, top=80.5):
    y = top
    centers = []
    for title, sub in items:
        card(x + 1.5, y - ch, cw, ch, title, sub, accent)
        centers.append((x + 1.5, y - ch, cw, ch))
        y -= ch + gap
    return centers


c1 = col_cards(xs[0], [
    ("AWS GPU Instances", "p5 / p4d  |  H100 / A100 80GB"),
    ("NVIDIA AI Enterprise", "NGC key, AI Enterprise AMI"),
    ("S3 + Run Manifest", "seeds, configs, outputs, seeds logged"),
    ("Seed Clips", "real + simulated, one ODD slice"),
], PHASE[0]["accent"])

c2 = col_cards(xs[1], [
    ("Cosmos Curator", "filter, annotate, deduplicate"),
    ("Scenario Matrix", "weather, light, actors, behaviour"),
    ("Cosmos Transfer + Predict", "controlled edge-case generation"),
], PHASE[1]["accent"], top=74.0)

c3 = col_cards(xs[2], [
    ("System Under Test", "open detector or planner"),
    ("Cosmos Reason (Judge)", "structured pass / fail + rationale"),
    ("Cosmos Evaluator", "realism scoring of clips"),
], PHASE[2]["accent"], top=74.0)

c4 = col_cards(xs[3], [
    ("Streamlit Dashboard", "coverage heatmap, metrics"),
    ("Failure Gallery", "clip, model output, verdict"),
    ("SOTIF / ISO 26262 Report", "auditable one-page export"),
], PHASE[3]["accent"], top=74.0)

# ---------------------------------------------------------------- flow arrows between phases
midy = 60.0
for a, b in zip(xs[:-1], xs[1:]):
    arrow(a + bw + 0.0, midy, b + 1.4, midy, color=NAVY, lw=2.0)

# feedback loop (close the loop) routed below the bands
arrow(xs[3] + bw / 2, 37.0, xs[1] + bw / 2, 37.0, color="#B5852A", lw=1.7, dashed=True, rad=-0.42)
ax.text((xs[1] + xs[3] + bw) / 2, 32.5, "close the loop  \u00b7  feed new failures back into the scenario matrix",
        fontsize=8.6, color="#9A6F1F", ha="center", va="center", style="italic", zorder=6)

# ---------------------------------------------------------------- infra ribbon
rib_y, rib_h = 11.0, 7.0
rounded(2.5, rib_y, 95.0, rib_h, NAVY, NAVY, lw=0, rad=0.03, z=2)
ax.text(5.0, rib_y + rib_h / 2, "INFRASTRUCTURE", color="#9FB0C9", fontsize=8.5,
        fontweight="bold", va="center", ha="left", zorder=3)
infra = "AWS  ·  NVIDIA AI Enterprise  ·  NGC containers  ·  H100 / A100 GPUs  ·  EBS + S3  ·  Docker / NVIDIA Container Toolkit"
ax.text(50.5, rib_y + rib_h / 2, infra, color="white", fontsize=9.6, va="center", ha="center", zorder=3)

# footer
ax.text(2.5, 6.5, "Outcome: from a handful of seed clips, generate hundreds of safety-relevant scenarios, surface failure modes the fleet never hit, and produce an auditable validation report.",
        fontsize=8.6, color=MUTE, va="top", ha="left")
ax.plot([2.5, 97.5], [8.7, 8.7], color=LINE, lw=1.0)

out = Path(__file__).resolve().parents[1] / "assets" / "poc_plan_diagram.png"
out.parent.mkdir(parents=True, exist_ok=True)
fig.savefig(out, dpi=220, bbox_inches="tight", facecolor=CANVAS, pad_inches=0.25)
print("wrote", out)
