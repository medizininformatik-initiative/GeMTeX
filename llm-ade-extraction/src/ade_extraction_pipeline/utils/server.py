from typing import Union


class BasicServer:
    def __init__(
        self,
        name: str,
        host: str = "localhost",
        port: Union[str, int] = 8080,
        protocol: str = "http",
    ):
        self._name = name
        self._host = host
        self._port = port
        self._protocol = protocol if not host.startswith("http") else ""

    @property
    def name(self):
        return self._name

    @property
    def host(self):
        return self._host

    @property
    def port(self):
        return self._port

    @property
    def url(self):
        if self.port is not None and self.port.is_integer():
            return f"{self._protocol}{'://' if len(self._protocol) > 0 else ''}{self._host}:{self._port}"
        else:
            return f"{self._protocol}{'://' if len(self._protocol) > 0 else ''}{self._host}"
