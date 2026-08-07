"""Shared SNOMED-related models and enums."""

from __future__ import annotations

import dataclasses
import enum

from pydantic import BaseModel


class SnomedLanguage(enum.Enum):
    DE = "de"
    EN = "en"
    NONE = None

    @classmethod
    def _missing_(cls, value):
        return cls.NONE


class SnomedTerm(BaseModel):
    term: str
    lang: SnomedLanguage


class SnomedConcept(BaseModel):
    conceptId: str
    fsn: SnomedTerm
    pt: SnomedTerm


class SnowstormResponse(BaseModel):
    success: bool
    content: list[SnomedConcept]


class DumpMode(enum.Enum):
    SEMANTIC = enum.auto()
    VERSION = enum.auto()


class FilterMode(enum.Enum):
    POSITIVE = enum.auto()
    NEGATIVE = enum.auto()


class ListDumpType(enum.Enum):
    BLACKLIST = enum.auto()
    WHITELIST = enum.auto()


@dataclasses.dataclass
class FilterLists:
    codes: list[str]
    tags: list[str]


@dataclasses.dataclass
class Information:
    log_dump_pretext_caption: str = "Vorbemerkung"
    log_dump_pretext: str = (
        f"### {log_dump_pretext_caption}\n"
        "Manche Codes, die als 'blacklisted' gekenzeichnet sind, mögen ersteinmal verwundern, da sie den Semantic Tag `(qualifier value)` haben,\n"
        "der nicht verboten ist. Diese fallen dann jedoch unter die Kategorien `Overlapping sites` oder `action`,\n"
        "welche wiederum als ganzes ausgeschlossen wurden.\n\n"
        "Es folgt:\n"
        "* eine Auflistung nach Annotator*in und dazugehörige Dokumente für: [Whitelist](#whitelist) und [Blacklist](#blacklist)\n"
        "* eine Tabelle, mit allen gefundenen [Whitelist Codes](#snomed-ct-codes) (mit Anzahl über das gesamte Projekt)\n"
        "* eine Tabelle, mit allen gefundenen [Semantic Tags](#semantic-tags) (mit Anzahl über das gesamte Projekt)\n\n"
    )
