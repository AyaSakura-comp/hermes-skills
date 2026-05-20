#!/usr/bin/env python3
"""
markdown-table-to-png
Convert markdown tables to high-quality PNG images via SVG.

Usage:
  python3 table2png.py --input table.md --output result.png
  echo "| a | b |
  |---|---|
  | 1 | 2 |" | python3 table2png.py --stdin -o out.png
"""

import argparse
import html
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from typing import Optional

# ─── Color Schemes ───────────────────────────────────────────────────────────

THEMES = {
    "dark": {
        "bg": "#1a1b2e",
        "header_bg": "#2d2f45",
        "body_bg": "#1e1f33",
        "alt_row_bg": "#252740",
        "text": "#e8e8f0",
        "border": "#3a3c52",
        "shadow": "rgba(0,0,0,0.4)",
    },
    "light": {
        "bg": "#ffffff",
        "header_bg": "#f0f2f5",
        "body_bg": "#ffffff",
        "alt_row_bg": "#f8f9fa",
        "text": "#1a1a2e",
        "border": "#e0e0e8",
        "shadow": "rgba(0,0,0,0.08)",
    },
}


# ─── Data Structures ─────────────────────────────────────────────────────────

@dataclass
class Cell:
    text: str
    align: str = "left"  # left | center | right
    colspan: int = 1
    raw: str = ""

    def escaped_text(self):
        """HTML-escape and decode entities for safe SVG embedding."""
        text = html.unescape(html.escape(self.text, quote=True))
        text = text.replace("&apos;", "'")
        return text


@dataclass
class Row:
    cells: list[Cell] = field(default_factory=list)

    def __len__(self):
        return len(self.cells)


# ─── Markdown Parser ─────────────────────────────────────────────────────────

def parse_markdown_table(text: str) -> tuple[list[Row], int]:
    """
    Parse a markdown table from text.
    Returns (rows, num_columns).
    Strips the separator line (|---|---|) automatically.
    """
    lines = text.strip().splitlines()
    lines = [l.strip() for l in lines if l.strip()]

    if not lines:
        return [], 0

    rows = []
    num_cols = 0

    for line_idx, line in enumerate(lines):
        # Skip separator line
        if line_idx == 0:
            # First line is header
            pass
        elif line_idx == 1 and re.match(r"^\|?[\s\-:|]+\|?(\s*\|?[\s\-:|]+\|?)*$", line):
            continue  # Skip separator

        # Parse pipe-delimited cells
        # Remove leading/trailing pipes
        line = line.strip()
        if line.startswith("|"):
            line = line[1:]
        if line.endswith("|"):
            line = line[:-1]

        raw_cells = line.split("|")
        cells = []
        for raw in raw_cells:
            raw = raw.strip()
            if not raw:
                continue
            # Detect alignment
            align = "left"
            if raw.startswith(":") and raw.endswith(":"):
                align = "center"
                raw = raw[1:-1].strip()
            elif raw.startswith(":"):
                align = "right"
                raw = raw[1:].strip()
            elif raw.endswith(":"):
                align = "left"
                raw = raw[:-1].strip()

            # Handle colspans in header
            colspan = 1
            m = re.match(r'^colspan="(\d+)"\s*(.+)$', raw)
            if m:
                colspan = int(m.group(1))
                raw = m.group(2).strip()

            cells.append(Cell(text=raw, align=align, colspan=colspan, raw=raw))

        if cells:
            rows.append(Row(cells=cells))
            num_cols = max(num_cols, len(cells))

    return rows, num_cols


# ─── SVG Generator ───────────────────────────────────────────────────────────

def _word_wrap(text: str, font_size: int, max_width: int, font_family: str) -> list[str]:
    """Simple word-wrap for SVG tspan rendering."""
    if not text:
        return [""]
    words = text.split()
    lines = []
    current = ""
    # Approximate: average char width ~ font_size * 0.6
    avg_char = font_size * 0.58
    chars_per_line = int(max_width / avg_char)

    for word in words:
        if len(current) == 0:
            current = word
        elif len(current) + 1 + len(word) <= chars_per_line:
            current += " " + word
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def generate_svg(
    rows: list[Row],
    num_cols: int,
    theme: dict,
    font_family: str,
    font_size: int,
    header_font_size: int,
    border_radius: int,
    cell_padding: int,
    max_width: int,
    alt_row: bool,
) -> str:
    """Generate a styled SVG representing the markdown table."""

    if not rows:
        return _empty_svg(theme)

    # Measure column widths
    col_widths = [0] * num_cols
    for row in rows:
        for ci, cell in enumerate(row.cells):
            if ci < num_cols:
                # Approximate pixel width per cell
                text_len = len(cell.text)
                cell_w = max(text_len * font_size * 0.55, 60)
                if ci < len(col_widths):
                    col_widths[ci] = max(col_widths[ci], cell_w)

    # Cap total width
    total_w = sum(col_widths)
    if total_w > max_width:
        scale = max_width / total_w
        col_widths = [max(int(w * scale), 60) for w in col_widths]

    total_w = sum(col_widths)
    header_h = header_font_size * 2.2
    body_h = font_size * 2.0
    table_h = header_h + len(rows) * body_h
    pad = cell_padding

    svg_parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{total_w}" height="{table_h}" '
                 f'font-family="{font_family}" font-size="{font_size}">']

    # Background
    svg_parts.append(
        f'<rect width="{total_w}" height="{table_h}" rx="{border_radius}" '
        f'fill="{theme["bg"]}"/>'
    )

    # Header row
    x = 0
    header_cells = rows[0].cells if rows else []
    for ci, cell in enumerate(header_cells):
        if ci >= num_cols:
            break
        w = col_widths[ci]
        text = cell.escaped_text()

        # Header cell background
        svg_parts.append(
            f'<rect x="{x}" y="0" width="{w}" height="{header_h}" '
            f'fill="{theme["header_bg"]}" '
            f'rx="{border_radius}" ry="{border_radius}"/>'
        )

        # Header cell border
        svg_parts.append(
            f'<rect x="{x}" y="0" width="{w}" height="{header_h}" '
            f'fill="none" stroke="{theme["border"]}" stroke-width="1" '
            f'rx="{border_radius}" ry="{border_radius}"/>'
        )

        # Right border (except last column)
        if ci < num_cols - 1:
            svg_parts.append(
                f'<line x1="{x + w}" y1="0" x2="{x + w}" y2="{header_h}" '
                f'stroke="{theme["border"]}" stroke-width="1"/>'
            )

        # Header text
        wrap = _word_wrap(text, header_font_size, w - pad * 2, font_family)
        for wi, line in enumerate(wrap):
            y = header_font_size + wi * (header_font_size * 1.3)
            align_attr = 'text-anchor="middle"' if cell.align == "center" else (
                'text-anchor="end"' if cell.align == "right" else 'text-anchor="start"'
            )
            x_offset = (x + w / 2) if cell.align == "center" else (
                x + w - pad if cell.align == "right" else x + pad
            )
            svg_parts.append(
                f'<text x="{x_offset}" y="{y}" {align_attr} '
                f'fill="{theme["text"]}" font-weight="600" '
                f'font-size="{header_font_size}">'
                f'{html.escape(line)}</text>'
            )

        x += w

    # Body rows
    for ri, body_row in enumerate(rows[1:], start=1):
        y = header_h + (ri - 1) * body_h
        row_bg = theme["alt_row_bg"] if (alt_row and ri % 2 == 0) else theme["body_bg"]

        # Row background (full width)
        svg_parts.append(
            f'<rect x="0" y="{y}" width="{total_w}" height="{body_h}" '
            f'fill="{row_bg}"/>'
        )

        # Bottom border
        svg_parts.append(
            f'<line x1="0" y1="{y + body_h}" x2="{total_w}" y2="{y + body_h}" '
            f'stroke="{theme["border"]}" stroke-width="1"/>'
        )

        # Left border
        svg_parts.append(
            f'<line x1="0" y1="{y}" x2="0" y2="{y + body_h}" '
            f'stroke="{theme["border"]}" stroke-width="1"/>'
        )

        x = 0
        for ci, cell in enumerate(body_row.cells):
            if ci >= num_cols:
                break
            w = col_widths[ci]
            text = cell.escaped_text()

            # Right border
            if ci < num_cols - 1:
                svg_parts.append(
                    f'<line x1="{x + w}" y1="{y}" x2="{x + w}" y2="{y + body_h}" '
                    f'stroke="{theme["border"]}" stroke-width="1"/>'
                )

            # Cell text
            wrap = _word_wrap(text, font_size, w - pad * 2, font_family)
            for wi, line in enumerate(wrap):
                cy = y + font_size + wi * (font_size * 1.3)
                align_attr = 'text-anchor="middle"' if cell.align == "center" else (
                    'text-anchor="end"' if cell.align == "right" else 'text-anchor="start"'
                )
                x_offset = (x + w / 2) if cell.align == "center" else (
                    x + w - pad if cell.align == "right" else x + pad
                )
                svg_parts.append(
                    f'<text x="{x_offset}" y="{cy}" {align_attr} '
                    f'fill="{theme["text"]}" font-size="{font_size}">'
                    f'{html.escape(line)}</text>'
                )

            x += w

    svg_parts.append("</svg>")
    return "\n".join(svg_parts)


def _empty_svg(theme: dict) -> str:
    """Return an SVG for an empty table."""
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="200" height="40" '
        f'font-family="system-ui, sans-serif" font-size="14">'
        f'<rect width="200" height="40" rx="6" fill="{theme["bg"]}"/>'
        f'<text x="100" y="25" text-anchor="middle" fill="{theme["text"]}">'
        f'No table data</text></svg>'
    )


# ─── SVG → PNG Converter ────────────────────────────────────────────────────

CONVERTERS = [
    ("rsvg", "rsvg-convert -w 2 -h 1 -f png -o {} {}"),
    ("magick", "magick {} -density 150 {}"),
    ("inkscape", "inkscape {} --export-type=png --export-filename={} --export-dpi=150"),
    ("sips", "sips -s format png {} --out {}"),
]


def find_converter(force: str = "auto") -> tuple[str, str] | None:
    """Find an available SVG→PNG converter. Returns (name, format_string)."""
    if force != "auto" and force != "":
        for name, cmd in CONVERTERS:
            if name == force:
                if shutil.which(cmd.split()[0]):
                    return name, cmd
        return None

    for name, cmd in CONVERTERS:
        if shutil.which(cmd.split()[0]):
            return name, cmd
    return None


# ─── Main ────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Convert markdown tables to PNG images via SVG."
    )
    parser.add_argument("--input", "-i", help="Path to markdown file")
    parser.add_argument("--stdin", action="store_true", help="Read markdown from stdin")
    parser.add_argument("--output", "-o", default="table.png", help="Output PNG file")
    parser.add_argument("--theme", choices=["dark", "light"], default="dark", help="Color theme")
    parser.add_argument("--font-size", type=int, default=14, help="Body font size (px)")
    parser.add_argument("--header-font-size", type=int, default=16, help="Header font size (px)")
    parser.add_argument("--font-family", default="system-ui, sans-serif", help="CSS font stack")
    parser.add_argument("--border-radius", type=int, default=6, help="Cell corner radius (px)")
    parser.add_argument("--dpi", type=int, default=150, help="Output PNG DPI")
    parser.add_argument("--max-width", type=int, default=900, help="Max table width (px)")
    parser.add_argument("--cell-padding", type=int, default=12, help="Cell padding (px)")
    parser.add_argument("--alt-row", action="store_true", default=True, help="Alternate row shading")
    parser.add_argument("--no-alt-row", action="store_true", help="Disable alternate row shading")
    parser.add_argument("--convert", default="auto", choices=["auto", "rsvg", "magick", "inkscape", "sips"],
                        help="Force converter backend")

    args = parser.parse_args()

    if args.no_alt_row:
        args.alt_row = False

    # Read markdown
    if args.stdin:
        markdown = sys.stdin.read().strip()
    elif args.input:
        if not os.path.isfile(args.input):
            print(f"Error: file not found: {args.input}", file=sys.stderr)
            sys.exit(1)
        with open(args.input) as f:
            markdown = f.read().strip()
    else:
        parser.print_help()
        sys.exit(1)

    # Parse
    rows, num_cols = parse_markdown_table(markdown)
    if not rows:
        print("Error: no table found in input", file=sys.stderr)
        sys.exit(1)

    # Resolve theme
    theme = THEMES[args.theme]

    # Generate SVG
    svg = generate_svg(
        rows=rows,
        num_cols=num_cols,
        theme=theme,
        font_family=args.font_family,
        font_size=args.font_size,
        header_font_size=args.header_font_size,
        border_radius=args.border_radius,
        cell_padding=args.cell_padding,
        max_width=args.max_width,
        alt_row=args.alt_row,
    )

    # Write SVG to temp file
    with tempfile.NamedTemporaryFile(mode="w", suffix=".svg", delete=False) as f:
        f.write(svg)
        svg_path = f.name

    # Find converter
    converter = find_converter(args.convert)
    if not converter:
        print("Error: no SVG→PNG converter found.", file=sys.stderr)
        print("Install one of:", file=sys.stderr)
        for name, cmd in CONVERTERS:
            print(f"  {name}: {cmd.split()[0]}", file=sys.stderr)
        os.unlink(svg_path)
        sys.exit(1)

    name, fmt = converter
    print(f"[table2png] Using converter: {name} ({fmt.split()[0]})", file=sys.stderr)

    # Convert
    success = False
    try:
        cmd = fmt.format(svg_path, args.output)
        cmd_list = cmd.split()
        if name == "rsvg":
            subprocess.run(cmd_list, check=True, capture_output=True)
            success = os.path.exists(args.output) and os.path.getsize(args.output) > 0
        elif name == "magick":
            subprocess.run(cmd_list, check=True, capture_output=True)
            success = True
        elif name == "inkscape":
            subprocess.run(cmd_list, check=True, capture_output=True)
            success = True
        elif name == "sips":
            subprocess.run(cmd_list, check=True, capture_output=True)
            success = os.path.exists(args.output) and os.path.getsize(args.output) > 0
    except subprocess.CalledProcessError as e:
        print(f"[{name}] conversion error: {e.stderr.decode(errors='replace')}", file=sys.stderr)
    except Exception as e:
        print(f"[{name}] error: {e}", file=sys.stderr)

    # Cleanup
    os.unlink(svg_path)

    if success:
        size = os.path.getsize(args.output)
        print(f"[table2png] Saved → {args.output} ({size} bytes)")
    else:
        print(f"Error: conversion failed with {name}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
