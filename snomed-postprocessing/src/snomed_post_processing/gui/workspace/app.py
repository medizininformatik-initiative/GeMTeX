"""Workspace shell using the guarded NiceGUI runtime."""
from ..nicegui.app import main as run_nicegui


def main(argv=None):
    from .page import build_page, register_assets

    def setup():
        from nicegui import app
        register_assets(app)

    return run_nicegui(
        argv,
        page_builder=build_page,
        setup=setup,
        title="SNOMED Postprocessing — Workspace",
    )


if __name__ == "__main__":
    raise SystemExit(main())
