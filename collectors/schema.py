from dataclasses import dataclass, asdict
from typing import Optional


@dataclass
class Observation:
    reservoir: str
    state: str
    report_date: Optional[str]
    reported_at: Optional[str]
    water_level: Optional[float]
    water_level_unit: Optional[str]
    storage: Optional[float]
    storage_unit: Optional[str]
    storage_percentage: Optional[float]
    inflow: Optional[float]
    inflow_unit: Optional[str]
    outflow: Optional[float]
    outflow_unit: Optional[str]
    source_name: str
    source_url: Optional[str]
    source_type: str
    retrieved_at: str
    status: str = "unverified"
    notes: Optional[str] = None

    def to_dict(self):
        return asdict(self)
