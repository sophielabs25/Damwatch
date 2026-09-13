# DamWatch

DamWatch is an official-source reservoir monitoring platform for India, starting with Karnataka, Andhra Pradesh and Telangana.

## Data principles

- Prefer state government primary sources over aggregators.
- Never invent a missing field.
- Preserve the source URL, report date/time and retrieval time for every observation.
- Keep raw observations and normalized observations separately.
- Use OpenAI for source discovery, extraction and discrepancy review; it is not treated as the authority over an official source.
- If official sources disagree, retain the observations and record the conflict.

## Source hierarchy

### Karnataka
1. KSNDMC / WRDO & KPTCL
2. KWRIS / Karnataka Water Resources Department
3. Official Karnataka SCADA where available
4. NWDP / NWIC fallback

### Andhra Pradesh
1. APWRIMS
2. Andhra Pradesh government / DES realtime reservoir data
3. NWDP / NWIC fallback

### Telangana
1. Telangana official water-resources / SCADA sources
2. NWDP / NWIC fallback

## Automated daily collection

GitHub Actions runs the collector every morning using the official-source whitelist. The workflow can also be started manually.

Required repository secrets:

- `OPENAI_API_KEY` — server-side OpenAI API key
- `X_BEARER_TOKEN` — optional, for KSNDMC X ingestion when enabled

The collector writes:

- `data/raw/YYYY-MM-DD/` — raw model/source evidence
- `data/observations/YYYY-MM-DD.json` — normalized observations

Do not commit API keys to the repository.

## Development

The collector is intentionally dependency-light and uses Python's standard library plus the OpenAI HTTP API. The frontend/backend can be added alongside it without changing the data contract.
