# Text Elements | NiceGUI

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

# *Text* Elements

## [Label](/documentation/label)

Displays some text.

:text: the content of the label

main.py

[Button]

````python
from nicegui import ui

ui.label('some label')

ui.run()
````

[See more →](/documentation/label)

## [Link](/documentation/link)

Create a hyperlink.

To jump to a specific location within a page you can place linkable anchors with ``ui.link_target("name")``
and link to it with ``ui.link(target="#name")``.

:text: display text
:target: page function, NiceGUI element on the same page or string that is a an absolute URL or relative path from base URL
:new_tab: open link in new tab (default: False)

main.py

[Button]

````python
from nicegui import ui

ui.link('NiceGUI on GitHub', 'https://github.com/zauberzeug/nicegui')

ui.run()
````

[See more →](/documentation/link)

## [Chat Message](/documentation/chat_message)

Based on Quasar's `Chat Message <https://quasar.dev/vue-components/chat/>`_ component.

:text: the message body (can be a list of strings for multiple message parts)
:name: the name of the message author
:label: renders a label header/section only
:stamp: timestamp of the message
:avatar: URL to an avatar
:sent: render as a sent message (so from current user) (default: ``False``)
:text_html: render text as HTML (default: ``False``)
:sanitize: sanitization mode (only relevant when ``text_html=True``):
    ``True`` (default) uses client-side sanitization via DOMPurify,
    ``False`` disables sanitization (use only with trusted content),
    or pass a callable to apply server-side sanitization

main.py

[Button]

````python
from nicegui import ui

ui.chat_message('Hello NiceGUI!',
                name='Robot',
                stamp='now',
                avatar='https://robohash.org/ui')

ui.run()
````

[See more →](/documentation/chat_message)

## [Generic Element](/documentation/element)

This class is the base class for all other UI elements.
But you can use it to create elements with arbitrary HTML tags.

:tag: HTML tag of the element
:_client: client for this element (for internal use only)

main.py

[Button]

````python
from nicegui import ui

with ui.element('div').classes('p-2 bg-blue-100'):
    ui.label('inside a colored div')

ui.run()
````

[See more →](/documentation/element)

## [Markdown Element](/documentation/markdown)

Renders Markdown onto the page.

:content: the Markdown content to be displayed
:extras: list of `markdown2 extensions <https://github.com/trentm/python-markdown2/wiki/Extras#implemented-extras>`_
    (default: ``['fenced-code-blocks', 'tables']``, *since in version 3.14.0*: can be set via ``ui.markdown.default_extras``)
:sanitize: sanitization mode:
    ``True`` (default) uses client-side sanitization via DOMPurify,
    ``False`` disables sanitization (use only with trusted content),
    or pass a callable to apply server-side sanitization

main.py

[Button]

````python
from nicegui import ui

ui.markdown('This is **Markdown**.')

ui.run()
````

[See more →](/documentation/markdown)

## [ReStructuredText](/documentation/restructured_text)

Renders ReStructuredText onto the page.

:content: the ReStructuredText content to be displayed

main.py

[Button]

````python
from nicegui import ui

ui.restructured_text('This is **reStructuredText**.')

ui.run()
````

[See more →](/documentation/restructured_text)

## [Mermaid Diagrams](/documentation/mermaid)

Renders diagrams and charts written in the Markdown-inspired `Mermaid <https://mermaid.js.org/>`_ language.
The mermaid syntax can also be used inside Markdown elements by providing the extension string 'mermaid' to the ``ui.markdown`` element.

The optional configuration dictionary is passed directly to mermaid before the first diagram is rendered.
This can be used to set such options as

    ``{'securityLevel': 'loose', ...}`` - allow running JavaScript when a node is clicked
    ``{'logLevel': 'info', ...}`` - log debug info to the console

Refer to the Mermaid documentation for the ``mermaid.initialize()`` method for a full list of options.

**Note:** When using click handlers with ``securityLevel: 'loose'``,
make sure to use unique node IDs across diagrams to avoid click events being bound to the wrong elements.

:content: the Mermaid content to be displayed
:config: configuration dictionary to be passed to ``mermaid.initialize()``
:on_node_click: callback that is invoked when a node is clicked (*added in version 3.3.0*)

main.py

[Button]

````python
from nicegui import ui

ui.mermaid('''
    graph LR;
        A --> B;
        A --> C;
''')

ui.run()
````

[See more →](/documentation/mermaid)

## [HTML Element](/documentation/html)

Renders arbitrary HTML onto the page, wrapped in the specified tag.
`Tailwind <https://tailwindcss.com/>`_ can be used for styling.
You can also use ``ui.add_head_html`` to add html code into the head of the document and ``ui.add_body_html``
to add it into the body.

:content: the HTML code to be displayed
:sanitize: sanitization mode:
    ``True`` (default) uses client-side sanitization via DOMPurify,
    ``False`` disables sanitization (use only with trusted content),
    or pass a callable to apply server-side sanitization
:tag: the HTML tag to wrap the content in (default: "div")

main.py

[Button]

````python
from nicegui import ui

ui.html('This is <strong>HTML</strong>.', sanitize=False)

ui.run()
````

[See more →](/documentation/html)

## Other HTML Elements

There is also an `html` module that allows you to insert other HTML elements like `<span>`, `<div>`, `<p>`, etc.
It is equivalent to using the `ui.element` method with the `tag` argument.

Like with any other element, you can add classes, style, props, tooltips and events.
One convenience is that the keyword arguments are automatically added to the element's `props` dictionary.

*Added in version 2.5.0*

main.py

[Button]

````python
from nicegui import html, ui

with html.section().style('font-size: 120%'):
    html.strong('This is bold.') \
        .classes('cursor-pointer') \
        .on('click', lambda: ui.notify('Bold!'))
    html.hr()
    html.em('This is italic.').tooltip('Nice!')
    with ui.row():
        html.img().props('src=https://placehold.co/60')
        html.img(src='https://placehold.co/60')

ui.run()
````

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