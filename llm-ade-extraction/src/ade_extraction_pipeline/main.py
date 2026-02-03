# ToDO: integrate libs/amts.jar into pipeline
import enum
import json
import logging
import uuid
import os
from dotenv import load_dotenv
from typing import Optional, Tuple

import click
import pathlib as pl

import yaml
from yaspin import yaspin
from yaspin.core import Yaspin

from ade_extraction_pipeline.pipeline_parts.coding import add_codes
from ade_extraction_pipeline.pipeline_parts.extraction import (
    run_agent_on_query,
    obscure_key,
)

# Reads .env file and makes values available through os.getenv
load_dotenv(os.getenv("WORK_DIR_ENV"))


class Mode(enum.Enum):
    FILE = enum.auto()
    TEXT = enum.auto()
    FOLDER = enum.auto()


class Step(enum.Enum):
    EXTRACTION = enum.auto()
    CODING = enum.auto()
    AMTS = enum.auto()

    def __int__(self):
        return self.value - 1


class DefaultConfigs(enum.Enum):
    OLLAMA = "OLLAMA"
    BLABLADOR = "BLABLADOR"


@click.command()
def obscure_api_key():
    key = click.prompt("     API key", type=str, hide_input=True)
    print(f"Obscured key: {obscure_key(key)}")


@click.command()
@click.argument("src")
@click.option(
    "--config",
    default=os.getenv("LLM_PIPELINE_CONFIG")
    if os.getenv("LLM_PIPELINE_CONFIG") is not None
    else "ollama",
    help=f"Path to a config file; or a name for a preconfigured one from these options: {[s.lower() for s in DefaultConfigs._member_names_]}. [Default: '{str(DefaultConfigs.OLLAMA.value).lower()}']",
)
@click.option(
    "--mode",
    default=Mode.TEXT,
    type=click.Choice(Mode, case_sensitive=False),
    help="The type of the input. [Default: 'text']",
)
@click.option(
    "--output",
    default="pipeline_out",
    type=click.Path(exists=False, dir_okay=True, allow_dash=False, path_type=pl.Path),
    help="The output path; filenames will be deduced from input file ('txt_input' if --mode='text'). If you want to dump the result to stdout, you can provide a dash (-). [Default: './pipeline_out/*']",
)
@click.option(
    "--api-key",
    default=os.getenv("LLM_PIPELINE_API_KEY"),
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
    "--workdir",
    default=".",
    type=click.Path(exists=True, dir_okay=True, allow_dash=False, path_type=pl.Path),
    help="The working directory to use for all file path resolution. [Default: current working directory]",
)
@click.option(
    "--force-text",
    is_flag=True,
    help="If set, skips text length validation (meaning you can provide a very short sentence as input SRC)",
)
@click.option(
    "--obscured-api-key",
    is_flag=True,
    help="If set, this assumes a previously obscured API key as '--api-key input' and will unobscure it. The obscuring has taken place with the 'obscure-api-key' command.",
)
def start_pipeline(
    src: str,
    config: str,
    mode: Mode,
    output: pl.Path,
    api_key: Optional[str],
    start_with: Step,
    workdir: pl.Path,
    force_text: bool,
    obscured_api_key: bool,
) -> None:
    if force_text:
        logging.info("Forcing text as input even if too short normally.")
    if obscured_api_key:
        logging.info("API key is assumed as obscured and will be unobscured.")

    _default_configs = list_configs()
    if pl.Path(config).is_file():
        _config_path = pl.Path(config)
    elif _saved_config := _default_configs.get(config, None):
        _config_path = _saved_config
    else:
        _config_path = _default_configs.get("ollama")
    _config = yaml.safe_load(_config_path.open("rb"))

    _is_text = False
    srcs = []
    if mode == Mode.TEXT:
        _is_text = True
        srcs = [src]
        if not force_text and len(src) < 75:
            if not (workdir / pl.Path(src)).is_file():
                raise click.BadParameter(
                    "When using 'SRC' as text input, it must be at least 75 characters long. If you want to skip this check use the flag '--force-text'."
                )
            else:
                src = workdir / pl.Path(src)
                srcs = [src]
                logging.warning(
                    f"'SRC' was too short for being recognized as text input.\n"
                    f"Treated 'SRC' as 'file' ({src.resolve()}).\n"
                    f"Please set '--mode file' if using a file as input to avoid this warning."
                )
                _is_text = False
    elif mode == Mode.FILE:
        srcs = [workdir / pl.Path(src)]
    elif mode == Mode.FOLDER:
        srcs = list((workdir / pl.Path(src)).iterdir())

    _output_path = None
    if output.name != "-":
        _output_path = workdir / output
    else:
        if mode == Mode.FOLDER:
            pass

    if start_with == Step.EXTRACTION:
        extraction_list = [
            start_extraction(
                src=src.read_text(encoding="utf-8") if not _is_text else src,
                config=_config,
                api_key=api_key,
                obscured_api_key=obscured_api_key,
                output_path=_output_path
                if _output_path is None
                else _output_path / (f"{src.stem}" if not _is_text else "txt_input"),
                number=i,
            )
            for i, src in enumerate(srcs)
        ]
    elif start_with == Step.CODING:
        # ToDo: "MODE == folder" not yet implemented for "start_with == CODING"?!
        src = workdir / src
        if not src.is_file():
            raise click.BadParameter(
                f"When starting with {Step.CODING.name}, you need to provide a file with the extraction results."
            )
        extraction_list = [(json.load(src.open("r", encoding="utf-8")), None)]
    else:
        extraction_list = [(None, None)]

    coding_list = [
        start_coding(
            extraction=extraction_tuple[0],
            config=_config,
            output_path=_output_path
            if _output_path is None
            else _output_path / (f"{src.stem}" if not _is_text else "txt_input"),
            number=i,
        )
        for i, (src, extraction_tuple) in enumerate(zip(srcs, extraction_list))
        if extraction_tuple is not None
    ]

    if _output_path is None and mode != Mode.FOLDER:
        if len(coding_list) > 0:
            print(coding_list[0][1])


def start_extraction(
    src: str,
    config: dict,
    api_key: str,
    obscured_api_key: bool,
    output_path: pl.Path,
    number: int,
) -> Optional[Tuple[dict, Optional[str]]]:
    with yaspin(text=f"Extracting [{number}]...") as spinner:
        successful, extraction = run_agent_on_query(
            src,
            config,
            api_key,
            obscured_api_key,
        )
        if successful:
            extraction = add_ids_to_results(extraction.output.model_dump())
        else:
            logging.error(f"Extraction failed: {extraction}")
            return None
    dump_str = dump_steps(extraction, output_path, Step.EXTRACTION, spinner)
    return extraction, dump_str


def start_coding(
    extraction: Optional[dict], config: dict, output_path: pl.Path, number: int
) -> Optional[Tuple[dict, str]]:
    with yaspin(text=f"Integrating codes [{number}]...") as spinner:
        if extraction is None:
            logging.error(f"Coding failed: no extraction results: {extraction}.")
            return None
        coding = add_codes(extraction, config)
        dump_str = dump_steps(coding, output_path, Step.CODING, spinner)
        return coding, dump_str


def dump_steps(
    result: dict, output_path: pl.Path, step: Step, spinner: Optional[Yaspin] = None
) -> Optional[str]:
    if result is not None:
        if output_path is None:
            return json.dumps(
                result,
                indent=2,
                ensure_ascii=False,
            )
        else:
            output_path = pl.Path(output_path)
            suffix = ".json"
            final = pl.Path(
                output_path.parent, f"{output_path.stem}_[{int(step)}]{suffix}"
            )
            final.parent.mkdir(parents=True, exist_ok=True)
            final.touch()
            json.dump(
                result,
                final.open("w", encoding="utf-8"),
                indent=2,
                ensure_ascii=False,
            )
            spinner.write(f"Written results for '{step.name}' to '{final.resolve()}'.")
            return None
    return None


def add_ids_to_results(results: dict) -> dict:
    for k in results.keys():
        if results.get(k) is None:
            results[k] = []
            continue
        for d in results.get(k, []):
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
