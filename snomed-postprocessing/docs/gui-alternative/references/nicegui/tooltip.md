# ui.tooltip | NiceGUI

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

# ui.*tooltip*

## Tooltip

This element is based on Quasar's `QTooltip <https://quasar.dev/vue-components/tooltip>`_ component.
It can be placed in another element to show additional information on hover.

Instead of passing a string as the first argument, you can also nest other elements inside the tooltip.

:text: the content of the tooltip (default: '')

main.py

[Button]

````python
from nicegui import ui

with ui.button(icon='thumb_up'):
    ui.tooltip('I like this').classes('bg-green')

ui.run()
````

## Tooltip method

Instead of nesting a tooltip element inside another element, you can also use the `tooltip` method.

Note that with this method you cannot apply additional properties (props) or styling directly to the tooltip.
If you need custom styling or properties, nest a `ui.tooltip` element instead.

main.py

[Button]

````python
from nicegui import ui

ui.label('Tooltips...').tooltip('...are shown on mouse over')

ui.run()
````

## Tooltip with HTML

You can use HTML in tooltips by nesting a `ui.html` element.

main.py

[Button]

````python
from nicegui import ui

with ui.label('HTML...'):
    with ui.tooltip():
        ui.html('<b>b</b>, <em>em</em>, <u>u</u>, <s>s</s>', sanitize=False)

ui.run()
````

## Tooltip with other content

Other elements like `ui.images` can also be nested inside a tooltip.

main.py

[Button]

````python
from nicegui import ui

with ui.label('Mountains...'):
    with ui.tooltip().classes('bg-transparent'):
        ui.image('https://picsum.photos/id/377/640/360').classes('w-64')

ui.run()
````

## Reference

## Initializer

:text: the content of the tooltip (default: '')

## Properties

**Inherited properties**

**`classes`**`: 'Classes[Self]'`

The classes of the element.

**`client`**`: 'Client'`

The client this element belongs to.

**`html_id`**`: 'str'`

The ID of the element in the HTML DOM.

*Added in version 2.16.0*, *updated in version 4.0.0*: ``ng-<id>`` instead of ``c<id>``

**`is_deleted`**`: 'bool'`

Whether the element has been deleted.

**`is_ignoring_events`**`: bool`

Return whether the element is currently ignoring events.

**`parent_slot`**`: 'Slot | None' (settable)`

The parent slot of the element.

**`props`**`: 'Props[Self]'`

The props of the element.

**`style`**`: 'Style[Self]'`

The style of the element.

**`text`**`: BindableProperty`

**`visible`**`: BindableProperty`

## Methods

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

**`bind_text`**`(target_object: Any, target_name: str | tuple[str, ...] = 'text', forward: collections.abc.Callable[[Any], Any] | None = None, backward: collections.abc.Callable[[Any], Any] | None = None, strict: bool | None = None) -> Self`

Bind the text of this element to the target object's target_name property.

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

**`bind_text_from`**`(target_object: Any, target_name: str | tuple[str, ...] = 'text', backward: collections.abc.Callable[[Any], Any] | None = None, strict: bool | None = None) -> Self`

Bind the text of this element from the target object's target_name property.

The binding works one way only, from the target to this element.
The update happens immediately and whenever a value changes.
The ``target_name`` parameter also accepts a tuple of strings for nested keys (*since version 3.10.0*).

:param target_object: The object to bind from.
:param target_name: The name of the property to bind from.
:param backward: A function to apply to the value before applying it to this element (default: identity).
:param strict: Whether to check (and raise) if the target object has the specified property (default: None,
    performs a check if the object is not a dictionary, *added in version 3.0.0*).

**`bind_text_to`**`(target_object: Any, target_name: str | tuple[str, ...] = 'text', forward: collections.abc.Callable[[Any], Any] | None = None, strict: bool | None = None) -> Self`

Bind the text of this element to the target object's target_name property.

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

**`set_text`**`(text: str) -> Self`

Set the text of this element.

:param text: The new text.

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

- `TextElement`
- `Element`
- `Visibility`

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