import json
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from novel2img.config import Settings
from novel2img.image_gen import GeneratedImage, ModelLoadError
from novel2img.llm import LLMError
from novel2img.scenes import Scene
from novel2img.server import create_app

NOVEL = (
    "Chapter 1: The Storm\nThe storm came.\n\n"
    "Chapter 2: The Stranger\nA stranger washed ashore."
)


class FakePlanner:
    def __init__(self, error=None):
        self.error = error
        self.unloaded = False

    async def plan(self, chapter, max_scenes=None):
        if self.error:
            raise self.error
        scenes = [Scene("Mara runs", "1girl, running"), Scene("The wreck", "no humans, shipwreck")]
        return scenes[: max_scenes or 2]

    async def adjust(self, scenes, adjustment):
        return [
            replace(s, prompt=f"{s.prompt}, {adjustment}", original_prompt=s.prompt) for s in scenes
        ]

    async def unload_llm(self):
        self.unloaded = True


class FakeGenerator:
    def __init__(self, output_dir, fail_on="", load_error=None):
        self.output_dir = output_dir
        self.fail_on = fail_on
        self.load_error = load_error
        self.is_loaded = False

    async def load(self):
        if self.load_error:
            raise self.load_error
        self.is_loaded = True

    async def generate(self, prompt, seed):
        if self.fail_on and self.fail_on in prompt:
            raise RuntimeError("out of memory")
        path = self.output_dir / f"{seed}.png"
        path.write_bytes(b"\x89PNG fake")
        return GeneratedImage(path=path, prompt=f"masterpiece, {prompt}", seed=seed)


@pytest.fixture
def make_client(tmp_path):
    def make(planner=None, generator=None, **settings):
        app = create_app(
            Settings(output_dir=tmp_path, **settings),
            planner=planner or FakePlanner(),
            generator=generator or FakeGenerator(tmp_path),
        )
        return TestClient(app)

    return make


def read_events(response):
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    events = []
    for block in response.text.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.split("\n"))
        events.append((lines["event"], json.loads(lines["data"])))
    return events


def test_web_ui_and_config_are_served(make_client):
    client = make_client(max_scenes=5)
    page = client.get("/")
    assert page.status_code == 200
    assert "novel2img" in page.text
    assert client.get("/app.js").headers["content-type"].startswith("text/javascript")
    config = client.get("/api/config").json()
    assert config["max_scenes"] == 5
    assert config["image_model"] == "waiIllustriousSDXL_v170.safetensors"


def test_split(make_client):
    response = make_client().post("/api/split", json={"text": NOVEL})
    assert response.json() == {
        "chapters": [
            {"index": 0, "title": "Chapter 1: The Storm", "length": 15},
            {"index": 1, "title": "Chapter 2: The Stranger", "length": 25},
        ]
    }


def test_generate_streams_the_whole_chapter(make_client, tmp_path):
    planner = FakePlanner()
    client = make_client(planner=planner)
    events = read_events(
        client.post("/api/generate", json={"text": NOVEL, "style": "watercolor", "seed": 7})
    )

    assert [e for e, _ in events] == [
        "chapter",
        "status",  # planning
        "status",  # adjusting
        "scenes",
        "status",  # unloading_llm
        "status",  # loading_model
        "status",  # rendering scene 1
        "image",
        "status",  # rendering scene 2
        "image",
        "done",
    ]
    assert events[0][1] == {
        "index": 0,
        "title": "Chapter 1: The Storm",
        "total": 2,
        "has_next": True,
    }
    stages = [data["stage"] for event, data in events if event == "status"]
    assert stages == ["planning", "adjusting", "unloading_llm", "loading_model"] + ["rendering"] * 2
    scenes = events[3][1]
    assert scenes["count"] == 2
    assert scenes["scenes"][0] == {
        "summary": "Mara runs",
        "prompt": "1girl, running, watercolor",
        "original_prompt": "1girl, running",
    }
    images = [data for event, data in events if event == "image"]
    assert [image["seed"] for image in images] == [7, 8]  # scene i uses seed + i
    assert images[0]["full_prompt"] == "masterpiece, 1girl, running, watercolor"
    assert images[0]["url"] == "/outputs/7.png"
    assert client.get(images[0]["url"]).content == b"\x89PNG fake"
    assert planner.unloaded


def test_generate_without_style_seed_or_unloading(make_client):
    planner = FakePlanner()
    client = make_client(planner=planner, ollama_unload=False)
    events = read_events(
        client.post("/api/generate", json={"text": NOVEL, "chapter_index": 1, "max_scenes": 1})
    )
    stages = [data["stage"] for event, data in events if event == "status"]
    assert stages == ["planning", "loading_model", "rendering"]
    assert events[0][1]["has_next"] is False
    assert "original_prompt" not in events[2][1]["scenes"][0]
    assert 0 <= events[-2][1]["seed"] < 2**32
    assert not planner.unloaded


def test_a_failed_image_does_not_stop_the_chapter(make_client, tmp_path):
    client = make_client(generator=FakeGenerator(tmp_path, fail_on="shipwreck"))
    events = read_events(client.post("/api/generate", json={"text": NOVEL}))
    assert [e for e, _ in events][-4:] == ["image", "status", "error", "done"]
    assert events[-2][1] == {"scene_index": 1, "message": "Image generation failed: out of memory"}


@pytest.mark.parametrize(
    "planner_error, load_error",
    [(LLMError("Cannot reach Ollama"), None), (None, ModelLoadError("Image model not found"))],
)
def test_fatal_errors_end_the_stream(make_client, tmp_path, planner_error, load_error):
    client = make_client(
        planner=FakePlanner(error=planner_error),
        generator=FakeGenerator(tmp_path, load_error=load_error),
    )
    events = read_events(client.post("/api/generate", json={"text": NOVEL}))
    assert events[-1] == ("error", {"message": str(planner_error or load_error)})
    assert "done" not in [e for e, _ in events]


@pytest.mark.parametrize(
    "body, status",
    [
        ({"text": "  "}, 400),
        ({"text": NOVEL, "chapter_index": 2}, 400),
        ({"text": NOVEL, "max_scenes": 0}, 422),
        ({"text": NOVEL, "seed": -1}, 422),
        ({}, 422),
    ],
)
def test_bad_requests_are_rejected(make_client, body, status):
    assert make_client().post("/api/generate", json=body).status_code == status
