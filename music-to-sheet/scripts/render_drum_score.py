#!/usr/bin/env python3
from __future__ import annotations

import argparse
import shutil
import subprocess
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Engrave MusicXML to SVG pages and PDF with Verovio")
    parser.add_argument("--musicxml", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--pdf", type=Path)
    return parser.parse_args()


def main() -> None:
    options = parse_args()
    try:
        import verovio
    except ImportError as exc:
        raise SystemExit("Install Verovio in this Python environment: pip install verovio") from exc

    options.output_dir.mkdir(parents=True, exist_ok=True)
    for stale in options.output_dir.glob("page-*.svg"):
        stale.unlink()
    toolkit = verovio.toolkit()
    toolkit.setOptions(
        {
            "pageWidth": 2100,
            "pageHeight": 2970,
            "scale": 35,
            "adjustPageHeight": True,
            "breaks": "auto",
            "footer": "none",
            "header": "none",
        }
    )
    if not toolkit.loadFile(str(options.musicxml)):
        raise SystemExit(f"Verovio could not load {options.musicxml}")
    pages = []
    for page in range(1, toolkit.getPageCount() + 1):
        target = options.output_dir / f"page-{page:02d}.svg"
        target.write_text(toolkit.renderToSVG(page), encoding="utf-8")
        pages.append(target)

    if options.pdf:
        chrome = shutil.which("google-chrome") or shutil.which("chromium") or shutil.which("chromium-browser")
        if not chrome:
            raise SystemExit("Chrome/Chromium is required for PDF export")
        print_html = options.output_dir / "print.html"
        embedded = "\n".join(path.read_text(encoding="utf-8") for path in pages)
        print_html.write_text(
            "<!doctype html><meta charset='utf-8'><style>"
            "@page{size:A4;margin:10mm}body{margin:0}svg{width:100%;height:auto;display:block;page-break-after:always}"
            "svg:last-child{page-break-after:auto}</style>" + embedded,
            encoding="utf-8",
        )
        options.pdf.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            [
                chrome,
                "--headless=new",
                "--no-sandbox",
                "--disable-gpu",
                "--allow-file-access-from-files",
                "--no-pdf-header-footer",
                f"--print-to-pdf={options.pdf.resolve()}",
                print_html.resolve().as_uri(),
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        print_html.unlink(missing_ok=True)
    print(f"Rendered {len(pages)} SVG page(s)")


if __name__ == "__main__":
    main()
