from __future__ import annotations

from dataclasses import dataclass
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


def _text(reader: PdfReader) -> str:
    return "\n".join((page.extract_text() or "") for page in reader.pages)


def _count(pattern: str, text: str, flags: int = re.IGNORECASE) -> int:
    return len(re.findall(pattern, text, flags))


def discover_pdf(path: str | Path) -> PdfDiscovery:
    pdf_path = Path(path)
    reader = PdfReader(str(pdf_path))
    text = _text(reader)

    order = re.search(r"Order Number:\s*([^\n]+)", text, re.IGNORECASE)
    project = re.search(r"Proje Name:\s*([^\n]+)", text, re.IGNORECASE)
    ahu = re.search(r"Unit Number:\s*([^\n]+)", text, re.IGNORECASE)

    supply_fan = 0
    if re.search(r"Supply Motor Connections|Supply Fan Motor|SUPPLY MOTOR", text, re.IGNORECASE):
        supply_fan = max(1, _count(r"\bVLT\s*®?\s*HVAC Basic Drive\s*FC\s*101\b", text))
    return_fan = 1 if re.search(r"Return Motor Connections|Return Fan Motor", text, re.IGNORECASE) else 0

    damper = len(set(re.findall(r"\bFDA\s*([1-9]\d*)\b", text, re.IGNORECASE)))
    sensors = len(set(re.findall(r"\b(?:TS|DPT)\s*([1-9]\d*)\b", text, re.IGNORECASE)))
    filters = len(set(re.findall(r"\bP\s*([12])\b", text, re.IGNORECASE)))
    module_models = set(re.findall(r"\b(?:POL\d+[.]\d+(?:/STD)?|POL\d+)\b", text, re.IGNORECASE))
    module_count = len(module_models)

    return PdfDiscovery(
        page_count=len(reader.pages),
        order_no=order.group(1).strip() if order else "",
        project_name=project.group(1).strip() if project else "",
        ahu_name=ahu.group(1).strip() if ahu else "",
        supply_fan_count=supply_fan,
        return_fan_count=return_fan,
        damper_count=damper,
        sensor_count=sensors,
        filter_count=filters,
        module_count=module_count,
    )
