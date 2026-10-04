"""Prompt contract and the single-provider-boundary rule."""

import ast
from pathlib import Path

import pytest

from app.integrations.llm.prompts import BRIEF_SYSTEM_PROMPT

APP = Path(__file__).resolve().parents[2] / "app"


@pytest.mark.parametrize(
    "phrase",
    [
        "ONLY the provided Evidence Bundle",
        "Never invent an evidence ID",
        "at least one evidence ID",
        "Never calculate",
        "unsupported causation",
        "caused by",
        "observation",
        "inference",
        "insufficient",
        "concise",
    ],
)
def test_system_prompt_states_every_required_rule(phrase: str) -> None:
    assert phrase in BRIEF_SYSTEM_PROMPT


def test_openai_is_imported_only_inside_the_llm_boundary() -> None:
    offenders = []
    for path in APP.rglob("*.py"):
        if "integrations/llm" in path.as_posix():
            continue
        for node in ast.walk(ast.parse(path.read_text())):
            names = (
                [a.name for a in node.names]
                if isinstance(node, ast.Import)
                else [node.module or ""]
                if isinstance(node, ast.ImportFrom)
                else []
            )
            if any(n == "openai" or n.startswith("openai.") for n in names):
                offenders.append(str(path.relative_to(APP)))
    assert offenders == []


def test_openai_model_is_not_hardcoded() -> None:
    for path in APP.rglob("*.py"):
        text = path.read_text()
        assert "gpt-" not in text, path
