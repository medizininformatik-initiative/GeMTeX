# ui.upload | NiceGUI

[Button: icon:menu]

[](/)

[Installation](/#installation)

[Features](/#features)

[Demos](/#demos)

[Documentation](/documentation)

[Examples](/examples)

[Why?](/#why)

[Button]

[Button]

[Button]

[](https://github.com/zauberzeug/nicegui/)

[Button: icon:more_vert]

# ui.*upload*

## File Upload

Based on Quasar's `QUploader <https://quasar.dev/vue-components/uploader>`_ component.

Upload event handlers are called in the following order:

1. ``on_begin_upload``: The client begins uploading one or more files to the server.
2. ``on_upload``: The upload of an individual file is complete.
3. ``on_multi_upload``: The upload of all selected files is complete.

The following event handler is already called during the file selection process:

- ``on_rejected``: One or more files have been rejected.

:multiple: allow uploading multiple files at once (default: ``False``)
:max_file_size: maximum file size in bytes (default: ``0``)
:max_total_size: maximum total size of all files in bytes (default: ``0``)
:max_files: maximum number of files (default: ``0``)
:on_begin_upload: callback to execute when upload begins  (*added in version 2.14.0*)
:on_upload: callback to execute for each uploaded file
:on_multi_upload: callback to execute after multiple files have been uploaded
:on_rejected: callback to execute when one or more files have been rejected during file selection
:label: label for the uploader (default: ``''``)
:auto_upload: automatically upload files when they are selected (default: ``False``)

main.py

[Button]

````python
from nicegui import ui

ui.upload(on_upload=lambda e: ui.notify(f'Uploaded {e.file.name}')).classes('max-w-full')

ui.run()
````

## Upload event arguments


    The `UploadEventArguments` class is used to pass the uploaded file to the handler.
    It contains a single field `file` of type `ui.upload.FileUpload`, which contains properties

    - `name: str` and
    - `content_type: str`

    as well as methods for accessing the content:

    - `read()` - read the file contents as bytes,
    - `text()` - read the file contents as text,
    - `json()` - read the file contents as JSON dictionary,
    - `iterate()` - iterate over the file contents as bytes,
    - `save()` - save the file contents to a path,
    - `size()` - get the file size in bytes.

    *Added in version 3.0.0*


## Upload restrictions

In this demo, the upload is restricted to a maximum file size of 1 MB.
When a file is rejected, a notification is shown.

main.py

[Button]

````python
from nicegui import ui

ui.upload(on_upload=lambda e: ui.notify(f'Uploaded {e.file.name}'),
          on_rejected=lambda: ui.notify('Rejected!'),
          max_file_size=1_000_000).classes('max-w-full')

ui.run()
````

## Show file content

In this demo, the uploaded markdown file is shown in a dialog.

main.py

[Button]

````python
from nicegui import events, ui

with ui.dialog().props('full-width') as dialog:
    with ui.card():
        markdown = ui.markdown()

async def handle_upload(e: events.UploadEventArguments):
    markdown.content = await e.file.text()
    dialog.open()

ui.upload(on_upload=handle_upload, max_file_size=1_000_000) \
    .props('accept=.md').classes('max-w-full')

ui.run()
````

## Uploading large files

Large file uploads may encounter issues due to the default file size parameter set within the underlying Starlette library.
To ensure smooth uploads of larger files, it is recommended to increase the `spool_max_size` parameter in Starlette's `MultiPartParser` class from the default of `1024 * 1024` (1 MB) to a higher limit that aligns with the expected file sizes.

This demo increases Starlette Multiparser's `max_file_size` to be kept in RAM to 5 MB.
This change allows the system to handle larger files more efficiently by keeping them in RAM, thus avoiding the need to write data to temporary files on disk and preventing upload "stuttering".

However, be mindful of the potential impact on your server when allowing users to upload large files and retaining them in RAM.

main.py

[Button]

````python
from nicegui import ui
from starlette.formparsers import MultiPartParser

MultiPartParser.spool_max_size = 1024 * 1024 * 5  # 5 MB

ui.upload(on_upload=lambda e: ui.notify(f'Uploaded {e.file.name}')).classes('max-w-full')

ui.run()
````

## Reference for ui.upload

## Initializer

:multiple: allow uploading multiple files at once (default: ``False``)
:max_file_size: maximum file size in bytes (default: ``0``)
:max_total_size: maximum total size of all files in bytes (default: ``0``)
:max_files: maximum number of files (default: ``0``)
:on_begin_upload: callback to execute when upload begins  (*added in version 2.14.0*)
:on_upload: callback to execute for each uploaded file
:on_multi_upload: callback to execute after multiple files have been uploaded
:on_rejected: callback to execute when one or more files have been rejected during file selection
:label: label for the uploader (default: ``''``)
:auto_upload: automatically upload files when they are selected (default: ``False``)

## Properties

**Inherited properties**

**`classes`**`: 'Classes[Self]'`

The classes of the element.

**`client`**`: 'Client'`

The client this element belongs to.

**`enabled`**`: BindableProperty`

**`html_id`**`: 'str'`

The ID of the element in the HTML DOM.

*Added in version 2.16.0*, *updated in version 4.0.0*: ``ng-<id>`` instead of ``c<id>``

**`is_deleted`**`: 'bool'`

Whether the element has been deleted.

**`is_ignoring_events`**`: bool`

Return whether the element is currently ignoring events.

**`is_ignoring_events`**`: bool`

Return whether the element is currently ignoring events.

**`label`**`: BindableProperty`

**`parent_slot`**`: 'Slot | None' (settable)`

The parent slot of the element.

**`props`**`: 'Props[Self]'`

The props of the element.

**`style`**`: 'Style[Self]'`

The style of the element.

**`visible`**`: BindableProperty`

## Methods

**`handle_uploads`**`(files: list[nicegui.elements.upload_files.FileUpload]) -> None`

Handle the uploaded files.

This method is primarily intended for internal use and for simulating file uploads in tests.

**`on_begin_upload`**`(callback: collections.abc.Callable[[nicegui.events.UiEventArguments], Any] | collections.abc.Callable[[], Any]) -> Self`

Add a callback to be invoked when the upload begins.

**`on_multi_upload`**`(callback: collections.abc.Callable[[nicegui.events.MultiUploadEventArguments], Any] | collections.abc.Callable[[], Any]) -> Self`

Add a callback to be invoked when multiple files have been uploaded.

**`on_rejected`**`(callback: collections.abc.Callable[[nicegui.events.UiEventArguments], Any] | collections.abc.Callable[[], Any]) -> Self`

Add a callback to be invoked when one or more files have been rejected during file selection.

**`on_upload`**`(callback: collections.abc.Callable[[nicegui.events.UploadEventArguments], Any] | collections.abc.Callable[[], Any]) -> Self`

Add a callback to be invoked when a file is uploaded.

**`reset`**`() -> Self`

Clear the upload queue.

**Inherited methods**

**`add_dynamic_resource`**`(name: str, function: Callable) -> None`

Add a dynamic resource to the element which returns the result of a function.

:param name: name of the resource
:param function: function that returns the resource response

**`add_resource`**`(path: str | Path) -> None`

Add a resource to the element.

:param path: path to the resource (e.g. folder with CSS and JavaScript files)

**`add_slot`**`(name: str, template: str | None = None) -> Slot`

Add a slot to the element.

NiceGUI is using the slot concept from Vue:
Elements can have multiple slots, each possibly with a number of children.
Most elements only have one slot, e.g. a ``ui.card`` (QCard) only has a default slot.
But more complex elements like ``ui.table`` (QTable) can have more slots like "header", "body" and so on.
If you nest NiceGUI elements via with ``ui.row(): ...`` you place new elements inside of the row's default slot.
But if you use with ``table.add_slot(...): ...``, you enter a different slot.

The slot stack helps NiceGUI to keep track of which slot is currently used for new elements.
The ``parent`` field holds a reference to its element.
Whenever an element is entered via a ``with`` expression, its default slot is automatically entered as well.

:param name: name of the slot
:param template: Vue template of the slot
:return: the slot

**`ancestors`**`(include_self: bool = False) -> Iterator[Element]`

Iterate over the ancestors of the element.

:param include_self: whether to include the element itself in the iteration

**`bind_enabled`**`(target_object: Any, target_name: str | tuple[str, ...] = 'enabled', forward: collections.abc.Callable[[Any], Any] | None = None, backward: collections.abc.Callable[[Any], Any] | None = None, strict: bool | None = None) -> Self`

Bind the enabled state of this element to the target object's target_name property.

The binding works both ways, from this element to the target and from the target to this element.
The update happens immediately and whenever a value changes.
The backward binding takes precedence for the initial synchronization.
The ``target_name`` parameter also accepts a tuple of strings for nested keys (*since version 3.10.0*).

:param target_object: The object to bind to.
:param target_name: The name of the property to bind to.
:param forward: A function to apply to the value before applying it to the target (default: identity).
:param backward: A function to apply to the value before applying it to this element (default: identity).
:param strict: Whether to check (and raise) if the target object has the specified property (default: None,
    performs a check if the object is not a dictionary, *added in version 3.0.0*).

**`bind_enabled_from`**`(target_object: Any, target_name: str | tuple[str, ...] = 'enabled', backward: collections.abc.Callable[[Any], Any] | None = None, strict: bool | None = None) -> Self`

Bind the enabled state of this element from the target object's target_name property.

The binding works one way only, from the target to this element.
The update happens immediately and whenever a value changes.
The ``target_name`` parameter also accepts a tuple of strings for nested keys (*since version 3.10.0*).

:param target_object: The object to bind from.
:param target_name: The name of the property to bind from.
:param backward: A function to apply to the value before applying it to this element (default: identity).
:param strict: Whether to check (and raise) if the target object has the specified property (default: None,
    performs a check if the object is not a dictionary, *added in version 3.0.0*).

**`bind_enabled_to`**`(target_object: Any, target_name: str | tuple[str, ...] = 'enabled', forward: collections.abc.Callable[[Any], Any] | None = None, strict: bool | None = None) -> Self`

Bind the enabled state of this element to the target object's target_name property.

The binding works one way only, from this element to the target.
The update happens immediately and whenever a value changes.
The ``target_name`` parameter also accepts a tuple of strings for nested keys (*since version 3.10.0*).

:param target_object: The object to bind to.
:param target_name: The name of the property to bind to.
:param forward: A function to apply to the value before applying it to the target (default: identity).
:param strict: Whether to check (and raise) if the target object has the specified property (default: None,
    performs a check if the object is not a dictionary, *added in version 3.0.0*).

**`bind_label`**`(target_object: Any, target_name: str | tuple[str, ...] = 'label', forward: collections.abc.Callable[[Any], Any] | None = None, backward: collections.abc.Callable[[Any], Any] | None = None, strict: bool | None = None) -> Self`

Bind the label of this element to the target object's target_name property.

The binding works both ways, from this element to the target and from the target to this element.
The update happens immediately and whenever a value changes.
The backward binding takes precedence for the initial synchronization.
The ``target_name`` parameter also accepts a tuple of strings for nested keys (*since version 3.10.0*).

:param target_object: The object to bind to.
:param target_name: The name of the property to bind to.
:param forward: A function to apply to the value before applying it to the target (default: identity).
:param backward: A function to apply to the value before applying it to this element (default: identity).
:param strict: Whether to check (and raise) if the target object has the specified property (default: None,
    performs a check if the object is not a dictionary, *added in version 3.0.0*).

**`bind_label_from`**`(target_object: Any, target_name: str | tuple[str, ...] = 'label', backward: collections.abc.Callable[[Any], Any] | None = None, strict: bool | None = None) -> Self`

Bind the label of this element from the target object's target_name property.

The binding works one way only, from the target to this element.
The update happens immediately and whenever a value changes.
The ``target_name`` parameter also accepts a tuple of strings for nested keys (*since version 3.10.0*).

:param target_object: The object to bind from.
:param target_name: The name of the property to bind from.
:param backward: A function to apply to the value before applying it to this element (default: identity).
:param strict: Whether to check (and raise) if the target object has the specified property (default: None,
    performs a check if the object is not a dictionary, *added in version 3.0.0*).

**`bind_label_to`**`(target_object: Any, target_name: str | tuple[str, ...] = 'label', forward: collections.abc.Callable[[Any], Any] | None = None, strict: bool | None = None) -> Self`

Bind the label of this element to the target object's target_name property.

The binding works one way only, from this element to the target.
The update happens immediately and whenever a value changes.
The ``target_name`` parameter also accepts a tuple of strings for nested keys (*since version 3.10.0*).

:param target_object: The object to bind to.
:param target_name: The name of the property to bind to.
:param forward: A function to apply to the value before applying it to the target (default: identity).
:param strict: Whether to check (and raise) if the target object has the specified property (default: None,
    performs a check if the object is not a dictionary, *added in version 3.0.0*).

**`bind_visibility`**`(target_object: Any, target_name: str | tuple[str, ...] = 'visible', forward: collections.abc.Callable[[Any], Any] | None = None, backward: collections.abc.Callable[[Any], Any] | None = None, value: Any = None, strict: bool | None = None) -> Self`

Bind the visibility of this element to the target object's target_name property.

The binding works both ways, from this element to the target and from the target to this element.
The update happens immediately and whenever a value changes.
The backward binding takes precedence for the initial synchronization.
The ``target_name`` parameter also accepts a tuple of strings for nested keys (*since version 3.10.0*).

:param target_object: The object to bind to.
:param target_name: The name of the property to bind to.
:param forward: A function to apply to the value before applying it to the target (default: identity).
:param backward: A function to apply to the value before applying it to this element (default: identity).
:param value: If specified, the element will be visible only when the target value is equal to this value.
:param strict: Whether to check (and raise) if the target object has the specified property (default: None,
    performs a check if the object is not a dictionary, *added in version 3.0.0*).

**`bind_visibility_from`**`(target_object: Any, target_name: str | tuple[str, ...] = 'visible', backward: collections.abc.Callable[[Any], Any] | None = None, value: Any = None, strict: bool | None = None) -> Self`

Bind the visibility of this element from the target object's target_name property.

The binding works one way only, from the target to this element.
The update happens immediately and whenever a value changes.
The ``target_name`` parameter also accepts a tuple of strings for nested keys (*since version 3.10.0*).

:param target_object: The object to bind from.
:param target_name: The name of the property to bind from.
:param backward: A function to apply to the value before applying it to this element (default: identity).
:param value: If specified, the element will be visible only when the target value is equal to this value.
:param strict: Whether to check (and raise) if the target object has the specified property (default: None,
    performs a check if the object is not a dictionary, *added in version 3.0.0*).

**`bind_visibility_to`**`(target_object: Any, target_name: str | tuple[str, ...] = 'visible', forward: collections.abc.Callable[[Any], Any] | None = None, strict: bool | None = None) -> Self`

Bind the visibility of this element to the target object's target_name property.

The binding works one way only, from this element to the target.
The update happens immediately and whenever a value changes.
The ``target_name`` parameter also accepts a tuple of strings for nested keys (*since version 3.10.0*).

:param target_object: The object to bind to.
:param target_name: The name of the property to bind to.
:param forward: A function to apply to the value before applying it to the target (default: identity).
:param strict: Whether to check (and raise) if the target object has the specified property (default: None,
    performs a check if the object is not a dictionary, *added in version 3.0.0*).

**`clear`**`() -> Self`

Remove all child elements.

`@classmethod`<br />**`default_classes`**`(add: str | None = None, remove: str | None = None, toggle: str | None = None, replace: str | None = None) -> type[Self]`

Apply, remove, toggle, or replace default HTML classes.

This allows modifying the look of the element or its layout using `Tailwind <https://tailwindcss.com/>`_ or `Quasar <https://quasar.dev/>`_ classes.

Removing or replacing classes can be helpful if predefined classes are not desired.
All elements of this class will share these HTML classes.
These must be defined before element instantiation.

:param add: whitespace-delimited string of classes
:param remove: whitespace-delimited string of classes to remove from the element
:param toggle: whitespace-delimited string of classes to toggle (*added in version 2.7.0*)
:param replace: whitespace-delimited string of classes to use instead of existing ones

`@classmethod`<br />**`default_props`**`(add: str | None = None, remove: str | None = None) -> type[Self]`

Add or remove default props.

This allows modifying the look of the element or its layout using `Quasar <https://quasar.dev/>`_ props.
Since props are simply applied as HTML attributes, they can be used with any HTML element.
All elements of this class will share these props.
These must be defined before element instantiation.

Boolean properties are assumed ``True`` if no value is specified.

:param add: whitespace-delimited list of either boolean values or key=value pair to add
:param remove: whitespace-delimited list of property keys to remove

`@classmethod`<br />**`default_style`**`(add: str | None = None, remove: str | None = None, replace: str | None = None) -> type[Self]`

Apply, remove, or replace default CSS definitions.

Removing or replacing styles can be helpful if the predefined style is not desired.
All elements of this class will share these CSS definitions.
These must be defined before element instantiation.

:param add: semicolon-separated list of styles to add to the element
:param remove: semicolon-separated list of styles to remove from the element
:param replace: semicolon-separated list of styles to use instead of existing ones

**`delete`**`() -> None`

Delete the element and all its children.

**`descendants`**`(include_self: bool = False) -> Iterator[Element]`

Iterate over the descendants of the element.

:param include_self: whether to include the element itself in the iteration

**`disable`**`() -> Self`

Disable the element.

**`enable`**`() -> Self`

Enable the element.

**`get_computed_prop`**`(prop_name: str, timeout: float = 1) -> AwaitableResponse`

Return a computed property.

This function should be awaited so that the computed property is properly returned.

:param prop_name: name of the computed prop
:param timeout: maximum time to wait for a response (default: 1 second)

**`mark`**`(*markers: str) -> Self`

Replace markers of the element.

Markers are used to identify elements for querying with `ElementFilter </documentation/element_filter>`_
which is heavily used in testing
but can also be used to reduce the number of global variables or passing around dependencies.

:param \*markers: list of strings or single string with whitespace-delimited markers; replaces existing markers

**`move`**`(target_container: Element | None = None, target_index: int = -1, target_slot: str | None = None) -> Self`

Move the element to another container.

:param target_container: container to move the element to (default: the parent container)
:param target_index: index within the target slot (default: append to the end)
:param target_slot: slot within the target container (default: default slot)

**`on`**`(type: str, handler: events.Handler[events.GenericEventArguments] | None = None, args: Sequence[str] | Sequence[Sequence[str] | None] | None = None, throttle: float = 0.0, leading_events: bool = True, trailing_events: bool = True, js_handler: str = '(...args) => emit(...args)') -> Self`

Subscribe to an event.

The event handler can be a Python function, a JavaScript function or a combination of both:

- If you want to handle the event on the server with all (serializable) event arguments,
  use a Python ``handler``.
- If you want to handle the event on the client side without emitting anything to the server,
  use ``js_handler`` with a JavaScript function handling the event.
- If you want to handle the event on the server with a subset or transformed version of the event arguments,
  use ``js_handler`` with a JavaScript function emitting the transformed arguments using ``emit()``, and
  use a Python ``handler`` to handle these arguments on the server side.
  The ``js_handler`` can also decide to selectively emit arguments to the server,
  in which case the Python ``handler`` will not always be called.

Note that the arguments ``throttle``, ``leading_events``, and ``trailing_events`` are only relevant
when emitting events to the server.

*Updated in version 2.18.0: Both handlers can be specified at the same time.*

:param type: name of the event (e.g. "click", "mousedown", or "update:model-value")
:param handler: callback that is called upon occurrence of the event
:param args: arguments included in the event message sent to the event handler (default: ``None`` meaning all)
:param throttle: minimum time (in seconds) between event occurrences (default: 0.0)
:param leading_events: whether to trigger the event handler immediately upon the first event occurrence (default: ``True``)
:param trailing_events: whether to trigger the event handler after the last event occurrence (default: ``True``)
:param js_handler: JavaScript function that is handling the event on the client (default: "(...args) => emit(...args)")

**`remove`**`(element: Element | int) -> None`

Remove a child element.

:param element: either the element instance or its ID

**`run_method`**`(name: str, *args: Any, timeout: float = 1) -> AwaitableResponse`

Run a method on the client side.

If the function is awaited, the result of the method call is returned.
Otherwise, the method is executed without waiting for a response.

:param name: name of the method
:param \*args: arguments to pass to the method
:param timeout: maximum time to wait for a response (default: 1 second)

**`set_enabled`**`(value: bool) -> Self`

Set the enabled state of the element.

**`set_label`**`(label: str | None) -> Self`

Set the label of this element.

:param label: The new label.

**`set_visibility`**`(visible: bool) -> Self`

Set the visibility of this element.

:param visible: Whether the element should be visible.

**`tooltip`**`(text: str) -> Self`

Add a tooltip to the element.

:param text: text of the tooltip

**`update`**`() -> None`

Update the element on the client side.

Subclasses can override this to rebuild derived state before calling ``super().update()``.

## Inheritance

- `LabelElement`
- `DisableableElement`
- `Element`
- `Visibility`

## Reference for ui.upload.FileUpload

## Methods

**`iterate`**`(chunk_size: int = 1048576) -> collections.abc.AsyncIterator[bytes]`

Iterate over the file contents as bytes.

:param chunk_size: the size of each chunk to read in bytes (default: 1 MB)

**`json`**`(encoding: str = 'utf-8') -> dict`

Read the file contents as JSON dictionary.

:param encoding: the encoding to use for the text (default: "utf-8")

**`read`**`() -> bytes`

Read the file contents as bytes.

**`save`**`(path: str | pathlib.Path) -> None`

Save the file contents to a path.

:param path: the path to save the file contents to

**`size`**`() -> int`

Get the file size in bytes.

**`text`**`(encoding: str = 'utf-8') -> str`

Read the file contents as text.

:param encoding: the encoding to use for the text (default: "utf-8")

**Nice**GUI

The Python UI framework that shows up in your browser.

[](https://github.com/zauberzeug/nicegui/)

[](https://discord.gg/TEpFeAaF4f)

[](https://www.reddit.com/r/nicegui/)

Resources

[Documentation](/documentation)

[Examples](/examples)

[LLM reference](/llms.txt)

[GitHub](https://github.com/zauberzeug/nicegui/)

[PyPI](https://pypi.org/project/nicegui/)

Community

[Discussions](https://github.com/zauberzeug/nicegui/discussions)

[Discord](https://discord.gg/TEpFeAaF4f)

[Reddit](https://www.reddit.com/r/nicegui/)

[Contributing](https://github.com/zauberzeug/nicegui/blob/main/CONTRIBUTING.md)

[Sponsors](https://github.com/sponsors/zauberzeug)

Legal

[Imprint](/imprint_privacy#imprint)

[Privacy](/imprint_privacy#privacy)

Made with NiceGUI by [Zauberzeug](https://zauberzeug.com)

© 2026 [Zauberzeug GmbH](https://zauberzeug.com)