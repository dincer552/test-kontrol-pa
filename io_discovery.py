from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

import fitz


# Siemens POL648.10 capability reference. These are possible modes, not
# assumed active modes; the PDF wiring determines which terminal is used.
POL648_TERMINAL_MODES = {
    **{f"X{i}": ("N", "Ni", "Pt", "R", "V in", "mA in", "DIx", "V out") for i in range(1, 9)},
    **{f"X{i}": ("N", "Ni", "Pt", "DI") for i in range(9, 12)},
    "D1": ("DI",),
    "D2": ("DIp",),
    "DU1": ("DG (24 V aktif DI)",),
    "DU2": ("DG (24 V aktif DI)",),
    "Q1": ("DS röle (NO/NC)",),
    "Q2": ("DS röle (NO/NC)",),
    **{f"Q{i}": ("DO röle (NO)",) for i in range(3, 7)},
}

_MODE_HINTS = (
    (re.compile(r"\b4\s*[-–]\s*20\s*mA\b|\b20\s*mA\b", re.I), "4–20 mA AI"),
    (re.compile(r"\b0\s*[-–]\s*10\s*V\b|\b0\s*[-–]\s*10V\b", re.I), "0–10 V AI"),
    (re.compile(r"\bPT\s*1000\b|\bPT1000\b", re.I), "Pt1000 AI"),
    (re.compile(r"\bNI\s*1000\b|\bNI1000\b", re.I), "Ni1000 AI"),
    (re.compile(r"\bNTC\s*10?k?\b|\bNTC100k\b", re.I), "NTC AI"),
    (re.compile(r"\bDI\b|\bDIGITAL INPUT\b|\bPOTENTIAL[- ]FREE\b", re.I), "DI"),
    (re.compile(r"\bDO\b|\bDIGITAL OUTPUT\b", re.I), "DO"),
    (re.compile(r"\b0\s*[-–]\s*10\s*V\s*OUT\b|\bAO\b", re.I), "Analog output"),
)

@dataclass(frozen=True)
class IoConnection:
    terminal: str
    signal: str
    cable: str = ""
    signal_type: str = "PDF bağlantısı bulundu; elektriksel tip belirtilmemiş"
    page: int = 0


def _span_items(page: fitz.Page):
    data = page.get_text("dict")
    for block in data.get("blocks", []):
        for line in block.get("lines", []):
            direction = line.get("dir", (1, 0))
            for span in line.get("spans", []):
                text = str(span.get("text", "")).strip()
                if text:
                    yield text, span.get("bbox", (0, 0, 0, 0)), direction


def _classify_signal(text: str) -> str:
    for pattern, label in _MODE_HINTS:
        if pattern.search(text):
            return label
    return "PDF bağlantısı bulundu; elektriksel tip belirtilmemiş"


def discover_pol648_connections(pdf_path: str | Path) -> list[IoConnection]:
    """Extract wired POL648 terminal labels from PDF text geometry.

    A signal is associated only when a terminal label and a signal/cable label
    occur on the same page and their text anchors are close horizontally.
    No unused terminal or hypothetical hardware channel is emitted.
    """
    doc = fitz.open(str(pdf_path))
    found: dict[tuple[str, str, str, int], IoConnection] = {}
    try:
        for page_index, page in enumerate(doc, start=1):
            spans = list(_span_items(page))
            terminals = []
            for text, bbox, direction in spans:
                match = re.fullmatch(r"\s*(X(?:[1-9]|1[01])|D[12]|DU[12]|Q[1-6])\s*", text, re.I)
                if match:
                    terminal = match.group(1).upper()
                    terminals.append((terminal, (bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2, bbox))

            if not terminals:
                continue

            for text, bbox, direction in spans:
                cleaned = re.sub(r"\s+", " ", text).strip()
                if len(cleaned) < 3 or re.fullmatch(r"(?:X(?:[1-9]|1[01])|D[12]|DU[12]|Q[1-6])", cleaned, re.I):
                    continue
                # Ignore drawing frame labels, page numbers and generic symbols.
                if not re.search(r"[A-Za-z]", cleaned) or re.fullmatch(r"(?:M|GND|COM|0V|24V|5V|N|L|PE)", cleaned, re.I):
                    continue
                cx = (bbox[0] + bbox[2]) / 2
                cy = (bbox[1] + bbox[3]) / 2
                candidates = []
                for terminal, tx, ty, tb in terminals:
                    dx = abs(cx - tx)
                    dy = cy - ty
                    # Terminal label sits at the connector; connected wire
                    # descriptions are normally below it on the same x-axis.
                    if dx <= 24 and -8 <= dy <= min(360, page.rect.height * 0.65):
                        candidates.append((dx + max(0, dy) * 0.025, terminal))
                if not candidates:
                    continue
                candidates.sort()
                terminal = candidates[0][1]
                # Extract a leading wire/cable number where present.
                cable_match = re.match(r"^\s*(\d{1,4})\s*[-:]\s*(.+)$", cleaned)
                cable = cable_match.group(1) if cable_match else ""
                signal = cable_match.group(2).strip() if cable_match else cleaned
                if not signal or len(signal) < 3:
                    continue
                # Avoid treating the terminal's own electrical symbols as a wire label.
                if signal.upper() in {"N", "NI", "PT", "DI", "DIx", "VIN", "MA IN", "VOUT", "M"}:
                    continue
                item = IoConnection(
                    terminal=terminal,
                    signal=signal,
                    cable=cable,
                    signal_type=_classify_signal(cleaned),
                    page=page_index,
                )
                found[(terminal, signal.casefold(), cable, page_index)] = item
    finally:
        doc.close()

    order = {name: i for i, name in enumerate(POL648_TERMINAL_MODES)}
    return sorted(found.values(), key=lambda item: (item.page, order.get(item.terminal, 999), item.signal.casefold()))
