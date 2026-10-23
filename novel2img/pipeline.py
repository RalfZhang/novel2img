"""Turn one chapter into a storyboard, reporting progress as a stream of events.

The web server forwards these events as Server-Sent Events. Types and payloads:

- ``status``: ``{"stage", "message"}``. Stages: ``planning``, ``adjusting``, ``unloading_llm``,
  ``loading_model``, and ``rendering`` (which also has ``scene_index`` and ``total``).
- ``scenes``: ``{"count", "scenes": [{"summary", "prompt", "original_prompt"?}]}``
- ``image``: ``{"scene_index", "summary", "prompt", "full_prompt", "seed", "filename"}``
- ``error``: ``{"scene_index", "message"}`` when one image fails; the other scenes still render.
"""
from __future__ import annotations

import logging
import random
from dataclasses import dataclass
from typing import Any, AsyncIterator, Optional

from .chapters import Chapter
from .image_gen import ImageGenerator
from .scenes import ScenePlanner

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Event:
    type: str
    data: dict[str, Any]


def _status(stage: str, message: str, **extra: Any) -> Event:
    return Event("status", {"stage": stage, "message": message, **extra})


async def generate_storyboard(
    chapter: Chapter,
    planner: ScenePlanner,
    generator: ImageGenerator,
    *,
    style: str = "",
    max_scenes: Optional[int] = None,
    seed: Optional[int] = None,
    unload_llm: bool = True,
) -> AsyncIterator[Event]:
    """Plan the scenes of ``chapter`` and render one image per scene.

    ``style`` is merged into every prompt by the LLM. With a ``seed``, scene *i* uses
    ``seed + i``; without one, every scene gets a random seed. LLM and model-loading errors are
    raised; a single image that fails to render is reported as an ``error`` event instead.
    """
    yield _status("planning", "Planning scenes")
    scenes = await planner.plan(chapter, max_scenes)
    if style.strip():
        yield _status("adjusting", "Applying the style description")
        scenes = await planner.adjust(scenes, style)
    yield Event("scenes", {"count": len(scenes), "scenes": [s.to_dict() for s in scenes]})

    if unload_llm:
        yield _status("unloading_llm", "Freeing LLM memory")
        await planner.unload_llm()
    if not generator.is_loaded:
        yield _status("loading_model", "Loading the image model")
        await generator.load()

    for i, scene in enumerate(scenes):
        yield _status(
            "rendering", f"Rendering image {i + 1}/{len(scenes)}", scene_index=i, total=len(scenes)
        )
        scene_seed = seed + i if seed is not None else random.randrange(2**32)
        try:
            image = await generator.generate(scene.prompt, scene_seed)
        except Exception as exc:  # report it and carry on with the next scene
            log.exception("Rendering scene %d failed", i)
            yield Event("error", {"scene_index": i, "message": f"Image generation failed: {exc}"})
            continue
        yield Event(
            "image",
            {
                "scene_index": i,
                "summary": scene.summary,
                "prompt": scene.prompt,
                "full_prompt": image.prompt,
                "seed": image.seed,
                "filename": image.path.name,
            },
        )
