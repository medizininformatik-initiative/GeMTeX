import enum


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
