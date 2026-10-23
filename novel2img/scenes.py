"""Use the LLM to split a chapter into scenes and to merge style adjustments into their prompts."""
from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, Optional

from . import prompts
from .chapters import Chapter
from .config import Settings
from .llm import LLMError, OllamaClient
from .tags import sanitize_prompt, split_tags

log = logging.getLogger(__name__)

_PLAN_TEMPERATURE = 0.7
_PLAN_TIMEOUT = 600.0
_ADJUST_TEMPERATURE = 0.5
_ADJUST_TIMEOUT = 180.0


@dataclass(frozen=True)
class Scene:
    summary: str
    prompt: str  # comma-separated Danbooru tags
    original_prompt: Optional[str] = None  # the prompt before a style adjustment changed it

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        if self.original_prompt is None:
            del data["original_prompt"]
        return data


class ScenePlanner:
    def __init__(
        self, llm: OllamaClient, *, max_scenes: int = 8, prompts_dir: Optional[Path] = None
    ) -> None:
        self.llm = llm
        self.max_scenes = max_scenes
        self.prompts_dir = prompts_dir

    @classmethod
    def from_settings(cls, settings: Settings) -> ScenePlanner:
        llm = OllamaClient(
            settings.ollama_url, settings.ollama_model, num_ctx=settings.ollama_num_ctx
        )
        return cls(llm, max_scenes=settings.max_scenes, prompts_dir=settings.prompts_dir)

    async def plan(self, chapter: Chapter, max_scenes: Optional[int] = None) -> list[Scene]:
        """Pick up to ``max_scenes`` scenes from the chapter, each with a neutral tag prompt."""
        limit = max_scenes or self.max_scenes
        system = prompts.render("scene_system", self.prompts_dir, max_scenes=limit)
        user = prompts.render(
            "scene_user",
            self.prompts_dir,
            title=chapter.title or "(untitled)",
            body=chapter.body,
            max_scenes=limit,
        )
        data = await self.llm.chat_json(
            system, user, temperature=_PLAN_TEMPERATURE, timeout=_PLAN_TIMEOUT
        )
        scenes = _parse_scenes(data)[:limit]
        if not scenes:
            raise LLMError(
                "The LLM did not return any usable scene. Try again or use another OLLAMA_MODEL."
            )
        for i, scene in enumerate(scenes):
            log.info("scene[%d] %d tags | %s", i, len(split_tags(scene.prompt)), scene.prompt)
        return scenes

    async def adjust(self, scenes: list[Scene], adjustment: str) -> list[Scene]:
        """Merge a free-form style description into every scene's prompt.

        Runs one LLM call per scene, concurrently. A scene whose call fails keeps its prompt.
        """
        adjustment = adjustment.strip()
        if not adjustment:
            return list(scenes)
        new_prompts = await asyncio.gather(
            *(self._adjust_prompt(i, s.prompt, adjustment) for i, s in enumerate(scenes))
        )
        adjusted = []
        for scene, new_prompt in zip(scenes, new_prompts):
            if new_prompt != scene.prompt:
                scene = replace(scene, prompt=new_prompt, original_prompt=scene.prompt)
            adjusted.append(scene)
        return adjusted

    async def unload_llm(self) -> None:
        await self.llm.unload()

    async def _adjust_prompt(self, index: int, prompt: str, adjustment: str) -> str:
        system = prompts.render("adjust_system", self.prompts_dir)
        user = prompts.render(
            "adjust_user",
            self.prompts_dir,
            input=json.dumps({"prompt": prompt, "adjustment": adjustment}, ensure_ascii=False),
            prompt=prompt,
            adjustment=adjustment,
        )
        try:
            data = await self.llm.chat_json(
                system, user, temperature=_ADJUST_TEMPERATURE, timeout=_ADJUST_TIMEOUT
            )
        except LLMError as exc:
            log.warning("Adjusting scene[%d] failed, keeping its prompt: %s", index, exc)
            return prompt
        new_prompt = _parse_prompt(data)
        if not new_prompt:
            log.warning("Adjusting scene[%d]: no prompt in the LLM reply, keeping it", index)
            return prompt
        log.info(
            "adjusted scene[%d] %d -> %d tags | %s",
            index,
            len(split_tags(prompt)),
            len(split_tags(new_prompt)),
            new_prompt,
        )
        return new_prompt


def _parse_scenes(data: Any) -> list[Scene]:
    """Accept {"scenes": [...]}, a bare list of scenes, or a single scene object."""
    items = data
    if isinstance(data, dict):
        items = data.get("scenes", [data] if "prompt" in data else None)
    if not isinstance(items, list):
        return []
    scenes = []
    for item in items:
        if not isinstance(item, dict):
            continue
        prompt = sanitize_prompt(_as_text(item.get("prompt")))
        if prompt:
            scenes.append(Scene(summary=_as_text(item.get("summary")).strip(), prompt=prompt))
    return scenes


def _parse_prompt(data: Any) -> str:
    """Accept {"prompt": "..."}, or {"prompts": ["..."]} as some models answer."""
    if not isinstance(data, dict):
        return ""
    value = data.get("prompt")
    if value is None and isinstance(data.get("prompts"), list) and data["prompts"]:
        value = data["prompts"][0]
    return sanitize_prompt(_as_text(value))


def _as_text(value: Any) -> str:
    if isinstance(value, list):  # some models return a list of tags instead of a string
        return ", ".join(str(v) for v in value)
    return "" if value is None else str(value)
