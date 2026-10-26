#!/usr/bin/env python3
"""Upload a local image to Google Lens and emit external result URLs as JSON."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from urllib.parse import parse_qs, unquote, urljoin, urlparse

try:
    from bs4 import BeautifulSoup
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
    from playwright.sync_api import sync_playwright
except ImportError as exc:  # pragma: no cover - exercised by the CLI environment
    raise SystemExit(
        "Missing dependency. Install/use a Python environment with beautifulsoup4 "
        "and playwright."
    ) from exc


SEARCH_BUTTON_LABELS = (
    "以圖搜尋",
    "使用圖像搜尋",
    "Search by image",
    "Search with an image",
    "Recherche par image",
    "Bildersuche",
)


def _is_google_host(host: str) -> bool:
    host = host.lower().split(":", 1)[0].rstrip(".")
    return host == "google.com" or host.endswith(".google.com") or host.endswith(
        ".google.com.tw"
    )


def normalize_result_url(href: str, base_url: str = "https://www.google.com/") -> str | None:
    """Return a direct HTTP(S) result URL, unwrapping Google redirect links."""
    if not href:
        return None

    absolute = urljoin(base_url, href.strip())
    parsed = urlparse(absolute)
    if parsed.scheme not in {"http", "https"}:
        return None

    if _is_google_host(parsed.netloc):
        query = parse_qs(parsed.query)
        for key in ("q", "url", "u"):
            target = query.get(key, [""])[0]
            if target:
                target_url = normalize_result_url(unquote(target), base_url)
                if target_url:
                    return target_url
        return None

    return absolute


def extract_result_records(html: str, limit: int = 20) -> list[dict[str, str | int]]:
    """Extract ordered, unique external anchors from a rendered Lens result page."""
    if limit < 1:
        return []

    soup = BeautifulSoup(html, "html.parser")
    anchors = soup.select("div.kb0PBd.cvP2Ce a[href]")
    if not anchors:
        # Lens changes its generated classes frequently. The document order on the
        # rendered page places visual matches before ordinary web-search cards.
        anchors = soup.select("a[href]")

    records: list[dict[str, str | int]] = []
    seen: set[str] = set()
    for anchor in anchors:
        result_url = normalize_result_url(anchor.get("href", ""))
        if not result_url or result_url in seen:
            continue
        seen.add(result_url)
        text = " ".join(anchor.get_text(" ", strip=True).split())
        records.append({"rank": len(records) + 1, "title": text, "url": result_url})
        if len(records) >= limit:
            break
    return records


def extract_result_urls(html: str, limit: int = 20) -> list[str]:
    """Compatibility helper returning only URLs."""
    return [record["url"] for record in extract_result_records(html, limit)]


def _click_search_by_image(page) -> None:
    for label in SEARCH_BUTTON_LABELS:
        locator = page.locator(f'[role="button"][aria-label="{label}"]').first
        if locator.count():
            locator.click()
            return

    # English/Chinese labels are the normal cases, but this fallback tolerates a
    # localized Google UI without using screen coordinates.
    locator = page.locator(
        '[role="button"][aria-label*="image" i], '
        '[role="button"][aria-label*="圖"], '
        '[role="button"][aria-label*="圖片"]'
    ).first
    if locator.count():
        locator.click()
        return
    raise RuntimeError("Could not find Google's Search by image control.")


def search_image(
    image_path: Path,
    *,
    limit: int = 20,
    lang: str = "zh-TW",
    headless: bool = True,
) -> dict:
    """Run one browser upload and return the current Lens URL plus result records."""
    if not image_path.is_file():
        raise FileNotFoundError(f"Image not found: {image_path}")
    if limit < 1:
        raise ValueError("limit must be at least 1")

    user_agent = (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            headless=headless,
            args=["--no-sandbox", "--disable-blink-features=AutomationControlled"],
        )
        context = browser.new_context(
            user_agent=user_agent,
            locale=lang,
            viewport={"width": 1280, "height": 900},
        )
        page = context.new_page()
        try:
            page.goto(
                f"https://lens.google.com/?hl={lang}",
                wait_until="domcontentloaded",
                timeout=30_000,
            )
            _click_search_by_image(page)
            file_input = page.locator('input[type="file"][name="encoded_image"]').first
            file_input.wait_for(state="attached", timeout=15_000)
            file_input.set_input_files(str(image_path))

            try:
                page.wait_for_url("**/search**", timeout=30_000)
            except PlaywrightTimeoutError:
                pass
            page.wait_for_timeout(2_500)

            if "/sorry/" in page.url:
                raise RuntimeError(
                    "Google presented an anti-bot verification page; rerun with --headed "
                    "and complete the verification in the opened browser."
                )

            html = page.content()
            records = extract_result_records(html, limit)
            return {
                "image": str(image_path),
                "search_url": page.url,
                "results": records,
            }
        finally:
            context.close()
            browser.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Search a local image with Google Lens and print result URLs."
    )
    parser.add_argument("image", type=Path)
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--lang", default="zh-TW")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument(
        "--headed",
        action="store_true",
        help="Show Chromium when Google requests human verification.",
    )
    args = parser.parse_args(argv)

    try:
        result = search_image(
            args.image,
            limit=args.limit,
            lang=args.lang,
            headless=not args.headed,
        )
    except (FileNotFoundError, ValueError, RuntimeError) as exc:
        print(f"image-search: {exc}", file=sys.stderr)
        return 1

    if args.output_dir:
        args.output_dir.mkdir(parents=True, exist_ok=True)
        (args.output_dir / "results.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        (args.output_dir / "urls.txt").write_text(
            "\n".join(record["url"] for record in result["results"]) + "\n",
            encoding="utf-8",
        )
        (args.output_dir / "search-url.txt").write_text(
            result["search_url"] + "\n", encoding="utf-8"
        )

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
