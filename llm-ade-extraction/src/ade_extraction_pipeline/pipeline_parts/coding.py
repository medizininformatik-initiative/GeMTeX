import asyncio
import json
import logging
import pathlib
import re
from collections import defaultdict
from dataclasses import dataclass
from typing import Union, Optional

from aiohttp import ClientSession
from pysolr import Results


@dataclass
class Result:
    src: str
    annotation_type: str
    original_dict: dict
    results: list[dict]

    def to_json(self):
        return self.original_dict | {"codes": { "results": self.results, "src": self.src }}


class CodingServer:
    def __init__(
        self,
        name: str,
        host: str = "localhost",
        port: Union[str, int] = 8080,
        endpoints: dict[str, str] = None,
        protocol: str = "http",
    ):
        self._name = name
        self._endpoints = {}
        self._host = host
        self._port = port
        self._protocol = protocol
        self.build_endpoint_dict(endpoints)

    def __str__(self):
        return json.dumps(self, default=lambda o: o.__dict__, indent=2)

    @property
    def url(self):
        return f"{self._protocol}://{self._host}:{self._port}"

    @property
    def endpoints(self):
        return self._endpoints

    def build_endpoint_dict(self, value):
        _temp_dict = {}
        if value is not None:
            for k, v in value.items():
                _temp_dict[k] = {
                    "endpoint": v.lstrip("/"),
                    "args": re.findall(r"\{(.*?)\}", v),
                }
        self._endpoints = _temp_dict

    def endpoint(self, anno_type: str, **kwargs) -> Optional[str]:
        _config_args = self.endpoints.get(anno_type, {}).get("args", [])
        if len(_config_args) == 0:
            return self._endpoints[anno_type]["endpoint"]
        _difference_set = set()
        for k in set(kwargs.keys()).difference(_config_args):
            _difference_set.add(k)
            kwargs.pop(k)
        if len(_difference_set) > 0:
            logging.warning(f"Some arguments were superfluous: {_difference_set}")
        if len(kwargs) != len(_config_args):
            logging.error(f"There are some arguments missing: {set(_config_args).difference(kwargs.keys())}")
            return None
        return self.endpoints[anno_type]["endpoint"].format(**kwargs)

    async def get_code(self, anno_type, **kwargs):
        _get_all = kwargs.pop("get_all", False)
        async with ClientSession() as session:
            rs = Result(src=self._name, annotation_type=anno_type, original_dict=kwargs, results=[])
            if _endpoint := self.endpoint(anno_type=anno_type, **kwargs):
                async with session.get(f"{self.url}/{_endpoint}") as response:
                    code = await response.json(content_type=None)
                    rs.results = code if _get_all else code[:1]
            return rs


    async def get_all_codes(self, extractions: dict, get_all: bool = False):
        tasks = []
        for anno_type, extr_list in extractions.items():
            for extr in extr_list:
                tasks.append(self.get_code(anno_type=anno_type, get_all=get_all, **extr))
        return await asyncio.gather(*tasks)

    def incorporate_codes(self, extractions: dict) -> dict:
        result_dict = defaultdict(list)
        for result in asyncio.run(self.get_all_codes(extractions)):
            result_dict[result.annotation_type].append(result.to_json())
        return result_dict


def add_codes(results: dict, config: dict) -> list[dict]:
    new_results = []
    _server_config = config.get("coding").get("servers")
    _coding_config = config.get("coding").get("config")
    for server_name, server_config in _server_config.items():
        ep_dict = {}
        for anno_type, endpoint_list in _coding_config.items():
            for ep in endpoint_list:
                if not server_name in ep:
                    continue
                ep_dict[anno_type] = ep.get(server_name)
        if len(ep_dict) == 0:
            continue
        coding_server = CodingServer(
            name=server_name,
            host=server_config.get("host", "localhost"),
            port=server_config.get("port", 8080),
            endpoints=ep_dict,
        )
        new_results.append(coding_server.incorporate_codes(results))
    return new_results

if __name__ == "__main__":
    _path = pathlib.Path(__file__).parent.parent.parent.parent / "test/test_file_out.txt"
    cs = CodingServer(
        name="id-logik",
        host="localhost",
        port=8080,
        endpoints={
            "diagnosen": "/inception/lookup_icd10?q={text}",
            "medikationen": "/inception/lookup_sct?q={text}",
        },
    )
    result = cs.incorporate_codes(json.load(_path.open('r', encoding='utf-8')))
    pathlib.Path(_path.parent, "test_file_out.json").write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding='utf-8')
