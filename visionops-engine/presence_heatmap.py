"""Temporal presence heatmap from person foot-points."""

from __future__ import annotations

from typing import Iterable

import numpy as np

from roi_manager import Detection


class PresenceHeatmap:
    """
    Accumulate person foot points into a coarse grid with exponential decay.

    Grid coordinates are normalized to the source frame (0..cols-1 / 0..rows-1).
    """

    def __init__(
        self,
        cols: int = 64,
        rows: int = 36,
        decay: float = 0.985,
        splat: float = 1.0,
        min_emit: float = 0.08,
        max_cells: int = 400,
    ) -> None:
        self.cols = max(8, int(cols))
        self.rows = max(8, int(rows))
        self.decay = float(decay)
        self.splat = float(splat)
        self.min_emit = float(min_emit)
        self.max_cells = max(32, int(max_cells))
        self._grid = np.zeros((self.rows, self.cols), dtype=np.float32)

    def reset(self) -> None:
        self._grid.fill(0.0)

    def update(
        self,
        detections: Iterable[Detection],
        *,
        frame_width: int,
        frame_height: int,
        class_name: str = "person",
    ) -> None:
        if frame_width <= 0 or frame_height <= 0:
            return
        self._grid *= self.decay
        for det in detections:
            if det.class_name != class_name:
                continue
            fx, fy = det.foot_point
            cx = int((fx / frame_width) * self.cols)
            cy = int((fy / frame_height) * self.rows)
            cx = max(0, min(self.cols - 1, cx))
            cy = max(0, min(self.rows - 1, cy))
            # Soft 3x3 splat
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    x = cx + dx
                    y = cy + dy
                    if 0 <= x < self.cols and 0 <= y < self.rows:
                        weight = self.splat if dx == 0 and dy == 0 else self.splat * 0.35
                        self._grid[y, x] += weight

    def snapshot(self) -> dict:
        peak = float(self._grid.max()) if self._grid.size else 0.0
        if peak <= 1e-6:
            return {
                "cols": self.cols,
                "rows": self.rows,
                "peak": 0.0,
                "cells": [],
            }
        ys, xs = np.where(self._grid >= self.min_emit * peak)
        values = self._grid[ys, xs]
        order = np.argsort(values)[::-1][: self.max_cells]
        cells = [
            [int(xs[i]), int(ys[i]), round(float(values[i] / peak), 3)]
            for i in order
        ]
        return {
            "cols": self.cols,
            "rows": self.rows,
            "peak": round(peak, 3),
            "cells": cells,
        }
