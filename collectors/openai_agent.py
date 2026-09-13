#!/usr/bin/env python3
"""OpenAI-powered official-source reservoir collector.

The model is used as a web-research/extraction layer. It is constrained to
official domains and must return null rather than infer a missing value.
"""
import json
import os
import re
import urllib.request
from datetime import datetime, timezone

API_URL = "https://api.openai.com/v1/responses"
MODEL = os.getenv("OPENAI_MODEL", "gpt-5.6-luna")

STATE_CONFIG = {
    "Karnataka": {
        "primary": [
            "ksndmc.karnataka.gov.in",
            "karnataka.gov.in",
            "kwris.aciwrm.org",
            "nwdp.nwic.gov.in",
        ],
        "search": "Karnataka KSNDMC WRDO KPTCL major reservoir level storage inflow outflow latest bulletin",
    },
    "Andhra Pradesh": {
        "primary": [
            "apwrims.ap.gov.in",
            "desweather.ap.gov.in",
            "ap.gov.in",
            "nwdp.nwic.gov.in",
        ],
        "search": "Andhra Pradesh APWRIMS reservoir level storage inflow outflow latest official",
    },
    "Telangana": {
        "primary": [
            "telangana.gov.in",
            "nwdp.nwic.gov.in",
        ],
        "search": "Telangana reservoir level storage inflow outflow latest official water resources SCADA",
    },
}

SCHEMA = {
    "type": "object",
    "properties": {
        "state": {"type": "string"},
        "observation_date": {"type": ["string", "null"]},
        "source_name": {"type": ["string", "null"]},
        "source_url": {"type": ["string", "null"]},
        "retrieved_at": {"type": "string"},
        "observations": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "reservoir": {"type": "string"},
                    "water_level": {"type": ["number", "null"]},
                    "water_level_unit": {"type": ["string", "null"]},
                    "storage": {"type": ["number", "null"]},
                    "storage_unit": {"type": ["string", "null"]},
                    "storage_percentage": {"type": ["number", "null"]},
                    "inflow": {"type": ["number", "null"]},
                    "inflow_unit": {"type": ["string", "null"]},
                    "outflow": {"type": ["number", "null"]},
                    "outflow_unit": {"type": ["string", "null"]},
                    "report_date": {"type": ["string", "null"]},
                    "notes": {"type": ["string", "null"]},
                },
                "required": ["reservoir", "water_level", "water_level_unit", "storage", "storage_unit", "storage_percentage", "inflow", "inflow_unit", "outflow", "outflow_unit", "report_date", "notes"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["state", "observation_date", "source_name", "source_url", "retrieved_at", "observations"],
    "additionalProperties": False,
}


def _call_openai(prompt):
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        raise RuntimeError("OPENAI_API_KEY is not configured")

    body = {
        "model": MODEL,
        "tools": [{"type": "web_search"}],
        "input": prompt,
        "text": {"format": {"type": "json_schema", "name": "reservoir_data", "strict": True, "schema": SCHEMA}},
        "include": ["web_search_call.action.sources"],
    }
    req = urllib.request.Request(
        API_URL,
        data=json.dumps(body).encode("utf-8"),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=180) as response:
        return json.loads(response.read().decode("utf-8"))


def _output_text(response):
    if response.get("output_text"):
        return response["output_text"]
    for item in response.get("output", []):
        if item.get("type") == "message":
            for part in item.get("content", []):
                if part.get("type") in ("output_text", "text") and part.get("text"):
                    return part["text"]
    raise ValueError("OpenAI response contained no output text")


def _safe_json(text):
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    return json.loads(text)


def _allowed(url, domains):
    if not url or not url.startswith("https://"):
        return False
    host = url.split("/", 3)[2].lower().split(":")[0]
    return any(host == d or host.endswith("." + d) for d in domains)


def collect_state(state):
    cfg = STATE_CONFIG[state]
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    prompt = f"""
You are the DamWatch official-source reservoir data agent.

State: {state}
Today (UTC): {today}

Search the web for the newest official government reservoir observations for this state.
Preferred official domains, in priority order:
{json.dumps(cfg['primary'])}

Starting search: {cfg['search']}

Rules:
1. Numeric values MUST come from an official source in the whitelist. Never use a news site, aggregator, DamToday, social repost, or third-party hydrology site for numeric values.
2. Prefer the state primary source. If it does not publish a field, use null; do not estimate or calculate it.
3. Preserve the units exactly as published. Do not silently convert units.
4. Preserve the report/observation date. Do not call retrieval date the observation date.
5. Return the source URL for the official page/document/post supporting the observations.
6. If multiple official sources disagree, retain the higher-priority state source and mention the disagreement in notes.
7. Include all reservoirs clearly supported by the latest official bulletin/table, not just one reservoir.
8. If the latest official source cannot be verified, return an empty observations array rather than using a third-party fallback.
9. Do not manufacture values from percentages, charts, memory, or nearby reservoirs.
"""
    raw = _call_openai(prompt)
    data = _safe_json(_output_text(raw))
    source_url = data.get("source_url")
    if source_url and not _allowed(source_url, cfg["primary"]):
        raise ValueError(f"Rejected non-whitelisted source URL: {source_url}")
    data["retrieved_at"] = datetime.now(timezone.utc).isoformat()
    data["_raw_response"] = raw
    return data
