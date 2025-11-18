import enum
import json
import logging
import uuid
from typing import Optional

import click
import pathlib as pl

import yaml

from ade_extraction_pipeline.pipeline_parts.coding import add_codes
from ade_extraction_pipeline.pipeline_parts.extraction import run_agent_on_query


class Mode(enum.Enum):
    FILE = enum.auto()
    TEXT = enum.auto()
    FOLDER = enum.auto()


class Step(enum.Enum):
    EXTRACTION = enum.auto()
    CODING = enum.auto()

    def __int__(self):
        return self.value - 1


@click.command()
@click.argument("src")
@click.option("--config", default="default", help="config file")
@click.option(
    "--mode", default=Mode.TEXT, type=click.Choice(Mode, case_sensitive=False)
)
@click.option(
    "--output",
    default=".",
    type=click.Path(exists=False, dir_okay=False, allow_dash=False, path_type=pl.Path),
)
@click.option("--api-key", default=None, type=click.STRING)
@click.option("--force-text", is_flag=True)
@click.option(
    "--start-with",
    default=Step.EXTRACTION,
    type=click.Choice(Step, case_sensitive=False),
)
def start_pipeline(
    src: str,
    config: str,
    mode: Mode,
    output: pl.Path,
    api_key: Optional[str],
    force_text: bool,
    start_with: Step,
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
        src = pl.Path(src)
    elif mode == Mode.FOLDER:
        raise NotImplementedError()

    if start_with == Step.EXTRACTION:
        extraction = run_agent_on_query(
            src.read_text(encoding="utf-8"), _config, api_key
        )
        if extraction is not None:
            extraction = add_ids_to_results(extraction.output.model_dump())
        else:
            logging.error("Extraction failed.")
            return
        dump_steps(extraction, output, int(Step.EXTRACTION))
    elif start_with == Step.CODING:
        if not src.is_file():
            raise click.BadParameter(
                f"When starting with {Step.CODING}, you need to provide a file with the extraction results."
            )
        extraction = json.load(src.open("r", encoding="utf-8"))
    coding = add_codes(extraction, _config)
    dump_steps(coding, output, int(Step.CODING))


def dump_steps(result: dict, output_path: pl.Path, step: int):
    if result is not None:
        if output_path is None:
            print(json.dumps(result, indent=2))
        else:
            output_path = pl.Path(output_path)
            final = pl.Path(
                output_path.parent, f"{output_path.stem}_[{step}]{output_path.suffix}"
            )
            final.touch()
            json.dump(
                result,
                final.open("w", encoding="utf-8"),
                indent=2,
                ensure_ascii=False,
            )


def add_ids_to_results(results: dict) -> dict:
    for k in results.keys():
        for d in results[k]:
            d["id"] = str(uuid.uuid4())
    return results


def list_configs() -> dict[str, pl.Path]:
    _config_folder = pl.Path(__file__).parent.parent / "configs"
    _dict = {}
    for config in _config_folder.glob("*"):
        if config.is_file() and config.suffix in [".yaml", ".yml"]:
            _dict[config.stem] = config
    return _dict


if __name__ == "__main__":
    start_pipeline()
