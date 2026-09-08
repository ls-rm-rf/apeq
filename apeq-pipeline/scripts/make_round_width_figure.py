#!/usr/bin/env python3
"""Generate the formal online-latency-sensitivity versus input-width figure."""

import argparse
import csv
from pathlib import Path

from reportlab.lib import colors
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas


WIDTHS = [8, 16, 24, 32, 48, 64]

SERIES = [
    ("apeq", "ole", "APEQ (OLE)"),
    ("apeq", "vole_hash", "APEQ (VOLE)"),
    ("lu_eq", "n/a", "Lu et al."),
    ("emp_eq", "n/a", "EMP-Yao"),
    ("aby_eq", "yao", "ABY-Yao"),
    ("aby_eq", "gmw", "ABY-GMW"),
    ("cryptflow2_eq", "n/a", "CrypTFlow2"),
    ("volepsi_eq", "n/a", "VOLE-PSI"),
]

STYLE = {
    ("apeq", "ole"): ("#1B4965", "circle", []),
    ("apeq", "vole_hash"): ("#4C9FD1", "square", []),
    ("lu_eq", "n/a"): ("#6A4C93", "x", [5, 2, 1.5, 2]),
    ("emp_eq", "n/a"): ("#9E2A2B", "triangle_up", [5, 3]),
    ("aby_eq", "yao"): ("#D69E2E", "triangle_down", [5, 3]),
    ("aby_eq", "gmw"): ("#E76F51", "triangle_left", [1.5, 2.5]),
    ("cryptflow2_eq", "n/a"): ("#6B1D1D", "diamond", [5, 2, 1.5, 2]),
    ("volepsi_eq", "n/a"): ("#177E73", "plus", [1.5, 2.5]),
}

CONSTANT_GROUP = [
    ("apeq", "vole_hash"),
    ("lu_eq", "n/a"),
    ("volepsi_eq", "n/a"),
]

FONT_REGULAR = "Times-Roman"
FONT_BOLD = "Times-Bold"


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("input_csv", type=Path)
    parser.add_argument("output_pdf", type=Path)
    return parser.parse_args()


def load_and_validate(path):
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))

    if len(rows) != len(SERIES) * len(WIDTHS):
        raise ValueError(f"expected 48 rows, found {len(rows)}")

    data = {}
    quality = []
    for protocol, variant, _ in SERIES:
        selected = [
            row for row in rows
            if row["protocol"] == protocol and row["variant"] == variant
        ]
        widths = sorted(int(row["input_bits"]) for row in selected)
        if widths != WIDTHS:
            raise ValueError(f"{protocol}/{variant}: widths are {widths}, expected {WIDTHS}")
        if {int(row["n_rtt"]) for row in selected} != {6}:
            raise ValueError(f"{protocol}/{variant}: expected six RTT levels")
        if {int(row["n_runs"]) for row in selected} != {60}:
            raise ValueError(f"{protocol}/{variant}: expected 60 runs per fit")

        ordered = sorted(selected, key=lambda row: int(row["input_bits"]))
        data[(protocol, variant)] = [float(row["online_rounds"]) for row in ordered]
        quality.extend(float(row["online_r2"]) for row in ordered)

    return data, min(quality)


def draw_marker(pdf, x, y, marker, color, size=3.0, hollow=False):
    pdf.saveState()
    pdf.setStrokeColor(color)
    pdf.setFillColor(colors.white if hollow else color)
    pdf.setLineWidth(0.8)
    if marker == "circle":
        pdf.circle(x, y, size, stroke=1, fill=1)
    elif marker == "square":
        pdf.rect(x - size, y - size, 2 * size, 2 * size, stroke=1, fill=1)
    elif marker == "x":
        pdf.line(x - size, y - size, x + size, y + size)
        pdf.line(x - size, y + size, x + size, y - size)
    elif marker == "triangle_up":
        path = pdf.beginPath()
        path.moveTo(x, y + size)
        path.lineTo(x - size, y - size)
        path.lineTo(x + size, y - size)
        path.close()
        pdf.drawPath(path, stroke=1, fill=1)
    elif marker == "triangle_down":
        path = pdf.beginPath()
        path.moveTo(x, y - size)
        path.lineTo(x - size, y + size)
        path.lineTo(x + size, y + size)
        path.close()
        pdf.drawPath(path, stroke=1, fill=1)
    elif marker == "triangle_left":
        path = pdf.beginPath()
        path.moveTo(x - size, y)
        path.lineTo(x + size, y + size)
        path.lineTo(x + size, y - size)
        path.close()
        pdf.drawPath(path, stroke=1, fill=1)
    elif marker == "diamond":
        path = pdf.beginPath()
        path.moveTo(x, y + size)
        path.lineTo(x - size, y)
        path.lineTo(x, y - size)
        path.lineTo(x + size, y)
        path.close()
        pdf.drawPath(path, stroke=1, fill=1)
    elif marker == "plus":
        pdf.setLineWidth(1.25)
        pdf.line(x - size, y, x + size, y)
        pdf.line(x, y - size, x, y + size)
    pdf.restoreState()


def draw_polyline(pdf, points, color, dash, width=1.45):
    pdf.saveState()
    pdf.setStrokeColor(color)
    pdf.setLineWidth(width)
    pdf.setLineJoin(1)
    pdf.setLineCap(1)
    pdf.setDash(dash)
    path = pdf.beginPath()
    path.moveTo(*points[0])
    for point in points[1:]:
        path.lineTo(*point)
    pdf.drawPath(path, stroke=1, fill=0)
    pdf.restoreState()


def draw_centered(pdf, text, x, y, font=FONT_REGULAR, size=8):
    pdf.setFont(font, size)
    pdf.drawString(x - stringWidth(text, font, size) / 2, y, text)


def plot(data, min_r2, output_path):
    page_w, page_h = 576, 310
    plot_x0, plot_y0 = 61, 52
    plot_x1, plot_y1 = 425, 282
    y_max = 7.25

    def x_pos(value):
        return plot_x0 + (value - 6) / 60 * (plot_x1 - plot_x0)

    def y_pos(value):
        return plot_y0 + value / y_max * (plot_y1 - plot_y0)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    pdf = canvas.Canvas(str(output_path), pagesize=(page_w, page_h), pageCompression=1)
    pdf.setTitle("Online latency sensitivity versus input width")
    pdf.setSubject("APEQ and equality-protocol RTT-sweep measurements")
    pdf.setCreator("APEQ evaluation pipeline")

    for tick in range(0, 8):
        y = y_pos(tick)
        pdf.setStrokeColor(colors.HexColor("#D6DEE8"))
        pdf.setLineWidth(0.45)
        pdf.line(plot_x0, y, plot_x1, y)
        pdf.setFillColor(colors.HexColor("#263746"))
        pdf.setFont(FONT_REGULAR, 8.2)
        pdf.drawRightString(plot_x0 - 7, y - 2.7, str(tick))

    for width in WIDTHS:
        x = x_pos(width)
        pdf.setStrokeColor(colors.HexColor("#E8EDF2"))
        pdf.setLineWidth(0.35)
        pdf.line(x, plot_y0, x, plot_y1)
        pdf.setFillColor(colors.HexColor("#263746"))
        draw_centered(pdf, str(width), x, plot_y0 - 14, size=8.2)

    pdf.setStrokeColor(colors.HexColor("#475569"))
    pdf.setLineWidth(0.8)
    pdf.line(plot_x0, plot_y0, plot_x1, plot_y0)
    pdf.line(plot_x0, plot_y0, plot_x0, plot_y1)

    # Curves use the measured coordinates directly; no display jitter is applied.
    for protocol, variant, label in SERIES:
        key = (protocol, variant)
        color_hex, marker, dash = STYLE[key]
        color = colors.HexColor(color_hex)
        points = [(x_pos(width), y_pos(value)) for width, value in zip(WIDTHS, data[key])]
        draw_polyline(pdf, points, color, dash, width=1.75 if protocol == "apeq" else 1.35)
        hollow = label in {"Lu et al.", "VOLE-PSI"}
        for x, y in points:
            draw_marker(pdf, x, y, marker, color, size=3.15, hollow=hollow)

    draw_centered(pdf, "Input width (bits)", (plot_x0 + plot_x1) / 2, 17, FONT_REGULAR, 10)
    pdf.saveState()
    pdf.translate(17, (plot_y0 + plot_y1) / 2)
    pdf.rotate(90)
    draw_centered(pdf, "Online latency sensitivity (effective RTTs)", 0, 0, FONT_REGULAR, 10)
    pdf.restoreState()

    legend_x, legend_y = 442, 272
    for protocol, variant, label in SERIES:
        key = (protocol, variant)
        color_hex, marker, dash = STYLE[key]
        color = colors.HexColor(color_hex)
        draw_polyline(pdf, [(legend_x, legend_y), (legend_x + 23, legend_y)], color, dash,
                      width=1.75 if protocol == "apeq" else 1.35)
        draw_marker(pdf, legend_x + 11.5, legend_y, marker, color, size=2.8,
                    hollow=label in {"Lu et al.", "VOLE-PSI"})
        pdf.setFillColor(colors.HexColor("#1F2937"))
        pdf.setFont(FONT_REGULAR, 8.5)
        pdf.drawString(legend_x + 30, legend_y - 3, label)
        legend_y -= 15.2

    # A true-coordinate inset resolves the three nearly coincident constant-slope curves.
    inset_x0, inset_y0 = 442, 74
    inset_x1, inset_y1 = 565, 138
    inset_min, inset_max = 2.002, 2.018

    def inset_x(value):
        return inset_x0 + (value - 6) / 60 * (inset_x1 - inset_x0)

    def inset_y(value):
        return inset_y0 + (value - inset_min) / (inset_max - inset_min) * (inset_y1 - inset_y0)

    pdf.setFillColor(colors.white)
    pdf.setStrokeColor(colors.HexColor("#64748B"))
    pdf.setLineWidth(0.65)
    pdf.rect(inset_x0, inset_y0, inset_x1 - inset_x0, inset_y1 - inset_y0, stroke=1, fill=1)
    for value in (2.005, 2.010, 2.015):
        y = inset_y(value)
        pdf.setStrokeColor(colors.HexColor("#DEE5EC"))
        pdf.setLineWidth(0.35)
        pdf.line(inset_x0, y, inset_x1, y)
        pdf.setFillColor(colors.HexColor("#475569"))
        pdf.setFont(FONT_REGULAR, 5.8)
        pdf.drawRightString(inset_x0 - 3, y - 1.8, f"{value:.3f}")
    for width in (8, 32, 64):
        pdf.setFillColor(colors.HexColor("#475569"))
        draw_centered(pdf, str(width), inset_x(width), inset_y0 - 8, size=5.8)

    for key in CONSTANT_GROUP:
        color_hex, marker, dash = STYLE[key]
        color = colors.HexColor(color_hex)
        points = [(inset_x(width), inset_y(value)) for width, value in zip(WIDTHS, data[key])]
        draw_polyline(pdf, points, color, dash, width=0.9)
        for x, y in points:
            draw_marker(pdf, x, y, marker, color, size=1.65,
                        hollow=key != ("apeq", "vole_hash"))

    pdf.setFillColor(colors.HexColor("#334155"))
    draw_centered(pdf, "Zoom: three near-2.01 curves", (inset_x0 + inset_x1) / 2,
                  inset_y1 + 5, FONT_BOLD, 6.8)

    pdf.setFillColor(colors.HexColor("#334155"))
    pdf.setFont(FONT_REGULAR, 6.8)
    pdf.drawString(442, 49, "Slope of per-RTT means of max(TA, TB)")
    pdf.drawString(442, 39, "6 RTT levels; 10 independent runs per level")
    pdf.drawString(442, 29, f"Minimum online R-squared = {min_r2:.3f}")
    pdf.drawString(442, 19, "Local durations; includes phase skew")

    pdf.showPage()
    pdf.save()


def main():
    args = parse_args()
    data, min_r2 = load_and_validate(args.input_csv)
    plot(data, min_r2, args.output_pdf)
    print(f"wrote {args.output_pdf}")
    print(f"validated 48 fits; minimum online R^2 = {min_r2:.6f}")


if __name__ == "__main__":
    main()
