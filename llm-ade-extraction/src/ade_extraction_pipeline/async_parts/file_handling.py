import json
import logging

import aiopath as pla


async def read_file_async(filename: str):
    """Asynchronously read a file and return its contents."""
    _path = pla.Path(filename)
    _path_str = str(_path.resolve())
    try:
        async with _path.open("r") as file:
            content = await file.read()
            return content
    except FileNotFoundError:
        logging.error(f"Error: File '{_path_str}' not found.")
    except Exception as e:
        logging.error(f"Error reading file: {_path_str} ({e})")


async def write_file_async(filename: str, data: dict) -> str:
    """Asynchronously write a file and return its path."""
    _path = pla.Path(filename)
    _path_str = str(_path.resolve())
    try:
        async with _path.open("w") as file:
            await file.write_text(
                json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
            )
    except Exception as e:
        logging.error(f"Error writing file: {_path_str} ({e})")
    return _path_str
