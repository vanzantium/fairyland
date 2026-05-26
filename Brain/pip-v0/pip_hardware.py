#!/usr/bin/env python3
"""
pip_hardware.py - portable hardware assessment wrapper.

The older version used Windows PowerShell directly. This wrapper delegates to
pip_hardware_scanner, which now has Windows/macOS/Linux fallbacks.
"""
from __future__ import annotations

import json

import pip_hardware_scanner


def assess_hardware() -> dict:
    report = pip_hardware_scanner.scan_and_save(optimize=False)
    recommendation = report.get("recommendation", {})
    return {
        "os": report.get("os", "Unknown"),
        "system_ram_gb": report.get("ram_gb", 0),
        "cpu": report.get("cpu", "Unknown CPU"),
        "gpus": [{"name": report.get("gpu", "Unknown GPU"), "vram_gb": 0}],
        "recommended_model": recommendation.get("model", ""),
        "reasoning": recommendation.get("reason", ""),
        "prompt_strategy": recommendation.get("prompt_strategy", ""),
    }


if __name__ == "__main__":
    print(json.dumps(assess_hardware(), indent=2))
