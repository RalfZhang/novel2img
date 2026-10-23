"""Render images with a single-file Stable Diffusion 1.5 / SDXL checkpoint through diffusers.

torch and diffusers are imported lazily, so the rest of the app (and the tests) don't load them.
"""
from __future__ import annotations

import asyncio
import logging
import os
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

from .config import Settings
from .tags import split_tags

log = logging.getLogger(__name__)

CLIP_TOKEN_LIMIT = 75  # CLIP reads 77 tokens, two of which are start/end markers


class ModelLoadError(RuntimeError):
    """The image model could not be loaded."""


@dataclass(frozen=True)
class GeneratedImage:
    path: Path
    prompt: str  # what the model received: quality tags + scene tags, trimmed to fit CLIP
    seed: int


class ImageGenerator:
    """Loads the checkpoint on first use and renders one image at a time."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._pipe: Any = None
        self._load_lock = threading.Lock()
        self._render_lock = threading.Lock()

    @property
    def is_loaded(self) -> bool:
        return self._pipe is not None

    async def load(self) -> None:
        """Load the model now instead of during the first :meth:`generate` call."""
        await asyncio.to_thread(self._get_pipe)

    async def generate(self, prompt: str, seed: int) -> GeneratedImage:
        """Render a comma-separated tag prompt and save it as a PNG in the output directory."""
        return await asyncio.to_thread(self._generate, prompt, seed)

    def _generate(self, prompt: str, seed: int) -> GeneratedImage:
        pipe = self._get_pipe()  # first, so torch is imported with the MPS fallback enabled
        import torch

        s = self.settings
        full_prompt = self._full_prompt(pipe, prompt)
        with self._render_lock:
            image = pipe(
                prompt=full_prompt,
                negative_prompt=s.negative_prompt,
                width=s.img_width,
                height=s.img_height,
                num_inference_steps=s.img_steps,
                guidance_scale=s.img_cfg,
                generator=torch.Generator(device="cpu").manual_seed(seed),
            ).images[0]
        s.output_dir.mkdir(parents=True, exist_ok=True)
        path = s.output_dir / f"{int(time.time() * 1000)}_{uuid.uuid4().hex[:8]}.png"
        image.save(path, format="PNG")
        return GeneratedImage(path=path, prompt=full_prompt, seed=seed)

    def _full_prompt(self, pipe: Any, prompt: str) -> str:
        tags = split_tags(self.settings.quality_tags) + split_tags(prompt)
        tokenizers = [
            tok
            for tok in (getattr(pipe, "tokenizer", None), getattr(pipe, "tokenizer_2", None))
            if tok is not None
        ]
        kept = fit_to_token_limit(tags, tokenizers)
        if len(kept) < len(tags):
            log.info("Trimmed to fit CLIP, dropped: %s", ", ".join(tags[len(kept) :]))
        return ", ".join(kept)

    def _get_pipe(self) -> Any:
        if self._pipe is None:
            with self._load_lock:
                if self._pipe is None:
                    self._pipe = self._load_pipeline()
        return self._pipe

    def _load_pipeline(self) -> Any:
        s = self.settings
        path = s.sd_model_path
        if not path.is_file():
            raise ModelLoadError(
                f"Image model not found: {path.resolve()}. "
                "Put a checkpoint there or set SD_MODEL_PATH in .env."
            )
        # Let operations that MPS lacks fall back to the CPU instead of failing (Apple Silicon).
        os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")
        try:
            import torch
            from diffusers import (
                EulerAncestralDiscreteScheduler,
                StableDiffusionPipeline,
                StableDiffusionXLPipeline,
            )

            device = resolve_device(s.sd_device)
            # Half precision is slow or unsupported on the CPU.
            dtype = torch.float32 if device == "cpu" else getattr(torch, s.sd_dtype)
            log.info("Loading %s on %s (%s)…", path.name, device, str(dtype).replace("torch.", ""))
            started = time.perf_counter()
            if s.sd_is_sdxl:
                pipe = StableDiffusionXLPipeline.from_single_file(
                    str(path), torch_dtype=dtype, add_watermarker=False
                )
            else:
                pipe = StableDiffusionPipeline.from_single_file(str(path), torch_dtype=dtype)
            # Euler a is the usual sampler for anime checkpoints, and it stays stable with
            # MPS + fp16, where DPM-Solver SDE, attention slicing and VAE tiling give NaN (black)
            # images.
            pipe.scheduler = EulerAncestralDiscreteScheduler.from_config(pipe.scheduler.config)
            pipe = pipe.to(device)
            load_loras(pipe, s.lora_dir, s.lora_spec)
        except Exception as exc:
            raise ModelLoadError(f"Could not load the image model {path.name}: {exc}") from exc
        log.info("Image model ready in %.0f s", time.perf_counter() - started)
        return pipe


def resolve_device(requested: str) -> str:
    """Map ``auto`` to the best available device; fall back to the CPU if one is unavailable."""
    import torch

    cuda = torch.cuda.is_available()
    mps = torch.backends.mps.is_available()
    if requested == "auto":
        return "cuda" if cuda else "mps" if mps else "cpu"
    if (requested == "cuda" and not cuda) or (requested == "mps" and not mps):
        log.warning("%s is not available, falling back to the CPU (slow)", requested.upper())
        return "cpu"
    return requested


def fit_to_token_limit(
    tags: Sequence[str], tokenizers: Sequence[Any], limit: int = CLIP_TOKEN_LIMIT
) -> list[str]:
    """Drop tags from the end until the joined prompt fits ``limit`` tokens in every tokenizer.

    Tags come ordered by importance, so this keeps the important ones, where CLIP's own
    truncation would cut the prompt in the middle of a tag.
    """
    kept = list(tags)

    def too_long() -> bool:
        text = ", ".join(kept)
        return any(
            len(tok(text, add_special_tokens=False)["input_ids"]) > limit for tok in tokenizers
        )

    while kept and too_long():
        kept.pop()
    return kept


def parse_lora_spec(spec: str) -> list[tuple[str, float]]:
    """Parse ``"a.safetensors:0.8, b.safetensors"`` into ``[("a.safetensors", 0.8),
    ("b.safetensors", 1.0)]``. A missing weight means 1.0."""
    loras = []
    for item in spec.split(","):
        item = item.strip()
        if not item:
            continue
        name, weight = item, 1.0
        head, sep, tail = item.rpartition(":")
        if sep:
            try:
                name, weight = head.strip(), float(tail)
            except ValueError:
                pass  # no weight given; the colon belongs to the path (C:\...)
        loras.append((name, weight))
    return loras


def load_loras(pipe: Any, lora_dir: Path, spec: str) -> None:
    """Load the LoRAs listed in ``spec``. Missing or broken files are skipped with a warning."""
    adapters, weights = [], []
    for i, (name, weight) in enumerate(parse_lora_spec(spec)):
        path = lora_dir / name  # an absolute name replaces lora_dir
        if not path.is_file():
            log.warning("LoRA not found, skipping: %s", path)
            continue
        adapter = f"lora{i}"
        try:
            pipe.load_lora_weights(str(path.parent), weight_name=path.name, adapter_name=adapter)
        except Exception as exc:  # one broken LoRA shouldn't stop the model from loading
            log.warning("Could not load LoRA %s: %s", path.name, exc)
            continue
        adapters.append(adapter)
        weights.append(weight)
        log.info("Loaded LoRA %s (weight %g)", path.name, weight)
    if adapters:
        pipe.set_adapters(adapters, adapter_weights=weights)
