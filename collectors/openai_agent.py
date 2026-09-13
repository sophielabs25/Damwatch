#!/usr/bin/env python3
"""OpenAI-powered official-source reservoir collector."""
import json
import os
import re
import urllib.request
from datetime import datetime, timezone

API_URL = "https://api.openai.com/v1/responses"
MODEL = os.getenv("OPENAI_MODEL", "gpt-5.6-luna")

STATE_CONFIG = {
    "Karnataka": {
        "primary": ["ksndmc.karnataka.gov.in", "karnataka.gov.in", "kwris.aciwrm.org", "nwdp.nwic.gov.in"],
        "source_pages": ["https://kwris.aciwrm.org/ReservoirPublic", "https://ksndmc.karnataka.gov.in/"],
        "search": "site:kwris.aciwrm.org Karnataka reservoir latest level storage 2026; site:ksndmc.karnataka.gov.in KSNDMC major reservoir level WRDO KPTCL latest 2026",
    },
    "Andhra Pradesh": {
        "primary": ["apwrims.ap.gov.in", "desweather.ap.gov.in", "ap.gov.in", "nwdp.nwic.gov.in"],
        "source_pages": ["https://apwrims.ap.gov.in/mis/reservoir/summary", "https://desweather.ap.gov.in/Realtime/Reservoir.jsp", "https://desweather.ap.gov.in/Realtime/ReservoirData.jsp"],
        "search": "site:apwrims.ap.gov.in reservoir summary latest official Andhra Pradesh; site:desweather.ap.gov.in Realtime Reservoir latest official Andhra Pradesh",
    },
    "Telangana": {
        "primary": ["telangana.gov.in", "nwdp.nwic.gov.in"],
        "source_pages": ["https://nwdp.nwic.gov.in/dataset/"],
        "search": "site:nwdp.nwic.gov.in Telangana reservoir telemetry hourly 2026; site:telangana.gov.in reservoir SCADA Telangana latest",
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
        "observations": {"type": "array", "items": {
            "type": "object", "properties": {
                "reservoir": {"type": "string"}, "water_level": {"type": ["number", "null"]}, "water_level_unit": {"type": ["string", "null"]},
                "storage": {"type": ["number", "null"]}, "storage_unit": {"type": ["string", "null"]}, "storage_percentage": {"type": ["number", "null"]},
                "inflow": {"type": ["number", "null"]}, "inflow_unit": {"type": ["string", "null"]}, "outflow": {"type": ["number", "null"]}, "outflow_unit": {"type": ["string", "null"]},
                "report_date": {"type": ["string", "null"]}, "notes": {"type": ["string", "null"]}
            },
            "required": ["reservoir", "water_level", "water_level_unit", "storage", "storage_unit", "storage_percentage", "inflow", "inflow_unit", "outflow", "outflow_unit", "report_date", "notes"],
            "additionalProperties": False
        }}
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
    req = urllib.request.Request(API_URL, data=json.dumps(body).encode(), headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=180) as response:
        return json.loads(response.read().decode())


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

Start by reviewing these known official pages:
{json.dumps(cfg['source_pages'], indent=2)}
If they do not contain the latest data, use this focused search:
{cfg['search']}

Allowed official domains: {json.dumps(cfg['primary'])}

Rules:
1. Numeric values MUST come from an allowed official source. Never use news, aggregators, DamToday, social reposts, or third-party hydrology sites.
2. Prefer the state primary source. If a field is not published, return null; never estimate it.
3. Preserve published units and report/observation dates exactly.
4. Return a direct official source URL supporting the observations.
5. If official sources disagree, use the higher-priority state source and explain in notes.
6. Return every reservoir clearly supported by the latest official table/bulletin you can verify. A verified subset is better than an empty result.
7. If a source is stale, retain its actual report date and explain that in notes.
8. Do not manufacture values from percentages, charts, memory, or nearby reservoirs.
9. Return an empty observations array only when no official reservoir observation can be verified.
Return ONLY the required JSON object.
"""
    raw = _call_openai(prompt)
    data = _safe_json(_output_text(raw))
    source_url = data.get("source_url")
    if source_url and not _allowed(source_url, cfg["primary"]):
        raise ValueError(f"Rejected non-whitelisted source URL: {source_url}")
    if data.get("observations") and not source_url:
        raise ValueError("Observations returned without an official source URL")
    data["retrieved_at"] = datetime.now(timezone.utc).isoformat()
    print(f"[{state}] source={source_url or 'none'} observations={len(data.get('observations', []))}")
    data["_raw_response"] = raw
    return data
