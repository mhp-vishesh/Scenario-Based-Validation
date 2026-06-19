"""Generate a professional architecture diagram for the Scenario-Based Validation POC."""
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch, Circle, Rectangle
from matplotlib.lines import Line2D
import numpy as np

# Set up the figure
fig, ax = plt.subplots(1, 1, figsize=(12, 16))
ax.set_xlim(0, 12)
ax.set_ylim(0, 16)
ax.axis('off')
ax.set_aspect('equal')

# Color palette - modern, professional
COLORS = {
    'primary': '#1e3a5f',      # Deep navy
    'cosmos': '#7c3aed',       # Purple for Cosmos
    'yolo': '#ea580c',         # Orange for YOLO
    'dashboard': '#2563eb',    # Blue for dashboard
    'report': '#dc2626',       # Red for report
    'accent': '#10b981',       # Green for success
    'data_bg': '#f1f5f9',      # Light gray for data boxes
    'data_border': '#64748b',  # Gray border
    'config_bg': '#fefce8',    # Light yellow for config
    'config_border': '#a16207',# Yellow border
    'text': '#1e293b',         # Dark text
    'muted': '#64748b',        # Muted text
    'white': '#ffffff',
    'line': '#94a3b8',         # Line color
}

def draw_stage_label(ax, y, number, label):
    """Draw stage number and label on the left."""
    # Number in a circle
    circle = Circle((1.2, y), 0.4, facecolor=COLORS['primary'], edgecolor='none', zorder=3)
    ax.add_patch(circle)
    ax.text(1.2, y, str(number), ha='center', va='center', 
            fontsize=14, fontweight='bold', color='white', zorder=4)
    # Label
    ax.text(1.9, y, label.upper(), ha='left', va='center',
            fontsize=11, fontweight='bold', color=COLORS['primary'], zorder=4)

def draw_process_box(ax, x, y, width, height, color, label, sublabel=None):
    """Draw a process box with rounded corners."""
    # Shadow
    shadow = FancyBboxPatch(
        (x + 0.06, y - 0.06), width, height,
        boxstyle="round,pad=0.02,rounding_size=0.12",
        facecolor='#00000012',
        edgecolor='none',
        zorder=1
    )
    ax.add_patch(shadow)
    
    # Main box
    box = FancyBboxPatch(
        (x, y), width, height,
        boxstyle="round,pad=0.02,rounding_size=0.12",
        facecolor=color,
        edgecolor='none',
        zorder=2
    )
    ax.add_patch(box)
    
    # Labels
    if sublabel:
        ax.text(x + width/2, y + height/2 + 0.15, label, ha='center', va='center',
                fontsize=12, fontweight='bold', color='white', zorder=3)
        ax.text(x + width/2, y + height/2 - 0.2, sublabel, ha='center', va='center',
                fontsize=9, color='white', alpha=0.9, zorder=3)
    else:
        ax.text(x + width/2, y + height/2, label, ha='center', va='center',
                fontsize=12, fontweight='bold', color='white', zorder=3)

def draw_data_box(ax, x, y, width, height, label, count=None):
    """Draw a data box."""
    box = FancyBboxPatch(
        (x, y), width, height,
        boxstyle="round,pad=0.02,rounding_size=0.08",
        facecolor=COLORS['data_bg'],
        edgecolor=COLORS['data_border'],
        linewidth=1.5,
        zorder=2
    )
    ax.add_patch(box)
    
    if count:
        ax.text(x + width/2, y + height/2 + 0.1, count, ha='center', va='center',
                fontsize=11, fontweight='bold', color=COLORS['primary'], zorder=3)
        ax.text(x + width/2, y + height/2 - 0.18, label, ha='center', va='center',
                fontsize=9, color=COLORS['text'], zorder=3)
    else:
        ax.text(x + width/2, y + height/2, label, ha='center', va='center',
                fontsize=10, fontweight='bold', color=COLORS['text'], zorder=3)

def draw_config_box(ax, x, y, label):
    """Draw a config file indicator."""
    width, height = 2.2, 0.5
    box = FancyBboxPatch(
        (x, y), width, height,
        boxstyle="round,pad=0.02,rounding_size=0.06",
        facecolor=COLORS['config_bg'],
        edgecolor=COLORS['config_border'],
        linewidth=1,
        linestyle='--',
        zorder=2
    )
    ax.add_patch(box)
    ax.text(x + width/2, y + height/2, label, ha='center', va='center',
            fontsize=8, color=COLORS['config_border'], family='monospace', zorder=3)

def draw_output_box(ax, x, y, title, lines):
    """Draw an output example box."""
    width, height = 2.4, 0.7
    box = FancyBboxPatch(
        (x, y), width, height,
        boxstyle="round,pad=0.02,rounding_size=0.06",
        facecolor='#fff7ed',
        edgecolor=COLORS['yolo'],
        linewidth=1,
        zorder=2
    )
    ax.add_patch(box)
    ax.text(x + width/2, y + height - 0.12, title, ha='center', va='top',
            fontsize=7, fontweight='bold', color=COLORS['yolo'], zorder=3)
    for i, line in enumerate(lines):
        ax.text(x + width/2, y + height - 0.32 - i*0.18, line, ha='center', va='top',
                fontsize=7, color=COLORS['text'], family='monospace', zorder=3)

def draw_arrow(ax, start, end, color=COLORS['line']):
    """Draw an arrow."""
    arrow = FancyArrowPatch(
        start, end,
        arrowstyle='-|>',
        mutation_scale=12,
        color=color,
        linewidth=2,
        zorder=1
    )
    ax.add_patch(arrow)

def draw_pill(ax, x, y, label, color):
    """Draw a small pill-shaped badge."""
    width, height = 0.9, 0.4
    box = FancyBboxPatch(
        (x, y), width, height,
        boxstyle="round,pad=0.02,rounding_size=0.2",
        facecolor=color,
        edgecolor='none',
        zorder=2
    )
    ax.add_patch(box)
    ax.text(x + width/2, y + height/2, label, ha='center', va='center',
            fontsize=8, fontweight='bold', color='white', zorder=3)

# ============== TITLE ==============
ax.text(6, 15.5, 'SCENARIO-BASED VALIDATION', ha='center', va='center',
        fontsize=18, fontweight='bold', color=COLORS['primary'])
ax.text(6, 15.1, 'Architecture Overview', ha='center', va='center',
        fontsize=11, color=COLORS['muted'])
ax.plot([3, 9], [14.85, 14.85], color=COLORS['line'], linewidth=1.5, alpha=0.5)

# Center X for main flow
cx = 6

# ============== STAGE 1: INPUT ==============
draw_stage_label(ax, 14, 1, 'Input')
draw_data_box(ax, cx - 1.3, 13.5, 2.6, 0.8, 'Seed Clips', '4-5')

# ============== STAGE 2: GENERATION ==============
draw_stage_label(ax, 12, 2, 'Generation')
draw_arrow(ax, (cx, 13.5), (cx, 12.6))
draw_process_box(ax, cx - 1.6, 11.5, 3.2, 1, COLORS['cosmos'], 'COSMOS', 'Transfer + Predict')
draw_config_box(ax, 8.5, 11.7, 'scenario_matrix.yaml')
# Dashed line to config
ax.plot([cx + 1.6, 8.5], [12, 12], color=COLORS['config_border'], linewidth=1, linestyle='--', alpha=0.7)

draw_arrow(ax, (cx, 11.5), (cx, 10.8))
draw_data_box(ax, cx - 1.3, 10, 2.6, 0.8, 'Generated Clips', '100+')

# Variation labels
variations = ['Rain', 'Fog', 'Night', 'Pedestrian', 'Occlusion']
start_x = cx - 2.4
for i, var in enumerate(variations):
    ax.text(start_x + i * 1.2, 9.65, var, ha='center', va='center',
            fontsize=7, color=COLORS['muted'], style='italic')

# ============== STAGE 3: DETECTION ==============
draw_stage_label(ax, 8.5, 3, 'Detection')
draw_arrow(ax, (cx, 10), (cx, 9.1))
draw_process_box(ax, cx - 1.6, 8, 3.2, 1, COLORS['yolo'], 'YOLO v8', 'Object Detection (SUT)')
draw_output_box(ax, 8.5, 8.05, 'Detection Output', ['"Person @ frame 15"', '"confidence: 0.87"'])
# Dashed line to output
ax.plot([cx + 1.6, 8.5], [8.5, 8.5], color=COLORS['yolo'], linewidth=1, linestyle=':', alpha=0.7)

# ============== STAGE 4: VALIDATION ==============
draw_stage_label(ax, 6.5, 4, 'Validation')
draw_arrow(ax, (cx, 8), (cx, 7.1))
draw_process_box(ax, cx - 1.6, 6, 3.2, 1, COLORS['cosmos'], 'COSMOS REASON', 'Automated Judge')
draw_config_box(ax, 8.5, 6.25, 'judge_rubric.yaml')
# Dashed line to config
ax.plot([cx + 1.6, 8.5], [6.5, 6.5], color=COLORS['config_border'], linewidth=1, linestyle='--', alpha=0.7)

draw_arrow(ax, (cx, 6), (cx, 5.5))

# Verdict box - no overlapping text
verdict_box = FancyBboxPatch(
    (cx - 1.3, 4.5), 2.6, 0.9,
    boxstyle="round,pad=0.02,rounding_size=0.08",
    facecolor=COLORS['data_bg'],
    edgecolor=COLORS['data_border'],
    linewidth=1.5,
    zorder=2
)
ax.add_patch(verdict_box)
ax.text(cx, 5.05, 'PASS / FAIL', ha='center', va='center',
        fontsize=11, fontweight='bold', color=COLORS['primary'])
ax.text(cx, 4.7, 'Verdict per Clip', ha='center', va='center',
        fontsize=8, color=COLORS['text'])

# Pass/Fail pills
draw_pill(ax, 8.5, 4.7, 'PASS', COLORS['accent'])
draw_pill(ax, 9.6, 4.7, 'FAIL', COLORS['report'])

# ============== STAGE 5: PRESENTATION ==============
draw_stage_label(ax, 2.0, 5, 'Presentation')

# Split arrows
draw_arrow(ax, (cx - 0.5, 4.5), (4.2, 3.5))
draw_arrow(ax, (cx + 0.5, 4.5), (7.8, 3.5))

# Dashboard - moved right to avoid overlap with stage label
draw_process_box(ax, 3.2, 2.2, 2.6, 1, COLORS['dashboard'], 'DASHBOARD', 'Streamlit')
# Report
draw_process_box(ax, 6.8, 2.2, 2.6, 1, COLORS['report'], 'PDF REPORT', 'Validation Summary')

# Feature lists - positioned below boxes
features_dash = ['• Coverage Heatmap', '• Failure Gallery', '• Metrics']
for i, feat in enumerate(features_dash):
    ax.text(4.5, 1.9 - i*0.25, feat, ha='center', va='center',
            fontsize=7, color=COLORS['muted'])

features_report = ['• One-page Summary', '• SOTIF Aligned', '• Exportable']
for i, feat in enumerate(features_report):
    ax.text(8.1, 1.9 - i*0.25, feat, ha='center', va='center',
            fontsize=7, color=COLORS['muted'])

# ============== LEGEND ==============
ax.plot([2, 10], [1.0, 1.0], color=COLORS['line'], linewidth=1, alpha=0.3)

legend_y = 0.5
ax.text(2.2, legend_y, 'LEGEND', ha='left', va='center',
        fontsize=8, fontweight='bold', color=COLORS['text'])

# Data flow arrow
ax.annotate('', xy=(4.2, legend_y), xytext=(3.5, legend_y),
            arrowprops=dict(arrowstyle='-|>', color=COLORS['line'], lw=1.5))
ax.text(4.4, legend_y, 'Data Flow', ha='left', va='center', fontsize=7, color=COLORS['muted'])

# Config line
ax.plot([5.8, 6.4], [legend_y, legend_y], color=COLORS['config_border'], linewidth=1.5, linestyle='--')
ax.text(6.6, legend_y, 'Config', ha='left', va='center', fontsize=7, color=COLORS['muted'])

# Cosmos
cosmos_leg = FancyBboxPatch((7.5, legend_y - 0.12), 0.3, 0.24,
    boxstyle="round,pad=0.01,rounding_size=0.05", facecolor=COLORS['cosmos'], edgecolor='none')
ax.add_patch(cosmos_leg)
ax.text(7.95, legend_y, 'Cosmos', ha='left', va='center', fontsize=7, color=COLORS['muted'])

# YOLO
yolo_leg = FancyBboxPatch((9, legend_y - 0.12), 0.3, 0.24,
    boxstyle="round,pad=0.01,rounding_size=0.05", facecolor=COLORS['yolo'], edgecolor='none')
ax.add_patch(yolo_leg)
ax.text(9.45, legend_y, 'YOLO', ha='left', va='center', fontsize=7, color=COLORS['muted'])

# Footer
ax.text(6, 0.1, 'MHP  ·  Scenario-Based Validation POC  ·  June 2026',
        ha='center', va='center', fontsize=8, color=COLORS['muted'])

plt.tight_layout()
plt.savefig('POC_Architecture.pdf', format='pdf', dpi=300, bbox_inches='tight',
            facecolor='white', edgecolor='none')
plt.savefig('POC_Architecture.png', format='png', dpi=300, bbox_inches='tight',
            facecolor='white', edgecolor='none')
print("Saved: POC_Architecture.pdf and POC_Architecture.png")
plt.show()
