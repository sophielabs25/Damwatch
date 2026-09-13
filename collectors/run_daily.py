#!/usr/bin/env python3
"""Daily DamWatch collector.

This first version establishes the data contract and source registry. Source
adapters should return observations only when the official source publishes
the field; missing fields remain null.
"""
import json
import os
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TODAY = datetime.now(timezone.utc).strftime("%Y-%m-%d")
OUT = ROOT / "data" / "observations" / f"{TODAY}.json"

SOURCES = [
    {"state": "Karnataka", "name": "KSNDMC / WRDO & KPTCL", "priority": 1},
    {"state": "Karnataka", "name": "KWRIS / Karnataka Water Resources Department", "priority": 2},
    {"state": "Andhra Pradesh", "name": "APWRIMS", "priority": 1},
    {"state": "Andhra Pradesh", "name": "AP Government DES", "priority": 2},
    {"state": "Telangana", "name": "Telangana official water resources / SCADA", "priority": 1},
    {"state": "All", "name": "NWDP / NWIC", "priority": 4},
]


def main():
    # Placeholder until each official adapter is implemented. Never fabricate
    # observations merely to make the daily run non-empty.
    payload = {
        "observation_date": TODAY,
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "sources_checked": SOURCES,
        "observations": [],
        "status": "collector_ready",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
