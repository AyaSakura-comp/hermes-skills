#!/home/chihmin/src/Pixal3D/.venv/bin/python
"""Submit one image to the loopback Pixal3D service, collect GLB/STL, and render a rotating GIF."""
import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parents[1]
UPLOAD_SCRIPT = Path.home() / ".pi/agent/skills/upload-html/scripts/upload-html.sh"
GIF_SCRIPT = SKILL_DIR / "scripts" / "render_rotation_gif.py"

from gradio_client import Client, handle_file


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--size-mm", type=float, default=100.0)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--url", default="http://127.0.0.1:7866")
    parser.add_argument("--no-upload", action="store_true",
                        help="generate local files without publishing the HTML preview")
    args = parser.parse_args()

    image = args.image.expanduser().resolve()
    if not image.is_file():
        parser.error(f"input does not exist: {image}")
    if image.suffix.lower() not in {".jpg", ".jpeg", ".png", ".webp"}:
        parser.error("input must be JPG, PNG, or WebP")
    if image.stat().st_size > 20 * 1024 * 1024:
        parser.error("input exceeds the service's 20 MB upload limit")
    if not 0 <= args.seed <= 2**31 - 1:
        parser.error("seed must be between 0 and 2147483647")
    if not 1 <= args.size_mm <= 1000:
        parser.error("size-mm must be between 1 and 1000")

    output = args.output_dir.expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    try:
        response = Client(args.url, download_files=str(output), verbose=False).predict(
            handle_file(str(image)), args.seed, args.size_mm, api_name="/generate"
        )
    except Exception as exc:
        print(f"Pixal3D request failed: {exc}", file=sys.stderr)
        return 1

    glb_source, stl_source, report = response
    destinations = []
    for source, name in ((glb_source, "model.glb"), (stl_source, "model.stl")):
        source_path = Path(source).resolve()
        destination = output / name
        if source_path != destination:
            shutil.copy2(source_path, destination)
        destinations.append(destination)
    report_path = output / "result.json"
    report_path.write_text(json.dumps(report, indent=2) + "\n")

    result = {"glb": str(destinations[0]), "stl": str(destinations[1]),
              "report": str(report_path), "preview_url": None, "rotation_gif": None}

    # Render rotating GIF from the generated GLB
    glb_path = destinations[0]
    gif_path = output / "rotation.gif"
    if glb_path.is_file():
        os.environ.setdefault("DISPLAY", ":99")
        xvfb_auth = Path("/tmp/xvfb-run.CUriyG/Xauthority")
        if xvfb_auth.is_file():
            os.environ["XAUTHORITY"] = str(xvfb_auth)
            # Also copy for subprocess inheritance safety
            dest_auth = Path("/tmp/my_xauth")
            if not dest_auth.exists() or os.path.getmtime(str(xvfb_auth)) > os.path.getmtime(str(dest_auth)):
                shutil.copy2(str(xvfb_auth), str(dest_auth))
            os.environ["XAUTHORITY"] = str(dest_auth)
        try:
            gif_result = subprocess.run(
                [str(sys.executable), str(GIF_SCRIPT), str(glb_path), "-o", str(gif_path)],
                check=True, capture_output=True, text=True,
                timeout=120,
            )
            if gif_result.stdout.strip():
                result["rotation_gif"] = gif_result.stdout.strip()
                print(f"Rotating GIF: {result['rotation_gif']}")
        except subprocess.CalledProcessError as exc:
            print(f"GIF render failed (non-fatal): {exc.stderr}", file=sys.stderr)
        except subprocess.TimeoutExpired:
            print("GIF render timed out (non-fatal)", file=sys.stderr)
        except Exception as exc:
            print(f"GIF render skipped: {exc}", file=sys.stderr)

    if not args.no_upload:
        preview = output / "html-preview"
        preview.mkdir(exist_ok=True)
        shutil.copy2(SKILL_DIR / "assets/viewer.html", preview / "index.html")
        shutil.copy2(destinations[0], preview / "model.glb")
        # Normalize every supported input type to the viewer's predictable JPG asset.
        from PIL import Image
        with Image.open(image) as source:
            source.load()
            if source.mode in {"RGBA", "LA"} or "transparency" in source.info:
                rgba = source.convert("RGBA")
                flattened = Image.new("RGB", rgba.size, "white")
                flattened.paste(rgba, mask=rgba.getchannel("A"))
            else:
                flattened = source.convert("RGB")
            flattened.save(preview / "input.jpg", quality=92, optimize=True)
        if not UPLOAD_SCRIPT.is_file():
            print(f"HTML upload helper is missing: {UPLOAD_SCRIPT}", file=sys.stderr)
            return 2
        try:
            uploaded = subprocess.run(
                ["bash", str(UPLOAD_SCRIPT), str(preview)],
                check=True, text=True, capture_output=True,
            )
        except subprocess.CalledProcessError as exc:
            print(exc.stdout, file=sys.stderr)
            print(exc.stderr, file=sys.stderr)
            print("3D files were generated, but HTML upload failed", file=sys.stderr)
            return 2
        for line in uploaded.stdout.splitlines():
            if line.startswith("Site URL:"):
                result["preview_url"] = line.split(":", 1)[1].strip()
                break
        if not result["preview_url"]:
            print(uploaded.stdout, file=sys.stderr)
            print("Upload completed without a Site URL", file=sys.stderr)
            return 2

    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
