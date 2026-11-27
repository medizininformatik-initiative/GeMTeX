"""Explicit offline INCEpTION package download for preserved SQLite CAS."""
import copy

from .file_sources import FileSource
from .review import ReviewError, ReviewSession


class StoreRestorationControls:
    def __init__(self, ui, inputs, review):
        self.ui, self.inputs, self.review = ui, inputs, review
        self.busy = self.closed = False
        with ui.expansion('SQLite CAS restoration / INCEpTION review', value=False).classes('w-full') as self.container:
            ui.label('Requires a store built with --store-cas and one export-specific scope. Save review choices first. Prepares repaired CAS plus a schema shell for explicit INCEpTION deployment; never contacts the server.').classes('text-sm')
            self.template = FileSource(ui, 'Optional project template ZIP', ('.zip',), inputs.data_dir, self.refresh)
            ui.label('A template is needed only if the preserved export lacked project configuration. Downloads contain clinical text and full annotations.').classes('text-sm')
            self.download = ui.button('Download INCEpTION review package (offline)', on_click=self.prepare)
            self.status = ui.label().classes('text-sm')
        inputs.listeners.append(self.refresh)
        ui.context.client.on_disconnect(self.close)
        self.refresh()

    def refresh(self):
        if self.closed:
            return
        self.container.set_visibility(self.inputs.is_store)
        self.download.set_enabled(self.inputs.is_store and not self.busy and not self.template.uploading
                                  and self.inputs.project.snapshot() is not None and self.inputs.scope.value is not None)

    def close(self):
        self.closed = True
        self.template.close()

    async def prepare(self):
        if self.closed or self.busy or not self.inputs.is_store:
            return
        from nicegui import run
        from snomed_post_processing.pipelines.store_review_package import build_store_review_package
        controls = self.review.controls
        state, session = self.review.state, controls.session
        revision, input_revision = session.revision, self.inputs.revision
        project = self.inputs.project.snapshot()
        template = self.template.snapshot()
        store_scope = self.inputs.scope.value
        self.busy = True
        self.refresh()
        try:
            annotators = self.inputs.effective_annotators()
            if project is None or self.inputs.scope.value is None or self.template.uploading:
                raise ReviewError('Select a completed SQLite input, export scope and optional template first.')
            if session.dirty:
                raise ReviewError('Save choices or discard pending changes before preparing INCEpTION artifacts.')
            if controls.before_export is not None:
                await controls.before_export()
            stamp = project.stamp()
            template_stamp = template.stamp() if template is not None else None

            def current():
                return (not self.closed and not self.inputs.closed and self.inputs.revision == input_revision
                        and self.review.state is state and controls.session is session and session.revision == revision
                        and self.inputs.project.snapshot() == project and project.stamp() == stamp
                        and self.template.snapshot() == template and (template is None or template.stamp() == template_stamp))

            snapshot = ReviewSession(state, saved=copy.deepcopy(session.saved), rules=copy.deepcopy(session.rules),
                                     reviewed_documents=set(session.reviewed_documents),
                                     imported_metadata=copy.deepcopy(session.imported_metadata), rules_stale=session.rules_stale)
            text = await run.io_bound(snapshot.export_text)
            if not current():
                raise ReviewError('Inputs or review changed while preparing the package. Save choices and try again.')
            content = await run.cpu_bound(build_store_review_package, project.path, text,
                                          store_scope=store_scope, annotators=annotators,
                                          project_template=template.path if template is not None else None)
            if not current():
                raise ReviewError('Inputs or review changed while preparing the package. Save choices and try again.')
            self.ui.download.content(content, 'inception-review-package.zip', media_type='application/zip')
            self.status.set_text('Prepared offline. No INCEpTION connection or upload occurred. Deployment instructions are inside the ZIP.')
        except (ValueError, ReviewError) as error:
            if not self.closed:
                self.status.set_text(str(error))
        except Exception:
            if not self.closed:
                self.status.set_text('Could not prepare preserved CAS. Check the store, export scope and project template.')
        finally:
            self.busy = False
            self.refresh()
