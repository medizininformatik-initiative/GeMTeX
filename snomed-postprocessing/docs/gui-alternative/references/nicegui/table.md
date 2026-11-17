# ui.table | NiceGUI

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

# ui.*table*

## Table

A table based on Quasar's `QTable <https://quasar.dev/vue-components/table>`_ component.
Updates can be pushed to the table by updating the ``rows`` or ``columns`` properties.

If ``selection`` is "single" or "multiple", then a ``selected`` property is accessible containing the selected rows.

Note:
Cells in ``rows`` must not contain lists because they can cause the browser to crash.
To display complex data structures, convert them to strings first (e.g., using ``str()`` or custom formatting).

:rows: list of row objects
:columns: list of column objects (defaults to the columns of the first row *since version 2.0.0*)
:column_defaults: optional default column properties, *added in version 2.0.0*
:row_key: name of the column containing unique data identifying the row (default: "id")
:title: title of the table
:selection: selection type ("single" or "multiple"; default: ``None``)
:pagination: a dictionary correlating to a pagination object or number of rows per page (``None`` hides the pagination unless ``pagination_controls`` is ``True``, 0 means "infinite"; default: ``None``).
:pagination_controls: whether to show the pagination controls (default: ``None`` which shows them if ``pagination`` is provided, *added in version 4.0.0*)
:on_select: callback which is invoked when the selection changes
:on_pagination_change: callback which is invoked when the pagination changes

main.py

[Button]

````python
from nicegui import ui

columns = [
    {'name': 'name', 'label': 'Name', 'field': 'name', 'required': True, 'align': 'left'},
    {'name': 'age', 'label': 'Age', 'field': 'age', 'sortable': True},
]
rows = [
    {'name': 'Alice', 'age': 18},
    {'name': 'Bob', 'age': 21},
    {'name': 'Carol'},
]
ui.table(columns=columns, rows=rows, row_key='name')

ui.run()
````

## Omitting columns

If you omit the `columns` parameter, the table will automatically generate columns from the first row.
Labels are uppercased and sorting is enabled.

*Updated in version 2.0.0: The `columns` parameter became optional.*

main.py

[Button]

````python
from nicegui import ui

ui.table(rows=[
    {'make': 'Toyota', 'model': 'Celica', 'price': 35000},
    {'make': 'Ford', 'model': 'Mondeo', 'price': 32000},
    {'make': 'Porsche', 'model': 'Boxster', 'price': 72000},
])

ui.run()
````

## Default column parameters

You can define default column parameters that apply to all columns.
In this example, all columns are left-aligned by default and have a blue uppercase header.

*Added in version 2.0.0*

main.py

[Button]

````python
from nicegui import ui

ui.table(rows=[
    {'name': 'Alice', 'age': 18},
    {'name': 'Bob', 'age': 21},
], columns=[
    {'name': 'name', 'label': 'Name', 'field': 'name'},
    {'name': 'age', 'label': 'Age', 'field': 'age'},
], column_defaults={
    'align': 'left',
    'headerClasses': 'uppercase text-primary',
})

ui.run()
````

## Selection

You can set the selection type of a table using the `selection` parameter.
The `on_select` event handler is called when the selection changes
and the `selected` property contains the selected rows.

*Added in version 2.11.0:*
The `selection` property and the `set_selection` method can be used to change the selection type.

main.py

[Button]

````python
from nicegui import ui

table = ui.table(
    columns=[{'name': 'name', 'label': 'Name', 'field': 'name'}],
    rows=[{'name': 'Alice'}, {'name': 'Bob'}, {'name': 'Charlie'}],
    row_key='name',
    on_select=lambda e: ui.notify(f'selected: {e.selection}'),
)
ui.radio({None: 'none', 'single': 'single', 'multiple': 'multiple'},
         on_change=lambda e: table.set_selection(e.value))

ui.run()
````

## Table with expandable rows

Scoped slots can be used to insert buttons that toggle the expand state of a table row.
See the [Quasar documentation](https://quasar.dev/vue-components/table#expanding-rows) for more information.

main.py

[Button]

````python
from nicegui import ui

columns = [
    {'name': 'name', 'label': 'Name', 'field': 'name'},
    {'name': 'age', 'label': 'Age', 'field': 'age'},
]
rows = [
    {'name': 'Alice', 'age': 18},
    {'name': 'Bob', 'age': 21},
    {'name': 'Carol'},
]

table = ui.table(columns=columns, rows=rows, row_key='name').classes('w-72')
table.add_slot('header', r'''
    <q-tr :props="props">
        <q-th auto-width />
        <q-th v-for="col in props.cols" :key="col.name" :props="props">
            {{ col.label }}
        </q-th>
    </q-tr>
''')
table.add_slot('body', r'''
    <q-tr :props="props">
        <q-td auto-width>
            <q-btn size="sm" color="accent" round dense
                @click="props.expand = !props.expand"
                :icon="props.expand ? 'remove' : 'add'" />
        </q-td>
        <q-td v-for="col in props.cols" :key="col.name" :props="props">
            {{ col.value }}
        </q-td>
    </q-tr>
    <q-tr v-show="props.expand" :props="props">
        <q-td colspan="100%">
            <div class="text-left">This is {{ props.row.name }}.</div>
        </q-td>
    </q-tr>
''')

ui.run()
````

## Show and hide columns

Here is an example of how to show and hide columns in a table.

main.py

[Button]

````python
from nicegui import ui

columns = [
    {'name': 'name', 'label': 'Name', 'field': 'name', 'required': True, 'align': 'left'},
    {'name': 'age', 'label': 'Age', 'field': 'age', 'sortable': True},
]
rows = [
    {'name': 'Alice', 'age': 18},
    {'name': 'Bob', 'age': 21},
    {'name': 'Carol'},
]
table = ui.table(columns=columns, rows=rows, row_key='name')

def toggle(column: dict, visible: bool) -> None:
    column['classes'] = '' if visible else 'hidden'
    column['headerClasses'] = '' if visible else 'hidden'
    table.update()

with ui.button(icon='menu'):
    with ui.menu(), ui.column().classes('gap-0 p-2'):
        for column in table.columns:
            ui.switch(column['label'], value=True, on_change=lambda e,
                      column=column: toggle(column, e.value))

ui.run()
````

## Table with buttons

You can add buttons to the table cells using a named slot "body-cell-[name]".
In this example, we add a button to the "action" column.
When the button is clicked, a notification is shown with the name of the row.

*Since version 3.5.0:*
UI elements in scoped slots can access the `props` object to get the current row and column.
Previously, the `props` object was only available in Vue templates.

main.py

[Button]

````python
from nicegui import ui

columns = [
    {'name': 'name', 'label': 'Name', 'field': 'name'},
    {'name': 'action', 'label': 'Action', 'align': 'center'},
]
rows = [
    {'name': 'Alice'},
    {'name': 'Bob'},
]
table = ui.table(columns=columns, rows=rows)
with table.add_slot('body-cell-action'):
    with table.cell('action'):
        ui.button('Notify').props('flat').on(
            'click',
            js_handler='() => emit(props.row.name)',
            handler=lambda e: ui.notify(e.args),
        )

ui.run()
````

## Table with drop down selection

Here is an example of how to use a drop down selection in a table.
After emitting a "update:model-value" event from the `ui.select` element,
the `rename` function updates the table rows.

*Since version 3.5.0:*
UI elements in scoped slots can access the `props` object to get the current row and column.
Previously, the `props` object was only available in Vue templates.

main.py

[Button]

````python
from nicegui import events, ui

columns = [
    {'name': 'name', 'label': 'Name', 'field': 'name'},
    {'name': 'age', 'label': 'Age', 'field': 'age'},
]
rows = [
    {'id': 0, 'name': 'Alice', 'age': 18},
    {'id': 1, 'name': 'Bob', 'age': 21},
    {'id': 2, 'name': 'Carol'},
]
name_options = ['Alice', 'Bob', 'Carol']

def rename(e: events.GenericEventArguments) -> None:
    row_id, name_index = e.args
    for row in table.rows:
        if row['id'] == row_id:
            row['name'] = name_options[name_index]
    ui.notify(f'Table.rows is now: {table.rows}')

table = ui.table(columns=columns, rows=rows).classes('w-full')
with table.add_slot('body-cell-name'):
    with table.cell('name'):
        ui.select(name_options).props(':model-value=props.row.name').on(
            'update:model-value',
            js_handler='(e) => emit(props.row.id, e.value)',
            handler=rename,
        )

ui.run()
````

## Table from Pandas DataFrame

You can create a table from a Pandas DataFrame using the `from_pandas` method.
This method takes a Pandas DataFrame as input and returns a table.

main.py

[Button]

````python
import pandas as pd
from nicegui import ui

df = pd.DataFrame(data={'col1': [1, 2], 'col2': [3, 4]})
ui.table.from_pandas(df).classes('max-h-40')

ui.run()
````

## Table from Polars DataFrame

You can create a table from a Polars DataFrame using the `from_polars` method.
This method takes a Polars DataFrame as input and returns a table.

*Added in version 2.7.0*

main.py

[Button]

````python
import polars as pl
from nicegui import ui

df = pl.DataFrame(data={'col1': [1, 2], 'col2': [3, 4]})
ui.table.from_polars(df).classes('max-h-40')

ui.run()
````

## Adding rows

It's simple to add new rows by updating the `rows` property.
With the "virtual-scroll" prop set, the table can be programmatically scrolled with the `scrollTo` JavaScript function.

main.py

[Button]

````python
from datetime import datetime
from nicegui import ui

def add():
    table.rows.append({'date': datetime.now().strftime('%c')})
    table.run_method('scrollTo', len(table.rows) - 1)

columns = [{'name': 'date', 'label': 'Date', 'field': 'date'}]
table = ui.table(columns=columns, rows=[]).classes('h-52').props('virtual-scroll')
ui.button('Add row', on_click=add)

ui.run()
````

## Custom sorting and formatting

You can define dynamic column attributes using a `:` prefix.
This way you can define custom sorting and formatting functions.

The following example allows sorting the `name` column by length.
The `age` column is formatted to show the age in years.

main.py

[Button]

````python
from nicegui import ui

columns = [
    {
        'name': 'name',
        'label': 'Name',
        'field': 'name',
        'sortable': True,
        ':sort': '(a, b, rowA, rowB) => b.length - a.length',
    },
    {
        'name': 'age',
        'label': 'Age',
        'field': 'age',
        ':format': 'value => value + " years"',
    },
]
rows = [
    {'name': 'Alice', 'age': 18},
    {'name': 'Bob', 'age': 21},
    {'name': 'Carl', 'age': 42},
]
ui.table(columns=columns, rows=rows, row_key='name')

ui.run()
````

## Toggle fullscreen

You can toggle the fullscreen mode of a table using the `toggle_fullscreen()` method.

main.py

[Button]

````python
from nicegui import ui

table = ui.table(
    columns=[{'name': 'name', 'label': 'Name', 'field': 'name'}],
    rows=[{'name': 'Alice'}, {'name': 'Bob'}, {'name': 'Carol'}],
).classes('w-full')

with table.add_slot('top-left'):
    def toggle() -> None:
        table.toggle_fullscreen()
        button.props('icon=fullscreen_exit' if table.is_fullscreen else 'icon=fullscreen')
    button = ui.button('Toggle fullscreen', icon='fullscreen', on_click=toggle).props('flat')

ui.run()
````

## Pagination

You can provide either a single integer or a dictionary to define pagination.

The dictionary can contain the following keys:

- `rowsPerPage`: The number of rows per page.
- `sortBy`: The column name to sort by.
- `descending`: Whether to sort in descending order.
- `page`: The current page (1-based).

*Since version 4.0.0:*
The pagination controls are shown if pagination is provided, also when assigning `table.pagination` later.
Use `pagination_controls=False` to paginate the rows without showing the controls.

main.py

[Button]

````python
from nicegui import ui

columns = [
    {'name': 'name', 'label': 'Name', 'field': 'name', 'required': True, 'align': 'left'},
    {'name': 'age', 'label': 'Age', 'field': 'age', 'sortable': True},
]
rows = [
    {'name': 'Elsa', 'age': 18},
    {'name': 'Oaken', 'age': 46},
    {'name': 'Hans', 'age': 20},
    {'name': 'Sven'},
    {'name': 'Olaf', 'age': 4},
    {'name': 'Anna', 'age': 17},
]
ui.table(columns=columns, rows=rows, pagination=3)
ui.table(columns=columns, rows=rows, pagination={'rowsPerPage': 4, 'sortBy': 'age', 'page': 2})

ui.run()
````

## Handle pagination changes

You can handle pagination changes using the `on_pagination_change` parameter.

main.py

[Button]

````python
from nicegui import ui

ui.table(
    columns=[{'id': 'Name', 'label': 'Name', 'field': 'Name', 'align': 'left'}],
    rows=[{'Name': f'Person {i}'} for i in range(100)],
    pagination=3,
    on_pagination_change=lambda e: ui.notify(e.value),
)

ui.run()
````

## Computed props

You can access the computed props of a table within async callback functions.

main.py

[Button]

````python
from nicegui import ui

async def show_filtered_sorted_rows():
    ui.notify(await table.get_filtered_sorted_rows())

async def show_computed_rows():
    ui.notify(await table.get_computed_rows())

table = ui.table(
    columns=[
        {'name': 'name', 'label': 'Name', 'field': 'name', 'align': 'left', 'sortable': True},
        {'name': 'age', 'label': 'Age', 'field': 'age', 'align': 'left', 'sortable': True}
    ],
    rows=[
        {'name': 'Noah', 'age': 33},
        {'name': 'Emma', 'age': 21},
        {'name': 'Rose', 'age': 88},
        {'name': 'James', 'age': 59},
        {'name': 'Olivia', 'age': 62},
        {'name': 'Liam', 'age': 18},
    ],
    row_key='name',
    pagination=3,
)
ui.input('Search by name/age').bind_value(table, 'filter')
ui.button('Show filtered/sorted rows', on_click=show_filtered_sorted_rows)
ui.button('Show computed rows', on_click=show_computed_rows)

ui.run()
````

## Computed fields

You can use functions to compute the value of a column.
The function receives the row as an argument.
See the [Quasar documentation](https://quasar.dev/vue-components/table#defining-the-columns) for more information.

main.py

[Button]

````python
from nicegui import ui

columns = [
    {'name': 'name', 'label': 'Name', 'field': 'name', 'align': 'left'},
    {'name': 'length', 'label': 'Length', ':field': 'row => row.name.length'},
]
rows = [
    {'name': 'Alice'},
    {'name': 'Bob'},
    {'name': 'Christopher'},
]
ui.table(columns=columns, rows=rows, row_key='name')

ui.run()
````

## Conditional formatting

You can use scoped slots to conditionally format the content of a cell.
See the [Quasar documentation](https://quasar.dev/vue-components/table#example--body-cell-slot)
for more information about body-cell slots.

In this demo we use a `q-badge` to display the age in red if the person is under 21 years old.
We use the `body-cell-age` slot to insert the `q-badge` into the `age` column.
The ":color" attribute of the `q-badge` is set to "red" if the age is under 21, otherwise it is set to "green".
The colon in front of the "color" attribute indicates that the value is a JavaScript expression.

*Since version 3.5.0:*
UI elements in scoped slots can access the `props` object to get the current cell value.
Previously, the `props` object was only available in Vue templates.

main.py

[Button]

````python
from nicegui import ui

columns = [
    {'name': 'name', 'label': 'Name', 'field': 'name'},
    {'name': 'age', 'label': 'Age', 'field': 'age'},
]
rows = [
    {'name': 'Alice', 'age': 18},
    {'name': 'Bob', 'age': 21},
    {'name': 'Carol', 'age': 42},
]
table = ui.table(columns=columns, rows=rows, row_key='name')
with table.add_slot('body-cell-age'):
    with table.cell('age'):
        ui.badge().props('''
            :color="props.value < 21 ? 'red' : 'green'"
            :label="props.value"
        ''')

ui.run()
````

## Table cells with links

Here is a demo of how to insert links into table cells.
We use the `body-cell-link` slot to insert an `<a>` tag into the `link` column.

*Since version 3.5.0:*
UI elements in scoped slots can access the `props` object to get the current cell value.
Previously, the `props` object was only available in Vue templates.

main.py

[Button]

````python
from nicegui import ui

columns = [
    {'name': 'name', 'label': 'Name', 'field': 'name', 'align': 'left'},
    {'name': 'link', 'label': 'Link', 'field': 'link', 'align': 'left'},
]
rows = [
    {'name': 'Apple', 'link': 'https://apple.com'},
    {'name': 'Google', 'link': 'https://google.com'},
    {'name': 'Microsoft', 'link': 'https://microsoft.com'},
]
table = ui.table(columns=columns, rows=rows, row_key='name')
with table.add_slot('body-cell-link'):
    with table.cell('link'):
        ui.link().props(':href=props.value :textContent=props.value')

ui.run()
````

## Table cells with HTML

This demo shows how to define a named slot to render HTML content.
The slot name "body-cell-[name]" can be adjusted to match any column with corresponding name.

main.py

[Button]

````python
from nicegui import ui

ui.table(rows=[
    {'name': 'bold', 'code': '<b>Bold</b>'},
    {'name': 'italic', 'code': '<i>Italic</i>'},
    {'name': 'underline', 'code': '<u>Underline</u>'},
]).add_slot('body-cell-code', '<q-td v-html="props.row.code"></q-td>')

ui.run()
````

## Table with masonry-like grid

You can use the `grid` prop to display the table as a masonry-like grid.
See the [Quasar documentation](https://quasar.dev/vue-components/table#grid-style) for more information.

main.py

[Button]

````python
from nicegui import ui

columns = [
    {'name': 'name', 'label': 'Name', 'field': 'name'},
    {'name': 'age', 'label': 'Age', 'field': 'age'},
]
rows = [
    {'name': 'Alice', 'age': 18},
    {'name': 'Bob', 'age': 21},
    {'name': 'Carol', 'age': 42},
]
table = ui.table(columns=columns, rows=rows, row_key='name').props('grid')
with table.add_slot('item'):
    with ui.card().tight().props('flat bordered').classes('m-1 items-stretch text-center'):
        with ui.card_section():
            ui.label().props(':textContent=props.row.name').classes('font-bold')
        ui.separator()
        with ui.card_section():
            ui.label().props(''' :textContent="props.row.age + ' years'" ''')

ui.run()
````

## Slot templates with NiceGUI elements

Instead of using Vue templates, you can use NiceGUI elements in slot templates.
The following demo shows how to use the `props` object in JavaScript to customize buttons and badges.
The `js_handler` is used to forward the current value of the cell to the Python `handler`.

*Added in version 3.5.0*

main.py

[Button]

````python
from nicegui import ui

table = ui.table(rows=[{'name': 'Alice', 'age': 18}, {'name': 'Bob', 'age': 21}])
with table.add_slot('body-cell-name'):
    with table.cell('name'):
        ui.button().props(':label=props.value flat').on(
            'click',
            js_handler='() => emit(props.value)',
            handler=lambda e: ui.notify(f'Clicked {e.args}'),
        )
with table.add_slot('body-cell-age'):
    with table.cell('age'):
        ui.badge().props('''
            :label=props.value
            :color="props.value < 21 ? 'red' : 'green'"
        ''')

ui.run()
````

## Reference

## Initializer

:rows: list of row objects
:columns: list of column objects (defaults to the columns of the first row *since version 2.0.0*)
:column_defaults: optional default column properties, *added in version 2.0.0*
:row_key: name of the column containing unique data identifying the row (default: "id")
:title: title of the table
:selection: selection type ("single" or "multiple"; default: ``None``)
:pagination: a dictionary correlating to a pagination object or number of rows per page (``None`` hides the pagination unless ``pagination_controls`` is ``True``, 0 means "infinite"; default: ``None``).
:pagination_controls: whether to show the pagination controls (default: ``None`` which shows them if ``pagination`` is provided, *added in version 4.0.0*)
:on_select: callback which is invoked when the selection changes
:on_pagination_change: callback which is invoked when the pagination changes

## Properties

**`column_defaults`**`: dict | None (settable)`

Default column properties.

**`columns`**`: list[dict] (settable)`

List of columns.

**`is_fullscreen`**`: bool (settable)`

Whether the table is in fullscreen mode.

**`pagination`**`: dict (settable)`

Pagination object (assigning shows the pagination controls unless ``pagination_controls`` is set).

**`pagination_controls`**`: bool | None (settable)`

Whether the pagination controls are shown (``None``: shown if the table has pagination).

**`row_key`**`: str (settable)`

Name of the column containing unique data identifying the row.

**`rows`**`: list[dict] (settable)`

List of rows.

**`selected`**`: list[dict] (settable)`

List of selected rows.

**`selection`**`: Literal[None, 'single', 'multiple'] (settable)`

Selection type.

*Added in version 2.11.0*

**Inherited properties**

**`classes`**`: 'Classes[Self]'`

The classes of the element.

**`client`**`: 'Client'`

The client this element belongs to.

**`filter`**`: BindableProperty`

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

**`add_row`**`(row: dict) -> None`

Add a single row to the table.

**`add_rows`**`(rows: list[dict]) -> None`

Add rows to the table.

`@classmethod`<br />**`from_pandas`**`(df: pd.DataFrame, columns: list[dict] | None = None, column_defaults: dict | None = None, row_key: str = 'id', title: str | None = None, selection: Literal['single', 'multiple'] | None = None, pagination: int | dict | None = None, pagination_controls: bool | None = None, on_select: collections.abc.Callable[[nicegui.events.TableSelectionEventArguments], Any] | collections.abc.Callable[[], Any] | None = None, on_pagination_change: collections.abc.Callable[[nicegui.events.ValueChangeEventArguments[dict]], Any] | collections.abc.Callable[[], Any] | None = None) -> Self`

Create a table from a Pandas DataFrame.

Note:
If the DataFrame contains non-serializable columns of type ``datetime64[ns]``, ``timedelta64[ns]``, ``complex128`` or ``period[M]``,
they will be converted to strings.
To use a different conversion, convert the DataFrame manually before passing it to this method.
See `issue 1698 <https://github.com/zauberzeug/nicegui/issues/1698>`_ for more information.

*Added in version 2.0.0*

*Since version 3.12.0:*
Any DataFrame index other than an unnamed ``RangeIndex`` is auto-included as column(s).
Pass ``df.reset_index(drop=True)`` to drop the index instead.

:param df: Pandas DataFrame
:param columns: list of column objects (defaults to the columns of the dataframe)
:param column_defaults: optional default column properties
:param row_key: name of the column containing unique data identifying the row (default: "id")
:param title: title of the table
:param selection: selection type ("single" or "multiple"; default: ``None``)
:param pagination: a dictionary correlating to a pagination object or number of rows per page (``None`` hides the pagination unless ``pagination_controls`` is ``True``, 0 means "infinite"; default: ``None``).
:param pagination_controls: whether to show the pagination controls (default: ``None`` which shows them if ``pagination`` is provided, *added in version 4.0.0*)
:param on_select: callback which is invoked when the selection changes
:param on_pagination_change: callback which is invoked when the pagination changes (*added in version 4.0.0*)
:return: table element

`@classmethod`<br />**`from_polars`**`(df: pl.DataFrame, columns: list[dict] | None = None, column_defaults: dict | None = None, row_key: str = 'id', title: str | None = None, selection: Literal['single', 'multiple'] | None = None, pagination: int | dict | None = None, pagination_controls: bool | None = None, on_select: collections.abc.Callable[[nicegui.events.TableSelectionEventArguments], Any] | collections.abc.Callable[[], Any] | None = None, on_pagination_change: collections.abc.Callable[[nicegui.events.ValueChangeEventArguments[dict]], Any] | collections.abc.Callable[[], Any] | None = None) -> Self`

Create a table from a Polars DataFrame.

Note:
If the DataFrame contains non-UTF-8 datatypes, they will be converted to strings.
To use a different conversion, convert the DataFrame manually before passing it to this method.

*Added in version 2.7.0*

:param df: Polars DataFrame
:param columns: list of column objects (defaults to the columns of the dataframe)
:param column_defaults: optional default column properties
:param row_key: name of the column containing unique data identifying the row (default: "id")
:param title: title of the table
:param selection: selection type ("single" or "multiple"; default: ``None``)
:param pagination: a dictionary correlating to a pagination object or number of rows per page (``None`` hides the pagination unless ``pagination_controls`` is ``True``, 0 means "infinite"; default: ``None``).
:param pagination_controls: whether to show the pagination controls (default: ``None`` which shows them if ``pagination`` is provided, *added in version 4.0.0*)
:param on_select: callback which is invoked when the selection changes
:param on_pagination_change: callback which is invoked when the pagination changes (*added in version 4.0.0*)
:return: table element

**`get_computed_rows`**`(timeout: float = 1) -> list[dict]`

Asynchronously return the computed rows of the table.

**`get_computed_rows_number`**`(timeout: float = 1) -> int`

Asynchronously return the number of computed rows of the table.

**`get_filtered_sorted_rows`**`(timeout: float = 1) -> list[dict]`

Asynchronously return the filtered and sorted rows of the table.

**`on_pagination_change`**`(callback: collections.abc.Callable[[nicegui.events.ValueChangeEventArguments[dict]], Any] | collections.abc.Callable[[], Any]) -> Self`

Add a callback to be invoked when the pagination changes.

**`on_select`**`(callback: collections.abc.Callable[[nicegui.events.TableSelectionEventArguments], Any] | collections.abc.Callable[[], Any]) -> Self`

Add a callback to be invoked when the selection changes.

**`remove_row`**`(row: dict) -> None`

Remove a single row from the table.

**`remove_rows`**`(rows: list[dict]) -> None`

Remove rows from the table.

**`set_fullscreen`**`(value: bool) -> Self`

Set fullscreen mode.

**`set_selection`**`(value: Literal[None, 'single', 'multiple']) -> Self`

Set the selection type.

*Added in version 2.11.0*

**`toggle_fullscreen`**`() -> Self`

Toggle fullscreen mode.

**`update_from_pandas`**`(df: pd.DataFrame, clear_selection: bool = True, columns: list[dict] | None = None, column_defaults: dict | None = None) -> None`

Update the table from a Pandas DataFrame.

See ``from_pandas()`` for more information about the conversion of non-serializable columns.

If ``columns`` is not provided and the columns had been inferred from a DataFrame,
the columns will be updated to match the new DataFrame.

:param df: Pandas DataFrame
:param clear_selection: whether to clear the selection (default: True)
:param columns: list of column objects (defaults to the columns of the dataframe)
:param column_defaults: optional default column properties

**`update_from_polars`**`(df: pl.DataFrame, clear_selection: bool = True, columns: list[dict] | None = None, column_defaults: dict | None = None) -> None`

Update the table from a Polars DataFrame.

:param df: Polars DataFrame
:param clear_selection: whether to clear the selection (default: True)
:param columns: list of column objects (defaults to the columns of the dataframe)
:param column_defaults: optional default column properties

**`update_rows`**`(rows: list[dict], clear_selection: bool = True) -> None`

Update rows in the table.

:param rows: list of rows to update
:param clear_selection: whether to clear the selection (default: True)

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

**`bind_filter`**`(target_object: Any, target_name: str | tuple[str, ...] = 'filter', forward: collections.abc.Callable[[Any], Any] | None = None, backward: collections.abc.Callable[[Any], Any] | None = None, strict: bool | None = None) -> Self`

Bind the filter of this element to the target object's target_name property.

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

**`bind_filter_from`**`(target_object: Any, target_name: str | tuple[str, ...] = 'filter', backward: collections.abc.Callable[[Any], Any] | None = None, strict: bool | None = None) -> Self`

Bind the filter of this element from the target object's target_name property.

The binding works one way only, from the target to this element.
The update happens immediately and whenever a value changes.
The ``target_name`` parameter also accepts a tuple of strings for nested keys (*since version 3.10.0*).

:param target_object: The object to bind from.
:param target_name: The name of the property to bind from.
:param backward: A function to apply to the value before applying it to this element (default: identity).
:param strict: Whether to check (and raise) if the target object has the specified property (default: None,
    performs a check if the object is not a dictionary, *added in version 3.0.0*).

**`bind_filter_to`**`(target_object: Any, target_name: str | tuple[str, ...] = 'filter', forward: collections.abc.Callable[[Any], Any] | None = None, strict: bool | None = None) -> Self`

Bind the filter of this element to the target object's target_name property.

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

**`set_filter`**`(filter_: str) -> Self`

Set the filter of this element.

:param filter\_: The new filter.

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

- `FilterElement`
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