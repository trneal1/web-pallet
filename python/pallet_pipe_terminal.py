#!/usr/bin/env python3
"""
pallet_pipe_terminal.py
=======================
Pipe text into an existing Web Pallet terminal region.

Start the bridge and connect the browser first:

    python python/bridge.py

Then define a terminal region from any pallet client, or use --define here:

    echo "hello" | python python/pallet_pipe_terminal.py --id log
    some_command | python python/pallet_pipe_terminal.py --id log --color "#86EFAC"
"""
from __future__ import annotations

import argparse
import sys

from pallet import DEFAULT_BRIDGE_HOST, DEFAULT_BRIDGE_PORT, Pallet


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Write piped stdin lines to a Web Pallet terminal region"
    )
    parser.add_argument(
        "--id",
        default="default",
        help="terminal region id to write to",
    )
    parser.add_argument(
        "--bridge-host",
        default=DEFAULT_BRIDGE_HOST,
        help="bridge TCP host or IP address",
    )
    parser.add_argument(
        "--bridge-port",
        type=int,
        default=DEFAULT_BRIDGE_PORT,
        help="bridge TCP port",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="alias for --bridge-port",
    )
    parser.add_argument(
        "--color",
        default=None,
        help="optional CSS color for written text",
    )
    parser.add_argument(
        "--page",
        default=None,
        help="pallet page to draw on",
    )
    parser.add_argument(
        "--clear",
        action="store_true",
        help="clear the terminal region before writing",
    )
    parser.add_argument(
        "--define",
        action="store_true",
        help="define the terminal region before writing",
    )
    parser.add_argument("--x", type=int, default=24, help="region x position for --define")
    parser.add_argument("--y", type=int, default=24, help="region y position for --define")
    parser.add_argument("--width", type=int, default=700, help="region width for --define")
    parser.add_argument("--height", type=int, default=300, help="region height for --define")
    parser.add_argument("--title", default="", help="region title for --define")
    parser.add_argument(
        "--background",
        default="#020617",
        help="region background color for --define",
    )
    parser.add_argument(
        "--text-color",
        default="#E5E7EB",
        help="region default text color for --define",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=5.0,
        help="bridge connection timeout in seconds",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    bridge_port = args.port if args.port is not None else args.bridge_port

    try:
        with Pallet.for_bridge(
            args.bridge_host,
            bridge_port,
            timeout=args.timeout,
            page=args.page,
        ) as pallet:
            if args.define:
                pallet.define_terminal_region(
                    args.id,
                    x=args.x,
                    y=args.y,
                    width=args.width,
                    height=args.height,
                    title=args.title,
                    background=args.background,
                    color=args.text_color,
                )

            if args.clear:
                pallet.clear_terminal(args.id)

            for line in sys.stdin:
                pallet.write_terminal(
                    args.id,
                    line.rstrip("\r\n"),
                    color=args.color,
                    newline=True,
                )
    except BrokenPipeError:
        return 0
    except Exception as exc:
        print(f"Failed: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
