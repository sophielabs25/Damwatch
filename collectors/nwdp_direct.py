#!/usr/bin/env python3
"""Deterministic NWDP CSV discovery/download/parser.

NWDP exposes machine-readable CSV resources. This module discovers the current
2026 CSV link from the official dataset page, downloads it, and extracts only
recent rows. It deliberately does not infer reservoir metrics that are absent
from the source.
"""
import csv
import io
import re
from datetime import datetime, timezone
from urllib.parse import urljoin
from urllib.request import Request, urlopen

UA = "DamWatch/1.0 (+official-source-monitor)"

CONFIG = {
    "Karnataka": {
        "page": "https://nwdp.nwic.gov.in/dataset/reservoir-data-karnataka",
        "kind": "reservoir_level_daily",
    },
    "Andhra Pradesh": {
        "page": "https://nwdp.nwic.gov.in/en/dataset/reservoir-water-level-manual-daily-andhra-pradesh-surface-water-department",
        "kind": "reservoir_level_daily",
    },
    "Telangana": {
        "page": "https://nwdp.nwic.gov.in/dataset/water-level-and-discharge-scada-hourly-telangana-sw",
        "kind": "scada_hourly",
    },
}

DATE_FORMATS = (
    "%Y-%m-%d", "%Y/%m/%d", "%d/%m/%Y", "%d/%m/%Y %H:%M", "%d-%m-%Y",
    "%d-%m-%Y %H:%M", "%d-%m-%Y %H:%M:%S", "%d-%m-%y", "%d-%m-%y %H:%M",
    "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M",
)


def _get(url):
    req = Request(url, headers={"User-Agent": UA})
    with urlopen(req, timeout=60) as r:
        return r.read()


def _parse_date(value):
    if not value:
        return None
    s = str(value).strip()
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None


def _find_column(fields, patterns):
    for field in fields:
        n = re.sub(r"[^a-z0-9]", "", field.lower())
        for p in patterns:
            if p in n:
                return field
    return None


def _discover_csv(page_url):
    html = _get(page_url).decode("utf-8", errors="replace")
    links = re.findall(r'''href=["']([^"']+\.csv(?:\?[^"']*)?)["']''', html, flags=re.I)
    links += re.findall(r'''https?://[^\s"'<>]+\.csv(?:\?[^\s"'<>]*)?''', html, flags=re.I)
    clean = []
    for link in links:
        link = urljoin(page_url, link).replace("&amp;", "&")
        if link not in clean:
            clean.append(link)
    # Prefer a resource explicitly covering 2026-2030 / 2026, then the first CSV.
    preferred = [u for u in clean if re.search(r"2026|2030", u, re.I)]
    return (preferred + clean)[0] if (preferred or clean) else None


def _rows_from_csv(csv_bytes):
    text = csv_bytes.decode("utf-8-sig", errors="replace")
    sample = text[:8192]
    try:
        dialect = csv.Sniffer().sniff(sample)
    except csv.Error:
        dialect = csv.excel
    reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    return reader.fieldnames or [], list(reader)


def collect_nwdp(state, max_age_days=3):
    cfg = CONFIG[state]
    csv_url = _discover_csv(cfg["page"])
    if not csv_url:
        raise RuntimeError(f"No CSV resource discovered from {cfg['page']}")

    fields, rows = _rows_from_csv(_get(csv_url))
    date_col = _find_column(fields, ("dataacquisitiontime", "observationdate", "date", "datetime", "timestamp", "time"))
    station_col = _find_column(fields, ("station", "reservoir", "dam", "barrage", "location"))
    level_col = _find_column(fields, ("reservoirdischargewaterlevel", "waterlevel", "reservoirwaterlevel", "level"))
    discharge_col = _find_column(fields, ("discharge", "outflow", "flow")) if cfg["kind"] == "scada_hourly" else None

    if not date_col or not station_col:
        raise RuntimeError(f"Could not identify date/station columns. fields={fields}")

    now = datetime.now(timezone.utc)
    observations = []
    for row in rows:
        observed = _parse_date(row.get(date_col))
        if not observed:
            continue
        age = (now - observed).total_seconds() / 86400
        if age < -1 or age > max_age_days:
            continue
        station = (row.get(station_col) or "").strip()
        if not station:
            continue
        def number(col):
            if not col:
                return None
            value = str(row.get(col, "")).strip().replace(",", "")
            try:
                return float(value) if value not in ("", "-", "NA", "N/A", "null") else None
            except ValueError:
                return None

        level = number(level_col)
        discharge = number(discharge_col)
        if level is None and discharge is None:
            continue
        observations.append({
            "reservoir": station,
            "water_level": level,
            "water_level_unit": "m" if level is not None else None,
            "storage": None,
            "storage_unit": None,
            "storage_percentage": None,
            "inflow": None,
            "inflow_unit": None,
            "outflow": discharge,
            "outflow_unit": "m3/s" if discharge is not None else None,
            "report_date": observed.strftime("%Y-%m-%d"),
            "notes": f"Directly parsed from official NWDP CSV; source field: {level_col or discharge_col}",
        })

    # Keep the latest observation per station.
    latest = {}
    for item in observations:
        key = item["reservoir"].strip().lower()
        latest[key] = item

    return {
        "state": state,
        "observation_date": max((x["report_date"] for x in latest.values()), default=None),
        "source_name": "National Water Data Portal (NWIC)",
        "source_url": csv_url,
        "retrieved_at": now.isoformat(),
        "observations": list(latest.values()),
        "parser": {"type": cfg["kind"], "fields": fields, "row_count": len(rows)},
    }
