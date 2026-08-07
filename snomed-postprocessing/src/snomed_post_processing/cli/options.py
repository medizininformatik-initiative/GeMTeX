"""Reusable Click option decorators."""

from __future__ import annotations

import click


def click_server_options(fnc):
    fnc = click.option(
        "--use-secure_protocol", is_flag=True, help="Whether to use 'https'."
    )(fnc)
    fnc = click.option(
        "--port",
        default=8080,
        help="Port on which the Snowstorm/INCEpTION instance runs.",
    )(fnc)
    fnc = click.option(
        "--ip",
        default="localhost",
        help="The IP address of the Snowstorm/INCEpTION instance.",
    )(fnc)
    return fnc


def click_inception_client_options(fnc):
    fnc = click.option(
        "--inception-project",
        default=None,
        help="The name of the INCEpTION project (URL slug).",
    )(fnc)
    fnc = click.option(
        "--inception-password",
        default=None,
        help="The username for the INCEpTION client (needs to have REMOTE role).",
    )(fnc)
    fnc = click.option(
        "--inception-username",
        default=None,
        help="The username for the INCEpTION client (needs to have REMOTE role).",
    )(fnc)
    return fnc


def click_log_level(fnc):
    fnc = click.option(
        "--log-level",
        default="INFO",
        type=click.Choice(
            ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"], case_sensitive=False
        ),
        help="The log level.",
    )(fnc)
    return fnc


def common_click_args(fnc):
    fnc = click.argument("root_code", default="138875005")(fnc)
    return fnc
