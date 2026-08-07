"""Custom Click parameter types used by the command-line interface."""

from __future__ import annotations

import click


class ClickUnion(click.ParamType):
    def __init__(self, *types):
        self.types = [t[0] for t in types]
        self.name = f"[{','.join([t[1] for t in types])}]"

    def convert(self, value, param, ctx):
        for _type in self.types:
            try:
                return _type.convert(value, param, ctx)
            except click.BadParameter:
                continue

        self.fail("Didn't match any of the accepted types.")


class ClickEnumChoice(click.ParamType):
    def __init__(self, enum_type):
        self.enum_type = enum_type
        self.choices = [e.name.lower() for e in enum_type]
        self.name = "[" + "|".join(self.choices) + "]"

    def convert(self, value, param, ctx):
        if isinstance(value, self.enum_type):
            return value
        value_normalized = str(value).lower()
        for enum_value in self.enum_type:
            if enum_value.name.lower() == value_normalized:
                return enum_value
        self.fail(
            f"'{value}' is not one of {'/'.join(self.choices)}.", param, ctx
        )
