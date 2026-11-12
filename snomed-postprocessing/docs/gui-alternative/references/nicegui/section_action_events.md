# Action & Events | NiceGUI

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

# Action & *Events*

## [Timer](/documentation/timer)

One major drive behind the creation of NiceGUI was the necessity to have a simple approach to update the interface in regular intervals,
for example to show a graph with incoming measurements.
A timer will execute a callback repeatedly with a given interval.

:interval: the interval in which the timer is called (can be changed during runtime)
:callback: synchronous or asynchronous function to execute when interval elapses
:active: whether the callback should be executed or not (can be changed during runtime)
:once: whether the callback is only executed once after a delay specified by ``interval`` (default: ``False``)
:immediate: whether the callback should be executed immediately (default: ``True``, ignored if ``once`` is ``True``, *added in version 2.9.0*)

main.py

[Button]

````python
from datetime import datetime
from nicegui import ui

label = ui.label()
ui.timer(1.0, lambda: label.set_text(f'{datetime.now():%X}'))

ui.run()
````

[See more →](/documentation/timer)

## [Keyboard](/documentation/keyboard)

Adds global keyboard event tracking.

The ``on_key`` callback receives a ``KeyEventArguments`` object with the following attributes:

- ``sender``: the ``Keyboard`` element
- ``client``: the client object
- ``action``: a ``KeyboardAction`` object with the following attributes:
    - ``keydown``: whether the key was pressed
    - ``keyup``: whether the key was released
    - ``repeat``: whether the key event was a repeat
- ``key``: a ``KeyboardKey`` object with the following attributes:
    - ``name``: the name of the key (e.g. "a", "Enter", "ArrowLeft"; see `here <https://developer.mozilla.org/en-US/docs/Web/API/UI_Events/Keyboard_event_key_values>`_ for a list of possible values)
    - ``code``: the code of the key (e.g. "KeyA", "Enter", "ArrowLeft")
    - ``location``: the location of the key (0 for standard keys, 1 for left keys, 2 for right keys, 3 for numpad keys)
- ``modifiers``: a ``KeyboardModifiers`` object with the following attributes:
    - ``alt``: whether the alt key was pressed
    - ``ctrl``: whether the ctrl key was pressed
    - ``meta``: whether the meta key was pressed
    - ``shift``: whether the shift key was pressed

For convenience, the ``KeyboardKey`` object also has the following properties:
    - ``is_cursorkey``: whether the key is a cursor (arrow) key
    - ``number``: the integer value of a number key (0-9, ``None`` for other keys)
    - ``backspace``, ``tab``, ``enter``, ``shift``, ``control``, ``alt``, ``pause``, ``caps_lock``, ``escape``, ``space``,
      ``page_up``, ``page_down``, ``end``, ``home``, ``arrow_left``, ``arrow_up``, ``arrow_right``, ``arrow_down``,
      ``print_screen``, ``insert``, ``delete``, ``meta``,
      ``f1``, ``f2``, ``f3``, ``f4``, ``f5``, ``f6``, ``f7``, ``f8``, ``f9``, ``f10``, ``f11``, ``f12``: whether the key is the respective key

:on_key: callback to be executed when keyboard events occur.
:active: boolean flag indicating whether the callback should be executed or not (default: ``True``)
:repeating: boolean flag indicating whether held keys should be sent repeatedly (default: ``True``)
:ignore: ignore keys when one of these element types is focussed (default: ``['input', 'select', 'button', 'textarea']``)

main.py

[Button]

````python
from nicegui import events, ui

def handle_key(e: events.KeyEventArguments):
    if e.key == 'f' and not e.action.repeat:
        if e.action.keyup:
            ui.notify('f was just released')
        elif e.action.keydown:
            ui.notify('f was just pressed')
    if e.modifiers.shift and e.action.keydown:
        if e.key.arrow_left:
            ui.notify('going left')
        elif e.key.arrow_right:
            ui.notify('going right')
        elif e.key.arrow_up:
            ui.notify('going up')
        elif e.key.arrow_down:
            ui.notify('going down')

keyboard = ui.keyboard(on_key=handle_key)
ui.label('Key events can be caught globally by using the keyboard element.')
ui.checkbox('Track key events').bind_value_to(keyboard, 'active')

ui.run()
````

[See more →](/documentation/keyboard)

## UI Updates

NiceGUI tries to automatically synchronize the state of UI elements with the client,
e.g. when a label text, an input value or style/classes/props of an element have changed.
In other cases, you can explicitly call `element.update()` or `ui.update(*elements)` to update.
The demo code shows how to update a `ui.radio` after a new option is added.

main.py

[Button]

````python
from nicegui import ui

radio = ui.radio(['A', 'B', 'C'])

ui.button('Add option', on_click=lambda: radio.options.append('D'))
ui.button('Update', on_click=radio.update)

ui.run()
````

## [Refreshable UI functions](/documentation/refreshable)

The ``@ui.refreshable`` decorator allows you to create functions that have a ``refresh`` method.
This method will automatically delete all elements created by the function and recreate them.

For decorating refreshable methods in classes, there is a ``@ui.refreshable_method`` decorator,
which is equivalent but prevents static type checking errors.

main.py

[Button]

````python
import random
from nicegui import ui

numbers = []

@ui.refreshable
def number_ui() -> None:
    ui.label(', '.join(str(n) for n in sorted(numbers)))

def add_number() -> None:
    numbers.append(random.randint(0, 100))
    number_ui.refresh()

number_ui()
ui.button('Add random number', on_click=add_number)

ui.run()
````

[See more →](/documentation/refreshable)

## Async event handlers

Most elements also support asynchronous event handlers.

Note: You can also pass a `functools.partial` into the `on_click` property to wrap async functions with parameters.

main.py

[Button]

````python
import asyncio
from nicegui import ui

async def async_task():
    ui.notify('Asynchronous task started')
    await asyncio.sleep(5)
    ui.notify('Asynchronous task finished')

ui.button('start async task', on_click=async_task)

ui.run()
````

## [Generic Events](/documentation/generic_events)

Most UI elements come with predefined events.
For example, a `ui.button` like "A" in the demo has an `on_click` parameter that expects a synchronous or asynchronous function.
But you can also use the `on` method to register a generic event handler like for "B".
This allows you to register handlers for any event that is supported by JavaScript and Quasar.

For example, you can register a handler for the `mousemove` event like for "C", even though there is no `on_mousemove` parameter for `ui.button`.
Some events, like `mousemove`, are fired very often.
To avoid performance issues, you can use the `throttle` parameter to only call the handler every `throttle` seconds ("D").

The generic event handler can be synchronous or asynchronous and optionally takes `GenericEventArguments` as argument ("E").
You can also specify which attributes of the JavaScript or Quasar event should be passed to the handler ("F").
This can reduce the amount of data that needs to be transferred between the server and the client.

Here you can find more information about the events that are supported:

- <https://developer.mozilla.org/en-US/docs/Web/API/HTMLElement#events> for HTML elements
- <https://quasar.dev/vue-components> for Quasar-based elements (see the "Events" tab on the individual component page)

main.py

[Button]

````python
from nicegui import ui

with ui.row():
    ui.button('A', on_click=lambda: ui.notify('You clicked the button A.'))
    ui.button('B').on('click', lambda: ui.notify('You clicked the button B.'))
with ui.row():
    ui.button('C').on('mousemove', lambda: ui.notify('You moved on button C.'))
    ui.button('D').on('mousemove', lambda: ui.notify('You moved on button D.'), throttle=0.5)
with ui.row():
    ui.button('E').on('mousedown', lambda e: ui.notify(e))
    ui.button('F').on('mousedown', lambda e: ui.notify(e), ['ctrlKey', 'shiftKey'])

ui.run()
````

[See more →](/documentation/generic_events)

## Running CPU-bound tasks

NiceGUI provides a `cpu_bound` function for running CPU-bound tasks in a separate process.
This is useful for long-running computations that would otherwise block the event loop and make the UI unresponsive.
The function returns a future that can be awaited.

Note:
The function needs to transfer the whole state of the passed function to the process, which is done with pickle.
It is encouraged to create free functions or static methods which get all the data as simple parameters (i.e. no class or UI logic)
and return the result, instead of writing it in class properties or global variables.

The process pool uses the "spawn" start method by default (*updated in version 4.0.0*, before it was the platform's default),
so workers start from a fresh import and do not inherit module globals or other process state.
The function must also be importable there: define it at module level in a script file or module,
not via `python -c`, stdin, a zipapp or a package's `__main__.py`, and not under `if __name__ == '__main__':`.
Set `run.process_pool_start_method` before `ui.run()` to "fork" or "forkserver" if you need them,
or to `None` to use the platform's default ("fork" on Linux up to Python 3.13, which is unsafe in threaded processes).
*Added in version 3.15.0*

main.py

[Button]

````python
import time
from nicegui import run, ui

def compute_sum(a: float, b: float) -> float:
    time.sleep(1)  # simulate a long-running computation
    return a + b

async def handle_click():
    result = await run.cpu_bound(compute_sum, 1, 2)
    ui.notify(f'Sum is {result}')

ui.button('Compute', on_click=handle_click)

ui.run()
````

## Running I/O-bound tasks

NiceGUI provides an `io_bound` function for running I/O-bound tasks in a separate thread.
This is useful for long-running I/O operations that would otherwise block the event loop and make the UI unresponsive.
The function returns a future that can be awaited.

main.py

[Button]

````python
import httpx2
from nicegui import run, ui

async def handle_click():
    URL = 'https://httpbin.org/delay/1'
    response = await run.io_bound(httpx2.get, URL, timeout=3)
    ui.notify(f'Downloaded {len(response.content)} bytes')

ui.button('Download', on_click=handle_click)

ui.run()
````

## [Run JavaScript](/documentation/run_javascript)

This function runs arbitrary JavaScript code on a page that is executed in the browser.
To access a client-side Vue component or HTML element by ID,
use the JavaScript functions ``getElement()`` or ``getHtmlElement()`` (*added in version 2.9.0*).

If the function is awaited, the result of the JavaScript code is returned.
Otherwise, the JavaScript code is executed without waiting for a response.

Obviously the JavaScript code is only executed after the client is connected.
Internally, ``await client.connected()`` is called before the JavaScript code is executed (*since version 3.0.0*).
This might delay the execution of the JavaScript code and is not covered by the ``timeout`` parameter.

*Updated in version 3.17.0: Awaiting the response resolves with ``None`` when the client has been deleted,
e.g. because the browser tab was closed.*

:code: JavaScript code to run
:timeout: timeout in seconds (default: 1.0)

:return: AwaitableResponse that can be awaited to get the result of the JavaScript code,
    or ``None`` if the client has been deleted

main.py

[Button]

````python
from nicegui import ui

def alert():
    ui.run_javascript('alert("Hello!")')

async def get_date():
    time = await ui.run_javascript('Date()')
    ui.notify(f'Browser time: {time}')

def access_elements():
    ui.run_javascript(f'getHtmlElement({label.id}).innerText += " Hello!"')

ui.button('fire and forget', on_click=alert)
ui.button('receive result', on_click=get_date)
ui.button('access elements', on_click=access_elements)
label = ui.label()

ui.run()
````

[See more →](/documentation/run_javascript)

## [Read and write to the clipboard](/documentation/clipboard)

The following demo shows how to use `ui.clipboard.read()`, `ui.clipboard.write()` and `ui.clipboard.read_image()` to interact with the clipboard.

Note that your browser may ask for permission to access the clipboard or may not support this feature at all.

main.py

[Button]

````python
from nicegui import ui

ui.button('Write Text', on_click=lambda: ui.clipboard.write('Hi!'))

async def read() -> None:
    ui.notify(await ui.clipboard.read())
ui.button('Read Text', on_click=read)

async def read_image() -> None:
    img = await ui.clipboard.read_image()
    if not img:
        ui.notify('You must copy an image to clipboard first.')
    else:
        image.set_source(img)
ui.button('Read Image', on_click=read_image)
image = ui.image().classes('w-72')

ui.run()
````

[See more →](/documentation/clipboard)

## [Event](/documentation/event)

Events are a powerful tool distribute information between different parts of your code,
especially from long-living objects like data models to the short-living UI.

Handlers can be synchronous or asynchronous.
They can also take arguments if the event contains arguments.

*Added in version 3.0.0*

main.py

[Button]

````python
from nicegui import Event, ui

tweet = Event[str]()

@ui.page('/')
def page():
    with ui.row(align_items='center'):
        message = ui.input('Tweet')
        ui.button(icon='send', on_click=lambda: tweet.emit(message.value)).props('flat')

    tweet.subscribe(lambda m: ui.notify(f'Someone tweeted: "{m}"'))

ui.run()
````

[See more →](/documentation/event)

## Error handling


    There are 3 error handling means in NiceGUI:

    1. [`app.on_exception`](#lifecycle_events):
        Global exception handler for **all** exceptions in the NiceGUI app.
        - Applied app-wide.
        - Handler has no UI context (cannot use `ui.*`).
        - Common sources: `app.timer`, `background_tasks.create`, `run.io_bound`, `run.cpu_bound`.
    2. [`@app.on_page_exception`](#custom_error_page):
        Custom error page for page-blocking exceptions (**before** page sent to browser)
        - Applied app-wide.
        - Handler may use UI elements but in a new client.
        - Common sources: sync `@ui.page` functions, exceptions in async `@ui.page` functions before `await ui.context.client.connected()`.
    3. [`ui.on_exception`](#ui_on_exception):
        Handler for in-page exceptions (**after** page sent to browser)
        - Applied per-page.
        - Handler may use UI elements with the original client at `ui.context.client`.
        - Common sources: `ui.button(on_click=...)`, `ui.timer`, `background_tasks.create(..., context=...)`,
            exceptions in async `@ui.page` functions after `await ui.context.client.connected()`

    When an exception occurs:

    - All will be logged via `app.on_exception` (1)
    - UI-context exceptions go to _either_, but never both:
        - `@app.on_page_exception` (2) if raised before client connection
        - `ui.on_exception` (3) if raised after client connection
    - Once the client has been deleted, its `ui.on_exception` handlers are skipped.


## Lifecycle events

You can register synchronous or asynchronous functions to be called for the following lifecycle events:

- `app.on_startup`: called when NiceGUI is started or restarted
- `app.on_shutdown`: called when NiceGUI is shut down or restarted
- `app.on_connect`: called for each client which connects (even when reconnecting, optional argument: `nicegui.Client`)
- `app.on_disconnect`: called for each client which disconnects (even when reconnecting, optional argument: `nicegui.Client`, *changed in version 3.0.0*)
- `app.on_delete`: called when a client is deleted (if it does not reconnect, optional argument: `nicegui.Client`, *added in version 3.0.0*)
- `app.on_exception`: called when an exception occurs (optional argument: exception)

When NiceGUI is shut down or restarted, all tasks still in execution will be automatically canceled.

main.py

[Button]

````python
from datetime import datetime
from nicegui import app, ui

dt = datetime.now()

def handle_connection():
    global dt
    dt = datetime.now()
app.on_connect(handle_connection)

label = ui.label()
ui.timer(1, lambda: label.set_text(f'Last new connection: {dt:%H:%M:%S}'))

ui.run()
````

## Custom error page

You can use `@app.on_page_exception` to define a custom error page.

The handler must be a synchronous function that creates a page like a normal page function.
It can take the exception as an argument, but it is not required.
It overrides the default "sad face" error page, except when the error is re-raised.

The following example shows how to create a custom error page handler that only handles a specific exception.
The default error page handler is still used for all other exceptions.

Note: Showing the traceback may not be a good idea in production, as it may leak sensitive information.

*Added in version 2.20.0*

main.py

[Button]

````python
import traceback
from nicegui import app, ui

@app.on_page_exception
def timeout_error_page(exception: Exception) -> None:
    if not isinstance(exception, TimeoutError):
        raise exception
    with ui.column().classes('absolute-center items-center gap-8'):
        ui.icon('sym_o_timer', size='xl')
        ui.label(f'{exception}').classes('text-2xl')
        ui.code(traceback.format_exc(chain=False))

@ui.page('/raise_timeout_error')
def raise_timeout_error():
    raise TimeoutError('This took too long')

@ui.page('/raise_runtime_error')
def raise_runtime_error():
    raise RuntimeError('Something is wrong')

@ui.page('/')
def page():
    ui.link('Raise timeout error (custom error page)', '/raise_timeout_error')
    ui.link('Raise runtime error (default error page)', '/raise_runtime_error')

ui.run()
````

## ui.on_exception

You can register callback functions using `ui.on_exception` to handle errors
that occur after the HTML response has been sent to the client.
This allows you to show a notification or dialog with the error details.
The following example shows how to create a dialog that displays the error details when an error occurs.

*Added in version 3.6.0*

main.py

[Button]

````python
import asyncio
import traceback
from nicegui import ui

@ui.page('/error_dialog_page')
async def error_dialog_page():
    with ui.page_sticky(x_offset=16, y_offset=16):
        fab_error = ui.button(icon='error', color='negative').props('fab')
        fab_error.set_visibility(False)

    def show_error_dialog(error):
        with ui.dialog() as error_dialog, ui.card():
            render_error_details(error, 'max-w-[calc(560px-2rem)]')
            ui.button('Close', on_click=error_dialog.close)
        fab_error.on('click', error_dialog.open).set_visibility(True)

    ui.on_exception(lambda e: show_error_dialog(e.args))
    ui.label('This @ui.page errors out post-HTML-response in 3 seconds')
    await ui.context.client.connected()
    await asyncio.sleep(3)
    raise ValueError('Test exception handling')

@ui.page('/clear_content_page')
async def clear_content_page():
    def clear_content_and_show_error(error):
        with ui.context.client.content.clear():
            render_error_details(error, 'w-full')
            ui.link('Back to menu', '/')

    ui.on_exception(lambda e: clear_content_and_show_error(e.args))
    ui.label('This @ui.page errors out post-HTML-response in 3 seconds')
    await ui.context.client.connected()
    await asyncio.sleep(3)
    raise ValueError('Test exception handling')

def render_error_details(error, code_classes=''):
    ui.label('Page error').classes('text-lg font-bold')
    ui.label(f'{error} ({type(error).__name__})').classes('text-red-600')
    ui.code(traceback.format_exc(chain=False)).classes(code_classes)

@ui.page('/')
def page():
    ui.link('@ui.page raises error, shows error dialog', '/error_dialog_page')
    ui.link('@ui.page raises error, clears the body and shows the error', '/clear_content_page')

ui.run()
````

## Shut down NiceGUI

This will programmatically stop the server.

main.py

[Button]

````python
from nicegui import app, ui

ui.button('shutdown', on_click=app.shutdown)

ui.run(reload=False)
````

## [Storage](/documentation/storage)

NiceGUI offers a straightforward mechanism for data persistence within your application.
It features five built-in storage types:

- `app.storage.tab`:
    Stored server-side in memory, this dictionary is unique to each tab session and can hold arbitrary objects.
    The data survives page reloads and is kept for up to `app.storage.max_tab_storage_age` (30 days by default).
    It is lost when restarting the server unless [Redis storage](#redis_storage) is used
    (persisting it on disk by default is discussed in <https://github.com/zauberzeug/nicegui/discussions/2841>).
    When a tab is duplicated, the new tab starts with a copy of the data, but afterwards the two tabs are independent.
    This storage requires an established connection, obtainable via [`await client.connected()`](/documentation/page#wait_for_client_connection).
- `app.storage.client`:
    Also stored server-side in memory, this dictionary is unique to each client connection and can hold arbitrary objects.
    Data will be discarded when the page is reloaded or the user navigates to another page.
    Unlike data stored in `app.storage.tab` which can be persisted on the server even for days,
    `app.storage.client` helps caching resource-hungry objects such as a streaming or database connection you need to keep alive
    for dynamic site updates but would like to discard as soon as the user leaves the page or closes the browser.
- `app.storage.user`:
    Stored server-side, each dictionary is associated with a unique identifier held in a browser session cookie.
    Unique to each user, this storage is accessible across all their browser tabs.
    `app.storage.browser['id']` is used to identify the user.
    This storage requires the `storage_secret` parameter in `ui.run()` to sign the browser session cookie.
- `app.storage.general`:
    Also stored server-side, this dictionary provides a shared storage space accessible to all users.
- `app.storage.browser`:
    Unlike the previous types, this dictionary is stored directly as the browser session cookie, shared among all browser tabs for the same user.
    However, `app.storage.user` is generally preferred due to its advantages in reducing data payload, enhancing security, and offering larger storage capacity.
    By default, NiceGUI holds a unique identifier for the browser session in `app.storage.browser['id']`.
    This storage requires the `storage_secret` parameter in `ui.run()` to sign the browser session cookie.

The following table will help you to choose storage.

| Storage type                | `client` | `tab`            | `browser` | `user` | `general` |
|-----------------------------|----------|------------------|-----------|--------|-----------|
| Location                    | Server   | Server           | Browser   | Server | Server    |
| Across tabs                 | No       | No               | Yes       | Yes    | Yes       |
| Across browsers             | No       | No               | No        | No     | Yes       |
| Across server restarts      | No       | No<sup>1)</sup>  | No        | Yes    | Yes       |
| Across page reloads         | No       | Yes              | Yes       | Yes    | Yes       |
| Needs client connection     | No       | Yes<sup>2)</sup> | No        | No     | No        |
| Write only before response  | No       | No               | Yes       | No     | No        |
| Needs serializable data     | No       | No               | Yes       | Yes    | Yes       |
| Needs `storage_secret`      | No       | No               | Yes       | Yes    | No        |

<sup>1)</sup>
Tab storage persists across server restarts only when using [Redis storage](#redis_storage).

<sup>2)</sup>
Tab storage can only be accessed after the WebSocket connection has been established.
In event handlers this is already the case, but while building the page you need to
[`await client.connected()`](/documentation/page#wait_for_client_connection) first.

main.py

[Button]

````python
from nicegui import app, ui

@ui.page('/')
def index():
    app.storage.user['count'] = app.storage.user.get('count', 0) + 1
    with ui.row():
       ui.label('your own page visits:')
       ui.label().bind_text_from(app.storage.user, 'count')

ui.run(storage_secret='private key to secure the browser session cookie')
````

[See more →](/documentation/storage)

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