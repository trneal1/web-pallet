#!/usr/bin/env python3
"""
pallet.py
=========
Small drawing client for ``pallet.html`` through ``bridge.py``.

Run ``bridge.py`` first, open ``pallet.html`` in a browser, then connect this
client to the bridge TCP port. Each drawing primitive is sent as one JSON line.
"""
from __future__ import annotations

import json
import os
import socket
from typing import Any, Iterable, Optional

DEFAULT_BRIDGE_HOST = os.environ.get("PALLET_BRIDGE_HOST", "127.0.0.1")
DEFAULT_BRIDGE_PORT = int(os.environ.get("PALLET_BRIDGE_PORT", "9000"))
DEFAULT_WIDTH = 960
DEFAULT_HEIGHT = 540


class Pallet:
    """TCP drawing client for the browser pallet.

    The method names intentionally mirror the ESP TFT terminal primitives so
    existing graph code is easy to port.
    """

    def __init__(
        self,
        host: str = DEFAULT_BRIDGE_HOST,
        port: int = DEFAULT_BRIDGE_PORT,
        *,
        width: Optional[int] = None,
        height: Optional[int] = None,
        timeout: float = 5.0,
        wait_for_ack: bool = True,
    ) -> None:
        self.host = host
        self.port = port
        self.width = width if width is not None else DEFAULT_WIDTH
        self.height = height if height is not None else DEFAULT_HEIGHT
        self._auto_width = width is None
        self._auto_height = height is None
        self.timeout = timeout
        self.wait_for_ack = wait_for_ack
        self.browser_status: dict[str, Any] = {}
        self.canvas_width: Optional[int] = None
        self.canvas_height: Optional[int] = None
        self.css_width: Optional[int] = None
        self.css_height: Optional[int] = None
        self.max_css_width: Optional[int] = None
        self.max_css_height: Optional[int] = None
        self.screen_width: Optional[int] = None
        self.screen_height: Optional[int] = None
        self.screen_avail_width: Optional[int] = None
        self.screen_avail_height: Optional[int] = None
        self.device_pixel_ratio: Optional[float] = None
        self._sock: Optional[socket.socket] = None
        self._file = None
        self._batch: Optional[list[dict[str, Any]]] = None

    @classmethod
    def for_bridge(
        cls,
        host: str = DEFAULT_BRIDGE_HOST,
        port: int = DEFAULT_BRIDGE_PORT,
        **kwargs: Any,
    ) -> "Pallet":
        return cls(host, port, **kwargs)

    def __enter__(self) -> "Pallet":
        self.connect()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def connect(self) -> dict[str, Any]:
        if self._sock is not None:
            return {"status": "already_connected"}

        try:
            self._sock = socket.create_connection((self.host, self.port), self.timeout)
        except OSError as exc:
            raise ConnectionError(
                f"could not connect to bridge TCP server at {self.host}:{self.port}: {exc}"
            ) from exc
        self._file = self._sock.makefile("r", encoding="utf-8", newline="\n")
        hello = self._read_response()
        if hello.get("status") == "no_web_clients":
            self.close()
            raise ConnectionError("bridge is running, but no browser pallet is connected")
        self._apply_browser_status(hello)
        return hello

    def status(self) -> dict[str, Any]:
        response = self.command({"type": "__pallet_get_status"})
        self._apply_browser_status(response)
        return response

    def _apply_browser_status(self, status: dict[str, Any]) -> None:
        self.browser_status = status
        self.canvas_width = self._positive_int(status.get("canvas_width"))
        self.canvas_height = self._positive_int(status.get("canvas_height"))
        self.css_width = self._positive_int(status.get("css_width"))
        self.css_height = self._positive_int(status.get("css_height"))
        self.max_css_width = self._positive_int(status.get("max_css_width"))
        self.max_css_height = self._positive_int(status.get("max_css_height"))
        self.screen_width = self._positive_int(status.get("screen_width"))
        self.screen_height = self._positive_int(status.get("screen_height"))
        self.screen_avail_width = self._positive_int(status.get("screen_avail_width"))
        self.screen_avail_height = self._positive_int(status.get("screen_avail_height"))
        self.device_pixel_ratio = status.get("device_pixel_ratio")

        logical_width = self.css_width or self.canvas_width
        logical_height = self.css_height or self.canvas_height
        if self._auto_width and logical_width:
            self.width = logical_width
        if self._auto_height and logical_height:
            self.height = logical_height

    @staticmethod
    def _positive_int(value: Any) -> Optional[int]:
        if isinstance(value, (int, float)) and value > 0:
            return round(value)
        return None

    def close(self) -> None:
        if self._file is not None:
            self._file.close()
            self._file = None
        if self._sock is not None:
            self._sock.close()
            self._sock = None

    def command(self, command: dict[str, Any]) -> dict[str, Any]:
        if self._batch is not None:
            self._batch.append(command)
            return {"status": "queued"}

        if self._sock is None:
            self.connect()

        assert self._sock is not None
        payload = json.dumps(command, separators=(",", ":")).encode("utf-8") + b"\n"
        self._sock.sendall(payload)
        return self._read_response() if self.wait_for_ack else {"status": "sent"}

    def commands(self, commands: Iterable[dict[str, Any]]) -> dict[str, Any]:
        if self._sock is None:
            self.connect()

        assert self._sock is not None
        payload = json.dumps(list(commands), separators=(",", ":")).encode("utf-8") + b"\n"
        self._sock.sendall(payload)
        return self._read_response() if self.wait_for_ack else {"status": "sent"}

    def begin_batch(self) -> None:
        if self._batch is not None:
            raise RuntimeError("A drawing batch is already active")
        self._batch = []

    def end_batch(self) -> dict[str, Any]:
        if self._batch is None:
            raise RuntimeError("No drawing batch is active")
        batch = self._batch
        self._batch = None
        if not batch:
            return {"status": "empty"}
        return self.commands(batch)

    def _read_response(self) -> dict[str, Any]:
        if self._file is None:
            return {}
        line = self._file.readline()
        if not line:
            raise ConnectionError("bridge closed the TCP connection")
        return json.loads(line)

    def clear(self, color: str = "white") -> dict[str, Any]:
        return self.command({"type": "clear", "color": color})

    def fill_screen(self, color: str = "white") -> dict[str, Any]:
        return self.clear(color)

    def line(self, x1: float, y1: float, x2: float, y2: float, color: str = "black", width: float = 1) -> dict[str, Any]:
        return self.command({
            "type": "line",
            "x1": round(x1),
            "y1": round(y1),
            "x2": round(x2),
            "y2": round(y2),
            "color": color,
            "width": width,
        })

    def hline(self, x: float, y: float, length: float, color: str = "black", width: float = 1) -> dict[str, Any]:
        return self.line(x, y, x + length - 1, y, color, width)

    def vline(self, x: float, y: float, length: float, color: str = "black", width: float = 1) -> dict[str, Any]:
        return self.line(x, y, x, y + length - 1, color, width)

    def rect(self, x: float, y: float, width: float, height: float, color: str = "black", line_width: float = 1) -> dict[str, Any]:
        return self.command({
            "type": "rect",
            "x": round(x),
            "y": round(y),
            "width": round(width),
            "height": round(height),
            "color": color,
            "lineWidth": line_width,
            "stroke": True,
        })

    def fill_rect(self, x: float, y: float, width: float, height: float, color: str) -> dict[str, Any]:
        return self.command({
            "type": "rect",
            "x": round(x),
            "y": round(y),
            "width": round(width),
            "height": round(height),
            "fill": color,
            "stroke": False,
        })

    def circle(self, x: float, y: float, radius: float, color: str = "black", line_width: float = 1) -> dict[str, Any]:
        return self.command({
            "type": "circle",
            "x": round(x),
            "y": round(y),
            "radius": round(radius),
            "color": color,
            "lineWidth": line_width,
            "stroke": True,
        })

    def fill_circle(self, x: float, y: float, radius: float, color: str) -> dict[str, Any]:
        return self.command({
            "type": "circle",
            "x": round(x),
            "y": round(y),
            "radius": round(radius),
            "fill": color,
            "stroke": False,
        })

    def text(
        self,
        x: float,
        y: float,
        text: str,
        *,
        color: str = "black",
        size: int = 1,
        font: Optional[str] = None,
    ) -> dict[str, Any]:
        px = max(8, round(12 * size))
        return self.command({
            "type": "text",
            "x": round(x),
            "y": round(y + px),
            "text": str(text),
            "color": color,
            "font": font or f"{px}px sans-serif",
        })

    def path(self, points: Iterable[tuple[float, float]], color: str = "black", width: float = 1) -> dict[str, Any]:
        return self.command({
            "type": "path",
            "points": [{"x": round(x), "y": round(y)} for x, y in points],
            "color": color,
            "width": width,
        })
