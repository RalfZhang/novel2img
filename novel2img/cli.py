"""Command-line entry point: ``novel2img`` (or ``python -m novel2img``) starts the web UI."""
from __future__ import annotations

import argparse
from typing import Optional, Sequence

from . import __version__


def main(argv: Optional[Sequence[str]] = None) -> None:
    parser = argparse.ArgumentParser(
        prog="novel2img",
        description="Turn novel chapters into illustrated storyboards with a local LLM and "
        "Stable Diffusion. Settings are read from ./.env (see .env.example).",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="address to bind (default: %(default)s; 0.0.0.0 makes it reachable from your network)",
    )
    parser.add_argument("--port", type=int, default=8000, help="port (default: %(default)s)")
    parser.add_argument(
        "--reload", action="store_true", help="restart when the code changes (for development)"
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    args = parser.parse_args(argv)

    import uvicorn

    uvicorn.run(
        "novel2img.server:create_app",
        factory=True,
        host=args.host,
        port=args.port,
        reload=args.reload,
    )
