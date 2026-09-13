#!/usr/bin/env python3
"""Run the DamWatch daily official-source collection pipeline."""
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from openai_agent import collect_state

ROOT = Path(__file__).resolve().parents[1]
TODAY = datetime.now(timezone.utc).strftime("%Y-%m-%d")
OBS_OUT = ROOT / "data" / "observations" / f"{TODAY}.json"
RAW_DIR = ROOT / "data" / "raw" / TODAY

STATES = ["Karnataka", "Andhra Pradesh", "Telangana"]


def main():
    retrieved_at = datetime.now(timezone.utc).isoformat()
    all_observations = []
    runs = []
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    for state in STATES:
        try:
            result = collect_state(state)
            raw_path = RAW_DIR / f"{state.lower().replace(' ', '-')}.json"
            raw_path.write_text(json.dumps(result.get("_raw_response", {}), indent=2), encoding="utf-8")
            result.pop("_raw_response", None)
            runs.append({"state": state, "status": "success", "source": result.get("source_url")})
            for item in result.get("observations", []):
                item.update({
                    "state": state,
                    "source_name": result.get("source_name"),
                    "source_url": result.get("source_url"),
                    "retrieved_at": result.get("retrieved_at", retrieved_at),
                    "status": "official_source_verified",
                })
                all_observations.append(item)
        except Exception as exc:
            runs.append({"state": state, "status": "error", "error": str(exc)})
            print(f"[{state}] collection failed: {exc}")

    payload = {
        "observation_date": TODAY,
        "retrieved_at": retrieved_at,
        "pipeline": "official-source -> OpenAI extraction -> whitelist validation",
        "runs": runs,
        "observations": all_observations,
    }
    OBS_OUT.parent.mkdir(parents=True, exist_ok=True)
    OBS_OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    if not all_observations:
        raise SystemExit("No verified official observations were collected; refusing to publish fabricated data.")

    print(f"Collected {len(all_observations)} verified observations")


if __name__ == "__main__":
    main()
