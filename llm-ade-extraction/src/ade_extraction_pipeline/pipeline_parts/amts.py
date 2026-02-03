import json
import logging
import pathlib
import re
import subprocess
from typing import Optional

from ade_extraction_pipeline.utils.server import BasicServer

logging.basicConfig(level=logging.INFO)


class AMTSServer(BasicServer):
    def __init__(self, name, host="localhost", port=9999, protocol="http"):
        super().__init__(name, host, port, protocol)


class AMTSJavaCaller:
    def __init__(
        self,
        java_bin: Optional[str],
        java_jar: str,
    ):
        self._java_bin = java_bin if java_bin is not None else "java"
        self._java_jar = java_jar

    def _popen_call(self, *args) -> tuple[str, str]:
        return subprocess.Popen(
            [self._java_bin] + list(args),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        ).communicate()

    def check_java(self) -> Optional[str]:
        out, err = self._popen_call("-version")
        match = re.match(
            r".*?version\s+\"(\d+\.\d+\.\d+(:?_\d+)*)\".*", err, re.MULTILINE
        )
        if match is not None and len(match.groups()) >= 1:
            return match.group(1)
        return None

    def call_amts_service(
        self,
        file: str,
        server: AMTSServer,
        step: int = 2
    ):
        _file_path = pathlib.Path(file).resolve()
        _id_output_path = pathlib.Path(
            _file_path.parent, f"{_file_path.stem}_out{_file_path.suffix}"
        ).resolve()
        _output_path = pathlib.Path(
            _file_path.parent, f"{_file_path.stem[:-2]}{step}].json"
        ).resolve()

        cmd = [
            "-jar",
            self._java_jar,
            server.protocol,
            server.host,
            server.port,
            file,
        ]
        logging.info(f" Executing '{' '.join([self._java_bin] + cmd)}'")
        out, err = self._popen_call(*cmd)
        if err.startswith("java.lang.UnsupportedClassVersionError"):
            logging.error(
                f"{err.split('\n')[0]}\n--> with java binary: '{self._java_bin}'"
            )
        elif len(out) != 0:
            return_code = out.split()[0]
            if return_code == "0":
                # rewrite json to indent it properly
                json_dump = json.load(_id_output_path.open("rb"))
                json.dump(
                    json_dump,
                    _output_path.open("w", encoding="utf-8"),
                    indent=2,
                    ensure_ascii=False,
                )
                _id_output_path.unlink(missing_ok=True)
                logging.info(f"Successful: output in '{_output_path}'")
            if return_code in ["1005", "1006"]:
                logging.error(f"Not successful, error code '{return_code}'!")
        else:
            logging.warning(
                f"Couldn't deduce return code. Check output location if process was successful: '{_id_output_path}'"
            )


if __name__ == "__main__":
    base_path = pathlib.Path(__file__).parent.parent.parent.parent
    _java = pathlib.Path(
        "C:/Users/fra3066mat/.jdks/openjdk-24.0.1/bin/java.exe"
    ).resolve()
    _jar_loc = pathlib.Path(base_path, "libs/amts.jar").resolve()
    _file = pathlib.Path(base_path, "test/out/Albers_[1].json").resolve()

    amts_server = AMTSServer(
        name="amts", host="dev-ci.id-berlin.de", port=443, protocol="https"
    )
    java_caller = AMTSJavaCaller(str(_java), str(_jar_loc))
    java_caller.call_amts_service(file=str(_file), server=amts_server)
    java_caller.check_java()
