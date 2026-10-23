"""Prompt templates for the LLM.

The built-in templates are the Markdown files next to this module:

- ``scene_system`` / ``scene_user`` split a chapter into scenes with tag prompts.
  Placeholders: ``$max_scenes``; the user template also gets ``$title`` and ``$body``.
- ``adjust_system`` / ``adjust_user`` merge the user's style description into one prompt.
  Placeholders (user template): ``$input`` (a JSON object with both), ``$prompt``, ``$adjustment``.

Point ``PROMPTS_DIR`` at a directory with files of the same names to override any of them;
missing files fall back to the built-ins. Templates are read on every use, so edits apply to the
next request without a restart.
"""
from __future__ import annotations

from pathlib import Path
from string import Template
from typing import Optional

BUILTIN_DIR = Path(__file__).resolve().parent
NAMES = ("scene_system", "scene_user", "adjust_system", "adjust_user")


def load_template(name: str, override_dir: Optional[Path] = None) -> str:
    for directory in (override_dir, BUILTIN_DIR):
        if directory is not None:
            path = directory / f"{name}.md"
            if path.is_file():
                return path.read_text(encoding="utf-8")
    raise FileNotFoundError(f"No prompt template named {name!r}")


def render(name: str, override_dir: Optional[Path] = None, **values: object) -> str:
    """Fill in a template. Unknown ``$placeholders`` and stray ``$`` signs are left as they are."""
    template = Template(load_template(name, override_dir))
    return template.safe_substitute({key: str(value) for key, value in values.items()})
