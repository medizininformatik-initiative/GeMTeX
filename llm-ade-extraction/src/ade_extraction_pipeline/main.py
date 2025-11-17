import enum
import json
import logging
from typing import Optional

import click
import pathlib as pl

import yaml

from ade_extraction_pipeline.pipeline_parts.coding import CodingServer, add_codes
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
@click.option("--api-key", default=None)
@click.option("--force-text", is_flag=True)
def start_pipeline(
    src: str,
    config: str,
    mode: Mode,
    output: Optional[str],
    api_key: Optional[str],
    force_text: bool,
) -> None:
    _default_configs = list_configs()
    if pl.Path(config).is_file():
        _config_path = pl.Path(config)
    elif _saved_config := _default_configs.get(config, None):
        _config_path = _saved_config
    else:
        _config_path = _default_configs.get("default")
    _config = yaml.safe_load(_config_path.open("rb"))

    if mode == Mode.TEXT:
        if not force_text and len(src) < 75:
            if not pl.Path(src).is_file():
                raise click.BadParameter(
                    "When using 'SRC' as text input, it must be at least 75 characters long. If you want to skip this check use the flag '--force-text'."
                )
            else:
                src = pl.Path(src)
                logging.warning(
                    f"'SRC' was too short for being recognized as text input.\n"
                    f"Treated 'SRC' as 'file' ({src.resolve()}).\n"
                    f"Please set '--mode file' if using a file as input to avoid this warning."
                )
    elif mode == Mode.FILE:
        src = pl.Path(src).read_text()
    elif mode == Mode.FOLDER:
        raise NotImplementedError()

    extraction = run_agent_on_query(src, _config, api_key)
    if extraction is not None:
        extraction = extraction.output.model_dump()
    else:
        logging.error("Extraction failed.")
        return
    dump_steps(extraction, output, 0)
    coding = add_codes(extraction, _config)
    dump_steps({"coding_results": coding}, output, 1)


def dump_steps(result: dict, output_path: str, step: int):
    if result is not None:
        if output_path is None:
            print(json.dumps(result, indent=2))
        else:
            output_path = pl.Path(output_path)
            final = pl.Path(output_path.parent, f"{output_path.stem}_[{step}]{output_path.suffix}")
            final.touch()
            json.dump(
                result,
                final.open("w", encoding="utf-8"),
                indent=2,
                ensure_ascii=False,
            )



def list_configs() -> dict[str, pl.Path]:
    _config_folder = pl.Path(__file__).parent.parent / "configs"
    _dict = {}
    for config in _config_folder.glob("*"):
        if config.is_file() and config.suffix in [".yaml", ".yml"]:
            _dict[config.stem] = config
    return _dict


if __name__ == "__main__":
    start_pipeline()
