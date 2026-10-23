"""Settings, read from environment variables and an optional ``.env`` file.

Every field of :class:`Settings` maps to the upper-case environment variable of the same name
(``ollama_url`` -> ``OLLAMA_URL``). Unset or empty variables keep the defaults below. Relative
paths are resolved against the directory novel2img is started from.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Mapping, Optional, Union, get_args, get_origin, get_type_hints

from dotenv import load_dotenv

DEVICES = ("auto", "cuda", "mps", "cpu")
DTYPES = ("float16", "bfloat16", "float32")

DEFAULT_QUALITY_TAGS = "masterpiece, best quality, amazing quality, very aesthetic, highres"
DEFAULT_NEGATIVE_PROMPT = (
    "bad quality, worst quality, low quality, lowres, jpeg artifacts, blurry, watermark, "
    "signature, text, bad anatomy, bad hands, extra fingers, missing fingers"
)


@dataclass(frozen=True)
class Settings:
    # LLM (Ollama)
    ollama_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "BlackHillsInfoSec/llama-3.1-8b-abliterated"
    ollama_num_ctx: int = 8192
    ollama_unload: bool = True  # free the LLM's memory before the image model renders

    # Image model
    sd_model_path: Path = Path("models/waiIllustriousSDXL_v170.safetensors")
    sd_is_sdxl: bool = True
    sd_device: str = "auto"
    sd_dtype: str = "float16"
    lora_dir: Path = Path("models/lora")
    lora_spec: str = ""  # "a.safetensors:0.8,b.safetensors" (files relative to lora_dir)

    # Generation
    img_width: int = 832
    img_height: int = 1216
    img_steps: int = 24
    img_cfg: float = 5.5
    max_scenes: int = 8
    quality_tags: str = DEFAULT_QUALITY_TAGS
    negative_prompt: str = DEFAULT_NEGATIVE_PROMPT

    # Files
    output_dir: Path = Path("outputs")
    prompts_dir: Optional[Path] = None  # custom LLM prompt templates, see novel2img/prompts/

    log_level: str = "INFO"

    def __post_init__(self) -> None:
        if self.sd_device not in DEVICES:
            raise ValueError(f"SD_DEVICE must be one of {'/'.join(DEVICES)}: {self.sd_device!r}")
        if self.sd_dtype not in DTYPES:
            raise ValueError(f"SD_DTYPE must be one of {'/'.join(DTYPES)}: {self.sd_dtype!r}")
        if self.max_scenes < 1:
            raise ValueError("MAX_SCENES must be at least 1")

    @classmethod
    def from_env(cls, env: Optional[Mapping[str, str]] = None) -> Settings:
        """Read settings from ``env``, or from ``os.environ`` after loading ``./.env``."""
        if env is None:
            load_dotenv(Path.cwd() / ".env")  # variables that are already set take precedence
            env = os.environ
        hints = get_type_hints(cls)
        values = {}
        for field in fields(cls):
            name = field.name.upper()
            raw = env.get(name, "").strip()
            if not raw:
                continue
            try:
                values[field.name] = _convert(hints[field.name], raw)
            except ValueError:
                raise ValueError(f"Invalid value for {name}: {raw!r}") from None
        return cls(**values)


def _convert(type_: object, raw: str) -> object:
    if get_origin(type_) is Union:  # Optional[X]
        type_ = next(arg for arg in get_args(type_) if arg is not type(None))
    if type_ is bool:
        if raw.lower() in ("1", "true", "yes", "on"):
            return True
        if raw.lower() in ("0", "false", "no", "off"):
            return False
        raise ValueError(raw)
    if type_ is Path:
        return Path(raw).expanduser()
    return type_(raw)  # str, int, float
