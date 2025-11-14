import enum
import json
from typing import Optional

import click
import pathlib as pl

import yaml

from ade_extraction_pipeline.pipeline_parts.extraction import run_agent_on_query


class Mode(enum.Enum):
    FILE = enum.auto()
    TEXT = enum.auto()
    FOLDER = enum.auto()

@click.command()
@click.argument("src")
@click.option("--config", default="default", help="config file")
@click.option("--mode", default="text", type=click.Choice(Mode, case_sensitive=False))
@click.option("--output", default=None)
def start_pipeline(src: str, config: str, mode: Mode, output: Optional[str]) -> None:
    _default_configs = list_configs()
    if pl.Path(config).is_file():
        _config_path = pl.Path(config)
    elif _saved_config := _default_configs.get(config, None):
        _config_path = _saved_config
    else:
        _config_path = _default_configs.get("default")
    _config = yaml.safe_load(_config_path.open('rb'))

    result = None
    if mode == Mode.TEXT:
        result = run_agent_on_query(src, _config)
    elif mode == Mode.FILE:
        src = pl.Path(src).read_text()
        result = run_agent_on_query(src, _config)
    elif mode == Mode.FOLDER:
        raise NotImplementedError()

    if output is None and result is not None:
        # json.dumps(result.output, indent=2)
        print(result.output)
    elif output := pl.Path(output):
        output.touch()
        json.dump(result.output, output.open('wb'), indent=2)

def list_configs() -> dict[str, pl.Path]:
    _config_folder = pl.Path(__file__).parent.parent / "configs"
    _dict = {}
    for config in _config_folder.glob("*"):
        if config.is_file() and config.suffix in [".yaml", ".yml"]:
            _dict[config.stem] = config
    return _dict
