# Page Layout | NiceGUI

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

# Page *Layout*

## Auto-context

In order to allow writing intuitive UI descriptions, NiceGUI automatically tracks the context in which elements are created.
This means that there is no explicit `parent` parameter.
Instead the parent context is defined using a `with` statement.
It is also passed to event handlers and timers.

In the demo, the label "Card content" is added to the card.
And because the `ui.button` is also added to the card, the label "Click!" will also be created in this context.
The label "Tick!", which is added once after one second, is also added to the card.

This design decision allows for easily creating modular components that keep working after moving them around in the UI.
For example, you can move label and button somewhere else, maybe wrap them in another container, and the code will still work.

main.py

[Button]

````python
from nicegui import ui

with ui.card():
    ui.label('Card content')
    ui.button('Add label', on_click=lambda: ui.label('Click!'))
    ui.timer(1.0, lambda: ui.label('Tick!'), once=True)

ui.run()
````

## [Card](/documentation/card)

This element is based on Quasar's `QCard <https://quasar.dev/vue-components/card>`_ component.
It provides a container with a dropped shadow.

Note:
In contrast to this element,
the original QCard has no padding by default and hides outer borders and shadows of nested elements.
If you want the original behavior, use the ``tight`` method.

*Updated in version 2.0.0: Don't hide outer borders and shadows of nested elements anymore.*

:align_items: alignment of the items in the card ("start", "end", "center", "baseline", or "stretch"; default: ``None``)

main.py

[Button]

````python
from nicegui import ui

with ui.card().tight():
    ui.image('https://picsum.photos/id/684/640/360')
    with ui.card_section():
        ui.label('Lorem ipsum dolor sit amet, consectetur adipiscing elit, ...')

ui.run()
````

[See more →](/documentation/card)

## [Column Element](/documentation/column)

Provides a container which arranges its child in a column.

:wrap: whether to wrap the content (default: ``False``)
:align_items: alignment of the items in the column ("start", "end", "center", "baseline", or "stretch"; default: ``None``)

main.py

[Button]

````python
from nicegui import ui

with ui.column():
    ui.label('label 1')
    ui.label('label 2')
    ui.label('label 3')

ui.run()
````

[See more →](/documentation/column)

## [Row Element](/documentation/row)

Provides a container which arranges its child in a row.

:wrap: whether to wrap the content (default: ``True``)
:align_items: alignment of the items in the row ("start", "end", "center", "baseline", or "stretch"; default: ``None``)

main.py

[Button]

````python
from nicegui import ui

with ui.row():
    ui.label('label 1')
    ui.label('label 2')
    ui.label('label 3')

ui.run()
````

[See more →](/documentation/row)

## [Grid Element](/documentation/grid)

Provides a container which arranges its child in a grid.

:rows: number of rows in the grid or a string with the grid-template-rows CSS property (e.g. 'auto 1fr')
:columns: number of columns in the grid or a string with the grid-template-columns CSS property (e.g. 'auto 1fr')

main.py

[Button]

````python
from nicegui import ui

with ui.grid(columns=2):
    ui.label('Name:')
    ui.label('Tom')

    ui.label('Age:')
    ui.label('42')

    ui.label('Height:')
    ui.label('1.80m')

ui.run()
````

[See more →](/documentation/grid)

## [List](/documentation/list)

A list element based on Quasar's `QList <https://quasar.dev/vue-components/list-and-list-items#qlist-api>`_ component.
It provides a container for ``ui.item`` elements.

main.py

[Button]

````python
from nicegui import ui

with ui.list().props('dense separator'):
    ui.item('3 Apples')
    ui.item('5 Bananas')
    ui.item('8 Strawberries')
    ui.item('13 Walnuts')

ui.run()
````

[See more →](/documentation/list)

## [Slide Item](/documentation/slide_item)

This element is based on Quasar's `QSlideItem <https://quasar.dev/vue-components/slide-item/>`_ component.

If the ``text`` parameter is provided, a nested ``ui.item`` element will be created with the given text.
If you want to customize how the text is displayed, you can place custom elements inside the slide item.

To fill slots for individual slide actions, use the ``left``, ``right``, ``top``, or ``bottom`` methods or
the ``action`` method with a side argument ("left", "right", "top", or "bottom").

Once a slide action has occurred, the slide item can be reset back to its initial state using the ``reset`` method.

*Added in version 2.12.0*

:text: text to be displayed (default: "")
:on_slide: callback which is invoked when any slide action is activated

main.py

[Button]

````python
from nicegui import ui

with ui.list().props('bordered separator'):
    with ui.slide_item('Slide me left or right') as slide_item_1:
        slide_item_1.left('Left', color='green')
        slide_item_1.right('Right', color='red')
    with ui.slide_item('Slide me up or down') as slide_item_2:
        slide_item_2.top('Top', color='blue')
        slide_item_2.bottom('Bottom', color='purple')

ui.run()
````

[See more →](/documentation/slide_item)

## [Fullscreen control element](/documentation/fullscreen)

This element is based on Quasar's `AppFullscreen <https://quasar.dev/quasar-plugins/app-fullscreen>`_ plugin
and provides a way to enter, exit and toggle the fullscreen mode.

Important notes:

* Due to security reasons, the fullscreen mode can only be entered from a previous user interaction such as a button click.
* The long-press escape requirement only works in some browsers like Google Chrome or Microsoft Edge.

*Added in version 2.11.0*

:require_escape_hold: whether the user needs to long-press the escape key to exit fullscreen mode
:on_value_change: callback which is invoked when the fullscreen state changes

main.py

[Button]

````python
from nicegui import ui

fullscreen = ui.fullscreen()

ui.button('Enter Fullscreen', on_click=fullscreen.enter)
ui.button('Exit Fullscreen', on_click=fullscreen.exit)
ui.button('Toggle Fullscreen', on_click=fullscreen.toggle)

ui.run()
````

[See more →](/documentation/fullscreen)

## [Skip link](/documentation/skip_link)

A keyboard-only "skip link" that is hidden until it receives focus via Tab
and moves keyboard focus to ``target`` when activated.
It lets keyboard users bypass repetitive navigation,
satisfying `WCAG 2.4.1 "Bypass Blocks" <https://www.w3.org/WAI/WCAG21/Understanding/bypass-blocks.html>`_.

Rendered as an ``<a href="#...">`` element so the browser handles fragment navigation natively;
an additional click handler sets ``tabindex="-1"`` on the target
so non-focusable elements (e.g. a ``<div>``) still receive focus.

The link is automatically moved to the top of the page layout so it is the first element the keyboard reaches.
Multiple skip links are kept in creation order.

Pass ``text=''`` and use the element as a context manager
to supply custom child content (e.g. an icon next to a label).

The target is resolved by its ID captured at creation time,
so ``target`` should be a stable container rather than transient content that is recreated
(e.g. by a refreshable or a sub-page route change), otherwise the link silently does nothing.

*Added in version 3.13.0*

:text: the link label (default: "Skip to main content")
:target: the element to move focus to when the link is activated

main.py

[Button]

````python
from nicegui import ui

@ui.page('/skip_link_demo')
def skip_link_demo():
    ui.button('Navigation 1')
    ui.button('Navigation 2')
    main = ui.label('Press Tab to reveal the skip link, then Enter to jump here.')
    ui.skip_link(target=main)

@ui.page('/')
def page():
    ui.link('show page with skip link', skip_link_demo)

ui.run()
````

[See more →](/documentation/skip_link)

## Clear Containers

To remove all elements from a row, column or card container, use can call
```py
container.clear()
```

Alternatively, you can remove individual elements by calling

- `container.remove(element: Element)`,
- `container.remove(index: int)`, or
- `element.delete()`.

main.py

[Button]

````python
from nicegui import ui

container = ui.row()

def add_face():
    with container:
        ui.icon('face')
add_face()

ui.button('Add', on_click=add_face)
ui.button('Remove', on_click=lambda: container.remove(0) if list(container) else None)
ui.button('Clear', on_click=container.clear)

ui.run()
````

## [Sortable](/documentation/sortable)

Container elements like `ui.column`, `ui.row`, and `ui.card` can be made sortable via drag-and-drop
using the `make_sortable()` method.
It returns a `Sortable` controller for enabling, disabling, or changing the sort behavior.

Note: Only direct children of the container are sortable; nested containers can be made sortable independently.

*Added in version 3.11.0*

main.py

[Button]

````python
from nicegui import ui

with ui.card() as card:
    for name in ['Alice', 'Bob', 'Carol']:
        ui.label(name).classes('cursor-grab active:cursor-grabbing')
card.make_sortable(on_end=lambda e: ui.notify(f'Moved from {e.old_index} to {e.new_index}'))

ui.run()
````

[See more →](/documentation/sortable)

## [Teleport](/documentation/teleport)

An element that allows us to transmit the content from within a component to any location on the page.

:to: NiceGUI element or CSS selector of the target element for the teleported content

main.py

[Button]

````python
from nicegui import ui

markdown = ui.markdown('Enter your **name**!')

def inject_input():
    with ui.teleport(f'#{markdown.html_id} strong'):
        ui.input('name').classes('inline-flex').props('dense outlined')

ui.button('inject input', on_click=inject_input)

ui.run()
````

[See more →](/documentation/teleport)

## [Keep Alive](/documentation/keep_alive)

Wraps its children so they stay mounted in the DOM even when the surrounding container is currently not visible
(e.g. an inactive ``ui.tab_panel``, a closed ``ui.dialog`` or ``ui.menu``, or a sub-page that is not currently routed to).

This is useful for elements whose client-side state would otherwise be lost or unreachable before first display:
writing to a ``ui.xterm`` inside a never-opened tab, reading ``ui.aggrid.get_client_data()`` from a closed dialog,
or preserving edit history in a ``ui.codemirror`` when switching between tabs.
Method calls and events on the inner elements are executed immediately on the live component instance.
They are never buffered or replayed.

Internally the children are rendered into a hidden host at the page root
and teleported to the wrapper's location whenever it becomes visible.
As a consequence, the server-side element tree parents the children to this host, not to the surrounding container:
``descendants()`` on the apparent parent and scoped ``ui.element_filter`` will not traverse into the subtree.
Keep a direct reference to the inner elements if you need to reach them programmatically.

Note that this keeps the children alive for the full lifetime of the client, which costs memory.
Only use it where eager mounting is actually required.
Because state is tied to the client, ``ui.keep_alive`` cannot preserve anything across ``@ui.page`` navigation,
which creates a fresh client every time;
it only helps within a single page (inactive tabs, closed dialogs, unrouted sub-pages).

*Added in version 3.11.0*

main.py

[Button]

````python
from nicegui import ui

with ui.tabs() as tabs:
    ui.tab('Other')
    ui.tab('Terminal')
with ui.tab_panels(tabs, value='Other'):
    with ui.tab_panel('Other'):
        ui.label('Open the second tab to see the buffered output.')
    with ui.tab_panel('Terminal'):
        with ui.keep_alive():
            terminal = ui.xterm({'cols': 28, 'rows': 9})

ui.button('Write hello', on_click=lambda: terminal.writeln('Hello, NiceGUI!'))

ui.run()
````

[See more →](/documentation/keep_alive)

## [Expansion Element](/documentation/expansion)

Provides an expandable container based on Quasar's `QExpansionItem <https://quasar.dev/vue-components/expansion-item>`_ component.

:text: title text
:caption: optional caption (or sub-label) text
:icon: optional icon (default: None)
:group: optional group name for coordinated open/close state within the group a.k.a. "accordion mode"
:value: whether the expansion should be opened on creation (default: ``False``)
:on_value_change: callback to execute when value changes

main.py

[Button]

````python
from nicegui import ui

with ui.expansion('Expand!', icon='work').classes('w-full'):
    ui.label('inside the expansion')

ui.run()
````

[See more →](/documentation/expansion)

## [Scroll Area](/documentation/scroll_area)

A way of customizing the scrollbars by encapsulating your content.
This element exposes the Quasar `ScrollArea <https://quasar.dev/vue-components/scroll-area/>`_ component.

:on_scroll: function to be called when the scroll position changes

main.py

[Button]

````python
from nicegui import ui

with ui.row():
    with ui.scroll_area().classes('size-32 border'):
        ui.label('I scroll. ' * 20)
    with ui.column().classes('p-4 size-32 border'):
        ui.label('I will not scroll. ' * 10)

ui.run()
````

[See more →](/documentation/scroll_area)

## [Separator](/documentation/separator)

This element is based on Quasar's `QSeparator <https://quasar.dev/vue-components/separator>`_ component.

It serves as a separator for cards, menus and other component containers and is similar to HTML's <hr> tag.

main.py

[Button]

````python
from nicegui import ui

ui.label('text above')
ui.separator()
ui.label('text below')

ui.run()
````

[See more →](/documentation/separator)

## [Space](/documentation/space)

This element is based on Quasar's `QSpace <https://quasar.dev/vue-components/space>`_ component.

Its purpose is to simply fill all available space inside of a flexbox element.

main.py

[Button]

````python
from nicegui import ui

with ui.row().classes('w-full border'):
    ui.label('Left')
    ui.space()
    ui.label('Right')

ui.run()
````

[See more →](/documentation/space)

## [Skeleton](/documentation/skeleton)

This element is based on Quasar's `QSkeleton <https://quasar.dev/vue-components/skeleton>`_ component.
It serves as a placeholder for loading content in cards, menus and other component containers.
See the `Quasar documentation <https://quasar.dev/vue-components/skeleton/#predefined-types>`_ for a list of available types.

:type: type of skeleton to display (default: "rect")
:tag: HTML tag to use for this element (default: "div")
:animation: animation effect of the skeleton placeholder (default: "wave")
:animation_speed: animation speed in seconds (default: 1.5)
:square: whether to remover border-radius so borders are squared (default: ``False``)
:bordered: whether to apply a default border to the component (default: ``False``)
:size: size in CSS units (overrides ``width`` and ``height``)
:width: width in CSS units (overridden by ``size`` if set)
:height: height in CSS units (overridden by ``size`` if set)

main.py

[Button]

````python
from nicegui import ui

ui.skeleton().classes('w-full')

ui.run()
````

[See more →](/documentation/skeleton)

## [Splitter](/documentation/splitter)

The ``ui.splitter`` element divides the screen space into resizable sections,
allowing for flexible and responsive layouts in your application.

Based on Quasar's Splitter component:
`Splitter <https://quasar.dev/vue-components/splitter>`_

It provides three customizable slots, ``before``, ``after``, and ``separator``,
which can be used to embed other elements within the splitter.

:horizontal: Whether to split horizontally instead of vertically
:reverse: Whether to apply the model size to the second panel instead of the first
:limits: Two numbers representing the minimum and maximum split size of the two panels
:value: Size of the first panel (or second if using reverse)
:on_change: callback which is invoked when the user releases the splitter

main.py

[Button]

````python
from nicegui import ui

with ui.splitter() as splitter:
    with splitter.before:
        ui.label('This is some content on the left hand side.').classes('mr-2')
    with splitter.after:
        ui.label('This is some content on the right hand side.').classes('ml-2')

ui.run()
````

[See more →](/documentation/splitter)

## [Tabs](/documentation/tabs)

The elements `ui.tabs`, `ui.tab`, `ui.tab_panels`, and `ui.tab_panel` resemble
[Quasar's tabs](https://quasar.dev/vue-components/tabs) and
[tab panels](https://quasar.dev/vue-components/tab-panels) API.

`ui.tabs` creates a container for the tabs. This could be placed in a `ui.header` for example.
`ui.tab_panels` creates a container for the tab panels with the actual content.
Each `ui.tab_panel` is associated with a `ui.tab` element.

main.py

[Button]

````python
from nicegui import ui

with ui.tabs().classes('w-full') as tabs:
    one = ui.tab('One')
    two = ui.tab('Two')
with ui.tab_panels(tabs, value=two).classes('w-full'):
    with ui.tab_panel(one):
        ui.label('First tab')
    with ui.tab_panel(two):
        ui.label('Second tab')

ui.run()
````

[See more →](/documentation/tabs)

## [Stepper](/documentation/stepper)

This element represents `Quasar's QStepper <https://quasar.dev/vue-components/stepper#qstepper-api>`_ component.
It contains individual steps.

To avoid issues with dynamic elements when switching steps,
this element uses Vue's `keep-alive <https://vuejs.org/guide/built-ins/keep-alive.html>`_ component.
If client-side performance is an issue, you can disable this feature.

:value: ``ui.step`` or name of the step to be initially selected (default: ``None`` meaning the first step)
:on_value_change: callback to be executed when the selected step changes
:keep_alive: whether to use Vue's keep-alive component on the content (default: ``True``)

main.py

[Button]

````python
from nicegui import ui

with ui.stepper().props('vertical').classes('w-full') as stepper:
    with ui.step('Preheat'):
        ui.label('Preheat the oven to 350 degrees')
        with ui.stepper_navigation():
            ui.button('Next', on_click=stepper.next)
    with ui.step('Ingredients'):
        ui.label('Mix the ingredients')
        with ui.stepper_navigation():
            ui.button('Next', on_click=stepper.next)
            ui.button('Back', on_click=stepper.previous).props('flat')
    with ui.step('Bake'):
        ui.label('Bake for 20 minutes')
        with ui.stepper_navigation():
            ui.button('Done', on_click=lambda: ui.notify('Yay!', type='positive'))
            ui.button('Back', on_click=stepper.previous).props('flat')

ui.run()
````

[See more →](/documentation/stepper)

## [Timeline](/documentation/timeline)

This element represents `Quasar's QTimeline <https://quasar.dev/vue-components/timeline#qtimeline-api>`_ component.

:side: Side ("left" or "right"; default: "left").
:layout: Layout ("dense", "comfortable" or "loose"; default: "dense").
:color: Color of the icons.

main.py

[Button]

````python
from nicegui import ui

with ui.timeline(side='right'):
    ui.timeline_entry('Rodja and Falko start working on NiceGUI.',
                      title='Initial commit',
                      subtitle='May 07, 2021')
    ui.timeline_entry('The first PyPI package is released.',
                      title='Release of 0.1',
                      subtitle='May 14, 2021')
    ui.timeline_entry('Large parts are rewritten to remove JustPy '
                      'and to upgrade to Vue 3 and Quasar 2.',
                      title='Release of 1.0',
                      subtitle='December 15, 2022',
                      icon='rocket')

ui.run()
````

[See more →](/documentation/timeline)

## [Carousel](/documentation/carousel)

This element represents `Quasar's QCarousel <https://quasar.dev/vue-components/carousel#qcarousel-api>`_ component.
It contains individual carousel slides.

:value: ``ui.carousel_slide`` or name of the slide to be initially selected (default: ``None`` meaning the first slide)
:on_value_change: callback to be executed when the selected slide changes
:animated: whether to animate slide transitions (default: ``False``)
:arrows: whether to show arrows for manual slide navigation (default: ``False``)
:navigation: whether to show navigation dots for manual slide navigation (default: ``False``)

main.py

[Button]

````python
from nicegui import ui

with ui.carousel(animated=True, arrows=True, navigation=True).props('height=180px'):
    with ui.carousel_slide().classes('p-0'):
        ui.image('https://picsum.photos/id/30/270/180').classes('w-[270px]')
    with ui.carousel_slide().classes('p-0'):
        ui.image('https://picsum.photos/id/31/270/180').classes('w-[270px]')
    with ui.carousel_slide().classes('p-0'):
        ui.image('https://picsum.photos/id/32/270/180').classes('w-[270px]')

ui.run()
````

[See more →](/documentation/carousel)

## [Pagination](/documentation/pagination)

A pagination element wrapping Quasar's `QPagination <https://quasar.dev/vue-components/pagination>`_ component.

:min: minimum page number
:max: maximum page number
:direction_links: whether to show direction links (previous/next); use ``.props('boundary-links')`` for first/last links
:value: initial page (defaults to ``min`` if no value is provided)
:on_change: callback to be invoked when the value changes

main.py

[Button]

````python
from nicegui import ui

p = ui.pagination(1, 5, direction_links=True)
ui.label().bind_text_from(p, 'value', lambda v: f'Page {v}')

ui.run()
````

[See more →](/documentation/pagination)

## [Menu](/documentation/menu)

Creates a menu based on Quasar's `QMenu <https://quasar.dev/vue-components/menu>`_ component.
The menu should be placed inside the element where it should be shown.

Advanced tip:
Use the ``auto-close`` prop to automatically close the menu on any click event directly without a server round-trip.

:value: whether the menu is already opened (default: ``False``)

main.py

[Button]

````python
from nicegui import ui

with ui.row().classes('w-full items-center'):
    result = ui.label().classes('mr-auto')
    with ui.button(icon='menu'):
        with ui.menu() as menu:
            ui.menu_item('Menu item 1', lambda: result.set_text('Selected item 1'))
            ui.menu_item('Menu item 2', lambda: result.set_text('Selected item 2'))
            ui.menu_item('Menu item 3 (keep open)',
                         lambda: result.set_text('Selected item 3'), auto_close=False)
            ui.separator()
            ui.menu_item('Close', menu.close)

ui.run()
````

[See more →](/documentation/menu)

## [Context Menu](/documentation/context_menu)

Creates a context menu based on Quasar's `QMenu <https://quasar.dev/vue-components/menu>`_ component.
The context menu should be placed inside the element where it should be shown.
It is automatically opened when the user right-clicks on the element and appears at the mouse position.

main.py

[Button]

````python
from nicegui import ui

with ui.image('https://picsum.photos/id/377/640/360'):
    with ui.context_menu():
        ui.menu_item('Flip horizontally')
        ui.menu_item('Flip vertically')
        ui.separator()
        ui.menu_item('Reset', auto_close=False)

ui.run()
````

[See more →](/documentation/context_menu)

## [Popup](/documentation/popup)

Creates a popup based on Quasar's `QPopupProxy <https://quasar.dev/vue-components/popup-proxy>`_ component.
The popup should be placed inside the element where it should be shown
and opens when the user clicks on that element.
Depending on the screen width, it is displayed as a menu or,
below the "breakpoint" prop (default: 450px), as a dialog.

*Added in version 3.15.0*

:value: whether the popup is already opened (default: ``False``)

main.py

[Button]

````python
from nicegui import app, ui

app.storage.client['name'] = 'NiceGUI User'

with ui.label().bind_text_from(app.storage.client, 'name').classes('cursor-pointer'):
    with ui.popup() as popup:
        ui.input().props('autofocus') \
            .bind_value(app.storage.client, 'name') \
            .on('keydown.enter', popup.close)

ui.run()
````

[See more →](/documentation/popup)

## [Tooltip](/documentation/tooltip)

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

[See more →](/documentation/tooltip)

## [Notification](/documentation/notify)

Displays a notification on the screen.

:message: content of the notification
:position: position on the screen ("top-left", "top-right", "bottom-left", "bottom-right", "top", "bottom", "left", "right" or "center", default: "bottom")
:close_button: optional label of a button to dismiss the notification (default: ``False``)
:type: optional type ("positive", "negative", "warning", "info" or "ongoing")
:color: optional color name
:multi_line: enable multi-line notifications
:\*\*kwargs: additional options according to `Quasar's Notify API <https://quasar.dev/quasar-plugins/notify#notify-api>`_

main.py

[Button]

````python
from nicegui import ui

ui.button('Say hi!', on_click=lambda: ui.notify('Hi!', close_button='OK'))

ui.run()
````

[See more →](/documentation/notify)

## [Notification element](/documentation/notification)

Displays a notification on the screen.
In contrast to ``ui.notify``, this element allows to update the notification message and other properties once the notification is displayed.
The notification can be removed with ``dismiss()``.

:message: content of the notification
:position: position on the screen ("top-left", "top-right", "bottom-left", "bottom-right", "top", "bottom", "left", "right" or "center", default: "bottom")
:close_button: optional label of a button to dismiss the notification (default: ``False``)
:type: optional type ("positive", "negative", "warning", "info" or "ongoing")
:color: optional color name
:multi_line: enable multi-line notifications
:icon: optional name of an icon to be displayed in the notification (default: ``None``)
:spinner: display a spinner in the notification (default: False)
:timeout: optional timeout in seconds after which the notification is dismissed (default: 5.0)
:on_dismiss: optional callback to be invoked when the notification is dismissed
:options: optional dictionary with all options (overrides all other arguments)
:\*\*kwargs: additional options according to `Quasar's Notify API <https://quasar.dev/quasar-plugins/notify#notify-api>`_

main.py

[Button]

````python
import asyncio
from nicegui import ui

async def compute():
    n = ui.notification(timeout=None)
    for i in range(10):
        n.message = f'Computing {i/10:.0%}'
        n.spinner = True
        await asyncio.sleep(0.2)
    n.message = 'Done!'
    n.spinner = False
    await asyncio.sleep(1)
    n.dismiss()

ui.button('Compute', on_click=compute)

ui.run()
````

[See more →](/documentation/notification)

## [Dialog](/documentation/dialog)

Creates a dialog based on Quasar's `QDialog <https://quasar.dev/vue-components/dialog>`_ component.
By default it is dismissible by clicking or pressing ESC.
To make it persistent, set ``.props('persistent')`` on the dialog element.

Note: The dialog is an element.
That means it is not removed when closed, but only hidden.
You should either create it only once and then reuse it, or remove it with ``.clear()`` after dismissal.

*Updated in version 3.16.0: Awaiting a dialog resolves with ``None`` when the dialog is deleted,
e.g. because the client disconnected.*

:value: whether the dialog should be opened on creation (default: ``False``)

main.py

[Button]

````python
from nicegui import ui

with ui.dialog() as dialog, ui.card():
    ui.label('Hello world!')
    ui.button('Close', on_click=dialog.close)

ui.button('Open a dialog', on_click=dialog.open)

ui.run()
````

[See more →](/documentation/dialog)

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