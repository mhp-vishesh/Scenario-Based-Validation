#!/usr/bin/env python3
"""Export validation results to PDF or CSV reports.

Usage:
    python scripts/export_report.py --manifest outputs/manifest.json --format pdf --output report.pdf
"""
import argparse
import csv
import json
import os
import sys
from datetime import datetime
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from manifest import Manifest
from utils import ensure_dir, logger


def parse_args():
    parser = argparse.ArgumentParser(description="Export validation report")
    parser.add_argument("--manifest", required=True, help="Path to manifest file")
    parser.add_argument("--format", choices=["pdf", "csv", "json"], default="pdf", help="Report format")
    parser.add_argument("--output", help="Output file path (default: report.<format>)")
    parser.add_argument("--include-passing", action="store_true", help="Include passing scenarios")
    parser.add_argument("--clips-dir", help="Path to clips for thumbnail extraction")
    return parser.parse_args()


def export_csv(manifest: Manifest, output_path: str, include_passing: bool):
    """Export results as CSV."""
    entries = manifest.entries
    if not include_passing:
        entries = [e for e in entries if e.get("validation", {}).get("verdict") == "fail"]
    
    with open(output_path, "w", newline="") as f:
        writer = csv.writer(f)
        
        # Header
        writer.writerow([
            "Clip ID",
            "Seed",
            "Weather",
            "Lighting",
            "Actors",
            "Behaviour",
            "Geometry",
            "Verdict",
            "Risk Score",
            "Failure Category",
            "Realism Score",
            "Rationale",
        ])
        
        # Data rows
        for entry in entries:
            scenario = entry.get("scenario", {})
            validation = entry.get("validation", {})
            
            writer.writerow([
                entry.get("clip_id", ""),
                entry.get("seed_id", ""),
                scenario.get("weather", ""),
                scenario.get("lighting", ""),
                ", ".join(scenario.get("actors", [])),
                scenario.get("behaviour", ""),
                scenario.get("geometry", ""),
                validation.get("verdict", ""),
                validation.get("risk_score", ""),
                validation.get("failure_category", ""),
                validation.get("realism_score", ""),
                validation.get("rationale", ""),
            ])
    
    logger.info(f"Exported {len(entries)} entries to {output_path}")


def export_json(manifest: Manifest, output_path: str, include_passing: bool):
    """Export results as JSON."""
    entries = manifest.entries
    if not include_passing:
        entries = [e for e in entries if e.get("validation", {}).get("verdict") == "fail"]
    
    stats = manifest.get_statistics()
    
    report = {
        "generated": datetime.now().isoformat(),
        "summary": {
            "total_scenarios": stats["total"],
            "validated": stats["validated"],
            "failures": stats["failures"],
            "pass_rate": stats["pass_rate"],
            "average_realism_score": stats["average_realism_score"],
            "failure_categories": stats["failure_categories"],
        },
        "entries": entries,
    }
    
    with open(output_path, "w") as f:
        json.dump(report, f, indent=2, default=str)
    
    logger.info(f"Exported {len(entries)} entries to {output_path}")


def export_pdf(manifest: Manifest, output_path: str, include_passing: bool, clips_dir: str = None):
    """Export results as PDF report."""
    try:
        from reportlab.lib.pagesizes import letter, A4
        from reportlab.lib import colors
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.platypus import (
            SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, Image
        )
        from reportlab.lib.units import inch
    except ImportError:
        logger.error("reportlab not installed. Install with: pip install reportlab")
        sys.exit(1)
    
    entries = manifest.entries
    if not include_passing:
        entries = [e for e in entries if e.get("validation", {}).get("verdict") == "fail"]
    
    stats = manifest.get_statistics()
    
    # Create PDF
    doc = SimpleDocTemplate(output_path, pagesize=letter)
    styles = getSampleStyleSheet()
    story = []
    
    # Title
    title_style = ParagraphStyle(
        "CustomTitle",
        parent=styles["Heading1"],
        fontSize=24,
        spaceAfter=30,
    )
    story.append(Paragraph("Scenario-Based Validation Report", title_style))
    story.append(Spacer(1, 12))
    
    # Metadata
    meta_style = styles["Normal"]
    story.append(Paragraph(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", meta_style))
    story.append(Spacer(1, 24))
    
    # Summary section
    story.append(Paragraph("Executive Summary", styles["Heading2"]))
    story.append(Spacer(1, 12))
    
    summary_data = [
        ["Metric", "Value"],
        ["Total Scenarios", str(stats["total"])],
        ["Validated", str(stats["validated"])],
        ["Failures Detected", str(stats["failures"])],
        ["Pass Rate", f"{stats['pass_rate']*100:.1f}%"],
        ["Average Realism Score", f"{stats['average_realism_score']:.3f}"],
    ]
    
    summary_table = Table(summary_data, colWidths=[2.5*inch, 2*inch])
    summary_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.grey),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 12),
        ("BACKGROUND", (0, 1), (-1, -1), colors.beige),
        ("GRID", (0, 0), (-1, -1), 1, colors.black),
    ]))
    story.append(summary_table)
    story.append(Spacer(1, 24))
    
    # Failure categories
    if stats["failure_categories"]:
        story.append(Paragraph("Failure Categories", styles["Heading2"]))
        story.append(Spacer(1, 12))
        
        cat_data = [["Category", "Count"]]
        for cat, count in sorted(stats["failure_categories"].items(), key=lambda x: -x[1]):
            cat_data.append([cat, str(count)])
        
        cat_table = Table(cat_data, colWidths=[3*inch, 1*inch])
        cat_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.grey),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
            ("ALIGN", (0, 0), (-1, -1), "LEFT"),
            ("ALIGN", (1, 0), (1, -1), "CENTER"),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("GRID", (0, 0), (-1, -1), 1, colors.black),
        ]))
        story.append(cat_table)
        story.append(PageBreak())
    
    # Detailed failures
    if entries:
        story.append(Paragraph("Detailed Failure Analysis", styles["Heading2"]))
        story.append(Spacer(1, 12))
        
        for entry in entries[:50]:  # Limit to first 50 for PDF size
            clip_id = entry.get("clip_id", "Unknown")
            scenario = entry.get("scenario", {})
            validation = entry.get("validation", {})
            
            # Entry header
            story.append(Paragraph(f"Clip: {clip_id}", styles["Heading3"]))
            
            # Scenario details
            scenario_text = (
                f"Weather: {scenario.get('weather', 'N/A')} | "
                f"Lighting: {scenario.get('lighting', 'N/A')} | "
                f"Actors: {', '.join(scenario.get('actors', []))} | "
                f"Behaviour: {scenario.get('behaviour', 'N/A')}"
            )
            story.append(Paragraph(scenario_text, meta_style))
            
            # Validation results
            val_text = (
                f"Risk Score: {validation.get('risk_score', 'N/A')} | "
                f"Category: {validation.get('failure_category', 'N/A')} | "
                f"Realism: {validation.get('realism_score', 'N/A')}"
            )
            story.append(Paragraph(val_text, meta_style))
            
            # Rationale
            rationale = validation.get("rationale", "No rationale provided.")
            story.append(Paragraph(f"Rationale: {rationale}", styles["Italic"]))
            
            story.append(Spacer(1, 18))
        
        if len(entries) > 50:
            story.append(Paragraph(
                f"... and {len(entries) - 50} more failures (see CSV export for complete list)",
                styles["Italic"]
            ))
    
    # Build PDF
    doc.build(story)
    logger.info(f"Exported PDF report to {output_path}")


def main():
    args = parse_args()
    
    # Load manifest
    manifest = Manifest(args.manifest)
    logger.info(f"Loaded manifest with {len(manifest.entries)} entries")
    
    # Determine output path
    output_path = args.output or f"report.{args.format}"
    ensure_dir(Path(output_path).parent)
    
    # Export
    if args.format == "csv":
        export_csv(manifest, output_path, args.include_passing)
    elif args.format == "json":
        export_json(manifest, output_path, args.include_passing)
    else:
        export_pdf(manifest, output_path, args.include_passing, args.clips_dir)
    
    logger.info("Report export complete")


if __name__ == "__main__":
    main()
