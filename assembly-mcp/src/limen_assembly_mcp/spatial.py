"""Bounded educational measures, implemented independently from textbook definitions."""
from collections import deque
import math


def _grid(grid):
    if not isinstance(grid, list) or not grid or len(grid) > 128: raise ValueError("Grid must have 1..128 rows")
    if not isinstance(grid[0], list) or not 1 <= len(grid[0]) <= 128: raise ValueError("Grid must have 1..128 columns")
    width = len(grid[0])
    for row in grid:
        if not isinstance(row, list) or len(row) != width: raise ValueError("Grid must be rectangular")
        if any(type(v) is not int or v not in (0, 1) for v in row): raise ValueError("Grid cells must be integer 0 or 1")
    return width, len(grid)


def _neighbours(x, y, width, height):
    for nx, ny in ((x-1, y), (x+1, y), (x, y-1), (x, y+1)):
        if 0 <= nx < width and 0 <= ny < height: yield nx, ny


def occupancy_connectivity(grid: list[list[int]]) -> dict:
    width, height = _grid(grid)
    occupied = {(x, y) for y, row in enumerate(grid) for x, value in enumerate(row) if value}
    remaining = set(occupied); sizes = []
    while remaining:
        start = min(remaining); remaining.remove(start); queue = deque([start]); size = 0
        while queue:
            x, y = queue.popleft(); size += 1
            for p in _neighbours(x, y, width, height):
                if p in remaining: remaining.remove(p); queue.append(p)
        sizes.append(size)
    largest = max(sizes, default=0)
    return {"evidence": "grid_measurement", "adjacency": "four_neighbour", "occupied_cells": len(occupied),
            "occupied_fraction": len(occupied)/(width*height), "component_count": len(sizes),
            "component_sizes": sorted(sizes, reverse=True), "largest_component_cells": largest,
            "largest_component_fraction": largest/len(occupied) if occupied else 0,
            "architectural_order_verified": False}


def access_paths(walkable: list[list[int]], start: list[int], destinations: list[list[int]]) -> dict:
    width, height = _grid(walkable)
    def point(p):
        if not isinstance(p, list) or len(p) != 2 or any(type(v) is not int for v in p): raise ValueError("Points must be [x,y] integer pairs")
        x, y = p
        if not (0 <= x < width and 0 <= y < height) or not walkable[y][x]: raise ValueError("Point is outside the walkable cells")
        return x, y
    origin = point(start)
    if not isinstance(destinations, list) or not 1 <= len(destinations) <= 128: raise ValueError("Supply 1..128 destinations")
    targets = [point(p) for p in destinations]
    distances = {origin: 0}; queue = deque([origin])
    while queue:
        x, y = queue.popleft()
        for p in _neighbours(x, y, width, height):
            if p not in distances and walkable[p[1]][p[0]]: distances[p] = distances[(x, y)] + 1; queue.append(p)
    rows = [{"point": list(p), "reachable": p in distances, "distance_cells": distances.get(p)} for p in targets]
    return {"evidence": "grid_measurement", "coordinate_order": "x,y", "destinations": rows,
            "reachable_fraction": sum(r["reachable"] for r in rows)/len(rows),
            "limitations": "Four-neighbour point-agent paths only; no widths, accessibility, egress or code checks."}


def resonance_decay(frequency_hz: float, quality_factor: float, seconds: float) -> dict:
    for value, name in ((frequency_hz, "frequency_hz"), (quality_factor, "quality_factor"), (seconds, "seconds")):
        if type(value) not in (float, int) or not math.isfinite(value) or value > 1e12: raise ValueError(name + " must be a finite number <= 1e12")
    if frequency_hz <= 0 or quality_factor <= 0 or seconds < 0: raise ValueError("Frequency and Q must be positive; time must be nonnegative")
    exponent = math.pi * frequency_hz * seconds / quality_factor
    return {"frequency_hz": frequency_hz, "quality_factor": quality_factor, "seconds": seconds,
            "amplitude_fraction": math.exp(-exponent), "energy_fraction": math.exp(-2*exponent),
            "evidence": "analytical_assumption", "measured": False,
            "limitations": "Ideal single-mode free decay with a supplied Q. No material, joint, support, room or audibility model."}
