"""Generate the storyboard of one chapter through the HTTP API and download the images.

Start the server first (``./run.sh``), then:

    python examples/api_client.py examples/novels/lantern-keeper.en.txt --out storyboard/
    python examples/api_client.py examples/novels/snow-night.zh.txt --chapter 3 --max-scenes 2 \\
        --style "ink wash painting, monochrome" --seed 42

Only needs ``httpx``, so it also works from another machine (``--server http://host:8000``).
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Iterator, Tuple

import httpx


def iter_sse(response: httpx.Response) -> Iterator[Tuple[str, dict]]:
    """Yield (event type, data) pairs from a Server-Sent Events response."""
    event, data = "message", []
    for line in response.iter_lines():
        if line.startswith("event:"):
            event = line[len("event:") :].strip()
        elif line.startswith("data:"):
            data.append(line[len("data:") :].strip())
        elif not line and data:  # a blank line ends the event
            yield event, json.loads("\n".join(data))
            event, data = "message", []


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate one chapter through the HTTP API.")
    parser.add_argument("novel", type=Path, help="text file with one or more chapters")
    parser.add_argument("--chapter", type=int, default=1, help="chapter number, from 1")
    parser.add_argument("--max-scenes", type=int, default=3, help="default: %(default)s")
    parser.add_argument("--style", default="", help="style description to merge into the prompts")
    parser.add_argument("--seed", type=int, help="scene i uses seed + i (default: random)")
    parser.add_argument("--server", default="http://127.0.0.1:8000", help="default: %(default)s")
    parser.add_argument("--out", type=Path, help="save the images into this directory")
    args = parser.parse_args()

    payload = {
        "text": args.novel.read_text(encoding="utf-8"),
        "chapter_index": args.chapter - 1,
        "style": args.style,
        "max_scenes": args.max_scenes,
        "seed": args.seed,
    }
    started = time.monotonic()
    failed = False
    # No read timeout: planning a long chapter or loading the model can take minutes.
    with httpx.Client(base_url=args.server, timeout=httpx.Timeout(10.0, read=None)) as client:
        with client.stream("POST", "/api/generate", json=payload) as response:
            if response.status_code != 200:
                response.read()
                print(f"HTTP {response.status_code}: {response.text}", file=sys.stderr)
                return 1
            for event, data in iter_sse(response):
                clock = f"[{time.monotonic() - started:6.1f}s]"
                if event == "chapter":
                    title = data["title"] or "(untitled)"
                    print(f"{clock} {title} (chapter {data['index'] + 1}/{data['total']})")
                elif event == "status":
                    print(f"{clock} {data['message']}")
                elif event == "scenes":
                    for number, scene in enumerate(data["scenes"], 1):
                        print(f"{clock}   {number}. {scene['summary']}")
                        print(f"{'':12}{scene['prompt']}")
                elif event == "image":
                    number = data["scene_index"] + 1
                    url = args.server + data["url"]
                    print(f"{clock} image {number}: {url} (seed {data['seed']})")
                    if args.out:
                        args.out.mkdir(parents=True, exist_ok=True)
                        target = args.out / f"chapter{args.chapter:02d}-scene{number:02d}.png"
                        target.write_bytes(client.get(data["url"]).content)
                        print(f"{clock}   saved {target}")
                elif event == "error":
                    failed = True
                    print(f"{clock} error: {data['message']}")
                elif event == "done":
                    print(f"{clock} done")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
