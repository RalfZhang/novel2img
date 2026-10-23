from pathlib import Path

import pytest

from novel2img.config import Settings


def test_defaults():
    settings = Settings.from_env({})
    assert settings.ollama_url == "http://127.0.0.1:11434"
    assert settings.sd_device == "auto"
    assert settings.max_scenes == 8
    assert settings.ollama_unload is True
    assert settings.prompts_dir is None


def test_values_are_converted_to_the_field_types():
    settings = Settings.from_env(
        {
            "IMG_STEPS": "30",
            "IMG_CFG": "6.5",
            "SD_IS_SDXL": "no",
            "OLLAMA_UNLOAD": "0",
            "OUTPUT_DIR": "~/pictures",
            "PROMPTS_DIR": "my-prompts",
            "LORA_SPEC": "a.safetensors:0.5",
        }
    )
    assert settings.img_steps == 30
    assert settings.img_cfg == 6.5
    assert settings.sd_is_sdxl is False
    assert settings.ollama_unload is False
    assert settings.output_dir == Path.home() / "pictures"
    assert settings.prompts_dir == Path("my-prompts")
    assert settings.lora_spec == "a.safetensors:0.5"


def test_empty_values_keep_the_defaults():
    assert Settings.from_env({"MAX_SCENES": "", "SD_DEVICE": "  "}) == Settings()


@pytest.mark.parametrize(
    "env, message",
    [
        ({"IMG_STEPS": "many"}, "IMG_STEPS"),
        ({"SD_IS_SDXL": "maybe"}, "SD_IS_SDXL"),
        ({"SD_DEVICE": "tpu"}, "SD_DEVICE"),
        ({"SD_DTYPE": "int8"}, "SD_DTYPE"),
        ({"MAX_SCENES": "0"}, "MAX_SCENES"),
    ],
)
def test_invalid_values_are_reported(env, message):
    with pytest.raises(ValueError, match=message):
        Settings.from_env(env)
