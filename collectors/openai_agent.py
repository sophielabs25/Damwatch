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
        "primary": ["x.com", "ksndmc.karnataka.gov.in", "karnataka.gov.in", "kwris.aciwrm.org", "nwdp.nwic.gov.in"],
        "source_pages": ["https://x.com/KarnatakaSNDMC", "https://kwris.aciwrm.org/ReservoirPublic", "https://nwdp.nwic.gov.in/"],
        "search": "site:x.com/KarnatakaSNDMC \"Major Reservoir Level\" Karnataka 2026; site:kwris.aciwrm.org Karnataka reservoir latest 2026; site:nwdp.nwic.gov.in Karnataka reservoir 2026",
    },
    "Andhra Pradesh": {
        "primary": ["apwrims.ap.gov.in", "desweather.ap.gov.in", "ap.gov.in", "nwdp.nwic.gov.in"],
        "source_pages": ["https://apwrims.ap.gov.in/mis/reservoir/summary", "https://desweather.ap.gov.in/Realtime/Reservoir.jsp", "https://desweather.ap.gov.in/Realtime/ReservoirData.jsp", "https://nwdp.nwic.gov.in/"],
        "search": "site:nwdp.nwic.gov.in Andhra Pradesh Surface Water Department reservoir 2026; site:apwrims.ap.gov.in reservoir summary latest 2026; site:desweather.ap.gov.in realtime reservoir latest 2026",
    },
    "Telangana": {
        "primary": ["telangana.gov.in", "nwdp.nwic.gov.in"],
        "source_pages": ["https://nwdp.nwic.gov.in/", "https://telangana.gov.in/"],
        "search": "site:nwdp.nwic.gov.in Telangana SW reservoir 2026 SCADA hourly; site:nwdp.nwic.gov.in Telangana reservoir 2026 water level discharge; site:telangana.gov.in reservoir SCADA latest 2026",
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

Known official source pages:
{json.dumps(cfg['source_pages'], indent=2)}

Focused official-source search:
{cfg['search']}

Allowed official domains: {json.dumps(cfg['primary'])}

Rules:
1. Numeric values MUST come directly from an allowed official government source. Never use news, aggregators, DamToday, third-party hydrology sites, or social reposts.
2. Find the newest 2026 observation available. An official page is NOT sufficient if its displayed observation/report date is old.
3. Prefer current state-primary data. For Karnataka, an official @KarnatakaSNDMC X post/bulletin is acceptable only if the source is the official account; never accept reposts.
4. For Andhra Pradesh, prefer current APWRIMS or NWDP Andhra Pradesh Surface Water Department data. Use DES only when its displayed data is current; do not accept the stale March 2026 table as current September data.
5. For Telangana, prefer current NWDP Telangana SW SCADA data. Do NOT use the old Telangana Agriculture reservoir page when its observation date is historical.
6. Preserve published units and report/observation dates exactly.
7. Return a direct official source URL supporting the observations.
8. If a field is not published, return null; never estimate.
9. If official sources disagree, use the higher-priority current source and explain in notes.
10. Return only observations whose numeric values and dates can be verified from the cited official source.
11. Never manufacture values from percentages, charts, memory, nearby reservoirs, or another reservoir.
12. If no current official numeric reservoir observation can be verified, return an empty observations array.
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
