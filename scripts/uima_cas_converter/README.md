# UIMA CAS Converter
Small script that converts a UIMA CAS JSON file to XMI and vice versa.
If converted to XMI a minimal ``TypeSystem.xml`` will also be generated from the information available in the JSON file.

## Usage
You can run the script with [uv](https://docs.astral.sh/uv/getting-started/installation/) environment. For further information run:  
``uv run convert-cas --help``