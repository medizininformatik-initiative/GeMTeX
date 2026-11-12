"""Download a bounded set of public NiceGUI docs as Markdown (stdlib only).

Run explicitly when refreshing the local reference; this script performs network I/O.
Existing reference files are overwritten, but unrelated files are never deleted.
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1] / "references" / "nicegui"
PAGES = {
    "llms": "https://nicegui.io/llms.txt",
    **{name: f"https://nicegui.io/documentation/{name}" for name in (
        "aggrid", "table", "section_action_events", "section_binding_properties",
        "refreshable", "storage", "section_page_layout", "section_controls",
        "section_text_elements", "select", "toggle", "upload", "download",
        "keyboard", "dialog", "menu", "tabs", "input", "number", "tooltip",
    )},
}


def fetch(item):
    name, url = item
    request = Request(url, headers={"Accept": "text/markdown", "User-Agent": "SNOMED-PP-migration-doc-review/1.0"})
    with urlopen(request, timeout=20) as response:
        body = response.read()
        content_type = response.headers.get("Content-Type", "")
        final_url = response.url
    text = body.decode("utf-8")
    if "<html" in text[:1000].lower() or not text.strip():
        raise ValueError(f"Expected Markdown, received HTML or empty content: {url}")
    filename = f"{name}.md"
    (ROOT / filename).write_text(text, encoding="utf-8")
    print(f"{filename}: {len(body)} bytes", flush=True)
    return {"file": filename, "url": url, "final_url": final_url,
            "content_type": content_type, "bytes": len(body),
            "sha256": hashlib.sha256(body).hexdigest()}


if __name__ == "__main__":
    ROOT.mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(max_workers=3) as pool:
        pages = list(pool.map(fetch, PAGES.items()))
    metadata = {"retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
                "note": "Live documentation snapshot; not a version-pinned API contract.",
                "pages": pages}
    (ROOT / "manifest.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    print(f"Saved {len(pages)} pages and manifest to {ROOT}")
