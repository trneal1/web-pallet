import asyncio
import argparse
import json
import sys
import websockets

web_clients = {}
tcp_event_queues = set()
replay_buffer = []
DEFAULT_LISTEN_HOST = "0.0.0.0"
DEFAULT_WEBSOCKET_PORT = 8080
DEFAULT_TCP_PORT = 9000
DEFAULT_TCP_LIMIT = 16 * 1024 * 1024
DEFAULT_REPLAY_LIMIT = 10000
WEBSOCKET_SEND_TIMEOUT = 5.0
STATE_METRICS_INTERVAL_SECONDS = 10
buffer_replay_enabled = True
replay_limit = DEFAULT_REPLAY_LIMIT

IGNORED_REPLAY_TYPES = {
    "__pallet_get_status",
    "__pallet_subscribe_events",
    "__pallet_status",
    "__pallet_terminal_input",
    "__pallet_xterm_input",
    "__pallet_xterm_resize",
    "__pallet_ui_event",
    "__pallet_chart_event",
    "__pallet_script_loaded",
    "__pallet_script_error",
    "__pallet_client_disconnected",
}

CHART_DEFINE_TYPES = {"chart_define", "chart_create"}
CHART_REMOVE_TYPES = {"chart_remove", "chart_delete"}
CHART_LAYOUT_TYPES = {"chart_resize", "chart_move"}
CHART_VISIBILITY_TYPES = {"chart_show", "chart_hide"}
PAGE_SHOW_TYPES = {"__pallet_show_page", "page_show"}
PAGE_DELETE_TYPES = {"__pallet_delete_page", "page_delete"}
GROUP_REPLACE_TYPES = {"__pallet_replace_group", "group_replace"}
UI_DEFINE_TYPES = {"ui_grid", "ui_card", "ui_control", "ui_status", "ui_table"}
UI_UPDATE_TYPES = {"ui_control_update", "ui_status_update", "ui_table_update"}
TERMINAL_DEFINE_TYPES = {"terminal_define", "terminal_xterm_define"}
TERMINAL_CLEAR_TYPES = {"terminal_clear", "terminal_xterm_clear"}

async def websocket_handler(websocket):
    web_clients[websocket] = {}
    print("Web app connected")
    if buffer_replay_enabled and replay_buffer:
        await websocket.send(json.dumps(replay_buffer))
    await publish_tcp_event({
        "type": "__pallet_browser_connected",
        **browser_status(),
    })

    try:
        async for message in websocket:
            try:
                command = json.loads(message)
            except json.JSONDecodeError:
                continue

            if isinstance(command, dict) and command.get("type") == "__pallet_status":
                web_clients[websocket] = {
                    "viewport_width": command.get("viewport_width"),
                    "viewport_height": command.get("viewport_height"),
                    "content_width": command.get("content_width"),
                    "content_height": command.get("content_height"),
                    "scroll_x": command.get("scroll_x"),
                    "scroll_y": command.get("scroll_y"),
                    "buffer_width": command.get("buffer_width"),
                    "buffer_height": command.get("buffer_height"),
                    "device_pixel_ratio": command.get("device_pixel_ratio"),
                    "screen_width": command.get("screen_width"),
                    "screen_height": command.get("screen_height"),
                    "screen_avail_width": command.get("screen_avail_width"),
                    "screen_avail_height": command.get("screen_avail_height"),
                    "echarts_version": command.get("echarts_version"),
                }
            elif (
                isinstance(command, dict)
                and command.get("type") in {
                    "__pallet_terminal_input",
                    "__pallet_xterm_input",
                    "__pallet_xterm_resize",
                    "__pallet_ui_event",
                    "__pallet_chart_event",
                    "__pallet_script_loaded",
                    "__pallet_script_error",
                }
            ):
                await publish_tcp_event(command)
    finally:
        web_clients.pop(websocket, None)
        print("Web app disconnected")

async def publish_tcp_event(event):
    dead = []
    message = {
        "status": "event",
        "event": event,
    }

    for queue in list(tcp_event_queues):
        try:
            queue.put_nowait(message)
        except Exception:
            dead.append(queue)

    for queue in dead:
        tcp_event_queues.discard(queue)

async def broadcast(command):
    message = json.dumps(command)
    clients = list(web_clients)

    async def send(ws):
        try:
            await asyncio.wait_for(
                ws.send(message),
                timeout=WEBSOCKET_SEND_TIMEOUT,
            )
            return True
        except Exception:
            return False

    results = await asyncio.gather(*(send(ws) for ws in clients))
    for ws, sent in zip(clients, results):
        if not sent:
            web_clients.pop(ws, None)

def remember_for_replay(command):
    if not buffer_replay_enabled:
        return
    if isinstance(command, list):
        for item in command:
            remember_for_replay(item)
        return
    if not isinstance(command, dict):
        return

    command_type = command.get("type")
    if command_type in IGNORED_REPLAY_TYPES:
        return

    if command_type == "clear":
        forget_page(command_page_key(command))
        replay_buffer.append(command)
        trim_replay_buffer()
        return

    if command_type in PAGE_DELETE_TYPES:
        forget_page(command_page_key(command))
        trim_replay_buffer()
        return

    if command_type in PAGE_SHOW_TYPES:
        replay_buffer[:] = [item for item in replay_buffer if item.get("type") not in PAGE_SHOW_TYPES]
        replay_buffer.append(command)
        trim_replay_buffer()
        return

    if command_type in GROUP_REPLACE_TYPES:
        replace_group_state(command)
        trim_replay_buffer()
        return

    if command_type in CHART_REMOVE_TYPES:
        forget_chart(command)
        trim_replay_buffer()
        return

    if command_type in CHART_DEFINE_TYPES:
        forget_chart(command)
        replay_buffer.append(command)
        trim_replay_buffer()
        return

    if command_type == "chart_option" and command.get("coalesce") is True:
        if replace_previous_chart_option(command):
            return

    if command_type == "chart_data" and command.get("append") is not True:
        if replace_previous_chart_data(command):
            return

    if command_type in CHART_LAYOUT_TYPES:
        if replace_previous_target_command(command, CHART_LAYOUT_TYPES, chart_id, stop_types=CHART_DEFINE_TYPES):
            return

    if command_type in CHART_VISIBILITY_TYPES:
        if replace_previous_target_command(command, CHART_VISIBILITY_TYPES, chart_id, stop_types=CHART_DEFINE_TYPES):
            return

    if command_type in UI_DEFINE_TYPES:
        forget_ui_target(command)
        replay_buffer.append(command)
        trim_replay_buffer()
        return

    if command_type in UI_UPDATE_TYPES:
        if coalesce_ui_update(command):
            return

    if command_type in TERMINAL_DEFINE_TYPES:
        forget_terminal(command)
        replay_buffer.append(command)
        trim_replay_buffer()
        return

    if command_type in TERMINAL_CLEAR_TYPES:
        if coalesce_terminal_clear(command):
            return

    replay_buffer.append(command)
    trim_replay_buffer()

def trim_replay_buffer():
    if replay_limit > 0 and len(replay_buffer) > replay_limit:
        del replay_buffer[:len(replay_buffer) - replay_limit]

def coalesced_state_metrics():
    payload = json.dumps(replay_buffer, separators=(",", ":")).encode()
    return {
        "commands": len(replay_buffer),
        "json_bytes": len(payload),
        "approx_memory_bytes": approximate_deep_size(replay_buffer),
    }

def approximate_deep_size(value, seen=None):
    if seen is None:
        seen = set()

    value_id = id(value)
    if value_id in seen:
        return 0
    seen.add(value_id)

    size = sys.getsizeof(value)
    if isinstance(value, dict):
        size += sum(
            approximate_deep_size(key, seen) + approximate_deep_size(item, seen)
            for key, item in value.items()
        )
    elif isinstance(value, (list, tuple, set, frozenset)):
        size += sum(approximate_deep_size(item, seen) for item in value)
    return size

async def log_coalesced_state_metrics():
    while True:
        await asyncio.sleep(STATE_METRICS_INTERVAL_SECONDS)
        if not buffer_replay_enabled:
            print("Coalesced state disabled")
            continue

        metrics = coalesced_state_metrics()
        print(
            "Coalesced state: "
            f"{metrics['commands']} commands, "
            f"{metrics['json_bytes']} JSON bytes, "
            f"~{metrics['approx_memory_bytes']} memory bytes"
        )

def command_page_key(command):
    page = command.get("palletPage", command.get("page"))
    return None if page is None else str(page)

def same_page(first, second):
    return command_page_key(first) == command_page_key(second)

def chart_id(command):
    return str(command.get("id", "chart"))

def command_id(command, default="default"):
    return str(command.get("id", default))

def chart_series_key(command):
    return (
        command.get("seriesId"),
        command.get("seriesName"),
        command.get("seriesIndex", 0),
    )

def forget_page(page_key):
    replay_buffer[:] = [
        item for item in replay_buffer
        if command_page_key(item) != page_key
    ]

def forget_chart(command):
    page_key = command_page_key(command)
    identity = chart_id(command)
    replay_buffer[:] = [
        item for item in replay_buffer
        if not (
            command_page_key(item) == page_key
            and chart_id(item) == identity
            and item.get("type") in {
                *CHART_DEFINE_TYPES,
                *CHART_REMOVE_TYPES,
                "chart_option",
                "chart_set_option",
                "chart_data",
                "chart_append",
                "chart_resize",
                "chart_move",
                "chart_show",
                "chart_hide",
            }
        )
    ]

def forget_ui_target(command):
    page_key = command_page_key(command)
    command_type = command.get("type")
    identity = command_id(command, {
        "ui_grid": "default",
        "ui_card": "card",
        "ui_control": "control",
        "ui_status": "status",
        "ui_table": "table",
    }.get(command_type, "default"))
    related_types = {
        "ui_grid": {"ui_grid"},
        "ui_card": {"ui_card"},
        "ui_control": {"ui_control", "ui_control_update"},
        "ui_status": {"ui_status", "ui_status_update"},
        "ui_table": {"ui_table", "ui_table_update"},
    }.get(command_type, {command_type})
    replay_buffer[:] = [
        item for item in replay_buffer
        if not (
            command_page_key(item) == page_key
            and (
                item.get("type") in related_types
                and command_id(item, identity) == identity
                or command_type == "ui_card"
                and str(item.get("card", "")) == identity
            )
        )
    ]

def forget_terminal(command):
    page_key = command_page_key(command)
    identity = command_id(command)
    command_type = command.get("type")
    related_types = {
        "terminal_define": {"terminal_define", "terminal_write", "terminal_clear"},
        "terminal_xterm_define": {"terminal_xterm_define", "terminal_xterm_output", "terminal_xterm_clear", "terminal_xterm_font_size"},
    }.get(command_type, {command_type})
    replay_buffer[:] = [
        item for item in replay_buffer
        if not (
            command_page_key(item) == page_key
            and item.get("type") in related_types
            and command_id(item) == identity
        )
    ]

def replace_group_state(command):
    page_key = command_page_key(command)
    group = str(command.get("group", ""))
    if not group:
        return

    insert_at = len(replay_buffer)
    kept = []
    for item in replay_buffer:
        if command_page_key(item) == page_key and item.get("group") == group:
            if insert_at == len(replay_buffer):
                insert_at = len(kept)
            continue
        kept.append(item)

    normalized = []
    for item in command.get("commands") or []:
        if not isinstance(item, dict):
            continue
        next_item = {**item, "group": group}
        if page_key is not None and "page" not in next_item and "palletPage" not in next_item:
            next_item["page"] = page_key
        normalized.append(next_item)

    insert_at = min(insert_at, len(kept))
    replay_buffer[:] = kept[:insert_at] + normalized + kept[insert_at:]

def replace_previous_chart_option(command):
    page_key = command_page_key(command)
    identity = chart_id(command)
    for index in range(len(replay_buffer) - 1, -1, -1):
        previous = replay_buffer[index]
        if command_page_key(previous) != page_key or chart_id(previous) != identity:
            continue
        previous_type = previous.get("type")
        if previous_type in CHART_DEFINE_TYPES:
            break
        if previous_type == "chart_option" and previous.get("coalesce") is True:
            replay_buffer[index] = command
            return True
    return False

def replace_previous_chart_data(command):
    page_key = command_page_key(command)
    identity = chart_id(command)
    series_key = chart_series_key(command)
    for index in range(len(replay_buffer) - 1, -1, -1):
        previous = replay_buffer[index]
        if command_page_key(previous) != page_key or chart_id(previous) != identity:
            continue
        previous_type = previous.get("type")
        if previous_type in CHART_DEFINE_TYPES:
            break
        if previous_type == "chart_data" and chart_series_key(previous) == series_key:
            replay_buffer[index] = command
            return True
    return False

def replace_previous_target_command(command, replace_types, identity_func, *, stop_types=frozenset()):
    page_key = command_page_key(command)
    identity = identity_func(command)
    for index in range(len(replay_buffer) - 1, -1, -1):
        previous = replay_buffer[index]
        if command_page_key(previous) != page_key or identity_func(previous) != identity:
            continue
        previous_type = previous.get("type")
        if previous_type in stop_types:
            break
        if previous_type in replace_types:
            replay_buffer[index] = command
            return True
    return False

def coalesce_ui_update(command):
    command_type = command.get("type")
    if command_type == "ui_control_update":
        return coalesce_patch_update(command, "ui_control", "ui_control_update", default_id="control")
    if command_type == "ui_status_update":
        return coalesce_patch_update(command, "ui_status", "ui_status_update", default_id="status")
    if command_type == "ui_table_update":
        return coalesce_table_update(command)
    return False

def coalesce_patch_update(command, define_type, update_type, *, default_id):
    page_key = command_page_key(command)
    identity = command_id(command, default_id)
    for index in range(len(replay_buffer) - 1, -1, -1):
        previous = replay_buffer[index]
        if command_page_key(previous) != page_key or command_id(previous, default_id) != identity:
            continue
        previous_type = previous.get("type")
        if previous_type == define_type:
            replay_buffer[index] = {**previous, **command, "type": define_type, "id": identity}
            return True
        if previous_type == update_type:
            replay_buffer[index] = {**previous, **command, "type": update_type, "id": identity}
            return True
    return False

def coalesce_table_update(command):
    action = str(command.get("action", "set"))
    if action == "set":
        return coalesce_patch_update(command, "ui_table", "ui_table_update", default_id="table")
    if action == "clear":
        return replace_previous_target_command(
            command,
            {"ui_table_update"},
            lambda item: command_id(item, "table"),
            stop_types={"ui_table"},
        )
    return False

def coalesce_terminal_clear(command):
    page_key = command_page_key(command)
    identity = command_id(command)
    command_type = command.get("type")
    if command_type == "terminal_clear":
        removable = {"terminal_write", "terminal_clear"}
        stop_type = "terminal_define"
    else:
        removable = {"terminal_xterm_output", "terminal_xterm_clear"}
        stop_type = "terminal_xterm_define"

    insert_at = len(replay_buffer)
    kept = []
    removed = False
    for item in replay_buffer:
        same_target = command_page_key(item) == page_key and command_id(item) == identity
        if same_target and item.get("type") == stop_type:
            insert_at = len(kept) + 1
        if same_target and item.get("type") in removable:
            removed = True
            continue
        kept.append(item)

    if not removed:
        return False
    insert_at = min(insert_at, len(kept))
    replay_buffer[:] = kept[:insert_at] + [command] + kept[insert_at:]
    return True

def browser_status():
    clients = [
        status
        for status in web_clients.values()
        if status.get("viewport_width") and status.get("viewport_height")
    ]
    status = {
        "web_clients": len(web_clients),
        "browsers": clients,
    }
    if clients:
        status.update(clients[0])
    return status

async def write_json_line(writer, lock, payload):
    async with lock:
        writer.write(json.dumps(payload).encode() + b"\n")
        await writer.drain()

async def tcp_event_writer(writer, lock, event_queue):
    while True:
        event = await event_queue.get()
        await write_json_line(writer, lock, event)

async def tcp_reader(reader, writer, lock, addr, event_queue):
    while True:
        try:
            line = await reader.readline()
        except ValueError as e:
            await write_json_line(writer, lock, {
                "status": "error",
                "message": f"TCP message is too large for the bridge read limit: {e}"
            })
            break

        if not line:
            break

        try:
            command = json.loads(line.decode())

            if isinstance(command, dict) and command.get("type") == "__pallet_subscribe_events":
                tcp_event_queues.add(event_queue)
                await write_json_line(writer, lock, {
                    "status": "ok",
                    "events": "subscribed",
                })
                continue

            if isinstance(command, dict) and command.get("type") == "__pallet_get_status":
                await write_json_line(writer, lock, {
                    "status": "ok",
                    **browser_status(),
                })
                continue

            remember_for_replay(command)
            await broadcast(command)

            await write_json_line(writer, lock, {
                "status": "ok",
                "web_clients": len(web_clients),
                "buffered": buffer_replay_enabled,
            })

        except Exception as e:
            await write_json_line(writer, lock, {
                "status": "error",
                "message": str(e)
            })

async def tcp_handler(reader, writer):
    addr = writer.get_extra_info("peername")
    print("TCP client connected:", addr)

    connected = len(web_clients) > 0
    write_lock = asyncio.Lock()
    event_queue = asyncio.Queue()
    event_task = None

    await write_json_line(writer, write_lock, {
        "status": "connected" if connected else "no_web_clients",
        **browser_status(),
    })

    try:
        event_task = asyncio.create_task(tcp_event_writer(writer, write_lock, event_queue))
        await tcp_reader(reader, writer, write_lock, addr, event_queue)
    finally:
        tcp_event_queues.discard(event_queue)
        if event_task:
            event_task.cancel()
        if len(web_clients) > 0:
            await broadcast({
                "type": "__pallet_client_disconnected",
                "client": str(addr),
            })
        writer.close()
        try:
            await writer.wait_closed()
        finally:
            print("TCP client disconnected:", addr)

async def main(host, websocket_port, tcp_port, tcp_limit, *, buffer_replay, buffer_limit):
    global buffer_replay_enabled, replay_limit
    buffer_replay_enabled = buffer_replay
    replay_limit = buffer_limit

    ws_server = await websockets.serve(
        websocket_handler,
        host,
        websocket_port
    )

    tcp_server = await asyncio.start_server(
        tcp_handler,
        host,
        tcp_port,
        limit=tcp_limit
    )

    print(f"WebSocket server listening on ws://{host}:{websocket_port}")
    print(f"TCP server listening on {host}:{tcp_port} with {tcp_limit} byte read limit")
    print(
        "Bridge reconnect state "
        + (f"enabled ({buffer_limit} command limit)" if buffer_replay else "disabled")
    )

    metrics_task = asyncio.create_task(log_coalesced_state_metrics())

    try:
        async with ws_server, tcp_server:
            await asyncio.Future()
    finally:
        metrics_task.cancel()

def parse_args():
    parser = argparse.ArgumentParser(description="Bridge TCP drawing clients to browser WebSocket clients")
    parser.add_argument("--host", default=DEFAULT_LISTEN_HOST, help="IP/interface to listen on")
    parser.add_argument("--websocket-port", type=int, default=DEFAULT_WEBSOCKET_PORT, help="browser WebSocket port")
    parser.add_argument("--tcp-port", type=int, default=DEFAULT_TCP_PORT, help="Python drawing TCP port")
    parser.add_argument("--tcp-limit", type=int, default=DEFAULT_TCP_LIMIT, help="maximum bytes per TCP JSON line")
    parser.add_argument(
        "--buffer-replay",
        dest="buffer_replay",
        action="store_true",
        default=True,
        help="keep compact reconnect state and replay it to web pallets on reconnect (default)",
    )
    parser.add_argument(
        "--no-buffer-replay",
        dest="buffer_replay",
        action="store_false",
        help="disable bridge-side reconnect state for web pallets",
    )
    parser.add_argument(
        "--buffer-limit",
        type=int,
        default=DEFAULT_REPLAY_LIMIT,
        help="maximum compact state commands retained for reconnect replay; 0 disables the count limit",
    )
    return parser.parse_args()

if __name__ == "__main__":
    args = parse_args()
    asyncio.run(main(
        args.host,
        args.websocket_port,
        args.tcp_port,
        args.tcp_limit,
        buffer_replay=args.buffer_replay,
        buffer_limit=max(0, args.buffer_limit),
    ))
