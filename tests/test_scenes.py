import asyncio

import pytest

from novel2img.chapters import Chapter
from novel2img.llm import LLMError
from novel2img.scenes import Scene, ScenePlanner


class FakeLLM:
    """Answers every chat with ``respond(system, user)`` and records the calls."""

    def __init__(self, respond):
        self.respond = respond
        self.calls = []

    async def chat_json(self, system, user, **options):
        self.calls.append((system, user))
        reply = self.respond(system, user)
        if isinstance(reply, Exception):
            raise reply
        return reply

    async def unload(self):
        pass


CHAPTER = Chapter("Chapter 1: The Storm", "The storm came in from the west.")


def plan(reply, max_scenes=None, planner_max=8):
    llm = FakeLLM(lambda system, user: reply)
    scenes = asyncio.run(ScenePlanner(llm, max_scenes=planner_max).plan(CHAPTER, max_scenes))
    return scenes, llm


def test_plan_sends_the_chapter_and_cleans_the_scenes():
    reply = {
        "scenes": [
            {"summary": " Mara climbs the stairs ", "prompt": "1girl, Raincoat, climbing_stairs"},
            {"summary": "empty", "prompt": ""},
            "not a scene",
        ]
    }
    scenes, llm = plan(reply, planner_max=5)

    assert scenes == [Scene("Mara climbs the stairs", "1girl, raincoat, climbing stairs")]
    system, user = llm.calls[0]
    assert "between 1 and 5 scenes" in system
    assert "Chapter 1: The Storm" in user
    assert "The storm came in from the west." in user


@pytest.mark.parametrize(
    "reply",
    [
        [{"summary": "s", "prompt": "1girl"}],  # a bare list
        {"summary": "s", "prompt": "1girl"},  # a single scene
        {"scenes": [{"summary": "s", "prompt": ["1girl"]}]},  # tags as a list
    ],
)
def test_plan_accepts_other_reply_shapes(reply):
    assert plan(reply)[0] == [Scene("s", "1girl")]


def test_plan_returns_at_most_max_scenes():
    reply = {"scenes": [{"summary": str(i), "prompt": f"tag{i}"} for i in range(5)]}
    scenes, llm = plan(reply, max_scenes=2)
    assert [s.summary for s in scenes] == ["0", "1"]
    assert "between 1 and 2 scenes" in llm.calls[0][0]


@pytest.mark.parametrize("reply", [None, {}, {"scenes": []}, {"scenes": "1girl"}])
def test_plan_fails_when_nothing_is_usable(reply):
    with pytest.raises(LLMError):
        plan(reply)


def test_adjust_merges_the_style_and_keeps_the_original():
    def respond(system, user):
        if "1boy, sword" in user:
            return {"prompt": "1girl, sword, Silver_Hair"}
        if "2boys" in user:
            return LLMError("Ollama is down")
        return {"answer": "no prompt here"}

    llm = FakeLLM(respond)
    scenes = [Scene("a", "1boy, sword"), Scene("b", "2boys"), Scene("c", "no humans")]
    adjusted = asyncio.run(ScenePlanner(llm).adjust(scenes, "make the hero a silver-haired girl"))

    assert adjusted == [
        Scene("a", "1girl, sword, silver hair", original_prompt="1boy, sword"),
        Scene("b", "2boys"),  # the call failed: unchanged
        Scene("c", "no humans"),  # the reply had no prompt: unchanged
    ]
    assert all("make the hero a silver-haired girl" in user for _, user in llm.calls)


def test_adjust_without_a_style_does_not_call_the_llm():
    llm = FakeLLM(lambda system, user: pytest.fail("unexpected LLM call"))
    scenes = [Scene("a", "1girl")]
    assert asyncio.run(ScenePlanner(llm).adjust(scenes, "   ")) == scenes


def test_scene_to_dict_omits_a_missing_original_prompt():
    assert Scene("a", "1girl").to_dict() == {"summary": "a", "prompt": "1girl"}
    assert Scene("a", "1girl", "1boy").to_dict()["original_prompt"] == "1boy"
