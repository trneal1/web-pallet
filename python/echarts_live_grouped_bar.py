"""Rolling Linux server performance dashboard for the web pallet.

Requires psutil (``python -m pip install psutil``), a running ``bridge.py``,
and pallet.html connected to the bridge. Application telemetry is optional;
``--service-url`` may point to JSON containing request_rate, latency_p95_ms,
error_rate_pct, and queue_depth.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import time
from pathlib import Path
from typing import Any, Callable
from urllib.request import urlopen

try:
    import psutil
except ImportError as exc:
    raise SystemExit("Install psutil first: python -m pip install psutil") from exc

from echarts_graph_lib import EChartsPallet
from pallet import DEFAULT_BRIDGE_HOST, DEFAULT_BRIDGE_PORT


PAGE = "linux-performance"
GIB = 1024**3


def read_key_values(path: str) -> dict[str, int]:
    """Read whitespace-separated Linux counter files such as /proc/vmstat."""
    result: dict[str, int] = {}
    try:
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            fields = line.replace(":", "").split()
            if len(fields) >= 2 and fields[1].isdigit():
                result[fields[0]] = int(fields[1])
    except (OSError, ValueError):
        pass
    return result


def pressure_values(resource: str) -> dict[str, float | None]:
    values: dict[str, float | None] = {"Some": None, "Full": None}
    try:
        for line in Path(f"/proc/pressure/{resource}").read_text().splitlines():
            fields = line.split()
            label = fields[0].title()
            if label in values:
                averages = dict(field.split("=", 1) for field in fields[1:])
                values[label] = float(averages["avg10"])
    except (OSError, ValueError, KeyError):
        pass
    return values


def tcp_retransmits() -> int:
    """Return the cumulative TCP RetransSegs counter from /proc/net/snmp."""
    try:
        lines = Path("/proc/net/snmp").read_text().splitlines()
        for index in range(0, len(lines) - 1, 2):
            names, values = lines[index].split(), lines[index + 1].split()
            if names[0] == "Tcp:" and values[0] == "Tcp:":
                return int(dict(zip(names[1:], values[1:]))["RetransSegs"])
    except (OSError, ValueError, KeyError):
        pass
    return 0


def failed_systemd_units() -> int | None:
    """Count failed systemd units without invoking systemctl every second."""
    directory = Path("/run/systemd/system")
    if not directory.exists():
        return None
    try:
        # systemd records failed unit state in runtime unit files/directories,
        # but D-Bus is the authoritative source. Report no value if unavailable.
        import subprocess

        completed = subprocess.run(
            ["systemctl", "--failed", "--no-legend", "--plain"],
            capture_output=True,
            text=True,
            timeout=1,
            check=False,
        )
        return len([line for line in completed.stdout.splitlines() if line.strip()])
    except (OSError, subprocess.SubprocessError):
        return None


def command_line_count(command: list[str], prefix: str | None = None) -> int | None:
    """Count nonblank output lines, returning no value when a tool is unavailable."""
    try:
        import subprocess

        completed = subprocess.run(
            command, capture_output=True, text=True, timeout=2, check=False
        )
        if completed.returncode not in (0, 1):
            return None
        lines = [line for line in completed.stdout.splitlines() if line.strip()]
        if prefix is not None:
            lines = [line for line in lines if line.startswith(prefix)]
        return len(lines)
    except (OSError, subprocess.SubprocessError):
        return None


class LinuxSampler:
    def __init__(self, service_url: str | None) -> None:
        self.service_url = service_url
        self.previous_time = time.monotonic()
        self.previous_disk = psutil.disk_io_counters()
        self.previous_net = psutil.net_io_counters(pernic=True)
        self.previous_ctx = psutil.cpu_stats().ctx_switches
        self.previous_retransmits = tcp_retransmits()
        self.previous_oom = read_key_values("/proc/vmstat").get("oom_kill", 0)
        self.last_systemd_check = 0.0
        self.systemd_failed: int | None = None
        self.kernel_errors: int | None = None
        self.reboots: int | None = None
        psutil.cpu_percent(interval=None, percpu=True)
        for process in psutil.process_iter():
            try:
                process.cpu_percent(interval=None)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

        self.interfaces = sorted(
            name
            for name, stats in psutil.net_if_stats().items()
            if stats.isup and name != "lo"
        ) or ["lo"]
        self.mounts = []
        seen: set[str] = set()
        for partition in psutil.disk_partitions(all=False):
            if partition.mountpoint not in seen:
                seen.add(partition.mountpoint)
                self.mounts.append(partition.mountpoint)

    def _service_metrics(self) -> dict[str, float | None]:
        output = {"Requests/s": None, "P95 latency (ms)": None,
                  "Error rate (%)": None, "Queue depth": None}
        if not self.service_url:
            return output
        try:
            with urlopen(self.service_url, timeout=0.75) as response:
                data = json.load(response)
            mapping = {
                "Requests/s": "request_rate",
                "P95 latency (ms)": "latency_p95_ms",
                "Error rate (%)": "error_rate_pct",
                "Queue depth": "queue_depth",
            }
            for label, key in mapping.items():
                if data.get(key) is not None:
                    output[label] = float(data[key])
        except (OSError, ValueError, TypeError):
            pass
        return output

    @staticmethod
    def _temperatures() -> dict[str, float | None]:
        readings: list[float] = []
        try:
            for sensors in psutil.sensors_temperatures().values():
                readings.extend(item.current for item in sensors if item.current is not None)
        except (AttributeError, OSError):
            pass
        return {
            "Average": sum(readings) / len(readings) if readings else None,
            "Maximum": max(readings) if readings else None,
        }

    def sample(self) -> tuple[dict[str, dict[str, float | None]], list[tuple[str, float, float]]]:
        now = time.monotonic()
        elapsed = max(now - self.previous_time, 0.001)
        cpu_times = psutil.cpu_times_percent(interval=None)
        core_loads = psutil.cpu_percent(interval=None, percpu=True)
        memory = psutil.virtual_memory()
        swap = psutil.swap_memory()
        disk = psutil.disk_io_counters()
        net = psutil.net_io_counters(pernic=True)
        ctx = psutil.cpu_stats().ctx_switches

        metrics: dict[str, dict[str, float | None]] = {}
        metrics["cpu-cores"] = {f"Core {i}": value for i, value in enumerate(core_loads)}
        metrics["cpu-modes"] = {
            "User": getattr(cpu_times, "user", 0.0),
            "System": getattr(cpu_times, "system", 0.0),
            "I/O wait": getattr(cpu_times, "iowait", 0.0),
            "Steal": getattr(cpu_times, "steal", 0.0),
        }
        load1, load5, load15 = os.getloadavg()
        cpu_count = psutil.cpu_count() or 1
        metrics["load"] = {
            "1 minute": load1 / cpu_count * 100,
            "5 minutes": load5 / cpu_count * 100,
            "15 minutes": load15 / cpu_count * 100,
        }
        metrics["memory"] = {
            "Used": memory.percent,
            "Available": memory.available / memory.total * 100,
            "Cache": getattr(memory, "cached", 0) / memory.total * 100,
            "Swap": swap.percent,
        }
        metrics["psi"] = {
            f"CPU {key}": value for key, value in pressure_values("cpu").items()
        } | {
            f"Memory {key}": value for key, value in pressure_values("memory").items()
        } | {
            f"I/O {key}": value for key, value in pressure_values("io").items()
        }

        if disk and self.previous_disk:
            reads = disk.read_count - self.previous_disk.read_count
            writes = disk.write_count - self.previous_disk.write_count
            metrics["disk-rate"] = {
                "Read MiB/s": (disk.read_bytes - self.previous_disk.read_bytes) / elapsed / 2**20,
                "Write MiB/s": (disk.write_bytes - self.previous_disk.write_bytes) / elapsed / 2**20,
                "Reads/s": reads / elapsed,
                "Writes/s": writes / elapsed,
            }
            metrics["disk-latency"] = {
                "Read latency (ms)": (disk.read_time - self.previous_disk.read_time) / reads if reads else 0,
                "Write latency (ms)": (disk.write_time - self.previous_disk.write_time) / writes if writes else 0,
                "Queue depth": max(0.0, (getattr(disk, "weighted_io", 0) -
                                          getattr(self.previous_disk, "weighted_io", 0)) /
                                   (elapsed * 1000)),
                "Busy (%)": min(100.0, max(0.0, (getattr(disk, "busy_time", 0) -
                                                   getattr(self.previous_disk, "busy_time", 0)) /
                                             (elapsed * 10))),
            }
        else:
            metrics["disk-rate"] = {name: None for name in ("Read MiB/s", "Write MiB/s", "Reads/s", "Writes/s")}
            metrics["disk-latency"] = {name: None for name in ("Read latency (ms)", "Write latency (ms)", "Queue depth", "Busy (%)")}

        metrics["filesystems"] = {}
        for mount in self.mounts:
            try:
                usage = psutil.disk_usage(mount)
                metrics["filesystems"][f"Space {mount}"] = usage.percent
                stats = os.statvfs(mount)
                inode_total = stats.f_files
                metrics["filesystems"][f"Inodes {mount}"] = (
                    (inode_total - stats.f_ffree) / inode_total * 100 if inode_total else None
                )
            except (OSError, PermissionError):
                metrics["filesystems"][f"Space {mount}"] = None
                metrics["filesystems"][f"Inodes {mount}"] = None

        metrics["network-rate"] = {}
        drops = errors = 0
        for interface in self.interfaces:
            current, previous = net.get(interface), self.previous_net.get(interface)
            if current and previous:
                metrics["network-rate"][f"Rx {interface}"] = (current.bytes_recv - previous.bytes_recv) * 8 / elapsed / 1_000_000
                metrics["network-rate"][f"Tx {interface}"] = (current.bytes_sent - previous.bytes_sent) * 8 / elapsed / 1_000_000
                drops += current.dropin - previous.dropin + current.dropout - previous.dropout
                errors += current.errin - previous.errin + current.errout - previous.errout

        retransmits = tcp_retransmits()
        connections = []
        try:
            connections = psutil.net_connections(kind="tcp")
        except (psutil.AccessDenied, OSError):
            pass
        metrics["network-health"] = {
            "Drops/s": max(0, drops) / elapsed,
            "Errors/s": max(0, errors) / elapsed,
            "Retransmits/s": max(0, retransmits - self.previous_retransmits) / elapsed,
            "Established TCP": sum(connection.status == psutil.CONN_ESTABLISHED for connection in connections),
        }

        process_counts = {"Running": 0.0, "Sleeping": 0.0, "Blocked": 0.0}
        top_processes: list[tuple[str, float, float]] = []
        for process in psutil.process_iter(["pid", "name", "status", "memory_percent"]):
            try:
                status = process.info["status"]
                if status == psutil.STATUS_RUNNING:
                    process_counts["Running"] += 1
                elif status == psutil.STATUS_DISK_SLEEP:
                    process_counts["Blocked"] += 1
                elif status == psutil.STATUS_SLEEPING:
                    process_counts["Sleeping"] += 1
                top_processes.append((
                    f"{process.info['name'] or '?'} ({process.info['pid']})",
                    process.cpu_percent(interval=None),
                    float(process.info["memory_percent"] or 0),
                ))
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        process_counts["Context switches/s"] = (ctx - self.previous_ctx) / elapsed
        metrics["processes"] = process_counts

        vmstat = read_key_values("/proc/vmstat")
        oom = vmstat.get("oom_kill", self.previous_oom)
        if now - self.last_systemd_check >= 30:
            self.systemd_failed = failed_systemd_units()
            self.kernel_errors = command_line_count(
                ["journalctl", "-k", "-p", "err", "--no-pager", "--output=cat"]
            )
            self.reboots = command_line_count(
                ["last", "-x", "reboot", "--time-format", "iso"], prefix="reboot"
            )
            self.last_systemd_check = now
        metrics["health"] = {
            "OOM kills": float(oom),
            "OOM kills/s": max(0, oom - self.previous_oom) / elapsed,
            "Failed services": self.systemd_failed,
            "Kernel errors": self.kernel_errors,
            "Recorded reboots": self.reboots,
            "Uptime (days)": (time.time() - psutil.boot_time()) / 86400,
        }
        metrics["temperature"] = self._temperatures()
        metrics["service"] = self._service_metrics()

        self.previous_time, self.previous_disk, self.previous_net = now, disk, net
        self.previous_ctx, self.previous_retransmits, self.previous_oom = ctx, retransmits, oom
        top_processes.sort(key=lambda item: max(item[1], item[2]), reverse=True)
        return metrics, top_processes[:10]


def axis(minimum: float | None = 0, maximum: float | None = None) -> dict[str, Any]:
    value: dict[str, Any] = {"type": "value"}
    if minimum is not None:
        value["min"] = minimum
    if maximum is not None:
        value["max"] = maximum
    return {"yAxis": value}


def main() -> None:
    parser = argparse.ArgumentParser(description="Rolling Linux server performance dashboard")
    parser.add_argument("host", nargs="?", default=None, help="bridge TCP host")
    parser.add_argument("--bridge-host", default=DEFAULT_BRIDGE_HOST)
    parser.add_argument("--bridge-port", type=int, default=DEFAULT_BRIDGE_PORT)
    parser.add_argument("--port", type=int, default=None, help="alias for --bridge-port")
    parser.add_argument("--timeout", type=float, default=5.0)
    parser.add_argument("--interval", type=float, default=2.0, help="seconds between samples")
    parser.add_argument("--points", type=int, default=60, help="samples per rolling chart")
    parser.add_argument("--service-url", help="optional application telemetry JSON URL")
    args = parser.parse_args()
    if platform.system() != "Linux":
        parser.error("this dashboard reads Linux /proc metrics and must run on Linux")
    if args.interval <= 0 or args.points < 2:
        parser.error("--interval must be positive and --points must be at least 2")

    sampler = LinuxSampler(args.service_url)
    first, top_processes = sampler.sample()
    host = args.host or args.bridge_host
    port = args.port if args.port is not None else args.bridge_port
    pallet = EChartsPallet(host=host, port=port)
    pallet.start(timeout=args.timeout)
    pallet.clear(color="#0f172a", page=PAGE)

    chart_specs: list[tuple[str, str, str, dict[str, Any]]] = [
        ("cpu-cores", "CPU cores", "Utilization (%)", axis(0, 100)),
        ("cpu-modes", "CPU modes", "CPU time (%)", axis(0, 100)),
        ("load", "Normalized load average", "CPU capacity (%)", axis(0)),
        ("memory", "Memory and swap", "Capacity (%)", axis(0, 100)),
        ("psi", "Linux pressure (10-second average)", "Stalled time (%)", axis(0)),
        ("disk-rate", "Disk throughput and operations", "Rate", axis(0)),
        ("disk-latency", "Disk latency, queue, and utilization", "Value", axis(0)),
        ("filesystems", "Filesystem space and inodes", "Used (%)", axis(0, 100)),
        ("network-rate", "Network throughput by interface", "Mbit/s", axis(0)),
        ("network-health", "Network health and TCP", "Count / rate", axis(0)),
        ("processes", "Process activity", "Count / rate", axis(0)),
        ("temperature", "Hardware temperatures", "Degrees Celsius", axis(None)),
        ("health", "Host health and uptime", "Value", axis(0)),
        ("service", "Application service telemetry", "Value", axis(0)),
    ]
    charts: dict[str, Any] = {}
    width, height, gap = 720, 330, 18
    for index, (chart_id, title, units, extra) in enumerate(chart_specs):
        charts[chart_id] = pallet.live_time_chart(
            id=chart_id,
            x=18 + (index % 2) * (width + gap),
            y=18 + (index // 2) * (height + gap),
            width=width,
            height=height,
            title=title,
            y_axis_name=units,
            series={name: ("bar" if chart_id == "cpu-cores" else "line") for name in first[chart_id]},
            max_points=args.points,
            page=PAGE,
            group="linux-performance",
            extra_option=extra,
        )

    top_id = "top-processes"
    top_index = len(chart_specs)
    pallet.chart(
        id=top_id,
        x=18 + (top_index % 2) * (width + gap),
        y=18 + (top_index // 2) * (height + gap),
        width=width,
        height=height,
        title="Current top processes",
        page=PAGE,
        option={
            "legend": {"top": 34},
            "tooltip": {"trigger": "axis"},
            "grid": {"left": 180, "right": 35, "top": 80, "bottom": 35},
            "xAxis": {"type": "value", "name": "%"},
            "yAxis": {"type": "category", "inverse": True,
                      "data": [item[0] for item in top_processes]},
            "series": [
                {"name": "CPU %", "type": "bar", "data": [item[1] for item in top_processes]},
                {"name": "Memory %", "type": "bar", "data": [item[2] for item in top_processes]},
            ],
        },
    )
    pallet.show_page(PAGE)
    print(f"Monitoring {platform.node()} on page {PAGE!r}; press Ctrl+C to stop.")

    try:
        while True:
            time.sleep(args.interval)
            timestamp = int(time.time() * 1000)
            metrics, top_processes = sampler.sample()
            for chart_id, chart in charts.items():
                chart.append(timestamp, metrics[chart_id])
            pallet.set_option(
                top_id,
                {
                    "yAxis": {"data": [item[0] for item in top_processes]},
                    "series": [
                        {"name": "CPU %", "data": [item[1] for item in top_processes]},
                        {"name": "Memory %", "data": [item[2] for item in top_processes]},
                    ],
                },
                coalesce=True,
                page=PAGE,
            )
    except KeyboardInterrupt:
        print("Stopping Linux performance monitor.")
    finally:
        pallet.stop()


if __name__ == "__main__":
    main()
