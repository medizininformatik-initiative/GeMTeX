"""Per-page Upload / Data directory / Server path inputs; no GUI imports."""
from dataclasses import dataclass, field
from pathlib import Path
import stat
from tempfile import TemporaryDirectory

MAX_UPLOAD_BYTES = 200 * 1024 * 1024


@dataclass(frozen=True)
class SourceFile:
    path: Path
    owner: TemporaryDirectory | None = field(default=None, repr=False, compare=False)

    def stamp(self):
        info = self.path.stat()
        if not stat.S_ISREG(info.st_mode):
            raise ValueError("Select a regular file.")
        return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns


def list_server_files(directory: Path, suffixes: tuple[str, ...]) -> list[Path]:
    if not directory.is_dir():
        return []
    suffixes = tuple(suffix.casefold() for suffix in suffixes)
    return sorted(path for path in directory.iterdir()
                  if path.is_file() and path.suffix.casefold() in suffixes)


class FileSource:
    def __init__(self, ui, label, suffixes, data_dir, on_change):
        self.suffixes, self.data_dir, self.on_change = suffixes, data_dir, on_change
        self.uploaded = None
        self.uploading = self.closed = False
        self.generation = 0
        with ui.column().classes("w-full min-w-0 gap-2") as self.container:
            ui.label(label).classes("font-medium")
            self.mode = ui.toggle(["Upload", "Data directory", "Server path"], value="Upload",
                                  on_change=lambda _: self.change_mode()).props("dense no-caps")
            self.uploader = ui.upload(label=f"Upload {label}", on_upload=self.load,
                                      multiple=False, max_files=1, auto_upload=True,
                                      max_file_size=MAX_UPLOAD_BYTES,
                                      on_rejected=lambda: self.note.set_text("Upload rejected. Limit: 200 MiB; use a server file for larger inputs.")) \
                .props("accept=" + ",".join(suffixes)).classes("w-full")
            self.uploader.on("removed", lambda _: self.clear_upload())
            self.choice = ui.select({}, label=f"Select {label}", with_input=True, on_change=lambda _: self.changed()).classes("w-full")
            self.path = ui.input(label=f"{label} path on this server", on_change=lambda _: self.changed()).classes("w-full")
            self.note = ui.label().classes("text-sm")
        self.show_mode()

    def changed(self):
        self.on_change()

    def show_mode(self):
        self.uploader.set_visibility(self.mode.value == "Upload")
        self.choice.set_visibility(self.mode.value == "Data directory")
        self.path.set_visibility(self.mode.value == "Server path")

    def change_mode(self):
        self.generation += 1
        self.uploading = False
        self.note.set_text("")
        self.show_mode()
        self.refresh_directory()
        self.changed()

    def refresh_directory(self):
        if self.mode.value != "Data directory":
            return
        try:
            paths = list_server_files(Path(self.data_dir.value or "").expanduser(), self.suffixes)
            options = {str(path): path.name for path in paths}
            self.choice.set_options(options, value=self.choice.value if self.choice.value in options else None)
            self.note.set_text("Files directly inside the data directory; subfolders are not searched."
                               if paths else "No matching files in the data directory.")
        except (OSError, ValueError, RuntimeError):
            self.choice.set_options({}, value=None)
            self.note.set_text("Could not list the server data directory.")

    def snapshot(self):
        if self.closed or self.uploading:
            return None
        if self.mode.value == "Upload":
            return self.uploaded
        value = self.choice.value if self.mode.value == "Data directory" else self.path.value
        try:
            return SourceFile(Path(value.strip()).expanduser()) if isinstance(value, str) and value.strip() else None
        except (ValueError, RuntimeError):
            return None

    def clear_upload(self):
        self.generation += 1
        self.uploaded = None
        self.uploading = False
        self.note.set_text("")
        self.changed()

    async def load(self, event):
        if self.closed or self.mode.value != "Upload":
            return
        self.generation += 1
        generation = self.generation
        self.uploading = True
        self.on_change()
        try:
            suffix = Path(event.file.name).suffix.casefold()
            if suffix not in self.suffixes or event.file.size() > MAX_UPLOAD_BYTES:
                raise ValueError("Unsupported upload.")
            owner = TemporaryDirectory(prefix="snomed-policy-upload-")
            target = Path(owner.name) / Path(event.file.name).name
            await event.file.save(target)
            if target.stat().st_size > MAX_UPLOAD_BYTES:
                raise ValueError("Upload too large.")
            if not self.closed and generation == self.generation and self.mode.value == "Upload":
                self.uploaded = SourceFile(target, owner)
                self.note.set_text(f"Uploaded: {event.file.name}")
        except Exception:
            if not self.closed and generation == self.generation:
                self.note.set_text("Could not load this file. Previous selection unchanged. Use a valid file up to 200 MiB.")
        finally:
            if not self.closed and generation == self.generation:
                self.uploading = False
                self.on_change()

    def close(self):
        self.closed = True
        self.generation += 1
        self.uploaded = None  # An in-flight worker holds its own SourceFile/temporary-directory reference.
