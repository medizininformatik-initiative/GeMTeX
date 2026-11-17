# ui.refreshable | NiceGUI

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

# ui.*refreshable*

## Refreshable UI functions

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

## Refreshable UI with parameters

Here is a demo of how to use the refreshable decorator to create a UI that can be refreshed with different parameters.

main.py

[Button]

````python
from datetime import datetime
from nicegui import ui
from zoneinfo import ZoneInfo

@ui.refreshable
def clock_ui(timezone: str):
    ui.label(f'Current time in {timezone}:')
    ui.label(datetime.now(tz=ZoneInfo(timezone)).strftime('%H:%M:%S'))

clock_ui('Europe/Berlin')
ui.button('Refresh', on_click=clock_ui.refresh)
ui.button('Refresh for New York', on_click=lambda: clock_ui.refresh('America/New_York'))
ui.button('Refresh for Tokyo', on_click=lambda: clock_ui.refresh('Asia/Tokyo'))

ui.run()
````

## Refreshable UI for input validation

Here is a demo of how to use the refreshable decorator to give feedback about the validity of user input.

main.py

[Button]

````python
import re
from nicegui import ui

pwd = ui.input('Password', password=True, on_change=lambda: show_info.refresh())

rules = {
    'Lowercase letter': lambda s: re.search(r'[a-z]', s),
    'Uppercase letter': lambda s: re.search(r'[A-Z]', s),
    'Digit': lambda s: re.search(r'\d', s),
    'Special character': lambda s: re.search(r"[!@#$%^&*(),.?':{}|<>]", s),
    'min. 8 characters': lambda s: len(s) >= 8,
}

@ui.refreshable
def show_info():
    for rule, check in rules.items():
        with ui.row().classes('items-center gap-2'):
            if check(pwd.value or ''):
                ui.icon('done', color='green')
                ui.label(rule).classes('text-xs text-green strike-through')
            else:
                ui.icon('radio_button_unchecked', color='red')
                ui.label(rule).classes('text-xs text-red')

show_info()

ui.run()
````

## Refreshable UI with reactive state

You can create reactive state variables with the `ui.state` function, like `count` and `color` in this demo.
They can be used like normal variables for creating UI elements like the `ui.label`.
Their corresponding setter functions can be used to set new values, which will automatically refresh the UI.

main.py

[Button]

````python
from nicegui import ui

@ui.refreshable
def counter(name: str):
    with ui.card():
        count, set_count = ui.state(0)
        color, set_color = ui.state('black')
        ui.label(f'{name} = {count}').classes(f'text-{color}')
        ui.button(f'{name} += 1', on_click=lambda: set_count(count + 1))
        ui.select(['black', 'red', 'green', 'blue'],
                  value=color, on_change=lambda e: set_color(e.value))

with ui.row():
    counter('A')
    counter('B')

ui.run()
````

## Awaitable refresh

When you have an async refreshable function, you can await the `refresh()` call to know when it completes.
This is useful for coordinating UI updates, such as disabling buttons during refresh operations.

main.py

[Button]

````python
import asyncio
from nicegui import events, ui
from uuid import uuid4

@ui.refreshable
async def compute():
    await asyncio.sleep(1)
    ui.label(uuid4())

async def handle_click(e: events.ClickEventArguments):
    e.sender.disable()
    await compute.refresh()
    e.sender.enable()

async def root():
    ui.button('Refresh', on_click=handle_click)
    await compute()

ui.run(root)
````

## Global scope

When defining a refreshable function in the global scope,
every refreshable UI that is created by calling this function will share the same state.
In this demo, `time()` will show the current date and time.
When opening the page in a new tab, _both_ tabs will be updated simultaneously when clicking the "Refresh" button.

See the "local scope" demos below for a way to create independent refreshable UIs instead.

main.py

[Button]

````python
from datetime import datetime
from nicegui import ui

@ui.refreshable
def time():
    ui.label(f'Time: {datetime.now()}')

@ui.page('/global_refreshable')
def demo():
    time()
    ui.button('Refresh', on_click=time.refresh)

@ui.page('/')
def page():
    ui.link('Open demo', demo)

ui.run()
````

## Local scope (variant A)

When defining a refreshable function in a local scope,
refreshable UI that is created by calling this function will refresh independently.
In contrast to the "global scope" demo,
the time will be updated only in the tab where the "Refresh" button was clicked.

main.py

[Button]

````python
from datetime import datetime
from nicegui import ui

@ui.page('/local_refreshable_a')
def demo():
    @ui.refreshable
    def time():
        ui.label(f'Time: {datetime.now()}')

    time()
    ui.button('Refresh', on_click=time.refresh)

@ui.page('/')
def page():
    ui.link('Open demo', demo)

ui.run()
````

## Local scope (variant B)

In order to define refreshable UIs with local state outside of page functions,
you can, e.g., define a class with a refreshable method.
This way, you can create multiple instances of the class with independent state,
because the `ui.refreshable` decorator acts on the class instance rather than the class itself.

main.py

[Button]

````python
from datetime import datetime
from nicegui import ui

class Clock:
    @ui.refreshable_method
    def time(self):
        ui.label(f'Time: {datetime.now()}')

@ui.page('/local_refreshable_b')
def demo():
    clock = Clock()
    clock.time()
    ui.button('Refresh', on_click=clock.time.refresh)

@ui.page('/')
def page():
    ui.link('Open demo', demo)

ui.run()
````

## Local scope (variant C)

As an alternative to the class definition shown above, you can also define the UI function in global scope,
but apply the `ui.refreshable` decorator inside the page function.
This way the refreshable UI will refresh independently.

main.py

[Button]

````python
from datetime import datetime
from nicegui import ui

def time():
    ui.label(f'Time: {datetime.now()}')

@ui.page('/local_refreshable_c')
def demo():
    refreshable_time = ui.refreshable(time)
    refreshable_time()
    ui.button('Refresh', on_click=refreshable_time.refresh)

@ui.page('/')
def page():
    ui.link('Open demo', demo)

ui.run()
````

## Reference

## Methods

**`prune`**`() -> None`

Remove all targets that are no longer on a page with a client connection.

This method is called automatically before each refresh.

**`refresh`**`(*args: Any, kwargs: Any) -> AwaitableResponse`

Refresh the UI elements created by this function.

This method accepts the same arguments as the function itself or a subset of them.
It will combine the arguments passed to the function with the arguments passed to this method.

If the function is awaited, it will wait for all async refresh operations to complete.
Otherwise, the refresh operations are executed in the background as fire-and-forget tasks.

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