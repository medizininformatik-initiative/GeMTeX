import enum
import json
import logging
import uuid
from typing import Optional
from pydantic_ai import ModelHTTPError

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
@click.option(
    "--config",
    default="ollama",
    help="Path to a config file; or a name for a preconfigured one from these options: {blablador, ollama}. [Default: 'blablador']",
)
@click.option(
    "--mode",
    default=Mode.TEXT,
    type=click.Choice(Mode, case_sensitive=False),
    help="The type of the input. [Default: 'text']",
)
@click.option(
    "--output",
    default="./pipeline_out.json",
    type=click.Path(exists=False, dir_okay=True, allow_dash=False, path_type=pl.Path),
    help="The output file if '--mode file|text' or a path if '--mode folder'. [Default: './pipeline_out.json']",
)
@click.option(
    "--api-key",
    default=None,
    type=click.STRING,
    help="The API key to use for authentication for the chosen ai module. An API key given in the config file takes precedence. [Default: None]",
)
@click.option(
    "--start-with",
    default=Step.EXTRACTION,
    type=click.Choice(Step, case_sensitive=False),
    help="The step to start the pipeline with. If not starting with the first step, the provided SRC needs to be a dump of the previous step. [Default: 'extraction']",
)
@click.option(
    "--force-text",
    is_flag=True,
    help="If set, skips text length validation (meaning you can provide a very short sentence as input SRC)",
)
def start_pipeline(
    src: str,
    config: str,
    mode: Mode,
    output: pl.Path,
    api_key: Optional[str],
    start_with: Step,
    force_text: bool,
) -> None:
    _default_configs = list_configs()
    if pl.Path(config).is_file():
        _config_path = pl.Path(config)
    elif _saved_config := _default_configs.get(config, None):
        _config_path = _saved_config
    else:
        _config_path = _default_configs.get("ollama")
    _config = yaml.safe_load(_config_path.open("rb"))

    _is_text = False
    if mode == Mode.TEXT:
        _is_text = True
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
                _is_text = False
    elif mode == Mode.FILE:
        src = pl.Path(src)
    elif mode == Mode.FOLDER:
        raise NotImplementedError()

    if start_with == Step.EXTRACTION:
        try:
            extraction = run_agent_on_query(
                src.read_text(encoding="utf-8") if not _is_text else src, _config, api_key
            )
        except ModelHTTPError | AttributeError as e:
            extraction = None
            _error = e.message

        if extraction is not None:
            extraction = add_ids_to_results(extraction.output.model_dump())
        else:
            logging.error(f"Extraction failed: {_error}")
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
