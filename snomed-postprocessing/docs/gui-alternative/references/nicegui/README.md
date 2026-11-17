# NiceGUI documentation snapshot

Targeted public documentation downloaded as Markdown on **2026-11-11** for the SNOMED-PP frontend migration assessment.

These files are upstream NiceGUI documentation, attributed to NiceGUI/Zauberzeug and its contributors. They are reference material, not project-authored API guarantees. This is a live-site snapshot, **not a version-pinned release manual**. Retain upstream attribution and consult upstream licensing before redistributing documentation outside this workspace.

See [`manifest.json`](manifest.json) for source URLs, retrieval timestamp, response content types, byte lengths and SHA-256 hashes of the downloaded UTF-8 response bodies. Local text files may have platform-normalised line endings.

## Index

| Topic | Local reference | Upstream |
|---|---|---|
| Framework/architecture and API overview | [llms.md](llms.md) | https://nicegui.io/llms.txt |
| AG Grid | [aggrid.md](aggrid.md) | https://nicegui.io/documentation/aggrid |
| Quasar table | [table.md](table.md) | https://nicegui.io/documentation/table |
| Events and task integration | [section_action_events.md](section_action_events.md) | https://nicegui.io/documentation/section_action_events |
| Bindings | [section_binding_properties.md](section_binding_properties.md) | https://nicegui.io/documentation/section_binding_properties |
| Refreshable UI | [refreshable.md](refreshable.md) | https://nicegui.io/documentation/refreshable |
| Storage and session scopes | [storage.md](storage.md) | https://nicegui.io/documentation/storage |
| Layout, popups and notifications | [section_page_layout.md](section_page_layout.md) | https://nicegui.io/documentation/section_page_layout |
| Controls | [section_controls.md](section_controls.md) | https://nicegui.io/documentation/section_controls |
| Text/Markdown/HTML | [section_text_elements.md](section_text_elements.md) | https://nicegui.io/documentation/section_text_elements |
| Select | [select.md](select.md) | https://nicegui.io/documentation/select |
| Toggle | [toggle.md](toggle.md) | https://nicegui.io/documentation/toggle |
| Upload | [upload.md](upload.md) | https://nicegui.io/documentation/upload |
| Download | [download.md](download.md) | https://nicegui.io/documentation/download |
| Keyboard | [keyboard.md](keyboard.md) | https://nicegui.io/documentation/keyboard |
| Dialog | [dialog.md](dialog.md) | https://nicegui.io/documentation/dialog |
| Menu | [menu.md](menu.md) | https://nicegui.io/documentation/menu |
| Tabs | [tabs.md](tabs.md) | https://nicegui.io/documentation/tabs |
| Text input/validation/debounce | [input.md](input.md) | https://nicegui.io/documentation/input |
| Number input | [number.md](number.md) | https://nicegui.io/documentation/number |
| Tooltip | [tooltip.md](tooltip.md) | https://nicegui.io/documentation/tooltip |

## Refresh

From the workspace root, explicitly run:

```bash
uvx --offline python scripts/download_nicegui_docs.py
```

Requires an available cached Python runtime when using `--offline`. The Python script uses only the standard library. **The script itself makes network requests** to the listed public NiceGUI URLs; `uvx --offline` only prevents uv dependency/runtime downloads. It overwrites these selected snapshot files, does not delete unrelated files, and writes the manifest after all requests succeed.

The downloader requests `Accept: text/markdown`, uses at most three concurrent requests, and rejects obvious HTML responses. No recursive crawl, browser automation or NiceGUI installation is involved.

Main design document: [`../../STREAMLIT_TO_NICEGUI_COMPONENTS.md`](../../STREAMLIT_TO_NICEGUI_COMPONENTS.md).
