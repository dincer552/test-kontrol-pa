from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import re

from pypdf import PdfReader


@dataclass(frozen=True)
class PdfDiscovery:
    page_count: int
    order_no: str = ""
    project_name: str = ""
    ahu_name: str = ""
    supply_fan_count: int = 0
    return_fan_count: int = 0
    damper_count: int = 0
    sensor_count: int = 0
    filter_count: int = 0
    module_count: int = 0
    components: dict[str, int] = field(default_factory=dict)


def _text(reader: PdfReader) -> str:
    return "\n".join((page.extract_text() or "") for page in reader.pages)


def _first_nonempty_after(lines: list[str], marker: str) -> str:
    for index, line in enumerate(lines):
        if line.strip().lower() == marker.lower():
            for candidate in lines[index + 1:]:
                value = candidate.strip()
                if value:
                    return value
    return ""


def _has_component(text: str, pattern: str) -> bool:
    return bool(re.search(pattern, text, re.IGNORECASE))


def _numbered_components(text: str, prefix: str) -> set[str]:
    return set(re.findall(rf"\\b{prefix}\s*([1-9]\d*)\b", text, re.IGNORECASE))


def discover_pdf(path: str | Path) -> PdfDiscovery:
    pdf_path = Path(path)
    reader = PdfReader(str(pdf_path))
    text = _text(reader)
    first_page = reader.pages[0].extract_text() or ""
    first_lines = [line.strip() for line in first_page.splitlines() if line.strip()]

    project_name = _first_nonempty_after(first_lines, "Appr")
    order_match = re.search(r"\b\d{8,}\b", first_page)
    ahu_match = re.search(r"\bFAHU_[A-Z0-9-]+\b", first_page, re.IGNORECASE)

    supply_fan = 1 if _has_component(
        text, r"VLT\s*(?:®|R)?\s*HVAC Basic Drive\s*FC\s*101"
    ) else 0
    return_fan = 1 if _has_component(
        text, r"Return Motor Connections"
    ) else 0

    fda_ids = _numbered_components(text, "FDA")
    ts_ids = _numbered_components(text, "TS")
    dpt_ids = _numbered_components(text, "DPT")
    filter_ids = _numbered_components(text, "P")

    components = {
        "supply_fan": supply_fan,
        "return_fan": return_fan,
        "fresh_air_damper": len(fda_ids),
        "temperature_sensor": len(ts_ids),
        "pressure_sensor": len(dpt_ids),
        "filter_sensor": len(filter_ids),
        "cooling_valve": 1 if _has_component(text, r"\bVA2\b|Cooling Valve Motor") else 0,
        "emergency_button": 1 if _has_component(text, r"Emergency Button") else 0,
        "door_switch": 1 if _has_component(text, r"Supply Door Switch") else 0,
        "fire_alarm": 1 if _has_component(text, r"Fire Alarm") else 0,
        "plc": 1 if _has_component(text, r"PLC MAN MODULE\s+POL648") else 0,
        "hmi": 1 if _has_component(text, r"POL871\.62/72") else 0,
    }

    module_count = components["plc"] + components["hmi"]

    return PdfDiscovery(
        page_count=len(reader.pages),
        order_no=order_match.group(0) if order_match else "",
        project_name=project_name,
        ahu_name=ahu_match.group(0) if ahu_match else "",
        supply_fan_count=supply_fan,
        return_fan_count=return_fan,
        damper_count=len(fda_ids),
        sensor_count=len(ts_ids) + len(dpt_ids),
        filter_count=len(filter_ids),
        module_count=module_count,
        components=components,
    )
