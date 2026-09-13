#!/usr/bin/env python3
"""Run the DamWatch daily official-source collection pipeline."""
import json
from datetime import datetime, timezone
from pathlib import Path

from openai_agent import collect_state
from nwdp_direct import collect_nwdp

ROOT = Path(__file__).resolve().parents[1]
TODAY = datetime.now(timezone.utc).strftime("%Y-%m-%d")
OBS_OUT = ROOT / "data" / "observations" / f"{TODAY}.json"
RAW_DIR = ROOT / "data" / "raw" / TODAY

STATES = ["Karnataka", "Andhra Pradesh", "Telangana"]
MAX_CURRENT_AGE_DAYS = 3


def _parse_date(value):
    if not value:
        return None
    text = str(value).strip()
    formats = [
        "%Y-%m-%d", "%d/%m/%Y", "%d/%m/%y %H:%M", "%d-%m-%Y", "%d-%m-%Y %H:%M",
        "%d-%m-%Y %H:%M:%S", "%d-%m-%y", "%d-%m-%y %H:%M", "%d %b %Y", "%d %B %Y",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    return None


def _is_current(item):
    observed = _parse_date(item.get("report_date"))
    if observed is None:
        return False, "unparseable report date"
    age = (datetime.now(timezone.utc) - observed).total_seconds() / 86400
    if age < -1:
        return False, "report date is in the future"
    if age > MAX_CURRENT_AGE_DAYS:
        return False, f"report is {age:.1f} days old"
    return True, None


def _is_individual_reservoir(item):
    name = str(item.get("reservoir", "")).lower()
    blocked = ("portfolio", "aggregate", "state total", "state aggregate")
    return not any(term in name for term in blocked)


def _save_raw(state, result):
    raw_path = RAW_DIR / f"{state.lower().replace(' ', '-')}.json"
    raw_path.write_text(json.dumps(result, indent=2), encoding="utf-8")


def _collect(state):
    """Use deterministic official NWDP data first; AI web extraction is fallback."""
    try:
        direct = collect_nwdp(state, max_age_days=MAX_CURRENT_AGE_DAYS)
        if direct.get("observations"):
            return direct, "nwdp_direct"
        print(f"[{state}] NWDP direct parser found no current rows; falling back to OpenAI official-source search")
    except Exception as exc:
        print(f"[{state}] NWDP direct parser unavailable: {exc}; falling back to OpenAI official-source search")

    result = collect_state(state)
    return result, "openai_official_search"


def main():
    retrieved_at = datetime.now(timezone.utc).isoformat()
    all_observations = []
    runs = []
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    for state in STATES:
        try:
            result, collector = _collect(state)
            _save_raw(state, result)
            accepted = 0
            rejected = []
            for item in result.get("observations", []):
                if not _is_individual_reservoir(item):
                    rejected.append({"reservoir": item.get("reservoir"), "reason": "aggregate/state-level observation"})
                    continue
                current, reason = _is_current(item)
                if not current:
                    rejected.append({"reservoir": item.get("reservoir"), "reason": reason, "report_date": item.get("report_date")})
                    continue
                item.update({
                    "state": state,
                    "source_name": result.get("source_name"),
                    "source_url": result.get("source_url"),
                    "retrieved_at": result.get("retrieved_at", retrieved_at),
                    "collector": collector,
                    "status": "official_source_verified_current",
                })
                all_observations.append(item)
                accepted += 1

            runs.append({
                "state": state,
                "status": "success" if accepted else "no_current_data",
                "collector": collector,
                "source": result.get("source_url"),
                "accepted_observations": accepted,
                "rejected_observations": rejected,
            })
            print(f"[{state}] accepted_current={accepted} rejected={len(rejected)} collector={collector}")
        except Exception as exc:
            runs.append({"state": state, "status": "error", "error": str(exc)})
            print(f"[{state}] collection failed: {exc}")

    payload = {
        "observation_date": TODAY,
        "retrieved_at": retrieved_at,
        "freshness_policy": {"max_current_age_days": MAX_CURRENT_AGE_DAYS},
        "pipeline": "official NWDP CSV -> deterministic parser -> freshness validation -> OpenAI official-source fallback",
        "runs": runs,
        "observations": all_observations,
    }
    OBS_OUT.parent.mkdir(parents=True, exist_ok=True)
    OBS_OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    if not all_observations:
        raise SystemExit("No current verified official observations were collected; refusing to publish stale or fabricated data.")

    print(f"Collected {len(all_observations)} current verified observations")


if __name__ == "__main__":
    main()
