import asyncio
import json
import logging
import pathlib
import re
from collections import defaultdict
from dataclasses import dataclass
from functools import reduce
from typing import Union, Optional

from aiohttp import ClientSession

from ade_extraction_pipeline.utils.server import BasicServer


@dataclass
class Result:
    src: str
    annotation_type: str
    original_dict: dict
    results: list[dict]

    def to_json(self, restrict_to: list[str] = None):
        _new_dict = self.original_dict | {"codes": []}
        restrict_to = [] if restrict_to is None else restrict_to
        for _d in self.results:
            _d["coding_src"] = self.src
            if restrict_to is not None and len(restrict_to) > 0:
                for k in list(_d.keys()):
                    if k not in restrict_to:
                        _d.pop(k, None)
            _new_dict["codes"].append(_d)
        return _new_dict


class CodingServer(BasicServer):
    def __init__(
        self,
        name: str,
        host: str = "localhost",
        port: Union[str, int] = 8080,
        endpoints: dict[str, str] = None,
        protocol: str = "http",
        ignore_fields: dict[str, list[str]] = None,
        response_parsing: dict = None,
    ):
        super().__init__(name, host, port, protocol)
        _rp = response_parsing if response_parsing is not None else {}
        self._endpoints = {}
        self._ignore_fields = {}
        self._response_parse_func = lambda x: x
        self._restrict_output = _rp.get("restrict", [])
        if _rp.get("parse", False):
            self.parse_response_def(_rp.get("parse"))
        self.build_endpoint_dict(endpoints)
        self.build_ignore_dict(ignore_fields)

    def __str__(self):
        return json.dumps(self, default=lambda o: o.__dict__, indent=2)

    @property
    def endpoints(self):
        return self._endpoints

    @property
    def ignore_fields(self) -> dict[str, list[str]]:
        return self._ignore_fields

    def parse_response_def(self, response_parsing: str):
        if response_parsing is None:
            return
        _lambda_list = [eval(r.strip()) for r in response_parsing.split("->")]
        self._response_parse_func = lambda x: reduce(lambda r, f: f(r), _lambda_list, x)

    def build_endpoint_dict(self, value):
        _temp_dict = {}
        if value is not None:
            for k, v in value.items():
                _temp_dict[k] = {
                    "endpoint": v.lstrip("/"),
                    "args": re.findall(r"\{(.*?)\}", v),
                }
        self._endpoints = _temp_dict

    def build_ignore_dict(self, value: Optional[dict[str, list[str]]]):
        self._ignore_fields = (
            value if value is not None else {k: [] for k in self.endpoints.keys()}
        )

    def endpoint(self, anno_type: str, **kwargs) -> Optional[str]:
        if not self.endpoints.get(anno_type, False):
            return None
        _config_args = self.endpoints.get(anno_type, {}).get("args", [])
        if len(_config_args) == 0:
            return self._endpoints[anno_type]["endpoint"]
        _difference_set = set()
        for k in set(kwargs.keys()).difference(_config_args):
            _difference_set.add(k)
            kwargs.pop(k)
        if (
            len(_difference_set) > 0
            and len(_difference_set.difference(self.ignore_fields.get(anno_type, [])))
            != 0
        ):
            logging.warning(f"Some arguments were superfluous: {_difference_set}")
        if len(kwargs) != len(_config_args):
            logging.error(
                f"There are some arguments missing: {set(_config_args).difference(kwargs.keys())}"
            )
            return None
        return self.endpoints[anno_type]["endpoint"].format(**kwargs)

    async def get_code(self, anno_type, **kwargs):
        _get_all = kwargs.pop("get_all", False)
        async with ClientSession() as session:
            rs = Result(
                src=self.name,
                annotation_type=anno_type,
                original_dict=kwargs,
                results=[],
            )
            if _endpoint := self.endpoint(anno_type=anno_type, **kwargs):
                async with session.get(f"{self.url}/{_endpoint}") as response:
                    code = await response.json(content_type=None)
                    if (
                        isinstance(code, dict)
                        and code.get("error", "").lower() == "not found"
                    ):
                        return rs
                    _rs_res = (
                        self._response_parse_func(code)
                        if _get_all
                        else self._response_parse_func(code)[:1]
                    )
                    rs.results = _rs_res if isinstance(_rs_res, list) else [_rs_res]
            return rs

    async def get_all_codes(self, extractions: dict, get_all: bool = False):
        tasks = []
        for anno_type, extr_list in extractions.items():
            if extr_list is None:
                continue
            for extr in extr_list:
                tasks.append(
                    self.get_code(anno_type=anno_type, get_all=get_all, **extr)
                )
        return await asyncio.gather(*tasks)

    def incorporate_codes(self, extractions: dict, **kwargs) -> dict:
        result_dict = defaultdict(list)
        for result in asyncio.run(
            self.get_all_codes(extractions, kwargs.pop("get_all", True))
        ):
            result_dict[result.annotation_type].append(
                result.to_json(restrict_to=self._restrict_output)
            )
        return result_dict


def add_codes(results: dict, config: dict) -> dict:
    final_results = {}
    _server_config = config.get("coding").get("servers")
    _annotations_config = config.get("coding").get("config").get("annotations")
    _response_parsing = config.get("coding").get("config").get("response")
    _get_all = config.get("coding").get("config").get("get_all", True)
    _ignore_fields = config.get("coding").get("ignore_fields")
    for server_name, server_config in _server_config.items():
        ep_dict = {}
        for anno_type, endpoint_list in _annotations_config.items():
            for ep in endpoint_list:
                if server_name not in ep:
                    continue
                ep_dict[anno_type] = ep.get(server_name)
        if len(ep_dict) == 0:
            continue
        coding_server = CodingServer(
            name=server_name,
            host=server_config.get("host", "localhost"),
            port=server_config.get("port", 8080),
            endpoints=ep_dict,
            ignore_fields=_ignore_fields,
            response_parsing=_response_parsing.get(server_name),
        )
        _results = coding_server.incorporate_codes(results, get_all=_get_all)
        if len(final_results) == 0:
            final_results.update(_results)
        else:
            for k, v in _results.items():
                for d in v:
                    _source_id = d.get("id")
                    for idx, _ in enumerate(final_results.get(k, [])):
                        _target_id = final_results[k][idx].get("id")
                        if _source_id != _target_id or len(d.get("codes", [])) == 0:
                            continue
                        final_results[k][idx]["codes"] += d.get("codes", [])
    return final_results


if __name__ == "__main__":
    _path = (
        pathlib.Path(__file__).parent.parent.parent.parent / "test/test_out_[0].json"
    )
    cs = CodingServer(
        name="id-logik",
        host="localhost",
        port=8080,
        endpoints={
            "diagnosen": "/inception/lookup_icd10?q={text}",
            "medikationen": "/inception/lookup_sct?q={text}",
        },
    )
    result = cs.incorporate_codes(json.load(_path.open("r", encoding="utf-8")))
    print(result)
    # pathlib.Path(_path.parent, "test_file_out.json").write_text(
    #     json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8"
    # )
