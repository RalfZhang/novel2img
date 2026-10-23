"""The FastAPI app: chapter detection, streaming generation (Server-Sent Events) and the web UI."""
import json
import logging
import mimetypes
from pathlib import Path
from typing import AsyncIterator, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import __version__
from .chapters import split_chapters
from .config import Settings
from .image_gen import ImageGenerator, ModelLoadError
from .llm import LLMError
from .pipeline import Event, generate_storyboard
from .scenes import ScenePlanner

STATIC_DIR = Path(__file__).resolve().parent / "static"

# Some Windows registries map .js to text/plain, which browsers refuse to run as a module.
mimetypes.add_type("text/javascript", ".js")

log = logging.getLogger(__name__)


class SplitRequest(BaseModel):
    text: str


class ChapterInfo(BaseModel):
    index: int
    title: str
    length: int


class SplitResponse(BaseModel):
    chapters: list[ChapterInfo]


class GenerateRequest(BaseModel):
    text: str = Field(description="One chapter or a whole novel")
    chapter_index: int = Field(0, ge=0, description="Which chapter of the text to illustrate")
    style: str = Field("", description="Free-form style description, merged into every prompt")
    max_scenes: Optional[int] = Field(None, ge=1, le=20, description="Defaults to MAX_SCENES")
    seed: Optional[int] = Field(
        None, ge=0, lt=2**32, description="Scene i uses seed + i; random when omitted"
    )


def create_app(
    settings: Optional[Settings] = None,
    *,
    planner: Optional[ScenePlanner] = None,
    generator: Optional[ImageGenerator] = None,
) -> FastAPI:
    """Build the app. ``planner`` and ``generator`` can be swapped out, e.g. for fakes in tests."""
    settings = settings or Settings.from_env()
    _setup_logging(settings.log_level)
    planner = planner or ScenePlanner.from_settings(settings)
    generator = generator or ImageGenerator(settings)
    settings.output_dir.mkdir(parents=True, exist_ok=True)

    app = FastAPI(title="novel2img", version=__version__)

    @app.get("/api/config")
    def get_config():
        return {
            "llm_model": settings.ollama_model,
            "image_model": settings.sd_model_path.name,
            "max_scenes": settings.max_scenes,
            "width": settings.img_width,
            "height": settings.img_height,
        }

    @app.post("/api/split", response_model=SplitResponse)
    def split(req: SplitRequest):
        chapters = split_chapters(req.text)
        return {
            "chapters": [
                {"index": i, "title": c.title, "length": len(c.body)}
                for i, c in enumerate(chapters)
            ]
        }

    @app.post("/api/generate")
    async def generate(req: GenerateRequest):
        chapters = split_chapters(req.text)
        if not chapters:
            raise HTTPException(400, "The text is empty.")
        if req.chapter_index >= len(chapters):
            raise HTTPException(
                400,
                f"chapter_index {req.chapter_index} is out of range: "
                f"the text has {len(chapters)} chapter(s).",
            )
        chapter = chapters[req.chapter_index]
        log.info(
            "Chapter %d/%d %r, style %r",
            req.chapter_index + 1,
            len(chapters),
            chapter.title,
            req.style[:120],
        )

        async def events() -> AsyncIterator[Event]:
            yield Event(
                "chapter",
                {
                    "index": req.chapter_index,
                    "title": chapter.title,
                    "total": len(chapters),
                    "has_next": req.chapter_index + 1 < len(chapters),
                },
            )
            try:
                async for event in generate_storyboard(
                    chapter,
                    planner,
                    generator,
                    style=req.style,
                    max_scenes=req.max_scenes,
                    seed=req.seed,
                    unload_llm=settings.ollama_unload,
                ):
                    if event.type == "image":
                        url = f"/outputs/{event.data['filename']}"
                        event = Event("image", {**event.data, "url": url})
                    yield event
            except Exception as exc:
                if isinstance(exc, (LLMError, ModelLoadError)):
                    log.error("Generation failed: %s", exc)
                else:
                    log.exception("Generation failed")
                yield Event("error", {"message": str(exc)})
                return
            yield Event("done", {"chapter_index": req.chapter_index})

        return StreamingResponse(
            (_encode_sse(event) async for event in events()),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache"},
        )

    app.mount("/outputs", StaticFiles(directory=settings.output_dir), name="outputs")
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="ui")
    return app


def _encode_sse(event: Event) -> bytes:
    return f"event: {event.type}\ndata: {json.dumps(event.data, ensure_ascii=False)}\n\n".encode()


def _setup_logging(level: str) -> None:
    logger = logging.getLogger("novel2img")
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s", "%H:%M:%S")
        )
        logger.addHandler(handler)
    logger.setLevel(level.upper())
