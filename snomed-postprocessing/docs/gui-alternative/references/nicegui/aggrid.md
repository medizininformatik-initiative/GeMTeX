# ui.aggrid | NiceGUI

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

# ui.*aggrid*

## AG Grid

An element to create a grid using `AG Grid <https://www.ag-grid.com/>`_.
Updates can be pushed to the grid by updating the ``options`` property.

The methods ``run_grid_method`` and ``run_row_method`` can be used to interact with the AG Grid instance on the client.

:options: dictionary of AG Grid options
:html_columns: list of columns that should be rendered as HTML (default: ``[]``)
:theme: AG Grid theme "quartz", "balham", "material", or "alpine" (default: ``options['theme']`` or "quartz")
:auto_size_columns: whether to automatically resize columns to fit the grid width (default: ``None``, i.e. fit to width unless columns use ``flex``)
:modules: either "community", "enterprise", or a list of `AG Grid Modules <https://www.ag-grid.com/javascript-data-grid/modules/>`_ (default: "community")

main.py

[Button]

````python
from nicegui import ui

grid = ui.aggrid({
    'columnDefs': [
        {'headerName': 'Name', 'field': 'name'},
        {'headerName': 'Age', 'field': 'age'},
        {'headerName': 'Parent', 'field': 'parent', 'hide': True},
    ],
    'rowData': [
        {'name': 'Alice', 'age': 18, 'parent': 'David'},
        {'name': 'Bob', 'age': 21, 'parent': 'Eve'},
        {'name': 'Carol', 'age': 42, 'parent': 'Frank'},
    ],
    'rowSelection': {'mode': 'multiRow'},
})

def update():
    grid.options['rowData'][0]['age'] += 1

ui.button('Update', on_click=update)
ui.button('Select all', on_click=lambda: grid.run_grid_method('selectAll'))
ui.button('Show parent', on_click=lambda: grid.run_grid_method('setColumnsVisible', ['parent'], True))

ui.run()
````

## Adding rows

It's simple to add new rows by updating the `options` property.
To scroll to the new row, use the AG Grid API method `ensureIndexVisible`.

main.py

[Button]

````python
import random
from nicegui import ui

def add():
    grid.options['rowData'].append({'number': random.randint(0, 100)})
    grid.run_grid_method('ensureIndexVisible', len(grid.options['rowData']) - 1)

grid = ui.aggrid({
    'columnDefs': [{'field': 'number'}],
    'rowData': [],
}).classes('h-52')
ui.button('Add row', on_click=add)

ui.run()
````

## Adding rows without losing client-side edits

Mutating `grid.options['rowData']` triggers a full rebuild on the client and discards any in-progress cell edits.

An AG Grid [transaction](https://www.ag-grid.com/javascript-data-grid/data-update-transactions/)
adds rows without rebuilding the grid, so unsaved edits are preserved.
Wrap the `rowData` mutation in `grid.props.suspend_updates()`
to keep the server-side list in sync without firing the rebuild.

Try it: start editing a cell, then click *Add row* without leaving the cell —
your edit stays intact.

main.py

[Button]

````python
from nicegui import ui

def add():
    row = {'Name': f'Row {len(grid.options["rowData"])}'}
    with grid.props.suspend_updates():
        grid.options['rowData'].append(row)
    grid.run_grid_method('applyTransaction', {'add': [row]})
    grid.run_grid_method('ensureIndexVisible', len(grid.options['rowData']) - 1)

grid = ui.aggrid({
    'columnDefs': [{'field': 'Name', 'editable': True}],
    'rowData': [],
    'stopEditingWhenCellsLoseFocus': True,
}).classes('h-52')
ui.button('Add row', on_click=add)

ui.run()
````

## Select AG Grid Rows

You can add checkboxes to grid cells to allow the user to select single or multiple rows.

To retrieve the currently selected rows, use the `get_selected_rows` method.
This method returns a list of rows as dictionaries.

If `rowSelection` is set to `{'mode': 'singleRow'}` or to get the first selected row,
you can also use the `get_selected_row` method.
This method returns a single row as a dictionary or `None` if no row is selected.

See the [AG Grid documentation](https://www.ag-grid.com/javascript-data-grid/row-selection/#example-single-row-selection) for more information.

main.py

[Button]

````python
from nicegui import ui

grid = ui.aggrid({
    'columnDefs': [
        {'headerName': 'Name', 'field': 'name'},
        {'headerName': 'Age', 'field': 'age'},
    ],
    'rowData': [
        {'name': 'Alice', 'age': 18},
        {'name': 'Bob', 'age': 21},
        {'name': 'Carol', 'age': 42},
    ],
    'rowSelection': {'mode': 'multiRow'},
})

async def output_selected_rows():
    rows = await grid.get_selected_rows()
    if rows:
        for row in rows:
            ui.notify(f"{row['name']}, {row['age']}")
    else:
        ui.notify('No rows selected.')

async def output_selected_row():
    row = await grid.get_selected_row()
    if row:
        ui.notify(f"{row['name']}, {row['age']}")
    else:
        ui.notify('No row selected!')

ui.button('Output selected rows', on_click=output_selected_rows)
ui.button('Output selected row', on_click=output_selected_row)

ui.run()
````

## Filter Rows using Mini Filters

You can add [mini filters](https://ag-grid.com/javascript-data-grid/filter-set-mini-filter/)
to the header of each column to filter the rows.

Note how the "agTextColumnFilter" matches individual characters, like "a" in "Alice" and "Carol",
while the "agNumberColumnFilter" matches the entire number, like "18" and "21", but not "1".

main.py

[Button]

````python
from nicegui import ui

ui.aggrid({
    'columnDefs': [
        {'headerName': 'Name', 'field': 'name', 'filter': 'agTextColumnFilter', 'floatingFilter': True},
        {'headerName': 'Age', 'field': 'age', 'filter': 'agNumberColumnFilter', 'floatingFilter': True},
    ],
    'rowData': [
        {'name': 'Alice', 'age': 18},
        {'name': 'Bob', 'age': 21},
        {'name': 'Carol', 'age': 42},
    ],
})

ui.run()
````

## AG Grid with Conditional Cell Formatting

This demo shows how to use [cellClassRules](https://www.ag-grid.com/javascript-grid-cell-styles/#cell-class-rules)
to conditionally format cells based on their values.

main.py

[Button]

````python
from nicegui import ui

ui.aggrid({
    'columnDefs': [
        {'headerName': 'Name', 'field': 'name'},
        {'headerName': 'Age', 'field': 'age', 'cellClassRules': {
            'bg-red-300': 'x < 21',
            'bg-green-300': 'x >= 21',
        }},
    ],
    'rowData': [
        {'name': 'Alice', 'age': 18},
        {'name': 'Bob', 'age': 21},
        {'name': 'Carol', 'age': 42},
    ],
})

ui.run()
````

## Create Grid from Pandas DataFrame

You can create an AG Grid from a Pandas DataFrame using the `from_pandas` method.
This method takes a Pandas DataFrame as input and returns an AG Grid.

main.py

[Button]

````python
import pandas as pd
from nicegui import ui

df = pd.DataFrame(data={'col1': [1, 2], 'col2': [3, 4]})
ui.aggrid.from_pandas(df).classes('max-h-40')

ui.run()
````

## Create Grid from Polars DataFrame

You can create an AG Grid from a Polars DataFrame using the `from_polars` method.
This method takes a Polars DataFrame as input and returns an AG Grid.

*Added in version 2.7.0*

main.py

[Button]

````python
import polars as pl
from nicegui import ui

df = pl.DataFrame(data={'col1': [1, 2], 'col2': [3, 4]})
ui.aggrid.from_polars(df).classes('max-h-40')

ui.run()
````

## Render columns as HTML

You can render columns as HTML by passing a list of column indices to the `html_columns` argument.

main.py

[Button]

````python
from nicegui import ui

ui.aggrid({
    'columnDefs': [
        {'headerName': 'Name', 'field': 'name'},
        {'headerName': 'URL', 'field': 'url'},
    ],
    'rowData': [
        {'name': 'Google', 'url': '<a href="https://google.com">https://google.com</a>'},
        {'name': 'Facebook', 'url': '<a href="https://facebook.com">https://facebook.com</a>'},
    ],
}, html_columns=[1])

ui.run()
````

## Respond to an AG Grid event

All AG Grid events are passed through to NiceGUI via the AG Grid global listener.
These events can be subscribed to using the `.on()` method.

main.py

[Button]

````python
from nicegui import ui

ui.aggrid({
    'columnDefs': [
        {'headerName': 'Name', 'field': 'name'},
        {'headerName': 'Age', 'field': 'age'},
    ],
    'rowData': [
        {'name': 'Alice', 'age': 18},
        {'name': 'Bob', 'age': 21},
        {'name': 'Carol', 'age': 42},
    ],
}).on('cellClicked', lambda event: ui.notify(f'Cell value: {event.args["value"]}'))

ui.run()
````


    **Note:** Certain events, e.g. `rowClicked`, don't seem to work.
    This is because some event arguments include cyclic references.
    For these seemingly non-working events you'll see a serialization error on the developer console in your browser.

    To inspect the event arguments and find the values you are interested in,
    you can replace the event registration with the following JavaScript handler:
    ```
    .on('rowClicked', js_handler='console.log')
    ```
    Then limit the event arguments to the necessary ones, e.g. `data`, thus excluding the cycles:
    ```
    .on('rowClicked', lambda event: ui.notify(f'Row: {event.args}'), ['data'])
    ```
    This selection can be serialized safely and will work correctly.


## AG Grid with complex objects

You can use nested complex objects in AG Grid by separating the field names with a period.
(This is the reason why keys in `rowData` are not allowed to contain periods.)

main.py

[Button]

````python
from nicegui import ui

ui.aggrid({
    'columnDefs': [
        {'headerName': 'First name', 'field': 'name.first'},
        {'headerName': 'Last name', 'field': 'name.last'},
        {'headerName': 'Age', 'field': 'age'}
    ],
    'rowData': [
        {'name': {'first': 'Alice', 'last': 'Adams'}, 'age': 18},
        {'name': {'first': 'Bob', 'last': 'Brown'}, 'age': 21},
        {'name': {'first': 'Carol', 'last': 'Clark'}, 'age': 42},
    ],
})

ui.run()
````

## JavaScript expressions in options

The options dictionary is sent to the browser as JSON, so a string value stays a string.
Many AG Grid options expect a JavaScript function instead, e.g. `getRowId`, `getRowHeight` or a column's `valueFormatter`.
Prefix such a key with a colon and NiceGUI evaluates the value as a JavaScript expression on the client.
The expression can be anything JavaScript understands: an arrow function, an object, a regular expression, etc.

Without the colon, `'getRowId': 'params.data.name'` hands AG Grid a plain string where it expects a function.
The grid then shows no rows and a `TypeError` in the browser console, while nothing is reported in Python.

Note that AG Grid has its own expression strings, e.g. `'x < 21'` in `cellClassRules`
(see [Conditional Cell Formatting](#ag_grid_with_conditional_cell_formatting) above).
These are evaluated by AG Grid itself and need no colon.

The `getRowId` callback gives each row a stable ID, which is needed to address rows from Python,
e.g. with `run_row_method` (see [Run row methods](#run_row_methods) below).

main.py

[Button]

````python
from nicegui import ui

grid = ui.aggrid({
    'columnDefs': [
        {'field': 'name'},
        {'field': 'age', ':valueFormatter': 'params => `${params.value} years`'},
    ],
    'rowData': [
        {'name': 'Alice', 'age': 18},
        {'name': 'Bob', 'age': 21},
        {'name': 'Carol', 'age': 42},
    ],
    ':getRowId': 'params => params.data.name',
})
ui.button('Update Bob', on_click=lambda: grid.run_row_method('Bob', 'setDataValue', 'age', 99))

ui.run()
````

## AG Grid with dynamic row height

You can set the height of individual rows by passing a function to the `getRowHeight` argument.

main.py

[Button]

````python
from nicegui import ui

ui.aggrid({
    'columnDefs': [{'field': 'name'}, {'field': 'age'}],
    'rowData': [
        {'name': 'Alice', 'age': '18'},
        {'name': 'Bob', 'age': '21'},
        {'name': 'Carol', 'age': '42'},
    ],
    ':getRowHeight': 'params => params.data.age > 35 ? 50 : 25',
})

ui.run()
````

## Run row methods

You can run methods on individual rows by using the `run_row_method` method.
This method takes the row ID, the method name and the method arguments as arguments.

The row ID is the value returned by the `getRowId` option, a JavaScript callback
(see [JavaScript expressions in options](#javascript_expressions_in_options)).
If `getRowId` is not defined, AG Grid uses the row index as a string, e.g. `'0'`.
A stable row ID is also what lets AG Grid match rows sent from Python against rows already in the grid,
e.g. for `applyTransaction` with `update` or `remove`, or to preserve the selection when replacing `rowData` via `setGridOption`.
If no row with the given ID exists, an error is logged in the browser console and on the server.

The following demo shows how to use it to update cell values.
Note that the row selection is preserved when the value is updated.
This would not be the case if the grid was updated using the `update` method.

main.py

[Button]

````python
from nicegui import ui

grid = ui.aggrid({
    'columnDefs': [
        {'field': 'name'},
        {'field': 'age'},
    ],
    'rowData': [
        {'name': 'Alice', 'age': 18},
        {'name': 'Bob', 'age': 21},
        {'name': 'Carol', 'age': 42},
    ],
    ':getRowId': '(params) => params.data.name',
})
ui.button('Update',
          on_click=lambda: grid.run_row_method('Alice', 'setDataValue', 'age', 99))

ui.run()
````

## Access grid API via JavaScript

You can access the AG Grid API directly via `ui.run_javascript()` for more complex operations.
This demo accesses the grid API to get the first displayed row's data.

main.py

[Button]

````python
from nicegui import ui

grid = ui.aggrid({
    'columnDefs': [{'field': 'name'}],
    'rowData': [{'name': 'Alice'}, {'name': 'Bob'}],
})

async def get_first_name() -> None:
    row = await ui.run_javascript(
        f'return getElement({grid.id}).api.getDisplayedRowAtIndex(0).data',
    )
    ui.notify(row['name'])

ui.button('Get First Name', on_click=get_first_name)

ui.run()
````

## Handle theme change

You can change the theme of the AG Grid via the `theme` property.
Dark mode is applied automatically depending on the dark mode setting of the page.

main.py

[Button]

````python
from nicegui import ui

grid = ui.aggrid({
    'columnDefs': [
        {'headerName': 'Make', 'field': 'make'},
        {'headerName': 'Country', 'field': 'country'},
    ],
    'rowData': [
        {'make': 'Ford', 'country': 'USA'},
        {'make': 'Toyota', 'country': 'Japan'},
        {'make': 'Volkswagen', 'country': 'Germany'},
    ],
})
ui.toggle(['quartz', 'balham', 'material', 'alpine']) \
    .bind_value(grid, 'theme').props('flat size="sm"')

ui.run()
````

## AG Grid Enterprise

You can use AG Grid Enterprise by setting the module source to the Enterprise bundle
(either from a CDN or from a self-hosted bundle)
and passing `modules='enterprise'` to the `ui.aggrid` constructor.

Use `ui.aggrid.VERSION` (*since version 3.8.0*) to programmatically reference the AG Grid version used by NiceGUI.
This ensures compatibility when building custom CDN URLs.

*Added in version 3.6.0*

main.py

[Button]

````python
from nicegui import ui

bundle_url = f'https://cdn.jsdelivr.net/npm/ag-grid-enterprise@{ui.aggrid.VERSION}/+esm'
ui.aggrid.set_module_source(bundle_url)

ui.aggrid({
    'columnDefs': [
        {'field': 'version'},
        {'field': 'description'},
    ],
    'rowData': [
        {'version': 'Community', 'description': 'Free, no license required.'},
        {'version': 'Enterprise', 'description': 'Restricted, free to test locally.'},
    ],
}, modules='enterprise')

ui.run()
````

## Debugging


    If the grid does not behave as expected, open the developer console in your browser.
    Typical errors you will find there (the last two are also forwarded to the server log):

    - `TypeError: ... is not a function` from AG Grid if an option expecting a function received a plain string (missing colon)
    - `Error while converting :getRowId attribute to function` if a JavaScript expression in the options does not evaluate
    - `Method "..." not found` if `run_grid_method` or `run_row_method` is called with an unknown method name
    - `Row "..." not found` if `run_row_method` is called with an unknown row ID

    To let AG Grid validate the options, e.g. to spot misspelled properties or missing modules,
    add its `ValidationModule`.
    The findings are then shown in the browser console and in an overlay on the grid.
    Note that AG Grid registers modules globally, so this applies to all grids on the page:
    ```
    ui.aggrid(options, modules=['AllCommunityModule', 'ValidationModule'])
    ```

    To inspect the arguments of an event, register a JavaScript handler
    (see [Respond to an AG Grid event](#respond_to_an_ag_grid_event)):
    ```
    .on('rowDataUpdated', js_handler='console.log')
    ```

    To poke at the grid directly, access the [AG Grid API](https://www.ag-grid.com/javascript-data-grid/grid-api/)
    via `ui.run_javascript` (see [Access grid API via JavaScript](#access_grid_api_via_javascript)):
    ```
    await ui.run_javascript(f'return getElement({grid.id}).api.getDisplayedRowCount()')
    ```


## Reference

## Initializer

:options: dictionary of AG Grid options
:html_columns: list of columns that should be rendered as HTML (default: ``[]``)
:theme: AG Grid theme "quartz", "balham", "material", or "alpine" (default: ``options['theme']`` or "quartz")
:auto_size_columns: whether to automatically resize columns to fit the grid width (default: ``None``, i.e. fit to width unless columns use ``flex``)
:modules: either "community", "enterprise", or a list of `AG Grid Modules <https://www.ag-grid.com/javascript-data-grid/modules/>`_ (default: "community")

## Properties

**`auto_size_columns`**`: bool (settable)`

Whether to automatically resize columns to fit the grid width.

**`html_columns`**`: list[int] (settable)`

The list of columns that should be rendered as HTML.

**`options`**`: dict (settable)`

The options dictionary.

**`theme`**`: Literal['quartz', 'balham', 'material', 'alpine'] | None (settable)`

The AG Grid theme.

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

**`visible`**`: BindableProperty`

## Methods

`@classmethod`<br />**`from_pandas`**`(df: pd.DataFrame, html_columns: list[int] = [], theme: Literal['quartz', 'balham', 'material', 'alpine'] | None = None, auto_size_columns: bool | None = None, options: dict = {}, modules: Literal['community', 'enterprise'] | list[str] = 'community') -> Self`

Create an AG Grid from a Pandas DataFrame.

Note:
If the DataFrame contains non-serializable columns of type ``datetime64[ns]``, ``timedelta64[ns]``, ``complex128`` or ``period[M]``,
they will be converted to strings.
To use a different conversion, convert the DataFrame manually before passing it to this method.
See `issue 1698 <https://github.com/zauberzeug/nicegui/issues/1698>`_ for more information.

*Since version 3.12.0:*
Any DataFrame index other than an unnamed ``RangeIndex`` is auto-included as column(s).
Pass ``df.reset_index(drop=True)`` to drop the index instead.

:param df: Pandas DataFrame
:param html_columns: list of columns that should be rendered as HTML (default: ``[]``, *added in version 2.19.0*)
:param theme: AG Grid theme "quartz", "balham", "material", or "alpine" (default: ``options['theme']`` or "quartz")
:param auto_size_columns: whether to automatically resize columns to fit the grid width (default: ``None``, i.e. fit to width unless columns use ``flex``)
:param options: dictionary of additional AG Grid options
:param modules: either "community", "enterprise", or a list of `AG Grid Modules <https://www.ag-grid.com/javascript-data-grid/modules/>`_ (default: "community")
:return: AG Grid element

`@classmethod`<br />**`from_polars`**`(df: pl.DataFrame, html_columns: list[int] = [], theme: Literal['quartz', 'balham', 'material', 'alpine'] | None = None, auto_size_columns: bool | None = None, options: dict = {}, modules: Literal['community', 'enterprise'] | list[str] = 'community') -> Self`

Create an AG Grid from a Polars DataFrame.

If the DataFrame contains non-UTF-8 datatypes, they will be converted to strings.
To use a different conversion, convert the DataFrame manually before passing it to this method.

*Added in version 2.7.0*

:param df: Polars DataFrame
:param html_columns: list of columns that should be rendered as HTML (default: ``[]``, *added in version 2.19.0*)
:param theme: AG Grid theme "quartz", "balham", "material", or "alpine" (default: ``options['theme']`` or "quartz")
:param auto_size_columns: whether to automatically resize columns to fit the grid width (default: ``None``, i.e. fit to width unless columns use ``flex``)
:param options: dictionary of additional AG Grid options
:param modules: either "community", "enterprise", or a list of `AG Grid Modules <https://www.ag-grid.com/javascript-data-grid/modules/>`_ (default: "community")
:return: AG Grid element

**`get_client_data`**`(timeout: float = 1, method: Literal['all_unsorted', 'filtered_unsorted', 'filtered_sorted', 'leaf'] = 'all_unsorted') -> list[dict]`

Get the data from the client including any edits made by the client.

This method is especially useful when the grid is configured with ``'editable': True``.

See `AG Grid API <https://www.ag-grid.com/javascript-data-grid/accessing-data/>`_ for more information.

Note that when editing a cell, the row data is not updated until the cell exits the edit mode.
This does not happen when the cell loses focus, unless ``stopEditingWhenCellsLoseFocus: True`` is set.

:param timeout: timeout in seconds (default: 1 second)
:param method: method to access the data, "all_unsorted" (default), "filtered_unsorted", "filtered_sorted", "leaf"

:return: list of row data

**`get_selected_row`**`() -> dict | None`

Get the single currently selected row.

This method is especially useful when the grid is configured with ``rowSelection: {'mode': 'singleRow'}``.

:return: row data of the first selection if any row is selected, otherwise ``None``

**`get_selected_rows`**`() -> list[dict]`

Get the currently selected rows.

This method is especially useful when the grid is configured with ``rowSelection: {'mode': 'multiRow'}``.

See `AG Grid API <https://www.ag-grid.com/javascript-data-grid/row-selection/#reference-selection-getSelectedRows>`_ for more information.

:return: list of selected row data

**`load_client_data`**`() -> None`

Obtain client data and update the element's row data with it.

This syncs edits made by the client in editable cells to the server.

Note that when editing a cell, the row data is not updated until the cell exits the edit mode.
This does not happen when the cell loses focus, unless ``stopEditingWhenCellsLoseFocus: True`` is set.

**`run_grid_method`**`(name: str, *args, timeout: float = 1) -> nicegui.awaitable_response.AwaitableResponse`

Run an AG Grid API method.

See `AG Grid API <https://www.ag-grid.com/javascript-data-grid/grid-api/>`_ for a list of methods.

If the function is awaited, the result of the method call is returned.
Otherwise, the method is executed without waiting for a response.

:param name: name of the method
:param \*args: arguments to pass to the method
:param timeout: timeout in seconds (default: 1 second)

:return: AwaitableResponse that can be awaited to get the result of the method call

**`run_row_method`**`(row_id: str, name: str, *args, timeout: float = 1) -> nicegui.awaitable_response.AwaitableResponse`

Run an AG Grid API method on a specific row.

See `AG Grid Row Reference <https://www.ag-grid.com/javascript-data-grid/row-object/>`_ for a list of methods.

If the function is awaited, the result of the method call is returned.
Otherwise, the method is executed without waiting for a response.

The row ID is the value returned by the ``getRowId`` option,
e.g. ``':getRowId': 'params => params.data.name'``.
If ``getRowId`` is not defined, AG Grid uses the row index as a string, e.g. ``'0'``.
If no row with the given ID exists, an error is logged and nothing happens.

:param row_id: ID of the row (as defined by the ``getRowId`` option, or the row index as a string)
:param name: name of the method
:param \*args: arguments to pass to the method
:param timeout: timeout in seconds (default: 1 second)

:return: AwaitableResponse that can be awaited to get the result of the method call

`@staticmethod`<br />**`set_module_source`**`(url: str) -> None`

Override the ESM module URL for all AG Grid elements.

This sets a global import map override, affecting all pages and clients.
Use this to switch to AG Grid Enterprise or a self-hosted bundle.

:param url: the ESM module URL (e.g., "https://cdn.jsdelivr.net/npm/ag-grid-enterprise@36.2.0/+esm")

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