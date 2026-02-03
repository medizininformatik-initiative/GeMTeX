import logging
import pathlib
import re
import subprocess
from ade_extraction_pipeline.utils.server import BasicServer

logging.basicConfig(level=logging.INFO)


class AMTSServer(BasicServer):
    def __init__(self, name, host="localhost", port=9999, protocol="http"):
        super().__init__(name, host, port, protocol)


def check_java(java):
    cp = subprocess.Popen(
        [java, "-version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
    )
    pattern = re.compile(r"version\s+\"(\d+\.\d+\.\d+)\"", re.MULTILINE)
    out, err = cp.communicate()
    match = pattern.match(err)
    print()


if __name__ == "__main__":
    base_path = pathlib.Path(__file__).parent.parent.parent.parent
    java = pathlib.Path(
        "C:/Users/fra3066mat/.jdks/openjdk-24.0.1/bin/java.exe"
    ).resolve()
    jar_loc = pathlib.Path(base_path, "libs/amts.jar").resolve()
    protocol = "https"
    ip = "dev-ci.id-berlin.de"
    port = 443
    file = pathlib.Path(base_path, "test/out/Albers_[1].json").resolve()

    cmd = [
        str(java),
        "-jar",
        str(jar_loc),
        str(protocol),
        str(ip),
        str(port),
        str(file),
    ]
    logging.info(f" Executing '{' '.join(cmd)}'")

    check_java(java)

    # cp = subprocess.run(cmd, shell=False, stdout=subprocess.PIPE,)
    # return_code = cp.stdout.decode().splitlines()[0]
    # if return_code in ["1005", "1006"]:
    #     logging.error(f"Not successful, error code '{return_code}'!")
