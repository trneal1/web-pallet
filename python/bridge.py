import asyncio
import argparse
import json
import websockets

web_clients = {}
tcp_event_queues = set()
DEFAULT_LISTEN_HOST = "0.0.0.0"
DEFAULT_WEBSOCKET_PORT = 8080
DEFAULT_TCP_PORT = 9000
DEFAULT_TCP_LIMIT = 16 * 1024 * 1024
WEBSOCKET_SEND_TIMEOUT = 5.0

async def websocket_handler(websocket):
    web_clients[websocket] = {}
    print("Web app connected")
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

            if len(web_clients) == 0:
                await write_json_line(writer, lock, {"status": "no_web_clients"})
                continue

            await broadcast(command)

            await write_json_line(writer, lock, {
                "status": "ok",
                "web_clients": len(web_clients)
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

    if not connected:
        writer.close()
        await writer.wait_closed()
        return

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

async def main(host, websocket_port, tcp_port, tcp_limit):
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

    async with ws_server, tcp_server:
        await asyncio.Future()

def parse_args():
    parser = argparse.ArgumentParser(description="Bridge TCP drawing clients to browser WebSocket clients")
    parser.add_argument("--host", default=DEFAULT_LISTEN_HOST, help="IP/interface to listen on")
    parser.add_argument("--websocket-port", type=int, default=DEFAULT_WEBSOCKET_PORT, help="browser WebSocket port")
    parser.add_argument("--tcp-port", type=int, default=DEFAULT_TCP_PORT, help="Python drawing TCP port")
    parser.add_argument("--tcp-limit", type=int, default=DEFAULT_TCP_LIMIT, help="maximum bytes per TCP JSON line")
    return parser.parse_args()

if __name__ == "__main__":
    args = parse_args()
    asyncio.run(main(args.host, args.websocket_port, args.tcp_port, args.tcp_limit))
