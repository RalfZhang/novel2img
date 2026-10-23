import asyncio

import pytest

from novel2img.config import Settings
from novel2img.image_gen import (
    ImageGenerator,
    ModelLoadError,
    fit_to_token_limit,
    parse_lora_spec,
)


class WordTokenizer:
    """Counts one token per word, standing in for a CLIP tokenizer."""

    def __call__(self, text, add_special_tokens=False):
        return {"input_ids": text.replace(",", " ").split()}


def test_fit_to_token_limit_drops_tags_from_the_end():
    tags = ["a b", "c", "d e f"]  # 2 + 1 + 3 tokens
    assert fit_to_token_limit(tags, [WordTokenizer()], limit=6) == tags
    assert fit_to_token_limit(tags, [WordTokenizer()], limit=5) == ["a b", "c"]
    assert fit_to_token_limit(tags, [WordTokenizer()], limit=1) == []


def test_fit_to_token_limit_respects_every_tokenizer():
    class Doubling(WordTokenizer):
        def __call__(self, text, add_special_tokens=False):
            return {"input_ids": super().__call__(text)["input_ids"] * 2}

    assert fit_to_token_limit(["a", "b", "c"], [WordTokenizer(), Doubling()], limit=4) == ["a", "b"]


def test_fit_to_token_limit_without_tokenizers_keeps_everything():
    assert fit_to_token_limit(["a", "b"], [], limit=0) == ["a", "b"]


def test_parse_lora_spec():
    spec = "a.safetensors:0.8, b.safetensors ,slider.safetensors:-1.5,,"
    assert parse_lora_spec(spec) == [
        ("a.safetensors", 0.8),
        ("b.safetensors", 1.0),
        ("slider.safetensors", -1.5),
    ]
    assert parse_lora_spec(r"C:\loras\x.safetensors") == [(r"C:\loras\x.safetensors", 1.0)]
    assert parse_lora_spec("") == []


def test_missing_model_file_gives_a_helpful_error(tmp_path):
    generator = ImageGenerator(Settings(sd_model_path=tmp_path / "missing.safetensors"))
    with pytest.raises(ModelLoadError, match="SD_MODEL_PATH"):
        asyncio.run(generator.load())
    assert not generator.is_loaded


def test_resolve_device():
    pytest.importorskip("torch")
    from novel2img.image_gen import resolve_device

    assert resolve_device("cpu") == "cpu"
    assert resolve_device("auto") in ("cuda", "mps", "cpu")
