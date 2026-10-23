"""The command reference must mention every command and every option (so docs cannot drift)."""

import argparse
from pathlib import Path

import pytest

from blogpub.cli import build_parser
from blogpub.config import DEFAULTS

DOCS = Path(__file__).parent.parent / "docs"


def options_by_command():
    parser = build_parser()
    sub = next(a for a in parser._actions if isinstance(a, argparse._SubParsersAction))
    for name, sp in sub.choices.items():
        flags = {f for a in sp._actions for f in a.option_strings if f.startswith("--") and f != "--help"}
        yield name, flags


@pytest.mark.parametrize("doc", ["usage.md", "usage.zh.md"])
def test_every_command_and_option_is_documented(doc):
    text = (DOCS / doc).read_text(encoding="utf-8")
    for name, flags in options_by_command():
        assert f"blogpub {name}" in text, f"{doc}: command '{name}' is not documented"
        for flag in flags:
            assert flag in text, f"{doc}: option {flag} of '{name}' is not documented"


@pytest.mark.parametrize("doc", ["usage.md", "usage.zh.md"])
def test_every_config_key_is_documented(doc):
    text = (DOCS / doc).read_text(encoding="utf-8")
    def keys(d, prefix=""):
        for k, v in d.items():
            if isinstance(v, dict) and k not in ("timeline_title_prefix",):
                yield from keys(v, f"{prefix}{k}.")
            else:
                yield f"{prefix}{k}"
    for key in keys(DEFAULTS):
        assert f"`{key}`" in text, f"{doc}: config key {key} is not documented"
