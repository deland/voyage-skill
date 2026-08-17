"""Deterministic argparse-derived command reference for VoyageSkill."""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from .cli import build_parser


START_MARKER = "<!-- voyage-cli-reference:start -->"
END_MARKER = "<!-- voyage-cli-reference:end -->"


def cli_leaf_commands(parser: argparse.ArgumentParser, prefix: tuple[str, ...] = ("voyage",)) -> list[str]:
    commands: list[str] = []
    subparser_actions = [action for action in parser._actions if isinstance(action, argparse._SubParsersAction)]
    if not subparser_actions:
        return [" ".join(prefix)]
    for action in subparser_actions:
        for name, child in sorted(action.choices.items()):
            commands.extend(cli_leaf_commands(child, prefix + (name,)))
    return sorted(commands)


def render_cli_reference() -> str:
    lines = [START_MARKER, "| Command |", "| --- |"]
    lines.extend(f"| `{command}` |" for command in cli_leaf_commands(build_parser()))
    lines.append(END_MARKER)
    return "\n".join(lines)


def _reference_body(document: str) -> str | None:
    pattern = re.compile(rf"{re.escape(START_MARKER)}.*?{re.escape(END_MARKER)}", flags=re.DOTALL)
    match = pattern.search(document)
    return match.group(0) if match else None


def documented_commands(document: str) -> list[str]:
    body = _reference_body(document)
    if body is None:
        return []
    return re.findall(r"`(voyage(?: [a-z][a-z-]*)+)`", body)


def check_cli_reference(document: str) -> list[str]:
    body = _reference_body(document)
    if body is None:
        return ["CLI reference markers are missing"]
    expected = cli_leaf_commands(build_parser())
    actual = documented_commands(document)
    errors: list[str] = []
    if actual != expected:
        missing = sorted(set(expected) - set(actual))
        extra = sorted(set(actual) - set(expected))
        if missing:
            errors.append("missing CLI commands: " + ", ".join(missing))
        if extra:
            errors.append("unknown CLI commands: " + ", ".join(extra))
        if not missing and not extra:
            errors.append("CLI commands are duplicated or out of deterministic order")
    if body != render_cli_reference():
        errors.append("CLI reference formatting differs from generated output")
    return errors


def replace_cli_reference(document: str) -> str:
    body = _reference_body(document)
    if body is None:
        raise ValueError("CLI reference markers are missing")
    return document.replace(body, render_cli_reference(), 1)


def check_cli_reference_file(path: Path) -> list[str]:
    return check_cli_reference(path.read_text(encoding="utf-8"))
