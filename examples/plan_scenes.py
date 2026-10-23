"""Plan the scenes of one chapter with the LLM only. No GPU or image model needed.

Handy for checking chapter detection and for tuning the prompt templates (see PROMPTS_DIR).
Needs Ollama running and the package installed (``pip install -e .``). Run from the repo root
so ./.env is picked up:

    python examples/plan_scenes.py examples/novels/lantern-keeper.en.txt
    python examples/plan_scenes.py examples/novels/snow-night.zh.txt --chapter 2 \\
        --style "watercolor; make the hero a silver-haired woman"
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from novel2img.chapters import split_chapters
from novel2img.config import Settings
from novel2img.llm import LLMError
from novel2img.scenes import ScenePlanner


async def run(args: argparse.Namespace) -> int:
    settings = Settings.from_env()
    chapters = split_chapters(args.novel.read_text(encoding="utf-8"))
    print(f"{len(chapters)} chapter(s):")
    for number, chapter in enumerate(chapters, 1):
        print(f"  {number}. {chapter.title or '(untitled)'} ({len(chapter.body)} characters)")
    if not 1 <= args.chapter <= len(chapters):
        print(f"--chapter must be between 1 and {len(chapters)}", file=sys.stderr)
        return 1

    chapter = chapters[args.chapter - 1]
    planner = ScenePlanner.from_settings(settings)
    print(f"\nPlanning scenes for {chapter.title or '(untitled)'} with {settings.ollama_model}…")
    try:
        scenes = await planner.plan(chapter, args.max_scenes)
        if args.style:
            print(f"Applying style: {args.style}")
            scenes = await planner.adjust(scenes, args.style)
    except LLMError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    for number, scene in enumerate(scenes, 1):
        print(f"\n[{number}] {scene.summary}")
        if scene.original_prompt:
            print(f"    before: {scene.original_prompt}")
        print(f"    prompt: {scene.prompt}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Plan the scenes of a chapter with the LLM only.")
    parser.add_argument("novel", type=Path, help="text file with one or more chapters")
    parser.add_argument("--chapter", type=int, default=1, help="chapter number, from 1")
    parser.add_argument("--max-scenes", type=int, help="default: MAX_SCENES from .env")
    parser.add_argument("--style", default="", help="style description to merge into the prompts")
    return asyncio.run(run(parser.parse_args()))


if __name__ == "__main__":
    sys.exit(main())
