# UIMA CAS Converter
Small script that converts a UIMA CAS JSON file to XMI and vice versa.
If converted to XMI a minimal ``TypeSystem.xml`` will also be generated from the information available in the JSON file.  
You can also give a ``zip`` file as input and the script will use and convert the JSON/XMI files from within it.
The ``zip`` file can also be an exported INCEpTION project.

## Usage
You can run the script within a [uv](https://docs.astral.sh/uv/getting-started/installation/) environment. For further information run:  
``uv run convert-cas --help``