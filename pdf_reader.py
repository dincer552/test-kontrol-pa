from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import re

import fitz
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
    damper_types: dict[str, bool] = field(default_factory=dict)
    sensor_types: dict[str, dict[str, bool]] = field(default_factory=dict)



_PROJECT_BOX = (383.0, 508.0, 228.0, 26.0)
_ORDER_NO_BOX = (379.0, 478.0, 300.0, 29.0)
_AHU_BOX = (381.0, 450.0, 315.0, 26.0)


def _viewer_rect(page: fitz.Page, box: tuple[float, float, float, float]) -> fitz.Rect:
    x, y, width, height = box
    page_height = float(page.rect.height)
    return fitz.Rect(x, page_height - (y + height), x + width, page_height - y)


def _coordinate_text(page: fitz.Page, box: tuple[float, float, float, float]) -> str:
    words = page.get_text("words", clip=_viewer_rect(page, box))
    words.sort(key=lambda word: (word[1], word[0]))
    return " ".join(word[4].strip() for word in words if word[4].strip()).strip()


def _read_general_fields(pdf_path: Path) -> tuple[str, str, str]:
    document = fitz.open(str(pdf_path))
    try:
        if len(document) < 1:
            return "", "", ""
        page = document[0]
        return (
            _coordinate_text(page, _PROJECT_BOX),
            _coordinate_text(page, _ORDER_NO_BOX),
            _coordinate_text(page, _AHU_BOX),
        )
    finally:
        document.close()


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
    return set(re.findall(rf"\b{prefix}\s*([1-9]\d*)\b", text, re.IGNORECASE))


def discover_pdf(path: str | Path) -> PdfDiscovery:
    pdf_path = Path(path)
    reader = PdfReader(str(pdf_path))
    text = _text(reader)
    first_page = reader.pages[0].extract_text() or ""
    first_lines = [line.strip() for line in first_page.splitlines() if line.strip()]

    coordinate_project, coordinate_order, coordinate_ahu = _read_general_fields(pdf_path)
    project_name = coordinate_project
    order_no = coordinate_order
    ahu_name = coordinate_ahu

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

    damper_types = {
        "Fresh": _has_component(text, r"Fresh Air Damper Actuator"),
        "Supply": _has_component(text, r"Supply Damper Actuator"),
        "Return": _has_component(text, r"Return Damper Actuator"),
        "Exhaust": _has_component(text, r"Exhaust Damper"),
        "Mix": _has_component(text, r"Mixing Damper Actuator"),
        "Bypass": _has_component(text, r"Bypass damper"),
    }

    sensor_types = {
        "Fresh Air Sensor": {
            "temperature": _has_component(text, r"Fresh\s+Air\s+(?:Humidity\s+And\s+)?Temperature\s+Sensor|Fresh\s+Air\s+Sensor"),
            "humidity": _has_component(text, r"Fresh\s+Air\s+Humidity\s+And\s+Temperature\s+Sensor"),
        },
        "Supply Air Sensor": {
            "temperature": _has_component(text, r"Supply\s+Air\s+(?:Humidity\s+And\s+)?Temperature\s+Sensor|Supply\s+Air\s+Sensor"),
            "humidity": _has_component(text, r"Supply\s+Air\s+Humidity\s+And\s+Temperature\s+Sensor"),
        },
        "Return Air Sensor": {
            "temperature": _has_component(text, r"Return\s+Air\s+(?:Humidity\s+And\s+)?Temperature\s+Sensor|Return\s+Air\s+Sensor"),
            "humidity": _has_component(text, r"Return\s+Air\s+Humidity\s+And\s+Temperature\s+Sensor"),
        },
        "Exhaust Air Sensor": {
            "temperature": _has_component(text, r"Exhaust\s+Air\s+(?:Humidity\s+And\s+)?Temperature\s+Sensor|Exhaust\s+Air\s+Sensor"),
            "humidity": _has_component(text, r"Exhaust\s+Air\s+Humidity\s+And\s+Temperature\s+Sensor"),
        },
        "AfterCoil Air Sensor": {
            "temperature": _has_component(text, r"After\s*Coil\s+Air\s+(?:Humidity\s+And\s+)?Temperature\s+Sensor|AfterCoil\s+Air\s+Sensor"),
            "humidity": _has_component(text, r"After\s*Coil\s+Air\s+Humidity\s+And\s+Temperature\s+Sensor"),
        },
        "Mix Air Sensor": {
            "temperature": _has_component(text, r"(?:Mixing|Mix)\s+Air\s+(?:Humidity\s+And\s+)?Temperature\s+Sensor|Mixing\s+Air\s+Sensor"),
            "humidity": _has_component(text, r"(?:Mixing|Mix)\s+Air\s+Humidity\s+And\s+Temperature\s+Sensor"),
        },
        "Room Temp Sensor 1": {
            "temperature": _has_component(text, r"Room\s+Temp(?:erature)?\s+Sensor(?:\s+1)?|Room\s+Temperature"),
            "humidity": False,
        },
        "Room Temp Sensor 2": {
            "temperature": _has_component(text, r"Room\s+Temp(?:erature)?\s+Sensor\s+2"),
            "humidity": False,
        },
        "Return CO2 Sensor": {
            "temperature": False,
            "humidity": False,
            "co2": _has_component(text, r"Return\s+CO2\s+Sensor"),
        },
        "Water Temp Sensor": {
            "temperature": _has_component(text, r"Water\s+Temperature\s+Sensor|Water\s+Temp\s+Sensor"),
            "humidity": False,
        },
        "Return CO2 Air Sensor": {
            "temperature": False,
            "humidity": False,
            "co2": _has_component(text, r"Return\s+CO2\s+Air\s+Sensor"),
        },
    }

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
        order_no=order_no,
        project_name=project_name,
        ahu_name=ahu_name,
        supply_fan_count=supply_fan,
        return_fan_count=return_fan,
        damper_count=len(fda_ids),
        sensor_count=len(ts_ids) + len(dpt_ids),
        filter_count=len(filter_ids),
        module_count=module_count,
        components=components,
        damper_types=damper_types,
        sensor_types=sensor_types,
    )
