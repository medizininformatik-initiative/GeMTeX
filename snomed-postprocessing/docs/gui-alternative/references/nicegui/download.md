# ui.download | NiceGUI

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

# ui.*download*

## Download functions

These functions allow you to download files, URLs or raw data.

*Added in version 2.14.0*

main.py

[Button]

````python
from nicegui import ui

ui.button('Local file', on_click=lambda: ui.download.file('main.py'))
ui.button('From URL', on_click=lambda: ui.download.from_url('/logo.png'))
ui.button('Content', on_click=lambda: ui.download.content('Hello World', 'hello.txt'))

ui.run()
````

## Download from a relative URL

Function to trigger the download from a relative URL.

Note:
This function is intended to be used with relative URLs only.
For absolute URLs, the browser ignores the download instruction and tries to view the file in a new tab
if possible, such as images, PDFs, etc.
Therefore, the download may only work for some file types such as .zip, .db, etc.
Furthermore, the browser ignores filename and media_type parameters,
respecting the origin server's headers instead.
Either replace the absolute URL with a relative one, or use ``ui.navigate.to(url, new_tab=True)`` instead.

*Added in version 2.14.0*

*Updated in version 2.19.0: Added warning for cross-origin downloads*

:url: URL
:filename: name of the file to download (default: name of the file on the server)
:media_type: media type of the file to download (default: "")

main.py

[Button]

````python
from nicegui import ui

ui.button('Download', on_click=lambda: ui.download.from_url('/logo.png'))

ui.run()
````

## Download raw bytes or string content

Function to trigger the download of raw data.

*Added in version 2.14.0*

:content: raw bytes or string
:filename: name of the file to download (default: name of the file on the server)
:media_type: media type of the file to download (default: "")

main.py

[Button]

````python
from nicegui import ui

ui.button('Download', on_click=lambda: ui.download.content('Hello World', 'hello.txt'))

ui.run()
````

## Download file from local path

Function to trigger the download of a file.

*Added in version 2.14.0*

:path: local path of the file
:filename: name of the file to download (default: name of the file on the server)
:media_type: media type of the file to download (default: "")

main.py

[Button]

````python
from nicegui import ui

ui.button('Download', on_click=lambda: ui.download.file('main.py'))

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