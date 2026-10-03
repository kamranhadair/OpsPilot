"""Schema creation belongs to Alembic; the app must never call create_all()."""

import ast
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[1] / "app"


def _calls_create_all(source: str) -> bool:
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Call):
            func = node.func
            name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
            if name == "create_all":
                return True
    return False


def test_app_package_never_calls_create_all() -> None:
    offenders = [
        str(path.relative_to(APP_DIR))
        for path in APP_DIR.rglob("*.py")
        if _calls_create_all(path.read_text())
    ]
    assert offenders == []


def test_detector_catches_a_real_call() -> None:
    assert _calls_create_all("Base.metadata.create_all(engine)")
    assert not _calls_create_all('"""never calls create_all()"""')
