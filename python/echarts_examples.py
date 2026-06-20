"""
example_echarts_gallery_helpers.py

Demonstrates higher-level helper functions inspired by the Apache ECharts
example gallery. These helpers avoid writing most ECharts option JSON.

Run bridge.py, open pallet.html and connect it, then run:
    python echarts_examples.py

Chart commands are sent through the existing bridge TCP connection.
"""

import math
import time

from echarts_graph_lib import EChartsPallet


def main():
    pallet = EChartsPallet()
    pallet.start()
    pallet.clear(color="#0f172a")

    pallet.progress_gauge(
        id="voltage",
        x=24,
        y=24,
        width=360,
        height=320,
        title="Supply Voltage",
        name="Voltage",
        value=12.4,
        min=0,
        max=15,
        units="V",
    )

    pallet.stacked_line_chart(
        id="stacked",
        x=410,
        y=24,
        width=650,
        height=320,
        title="Stacked Area",
        x_data=["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
        series={
            "A": [120, 132, 101, 134, 90, 230, 210],
            "B": [220, 182, 191, 234, 290, 330, 310],
            "C": [150, 232, 201, 154, 190, 330, 410],
        },
    )

    pallet.doughnut_chart(
        id="donut",
        x=24,
        y=370,
        width=360,
        height=320,
        title="Power Budget",
        data=[("Logic", 42), ("RF", 28), ("Display", 18), ("Other", 12)],
    )

    pallet.heatmap_chart(
        id="heat",
        x=410,
        y=370,
        width=650,
        height=320,
        title="Channel Heatmap",
        x_labels=["T0", "T1", "T2", "T3", "T4"],
        y_labels=["CH1", "CH2", "CH3", "CH4"],
        values=[
            (0, 0, 5), (1, 0, 7), (2, 0, 3), (3, 0, 8), (4, 0, 6),
            (0, 1, 2), (1, 1, 4), (2, 1, 6), (3, 1, 5), (4, 1, 7),
            (0, 2, 8), (1, 2, 3), (2, 2, 4), (3, 2, 9), (4, 2, 5),
            (0, 3, 1), (1, 3, 6), (2, 3, 7), (3, 3, 4), (4, 3, 2),
        ],
    )

    print("Charts are displayed in pallet.html through bridge.py")
    print("Press Ctrl+C to stop.")

    t = 0
    try:
        while True:
            voltage = 12.0 + 0.6 * math.sin(t / 10.0)
            pallet.update_gauge("voltage", round(voltage, 2), name="Voltage")
            t += 1
            time.sleep(0.25)
    except KeyboardInterrupt:
        pallet.stop()


if __name__ == "__main__":
    main()
