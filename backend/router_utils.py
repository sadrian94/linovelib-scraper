"""Shared utilities for bilinovel and bilimanga routers."""

from __future__ import annotations

from typing import Optional, Union


def parse_volume_input(volume_no: str) -> Optional[Union[int, list[int]]]:
    """Parse user volume input into a single volume number or list of volumes.

    Returns:
        An int for a single volume, a list[int] for a range/comma list,
        or None if the input is empty (meaning query only).
        Raises ValueError on invalid input.
    """
    if not volume_no:
        return None  # Query chapters only

    if volume_no.isdigit():
        vol = int(volume_no)
        if vol <= 0:
            raise ValueError("Volume number must be positive")
        return vol

    if "-" in volume_no:
        parts = volume_no.split("-")
        if len(parts) == 2 and all(p.isdigit() for p in parts):
            start, end = int(parts[0]), int(parts[1])
            if 0 < start < end:
                return list(range(start, end + 1))
        raise ValueError("Invalid range format, use e.g. '1-3'")

    if "," in volume_no:
        parts = volume_no.split(",")
        if all(p.isdigit() for p in parts):
            return [int(p) for p in parts]
        raise ValueError("Invalid comma list format, use e.g. '1,2,3'")

    raise ValueError("Invalid volume input")
