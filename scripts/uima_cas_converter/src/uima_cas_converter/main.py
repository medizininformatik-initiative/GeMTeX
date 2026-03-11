import enum
import logging
import pathlib
import shutil
import sys
from typing import Optional, Tuple

import click
from cassis import *
from PyInquirer import prompt


class TypeSystemHandling(enum.Enum):
    MERGE = 1
    OVERWRITE = 2
    BACKUP = 3


def _check_typesystem(
    ts_file: Optional[pathlib.Path], input_file: pathlib.Path
) -> TypeSystem:
    # if no typesystem file is given, try to find it in the same folder as the input file
    if ts_file is None:
        typesystem = input_file.parent / "typesystem.xml"
    else:
        typesystem = pathlib.Path(ts_file)
    if not typesystem.exists():
        logging.error(
            f" Typesystem file '{typesystem.name}' not found in {typesystem.parent.resolve()}; please specify via '--typesystem' option."
        )
        sys.exit(-1)
    try:
        return load_typesystem(typesystem)
    except Exception as e:
        logging.error(f" Could not load typesystem file '{typesystem.resolve()}': {e}")
        sys.exit(-1)


def _check_input_file(input_file: pathlib.Path) -> Tuple[bool, bool]:
    if not input_file.exists():
        logging.error(f" Input file '{input_file.resolve()}' not found.")
        sys.exit(-1)
    else:
        if input_file.suffix == ".xmi":
            return True, False
        elif input_file.suffix == ".json":
            return False, True
        else:
            logging.error(
                f" Input file '{input_file.resolve()}' has unsupported file extension; needs to be one of '.json' or '.xmi'."
            )
            sys.exit(-1)


def _load_cas(input_file: pathlib.Path, typesystem: TypeSystem, to_json: bool) -> Cas:
    with input_file.open("rb") as fi:
        try:
            if to_json:
                return load_cas_from_xmi(fi, typesystem)
            else:
                return load_cas_from_json(fi)
        except Exception as e:
            logging.error(
                f" Could not load CAS from file '{input_file.resolve()}': {e}"
            )
            sys.exit(-1)


def _check_output_file(
    output_file: Optional[pathlib.Path], input_file: pathlib.Path, to_json: bool
) -> pathlib.Path:
    if output_file is not None:
        output_path = pathlib.Path(output_file)
        if not output_path.exists():
            if output_path.suffix == "":
                output_path.mkdir(parents=True, exist_ok=True)
            else:
                output_path.parent.mkdir(parents=True, exist_ok=True)
        if output_path.is_dir():
            logging.warning(
                f" Output path '{output_path.resolve()}' is a directory; using '{input_file.stem}.{'json' if to_json else 'xmi'}' as output file name."
            )
            return output_path / f"{input_file.stem}.{'json' if to_json else 'xmi'}"
        else:
            logging.info(f" Writing output to '{output_path.resolve()}'.")
            if (output_path.suffix == ".xmi" and to_json) or (
                output_path.suffix == ".json" and not to_json
            ):
                logging.warning(
                    f" You specified '{output_path.suffix}' as file type but input type is already '{'.xmi' if to_json else '.json'}'; overwriting output file type to '{'.json' if to_json else '.xmi'}'."
                )
            return output_path.with_suffix(f".{'json' if to_json else 'xmi'}")
    else:
        logging.warning(
            " No output file specified; writing to same folder as input file."
        )
        return input_file.with_suffix(f".{'json' if to_json else 'xmi'}")


def _check_present_typesystem(output_path: pathlib.Path, cas: Cas, exclude_option: TypeSystemHandling = None, message: str = None):
    ts_output = output_path.parent / f"TypeSystem.xml"
    _ts = cas.typesystem
    if ts_output.exists():
        _menu_entry = "menu_entry"
        options = [to.name for to in TypeSystemHandling if (exclude_option is None) or (exclude_option != to)]
        questions = [
            {
                "type": "list",
                "name": _menu_entry,
                "message": f"A 'TypeSystem.xml' already exists at the location {output_path.parent.resolve()}. How to proceed?" if message is None else message,
                "choices": options,
                "default": 0,
            }
        ]
        answer = prompt(questions)
        try:
            if TypeSystemHandling[answer.get(_menu_entry)] == TypeSystemHandling.BACKUP:
                logging.info(
                    "Chosen 'BACKUP' option. Old 'TypeSystem.xml' will be backed up as 'TypeSystem.xml.bak'."
                )
                shutil.copy(ts_output, pathlib.Path(f"{ts_output.resolve()}.bak"))
            elif (
                TypeSystemHandling[answer.get(_menu_entry)]
                == TypeSystemHandling.OVERWRITE
            ):
                logging.info(
                    "Chosen 'OVERWRITE' option. 'TypeSystem.xml' will be replaced."
                )
            elif (
                TypeSystemHandling[answer.get(_menu_entry)] == TypeSystemHandling.MERGE
            ):
                logging.info("Chosen 'MERGE' option. Trying to merge typesystems.")
                try:
                    _ts = merge_typesystems(cas.typesystem, load_typesystem(ts_output))
                except Exception as e:
                    logging.error(
                        f" Could not merge typesystems: '{e}'."
                    )
                    _check_present_typesystem(output_path, cas, TypeSystemHandling.MERGE, "Maybe try another handling option:")
                    sys.exit(0)
            else:
                raise ValueError(
                    f"Unknown option '{answer.get(_menu_entry)}' selected."
                )
        except (ValueError, KeyError) as e:
            logging.error(f" {e}")
            sys.exit(-1)
    _ts.to_xml(ts_output)
    logging.info(f" Wrote new 'TypeSystem.xml' to '{ts_output.resolve()}'.")


def _set_log_level(log_level: str):
    log_level_ = {
        "debug": logging.DEBUG,
        "info": logging.INFO,
        "warning": logging.WARNING,
        "error": logging.ERROR,
        "critical": logging.CRITICAL,
    }.get(log_level.lower(), logging.INFO)
    logging.basicConfig(level=log_level_)


@click.command()
@click.argument("input_file")
@click.option("--output_file", default=None, help="Path to the output file.")
@click.option("--typesystem", default=None, help="Path to a typesystem file.")
@click.option(
    "--log-level",
    default="INFO",
    type=click.Choice(
        ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"], case_sensitive=False
    ),
    help="The log level.",
)
def main(
    input_file: str,
    output_file: Optional[str],
    typesystem: Optional[str],
    log_level: str,
):
    """
    Converts a UIMA CAS from JSON to XMI or vice versa. Direction will be inferred from the file extension.
    """
    _set_log_level(log_level)

    # Check whether input file exists and what file extension it has
    input_file = pathlib.Path(input_file)
    to_json, to_xmi = _check_input_file(input_file)

    # check whether typesystem file exists if input file is xmi
    final_typesystem = None
    if to_json:
        final_typesystem = _check_typesystem(typesystem, input_file)

    # load cas from either json or xmi file
    cas = _load_cas(input_file, final_typesystem, to_json)

    # check and/or create output file
    output_path = _check_output_file(output_file, input_file, to_json)

    if to_json:
        cas.to_json(output_path, pretty_print=True, ensure_ascii=False)
    else:
        _check_present_typesystem(output_path, cas)
        cas.to_xmi(output_path)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        main(["--help"])
    else:
        main(sys.argv[1:])
