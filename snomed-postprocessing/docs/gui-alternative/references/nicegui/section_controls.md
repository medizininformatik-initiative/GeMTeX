# Controls | NiceGUI

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

# *Controls*

## [Button](/documentation/button)

This element is based on Quasar's `QBtn <https://quasar.dev/vue-components/button>`_ component.

The ``color`` parameter accepts a Quasar color, a Tailwind color, or a CSS color.
If a Quasar color is used, the button will be styled according to the Quasar theme including the color of the text.
Note that there are colors like "red" being both a Quasar color and a CSS color.
In such cases the Quasar color will be used.

:text: the label of the button
:on_click: callback which is invoked when button is pressed
:color: the color of the button (either a Quasar, Tailwind, or CSS color or ``None``, default: 'primary')
:icon: the name of an icon to be displayed on the button (default: ``None``)

main.py

[Button]

````python
from nicegui import ui

ui.button('Click me!', on_click=lambda: ui.notify('You clicked me!'))

ui.run()
````

[See more →](/documentation/button)

## [Button Group](/documentation/button_group)

This element is based on Quasar's `QBtnGroup <https://quasar.dev/vue-components/button-group>`_ component.
You must use the same design props on both the parent button group and the children buttons.

main.py

[Button]

````python
from nicegui import ui

with ui.button_group():
    ui.button('One', on_click=lambda: ui.notify('You clicked Button 1!'))
    ui.button('Two', on_click=lambda: ui.notify('You clicked Button 2!'))
    ui.button('Three', on_click=lambda: ui.notify('You clicked Button 3!'))

ui.run()
````

[See more →](/documentation/button_group)

## [Dropdown Button](/documentation/button_dropdown)

This element is based on Quasar's `QBtnDropDown <https://quasar.dev/vue-components/button-dropdown>`_ component.

The ``color`` parameter accepts a Quasar color, a Tailwind color, or a CSS color.
If a Quasar color is used, the button will be styled according to the Quasar theme including the color of the text.
Note that there are colors like "red" being both a Quasar color and a CSS color.
In such cases the Quasar color will be used.

:text: the label of the button
:value: if the dropdown is open or not (default: ``False``)
:on_value_change: callback which is invoked when the dropdown is opened or closed
:on_click: callback which is invoked when button is pressed
:color: the color of the button (either a Quasar, Tailwind, or CSS color or ``None``, default: 'primary')
:icon: the name of an icon to be displayed on the button (default: ``None``)
:auto_close: whether the dropdown should close automatically when an item is clicked (default: ``False``)
:split: whether to split the dropdown icon into a separate button (default: ``False``)

main.py

[Button]

````python
from nicegui import ui

with ui.dropdown_button('Open me!', auto_close=True):
    ui.item('Item 1', on_click=lambda: ui.notify('You clicked item 1'))
    ui.item('Item 2', on_click=lambda: ui.notify('You clicked item 2'))

ui.run()
````

[See more →](/documentation/button_dropdown)

## [Floating Action Button (FAB)](/documentation/fab)

A floating action button that can be used to trigger an action.
This element is based on Quasar's `QFab <https://quasar.dev/vue-components/floating-action-button#qfab-api>`_ component.

*Added in version 2.22.0*

:icon: icon to be displayed on the FAB
:value: whether the FAB is already opened (default: ``False``)
:label: optional label for the FAB
:color: background color of the FAB (default: "primary")
:direction: direction of the FAB ("up", "down", "left", "right", default: "right")

main.py

[Button]

````python
from nicegui import ui

with ui.fab('navigation', label='Transport'):
    ui.fab_action('train', on_click=lambda: ui.notify('Train'))
    ui.fab_action('sailing', on_click=lambda: ui.notify('Boat'))
    ui.fab_action('rocket', on_click=lambda: ui.notify('Rocket'))

ui.run()
````

[See more →](/documentation/fab)

## [Badge](/documentation/badge)

A badge element wrapping Quasar's
`QBadge <https://quasar.dev/vue-components/badge>`_ component.

:text: the initial value of the text field
:color: the color name for component (either a Quasar, Tailwind, or CSS color or ``None``, default: "primary")
:text_color: text color (either a Quasar, Tailwind, or CSS color or ``None``, default: ``None``)
:outline: use 'outline' design (colored text and borders only) (default: False)

main.py

[Button]

````python
from nicegui import ui

with ui.button('Click me!', on_click=lambda: badge.set_text(int(badge.text) + 1)):
    badge = ui.badge('0', color='red').props('floating')

ui.run()
````

[See more →](/documentation/badge)

## [Chip](/documentation/chip)

A chip element wrapping Quasar's `QChip <https://quasar.dev/vue-components/chip>`_ component.
It can be clickable, selectable and removable.

:text: the initial value of the text field (default: "")
:icon: the name of an icon to be displayed on the chip (default: ``None``)
:color: the color name for component (either a Quasar, Tailwind, or CSS color or ``None``, default: "primary")
:text_color: text color (either a Quasar, Tailwind, or CSS color or ``None``, default: ``None``)
:on_click: callback which is invoked when chip is clicked. Makes the chip clickable if set
:selectable: whether the chip is selectable (default: ``False``)
:selected: whether the chip is selected (default: ``False``)
:on_selection_change: callback which is invoked when the chip's selection state is changed
:removable: whether the chip is removable. Shows a small "x" button if True (default: ``False``)
:on_value_change: callback which is invoked when the chip is removed or unremoved

main.py

[Button]

````python
from nicegui import ui

with ui.row().classes('gap-1'):
    ui.chip('Click me', icon='ads_click', on_click=lambda: ui.notify('Clicked'))
    ui.chip('Selectable', selectable=True, icon='bookmark', color='orange')
    ui.chip('Removable', removable=True, icon='label', color='indigo-3')
    ui.chip('Styled', icon='star', color='green').props('outline square')
    ui.chip('Disabled', icon='block', color='red').set_enabled(False)

ui.run()
````

[See more →](/documentation/chip)

## [Toggle](/documentation/toggle)

This element is based on Quasar's `QBtnToggle <https://quasar.dev/vue-components/button-toggle>`_ component.

The options can be specified as a list of values, or as a dictionary mapping values to labels.
After manipulating the options, call ``update()`` to update the options in the UI.

:options: a list ['value1', ...] or dictionary ``{'value1':'label1', ...}`` specifying the options
:value: the initial value
:on_change: callback to execute when selection changes
:clearable: whether the toggle can be cleared by clicking the selected option

main.py

[Button]

````python
from nicegui import ui

toggle1 = ui.toggle([1, 2, 3], value=1)
toggle2 = ui.toggle({1: 'A', 2: 'B', 3: 'C'}).bind_value(toggle1, 'value')

ui.run()
````

[See more →](/documentation/toggle)

## [Radio Selection](/documentation/radio)

This element is based on Quasar's `QOptionGroup <https://quasar.dev/vue-components/option-group>`_ component.

The options can be specified as a list of values, or as a dictionary mapping values to labels.
After manipulating the options, call ``update()`` to update the options in the UI.

:options: a list ['value1', ...] or dictionary ``{'value1':'label1', ...}`` specifying the options
:value: the initial value
:on_change: callback to execute when selection changes

main.py

[Button]

````python
from nicegui import ui

radio1 = ui.radio([1, 2, 3], value=1).props('inline')
radio2 = ui.radio({1: 'A', 2: 'B', 3: 'C'}).props('inline').bind_value(radio1, 'value')

ui.run()
````

[See more →](/documentation/radio)

## [Dropdown Selection](/documentation/select)

This element is based on Quasar's `QSelect <https://quasar.dev/vue-components/select>`_ component.

The options can be specified as a list of values, or as a dictionary mapping values to labels.
After manipulating the options, call ``update()`` to update the options in the UI.

If ``with_input`` is True, an input field is shown to filter the options.

If ``new_value_mode`` is not None, it implies ``with_input=True`` and the user can enter new values in the input field.
See `Quasar's documentation <https://quasar.dev/vue-components/select#the-new-value-mode-prop>`_ for details.
Note that this mode is ineffective when setting the ``value`` property programmatically.

You can use the ``validation`` parameter to define a dictionary of validation rules,
e.g. ``{'Too long!': lambda value: len(value) < 3}``.
The key of the first rule that fails will be displayed as an error message.
Alternatively, you can pass a callable that returns an optional error message.
To disable the automatic validation on every value change, you can use the ``without_auto_validation`` method.

:options: a list ['value1', ...] or dictionary ``{'value1':'label1', ...}`` specifying the options
:label: the label to display above the selection
:value: the initial value
:on_change: callback to execute when selection changes
:with_input: whether to show an input field to filter the options
:new_value_mode: handle new values from user input (default: None, i.e. no new values)
:multiple: whether to allow multiple selections
:clearable: whether to add a button to clear the selection
:validation: dictionary of validation rules or a callable that returns an optional error message (default: None for no validation)
:key_generator: a callback or iterator to generate a dictionary key for new values

main.py

[Button]

````python
from nicegui import ui

select1 = ui.select([1, 2, 3], value=1)
select2 = ui.select({1: 'One', 2: 'Two', 3: 'Three'}).bind_value(select1, 'value')

ui.run()
````

[See more →](/documentation/select)

## [Input Chips](/documentation/input_chips)

An input field that manages a collection of values as visual "chips" or tags.
Users can type to add new chips and remove existing ones by clicking or using keyboard shortcuts.

This element is based on Quasar's `QSelect <https://quasar.dev/vue-components/select>`_ component.
Unlike a traditional dropdown selection, this variant focuses on free-form text input with chips,
making it ideal for tags, keywords, or any list of user-defined values.

You can use the ``validation`` parameter to define a dictionary of validation rules,
e.g. ``{'Too long!': lambda value: len(value) < 3}``.
The key of the first rule that fails will be displayed as an error message.
Alternatively, you can pass a callable that returns an optional error message.
To disable the automatic validation on every value change, you can use the ``without_auto_validation`` method.

*Added in version 2.22.0*

:label: the label to display above the selection
:value: the initial value
:on_change: callback to execute when selection changes
:new_value_mode: handle new values from user input (default: "toggle")
:clearable: whether to add a button to clear the selection
:validation: dictionary of validation rules or a callable that returns an optional error message (default: None for no validation)

main.py

[Button]

````python
from nicegui import ui

ui.input_chips('My favorite chips', value=['Pringles', 'Doritos', "Lay's"])

ui.run()
````

[See more →](/documentation/input_chips)

## [Checkbox](/documentation/checkbox)

This element is based on Quasar's `QCheckbox <https://quasar.dev/vue-components/checkbox>`_ component.

:text: the label to display next to the checkbox
:value: whether it should be checked initially (default: ``False``)
:on_change: callback to execute when value changes

main.py

[Button]

````python
from nicegui import ui

checkbox = ui.checkbox('check me')
ui.label('Check!').bind_visibility_from(checkbox, 'value')

ui.run()
````

[See more →](/documentation/checkbox)

## [Switch](/documentation/switch)

This element is based on Quasar's `QToggle <https://quasar.dev/vue-components/toggle>`_ component.

:text: the label to display next to the switch
:value: whether it should be active initially (default: ``False``)
:on_change: callback which is invoked when state is changed by the user

main.py

[Button]

````python
from nicegui import ui

switch = ui.switch('switch me')
ui.label('Switch!').bind_visibility_from(switch, 'value')

ui.run()
````

[See more →](/documentation/switch)

## [Slider](/documentation/slider)

This element is based on Quasar's `QSlider <https://quasar.dev/vue-components/slider>`_ component.

:min: lower bound of the slider
:max: upper bound of the slider
:step: step size
:value: initial value to set position of the slider
:on_change: callback to execute when the value changes, including while dragging
    (to react only when the slider is released, use ``.on('change', ...)`` instead)

main.py

[Button]

````python
from nicegui import ui

slider = ui.slider(min=0, max=100, value=50)
ui.label().bind_text_from(slider, 'value')

ui.run()
````

[See more →](/documentation/slider)

## [Range](/documentation/range)

This element is based on Quasar's `QRange <https://quasar.dev/vue-components/range>`_ component.

:min: lower bound of the range
:max: upper bound of the range
:step: step size
:value: initial value to set min and max position of the range (default: ``min`` to ``max``)
:on_change: callback to execute when the value changes, including while dragging
    (to react only when the range is released, use ``.on('change', ...)`` instead)

main.py

[Button]

````python
from nicegui import ui

min_max_range = ui.range(min=0, max=100, value={'min': 20, 'max': 80})
ui.label().bind_text_from(min_max_range, 'value',
                          backward=lambda v: f'min: {v["min"]}, max: {v["max"]}')

ui.run()
````

[See more →](/documentation/range)

## [Rating](/documentation/rating)

This element is based on Quasar's `QRating <https://quasar.dev/vue-components/rating>`_ component.

*Added in version 2.12.0*

:value: initial value (default: ``None``)
:max: maximum rating, number of icons (default: 5)
:icon: name of icons to be displayed (default: star)
:icon_selected: name of an icon to be displayed when selected (default: same as ``icon``)
:icon_half: name of an icon to be displayed when half-selected (default: same as ``icon``)
:color: color(s) of the icons (Quasar, Tailwind, or CSS colors or ``None``, default: "primary")
:size: size in CSS units, including unit name or standard size name (xs|sm|md|lg|xl), examples: 16px, 2rem
:on_change: callback to execute when selection changes

main.py

[Button]

````python
from nicegui import ui

ui.rating(value=4)

ui.run()
````

[See more →](/documentation/rating)

## [Joystick](/documentation/joystick)

Create a joystick based on `nipple.js <https://yoannmoi.net/nipplejs/>`_.

:on_start: callback for when the user touches the joystick
:on_move: callback for when the user moves the joystick
:on_end: callback for when the user releases the joystick
:throttle: throttle interval in seconds for the move event (default: 0.05)
:\*\*options: arguments like ``color`` which should be passed to the `underlying nipple.js library <https://github.com/yoannmoinet/nipplejs#options>`_

main.py

[Button]

````python
from nicegui import ui

ui.joystick(
    color='blue', size=50,
    on_move=lambda e: coordinates.set_text(f'{e.x:.3f}, {e.y:.3f}'),
    on_end=lambda _: coordinates.set_text('0, 0'),
).classes('bg-slate-300')
coordinates = ui.label('0, 0')

ui.run()
````

[See more →](/documentation/joystick)

## [Text Input](/documentation/input)

This element is based on Quasar's `QInput <https://quasar.dev/vue-components/input>`_ component.

The ``on_change`` event is called on every keystroke and the value updates accordingly.
If you want to wait until the user confirms the input, you can register a custom event callback, e.g.
``ui.input(...).on('keydown.enter', ...)`` or ``ui.input(...).on('blur', ...)``.

You can use the ``validation`` parameter to define a dictionary of validation rules,
e.g. ``{'Too long!': lambda value: len(value) < 3}``.
The key of the first rule that fails will be displayed as an error message.
Alternatively, you can pass a callable that returns an optional error message.
To disable the automatic validation on every value change, you can use the ``without_auto_validation`` method.

Note about styling the input:
Quasar's ``QInput`` component is a wrapper around a native ``input`` element.
This means that you cannot style the input directly,
but you can use the ``input-class`` and ``input-style`` props to style the native input element.
See the "Style" props section on the `QInput <https://quasar.dev/vue-components/input>`_ documentation for more details.

:label: displayed label for the text input
:placeholder: text to show if no value is entered
:value: the current value of the text input
:password: whether to hide the input (default: False)
:password_toggle_button: whether to show a button to toggle the password visibility (default: False)
:prefix: a prefix to prepend to the displayed value (*added in version 3.5.0*)
:suffix: a suffix to append to the displayed value (*added in version 3.5.0*)
:on_change: callback to execute when the value changes
:autocomplete: optional list of strings for autocompletion
:validation: dictionary of validation rules or a callable that returns an optional error message (default: None for no validation)

main.py

[Button]

````python
from nicegui import ui

ui.input(label='Text', placeholder='start typing',
         on_change=lambda e: result.set_text('you typed: ' + e.value),
         validation={'Input too long': lambda value: len(value) < 20})
result = ui.label()

ui.run()
````

[See more →](/documentation/input)

## [Textarea](/documentation/textarea)

This element is based on Quasar's `QInput <https://quasar.dev/vue-components/input>`_ component.
The ``type`` is set to ``textarea`` to create a multi-line text input.

You can use the ``validation`` parameter to define a dictionary of validation rules,
e.g. ``{'Too long!': lambda value: len(value) < 3}``.
The key of the first rule that fails will be displayed as an error message.
Alternatively, you can pass a callable that returns an optional error message.
To disable the automatic validation on every value change, you can use the ``without_auto_validation`` method.

:label: displayed name for the textarea
:placeholder: text to show if no value is entered
:value: the initial value of the field
:on_change: callback to execute when the value changes
:validation: dictionary of validation rules or a callable that returns an optional error message (default: None for no validation)

main.py

[Button]

````python
from nicegui import ui

ui.textarea(label='Text', placeholder='start typing',
            on_change=lambda e: result.set_text('you typed: ' + e.value))
result = ui.label()

ui.run()
````

[See more →](/documentation/textarea)

## [CodeMirror](/documentation/codemirror)

An element to create a code editor using `CodeMirror <https://codemirror.net/>`_.

It supports syntax highlighting for over 140 languages, more than 30 themes, line numbers, code folding, (limited) auto-completion, and more.

Supported languages and themes:
    - Languages: A list of supported languages can be found in the `@codemirror/language-data <https://github.com/codemirror/language-data/blob/main/src/language-data.ts>`_ package.
    - Themes: A list can be found in the `@uiw/codemirror-themes-all <https://github.com/uiwjs/react-codemirror/tree/master/themes/all>`_ package.

At runtime, the methods ``supported_languages`` and ``supported_themes`` can be used to get supported languages and themes.

*Since version 3.13.0:*
Per-line tooltips can be attached via the ``line_tooltips`` dict.

*Since version 3.14.0:*
The ``keymap`` maps keystrokes (CodeMirror key strings) to Python callbacks.
Pass a bare callable for the default config (prevents the browser default, no per-OS override).
Wrap with ``KeyBinding`` for per-key overrides such as ``prevent_default=False`` or platform-specific shortcuts (``mac=``, ``linux=``, ``win=``).
Use ``map_key`` to add keybindings at runtime and ``unmap_key`` to drop them.
Keybindings do not fire while the editor is disabled.

*Since version 3.16.0:*
Line anchors that track document positions through edits can be attached via the ``line_anchors`` dict
(assign to declare, read back for the current positions).

*Since version 3.17.0:*
Decorations style, hide or annotate parts of the document without changing it.
Assign a list of specs to ``decorations`` or mutate ``decorations`` in place.

*Since version 3.18.0:*
Editor signals report the focus, visible line range and geometry,
and ``reveal_line`` scrolls a given line into view.

:value: initial value of the editor (default: "")
:on_change: callback to be executed when the value changes (default: ``None``)
:keymap: mapping of CodeMirror key strings (e.g. "Mod-s", "F5") to handlers, optionally wrapped with ``KeyBinding`` (default: ``None``, *added in version 3.14.0*)
:on_focus_change: callback when the editor gains or loses focus (*added in version 3.18.0*)
:on_viewport_change: callback when the visible line range changes (throttled to 100 ms) (*added in version 3.18.0*)
:on_geometry_change: callback when the editor or content size changes (throttled to 100 ms) (*added in version 3.18.0*)
:language: initial language of the editor (case-insensitive, default: ``None``)
:theme: initial theme of the editor (default: "basicLight")
:indent: string to use for indentation (any string consisting entirely of the same whitespace character, default: "    ")
:line_wrapping: whether to wrap lines (default: ``False``)
:highlight_whitespace: whether to highlight whitespace (default: ``False``)
:decorations: initial list of decoration specs applied to the editor;
    spec offsets (``from``/``to``/``position``) are Python ``str`` indices (default: ``None``, *added in version 3.17.0*)
:decoration_html: render the ``text`` field of replace/widget decorations as sanitized HTML rather than plain text (default: ``False``, *added in version 3.17.0*)
:line_anchors: initial ``{anchor_id: 1-indexed line}`` mapping of anchors tracking document positions through edits (default: ``None``, *added in version 3.16.0*)
:on_anchor_change: callback to be executed when tracked anchor positions change (default: ``None``, *added in version 3.16.0*)
:line_tooltips: initial mapping of 1-indexed line numbers to tooltip content (default: ``None``, *added in version 3.13.0*)
:line_tooltip_html: render tooltip content as sanitized HTML rather than plain text (default: ``False``, *added in version 3.13.0*)

main.py

[Button]

````python
from nicegui import ui

editor = ui.codemirror('print("Edit me!")', language='Python').classes('h-32')
ui.select(editor.supported_languages, label='Language', clearable=True) \
    .classes('w-32').bind_value(editor, 'language')
ui.select(editor.supported_themes, label='Theme') \
    .classes('w-32').bind_value(editor, 'theme')
ui.checkbox('Wrap Lines', value=editor.line_wrapping,
            on_change=lambda e: editor.set_line_wrapping(e.value))

ui.run()
````

[See more →](/documentation/codemirror)

## [Xterm](/documentation/xterm)

This element is a wrapper around `xterm.js <https://github.com/xtermjs/xterm.js>`_ to emulate a terminal.
Note: This element provides only a front-end component without an underlying shell.

*Added in version 3.1.0*

:options: A dictionary of options to configure the terminal, see the
                `xterm.js documentation <https://xtermjs.org/docs/api/terminal/classes/terminal/#constructor>`_.
:on_bell: Optional callback to be invoked when the terminal's bell is triggered (*added in version 3.10.0*).
:on_data: Optional callback to be invoked when the user types or pastes into the terminal (*added in version 3.10.0*).
                In a typical setup, this should be passed on to the backing pty.
:on_resize: Optional callback to be invoked when the terminal is resized (*added in version 3.10.0*).

main.py

[Button]

````python
from nicegui import ui

terminal = ui.xterm({'cols': 30, 'rows': 9})
ui.timer(0, lambda: terminal.write('Hello NiceGUI!'), once=True)

ui.run()
````

[See more →](/documentation/xterm)

## [Number Input](/documentation/number)

This element is based on Quasar's `QInput <https://quasar.dev/vue-components/input>`_ component.

You can use the ``validation`` parameter to define a dictionary of validation rules,
e.g. ``{'Too small!': lambda value: value > 3}``.
The key of the first rule that fails will be displayed as an error message.
Alternatively, you can pass a callable that returns an optional error message.
To disable the automatic validation on every value change, you can use the ``without_auto_validation`` method.

:label: displayed name for the number input
:placeholder: text to show if no value is entered
:value: the initial value of the field
:min: the minimum value allowed
:max: the maximum value allowed
:precision: the number of decimal places allowed (default: no limit, negative: decimal places before the dot)
:step: the step size for the stepper buttons
:prefix: a prefix to prepend to the displayed value
:suffix: a suffix to append to the displayed value
:format: a string like "%.2f" to format the displayed value
:on_change: callback to execute when the value changes
:validation: dictionary of validation rules or a callable that returns an optional error message (default: None for no validation)

main.py

[Button]

````python
from nicegui import ui

ui.number(label='Number', value=3.1415927, format='%.2f',
          on_change=lambda e: result.set_text(f'you entered: {e.value}'))
result = ui.label()

ui.run()
````

[See more →](/documentation/number)

## [Knob](/documentation/knob)

This element is based on Quasar's `QKnob <https://quasar.dev/vue-components/knob>`_ component.
The element is used to take a number input from the user through mouse/touch panning.

:value: the initial value (default: 0.0)
:min: the minimum value (default: 0.0)
:max: the maximum value (default: 1.0)
:step: the step size (default: 0.01)
:color: knob color (either a Quasar, Tailwind, or CSS color or ``None``, default: "primary")
:center_color: color name for the center part of the component, examples: primary, teal-10
:track_color: color name for the track of the component, examples: primary, teal-10
:size: size in CSS units, including unit name or standard size name (xs|sm|md|lg|xl), examples: 16px, 2rem
:show_value: whether to show the value as text
:on_change: callback to execute when the value changes

main.py

[Button]

````python
from nicegui import ui

knob = ui.knob(0.3, show_value=True)

with ui.knob(color='orange', track_color='grey-2').bind_value(knob, 'value'):
    ui.icon('volume_up')

ui.run()
````

[See more →](/documentation/knob)

## [Color Input](/documentation/color_input)

This element extends Quasar's `QInput <https://quasar.dev/vue-components/input>`_ component with a color picker.

:label: displayed label for the color input
:placeholder: text to show if no color is selected
:value: the current color value
:on_change: callback to execute when the value changes
:preview: change button background to selected color (default: False)

main.py

[Button]

````python
from nicegui import ui

label = ui.label('Change my color!')
ui.color_input(label='Color', value='#000000',
               on_change=lambda e: label.style(f'color:{e.value}'))

ui.run()
````

[See more →](/documentation/color_input)

## [Color Picker](/documentation/color_picker)

This element is based on Quasar's `QMenu <https://quasar.dev/vue-components/menu>`_ and
`QColor <https://quasar.dev/vue-components/color-picker>`_ components.

:on_pick: callback to execute when a color is picked
:value: whether the menu is already opened (default: ``False``)

main.py

[Button]

````python
from nicegui import ui

with ui.button(icon='colorize') as button:
    ui.color_picker(on_pick=lambda e: button.classes(f'!bg-[{e.color}]'))

ui.run()
````

[See more →](/documentation/color_picker)

## [Date Input](/documentation/date_input)

This element extends Quasar's `QInput <https://quasar.dev/vue-components/input>`_ component with a date picker.

*Added in version 3.3.0*

:label: displayed label for the date input
:range_input: if True, allows selecting a range of dates (value will be a dictionary with "from" and "to" keys)
:placeholder: text to show if no date is selected
:value: the current date value
:on_change: callback to execute when the value changes

main.py

[Button]

````python
from nicegui import ui

date = ui.date_input('Date', value='2025-05-31')
ui.label().bind_text_from(date, 'value', lambda v: f'date: {v}')

ui.run()
````

[See more →](/documentation/date_input)

## [Date Picker](/documentation/date)

This element is based on Quasar's `QDate <https://quasar.dev/vue-components/date>`_ component.
The date is a string in the format defined by the ``mask`` parameter.

You can also use the ``range`` or ``multiple`` props to select a range of dates or multiple dates::

    ui.date({'from': '2023-01-01', 'to': '2023-01-05'}).props('range')
    ui.date(['2023-01-01', '2023-01-02', '2023-01-03']).props('multiple')
    ui.date([{'from': '2023-01-01', 'to': '2023-01-05'}, '2023-01-07']).props('multiple range')

:value: the initial date
:mask: the format of the date string (default: 'YYYY-MM-DD')
:on_change: callback to execute when changing the date

main.py

[Button]

````python
from nicegui import ui

ui.date(value='2023-01-01', on_change=lambda e: result.set_text(e.value))
result = ui.label()

ui.run()
````

[See more →](/documentation/date)

## [Time Input](/documentation/time_input)

This element extends Quasar's `QInput <https://quasar.dev/vue-components/input>`_ component with a time picker.

*Added in version 3.3.0*

:label: displayed label for the time input
:placeholder: text to show if no time is selected
:value: the current time value
:on_change: callback to execute when the value changes

main.py

[Button]

````python
from nicegui import ui

time = ui.time_input('Time', value='12:30')
ui.label().bind_text_from(time, 'value', lambda v: f'time: {v}')

ui.run()
````

[See more →](/documentation/time_input)

## [Time Picker](/documentation/time)

This element is based on Quasar's `QTime <https://quasar.dev/vue-components/time>`_ component.
The time is a string in the format defined by the ``mask`` parameter.

:value: the initial time
:mask: the format of the time string (default: 'HH:mm')
:on_change: callback to execute when changing the time

main.py

[Button]

````python
from nicegui import ui

ui.time(value='12:00', on_change=lambda e: result.set_text(e.value))
result = ui.label()

ui.run()
````

[See more →](/documentation/time)

## [File Upload](/documentation/upload)

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

[See more →](/documentation/upload)

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