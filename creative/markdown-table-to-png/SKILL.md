---
name: markdown-table-to-png
description: Convert markdown tables to high-quality PNG images via SVG. Supports dark/light themes, custom fonts, colors, borders, and responsive sizing. Falls back gracefully when conversion tools are missing.
version: 1.0.0
author: Hermes Agent
license: MIT
dependencies: []
metadata:
  hermes:
    tags: [Markdown, Table, PNG, SVG, Image, Conversion, Diagram]
    related_skills: [ascii-art, excalidraw, popular-web-designs]

---

# Markdown Table to PNG Skill

Convert markdown-formatted tables into polished PNG images using a stable pipeline:

```
Markdown table → Python parser → Styled SVG → rsvg-convert / ImageMagick / Inkscape → PNG
```

This avoids browser screenshots entirely, which are unreliable and slow.

## Workflow

### 1. Call the conversion script

```bash
python3 skills/creative/markdown-table-to-png/scripts/table2png.py \
  --input markdown.md \
  --output result.png \
  --theme dark \
  --font-size 14
```

### 2. Pass markdown inline (no file needed)

```bash
echo "| Name | Score | Grade |
|------|------:|-------|
| Alice | 95 | A+ |
| Bob | 82 | B |" \
| python3 skills/creative/markdown-table-to-png/scripts/table2png.py \
  --stdin \
  --output scores.png \
  --theme light
```

### 3. Use as a helper inside a larger Python script

```python
import subprocess, textwrap, sys

markdown = """| Feature | Status | Priority |
|---------|--------|----------|
| Auth    | ✅ Done | High |
| API     | 🔄 In progress | High |
| Docs    | ⏳ Pending | Medium |"""

result = subprocess.run(
    [sys.executable, "scripts/table2png.py"],
    input=textwrap.dedent(markdown).strip(),
    text=True, capture_output=True,
    cwd="skills/creative/markdown-table-to-png"
)
```

## Command-Line Options

| Flag | Default | Description |
|------|---------|-------------|
| `--input` | none | Path to `.md` file containing a markdown table |
| `--stdin` | false | Read markdown from stdin |
| `--output`, `-o` | `table.png` | Output PNG path |
| `--theme` | `dark` | `dark` or `light` |
| `--font-size` | `14` | Body font size in px |
| `--header-font-size` | `16` | Header font size in px |
| `--font-family` | `system-ui, sans-serif` | CSS font stack |
| `--border-radius` | `6` | Cell corner radius in px |
| `--dpi` | `150` | Output PNG DPI (higher = sharper) |
| `--max-width` | `900` | Max table width in px |
| `--cell-padding` | `12` | Padding inside each cell in px |
| `--bg-color` | (theme-dependent) | Custom background hex |
| `--header-bg` | (theme-dependent) | Header row background hex |
| `--text-color` | (theme-dependent) | Body text hex |
| `--border-color` | (theme-dependent) | Cell border hex |
| `--alt-row` | `true` | Alternate row shading |
| `--convert` | `auto` | Force converter: `auto`, `rsvg`, `magick`, `inkscape`, `sips` |

## Theme Color Schemes

**Dark theme** (default):
- Background: `#1a1b2e`
- Header bg: `#2d2f45`
- Body bg: `#1e1f33`
- Text: `#e8e8f0`
- Border: `#3a3c52`
- Alt row: `#252740`

**Light theme**:
- Background: `#ffffff`
- Header bg: `#f0f2f5`
- Body bg: `#ffffff`
- Text: `#1a1a2e`
- Border: `#e0e0e8`
- Alt row: `#f8f9fa`

## SVG Rendering Details

The Python parser handles:
- **Alignment markers**: `:---` (left), `---:` (right), `:---:` (center)
- **Colspan**: `colspan="2"` in header cells
- **Multi-line cells**: Newlines rendered as `<tspan>` breaks
- **HTML entities**: `&amp;`, `&lt;`, `&gt;`, `&nbsp;` decoded
- **Unicode emojis**: Rendered as-is (requires system font support)
- **Nested pipes in cells**: `| escaped\|pipe |` (backslash-escaped)

## Converter Fallback Order

When `--convert auto` (default), the script tries these in order:
1. **`rsvg-convert`** (librsvg) — fastest, best quality, no GUI needed
2. **`magick`** (ImageMagick) — universally available
3. **`inkscape`** — highest quality, slower
4. **`sips`** (macOS only) — no extra install needed on Mac

Run with `--convert <name>` to force a specific tool.

## Usage Tips

- For **presentation slides**, use `--dpi 200 --font-size 16 --theme dark`
- For **documentation**, use `--dpi 150 --font-size 13 --theme light --max-width 800`
- For **social media / Discord**, use `--dpi 150 --font-size 14 --theme dark --max-width 600`
- Tables with many columns benefit from `--max-width 1200`
- If emojis render as boxes, install `fonts-noto-color-emoji` or set `--font-family` to a CJK-supporting font
- For **RTL / CJK tables**, use `--font-family "Noto Sans CJK TC, sans-serif"` and increase `--font-size` by 2px

## Common Pitfalls

- **Empty table** (no data rows): The parser still renders headers, but output will be very short
- **Mismatched column counts**: Extra cells are silently dropped; missing cells become empty
- **Very wide tables** (>10 columns): Use `--max-width` to constrain width; columns will shrink proportionally
- **No converter installed**: The script prints an error listing which tools to install; use `--convert auto` and check which one is available
- **Large tables** (>50 rows): Consider splitting into multiple tables; SVG grows linearly

## Setup (install converters)

```bash
# Ubuntu/Debian
sudo apt install librsvg2-bin imagemagick inkscape -y

# macOS (all 3)
brew install librsvg imagemagick inkscape

# Fedora
sudo dnf install librsvg2-tools ImageMagick inkscape -y

# Arch
sudo pacman -S librsvg imagemagick inkscape
```

No converter is strictly required — the script detects what's available at runtime.
