from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any

import pymupdf as fitz
import pdfplumber


# POL648.10: terminal identity/capability is used only to validate a PDF match.
# A capability is never shown as the active configuration of a connected pin.
POL648_TERMINAL_MODES = {
    **{f"X{i}": ("Universal I/O",) for i in range(1, 9)},
    **{f"X{i}": ("Universal input",) for i in range(9, 12)},
    "D1": ("Potential-free DI",),
    "D2": ("Potential-free DI",),
    "DU1": ("24 V active DI",),
    "DU2": ("24 V active DI",),
    "Q1": ("Relay output",),
    "Q2": ("Relay output",),
    **{f"Q{i}": ("Relay output",) for i in range(3, 7)},
}

_TERMINAL_RE = re.compile(
    r"(?<![A-Z0-9])(?P<terminal>DU[12]|X(?:[1-9]|1[01])|D[12]|Q[1-6])(?![A-Z0-9])",
    re.IGNORECASE,
)
_MODE_HINTS = (
    (re.compile(r"\b4\s*[-–]\s*20\s*mA\b", re.I), "4–20 mA (analog)"),
    (re.compile(r"\b0\s*[-–]\s*10\s*V\b", re.I), "0–10 V (analog)"),
    (re.compile(r"\bPT\s*1000\b|\bPT1000\b", re.I), "Pt1000 AI"),
    (re.compile(r"\bNI\s*1000\b|\bNI1000\b", re.I), "Ni1000 AI"),
    (re.compile(r"\bNTC\s*10?k?\b|\bNTC100k\b", re.I), "NTC AI"),
    (re.compile(r"\bANALOG\s+INPUT\b|\bAI\b", re.I), "AI"),
    (re.compile(r"\bDIGITAL\s+INPUT\b|\bDI\b|^DI[_\s-]", re.I), "DI"),
    (re.compile(r"\bANALOG\s+OUTPUT\b|\bAO\b", re.I), "AO"),
    (re.compile(r"\bDIGITAL\s+OUTPUT\b|\bDO\b|^DO[_\s-]", re.I), "DO"),
)
_DEFAULT_TYPE = "Tip PDF'de belirtilmemiş"


@dataclass(frozen=True)
class IoConnection:
    terminal: str
    signal: str
    cable: str = ""
    signal_type: str = _DEFAULT_TYPE
    page: int = 0
    confidence: float = 0.0
    source: str = "PDF"


@dataclass(frozen=True)
class _TextItem:
    text: str
    bbox: tuple[float, float, float, float]
    source: str = "PDF"
    confidence: float = 1.0

    @property
    def cx(self) -> float:
        return (self.bbox[0] + self.bbox[2]) / 2

    @property
    def cy(self) -> float:
        return (self.bbox[1] + self.bbox[3]) / 2


@dataclass(frozen=True)
class _Wire:
    x: float
    top: float
    bottom: float


_OCR_ENGINE = None


def _clean_ocr_terminal_text(value: str) -> str:
    """Repair common OCR confusions only where a terminal token is expected."""
    text = value.strip()
    text = re.sub(r"\bX\s*[lI|]\s*0\b", "X10", text, flags=re.I)
    text = re.sub(r"\bX\s*[lI|]\b", "X1", text, flags=re.I)
    text = re.sub(r"\bX\s*([1-9])\b", r"X\1", text, flags=re.I)
    text = re.sub(r"\bD\s*([12])\b", r"D\1", text, flags=re.I)
    text = re.sub(r"\bDU\s*([12])\b", r"DU\1", text, flags=re.I)
    return text


def _text_items(page: fitz.Page) -> list[_TextItem]:
    items: list[_TextItem] = []
    data = page.get_text("dict")
    for block in data.get("blocks", []):
        for line in block.get("lines", []):
            spans = line.get("spans", [])
            # Keep individual spans for exact terminal positions.
            for span in spans:
                text = str(span.get("text", "")).strip()
                bbox = span.get("bbox")
                if text and bbox and len(bbox) == 4:
                    items.append(_TextItem(text, tuple(float(v) for v in bbox)))
            # Also add a whole-line item so labels split across font runs survive.
            if spans:
                line_text = " ".join(
                    str(span.get("text", "")).strip()
                    for span in spans if str(span.get("text", "")).strip()
                ).strip()
                boxes = [span.get("bbox") for span in spans if span.get("bbox")]
                if line_text and boxes:
                    items.append(_TextItem(
                        line_text,
                        (
                            min(float(b[0]) for b in boxes),
                            min(float(b[1]) for b in boxes),
                            max(float(b[2]) for b in boxes),
                            max(float(b[3]) for b in boxes),
                        ),
                    ))
    return items


def _vertical_wires_from_pymupdf(page: fitz.Page) -> list[_Wire]:
    wires: list[_Wire] = []
    try:
        drawings = page.get_cdrawings()
    except Exception:
        drawings = page.get_drawings()
    for drawing in drawings:
        for item in drawing.get("items", []):
            if not item:
                continue
            op = item[0]
            if op == "l" and len(item) >= 3:
                a, b = item[1], item[2]
                try:
                    x1, y1 = float(a[0]), float(a[1])
                    x2, y2 = float(b[0]), float(b[1])
                except (TypeError, ValueError, IndexError):
                    continue
                if abs(x1 - x2) <= 2.5 and abs(y2 - y1) >= 12:
                    wires.append(_Wire((x1 + x2) / 2, min(y1, y2), max(y1, y2)))
            elif op == "re" and len(item) >= 2:
                rect = item[1]
                try:
                    x0, y0, x1, y1 = map(float, rect)
                except (TypeError, ValueError):
                    continue
                if abs(x1 - x0) <= 3 and abs(y1 - y0) >= 16:
                    wires.append(_Wire((x0 + x1) / 2, min(y0, y1), max(y0, y1)))
    return wires


def _vertical_wires_from_pdfplumber(page: Any) -> list[_Wire]:
    """Use pdfplumber's independent vector-edge model as a second geometry source."""
    wires: list[_Wire] = []
    try:
        for edge in page.edges:
            x0 = float(edge.get("x0", 0))
            x1 = float(edge.get("x1", 0))
            top = float(edge.get("top", 0))
            bottom = float(edge.get("bottom", top))
            if abs(x1 - x0) <= 2.5 and abs(bottom - top) >= 12:
                wires.append(_Wire((x0 + x1) / 2, min(top, bottom), max(top, bottom)))
    except Exception:
        pass
    return wires


def _image_coverage(page: fitz.Page) -> float:
    page_area = max(1.0, float(page.rect.width * page.rect.height))
    total = 0.0
    try:
        for info in page.get_image_info(xrefs=True):
            bbox = info.get("bbox")
            if bbox:
                rect = fitz.Rect(bbox) & page.rect
                total += max(0.0, rect.width * rect.height)
    except Exception:
        return 0.0
    return min(1.0, total / page_area)


def _should_run_ocr(page: fitz.Page, text_items: list[_TextItem]) -> bool:
    chars = sum(len(item.text.strip()) for item in text_items)
    image_coverage = _image_coverage(page)
    # OCR scanned/image-based drawings, but avoid OCR on already-readable vector PDFs.
    return chars < 80 or (image_coverage >= 0.08 and chars < 900)


def _get_ocr_engine():
    global _OCR_ENGINE
    if _OCR_ENGINE is None:
        try:
            from rapidocr import RapidOCR
        except ImportError as exc:
            raise RuntimeError(
                "Taranmış PDF sayfalarını okumak için RapidOCR kurulumu bulunamadı."
            ) from exc
        _OCR_ENGINE = RapidOCR()
    return _OCR_ENGINE


def _ocr_page(page: fitz.Page, dpi: int = 260) -> list[_TextItem]:
    """OCR image-only content with the bundled RapidOCR ONNX models."""
    import numpy as np

    pix = page.get_pixmap(dpi=dpi, colorspace=fitz.csRGB, alpha=False)
    image = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
    if pix.n == 4:
        image = image[:, :, :3]
    # RapidOCR accepts an OpenCV-style image array.
    image = image[:, :, ::-1].copy()
    result = _get_ocr_engine()(image)
    if result is None:
        return []

    boxes = getattr(result, "boxes", None)
    texts = getattr(result, "txts", None)
    scores = getattr(result, "scores", None)
    boxes = [] if boxes is None else boxes
    texts = [] if texts is None else texts
    scores = [] if scores is None else scores
    scale = 72.0 / float(dpi)
    items: list[_TextItem] = []
    for index, (box, text) in enumerate(zip(boxes, texts)):
        value = str(text).strip()
        score = float(scores[index]) if index < len(scores) else 0.5
        if not value or score < 0.25:
            continue
        points = list(box)
        xs = [float(point[0]) for point in points]
        ys = [float(point[1]) for point in points]
        bbox = (
            min(xs) * scale,
            min(ys) * scale,
            max(xs) * scale,
            max(ys) * scale,
        )
        items.append(_TextItem(value, bbox, "OCR", score))
    return items


def _terminal_anchors(items: list[_TextItem]) -> list[tuple[str, float, float, tuple[float, float, float, float], _TextItem]]:
    anchors = []
    for item in items:
        candidate = _clean_ocr_terminal_text(item.text)
        for match in _TERMINAL_RE.finditer(candidate):
            terminal = match.group("terminal").upper()
            anchors.append((terminal, item.cx, item.cy, item.bbox, item))

    # PyMuPDF may expose both a span and its enclosing line. Collapse anchors
    # only when the same terminal occupies the same physical point.
    unique = []
    for anchor in sorted(anchors, key=lambda value: (value[0], value[1], value[2])):
        if any(
            old[0] == anchor[0]
            and abs(old[1] - anchor[1]) <= 5
            and abs(old[2] - anchor[2]) <= 5
            for old in unique
        ):
            continue
        unique.append(anchor)
    return unique


def _wires_for_terminal(
    terminal_x: float,
    terminal_y: float,
    wires: list[_Wire],
) -> list[_Wire]:
    candidates = [
        wire for wire in wires
        if abs(wire.x - terminal_x) <= 28
        and wire.bottom > terminal_y
        and wire.top <= terminal_y + 140
    ]
    # Merge duplicate/superimposed edges from the two PDF geometry engines.
    candidates.sort(key=lambda wire: (wire.x, wire.top, wire.bottom))
    merged: list[_Wire] = []
    for wire in candidates:
        match = next((
            old for old in merged
            if abs(old.x - wire.x) <= 2.5
            and not (wire.top > old.bottom + 8 or old.top > wire.bottom + 8)
        ), None)
        if match is None:
            merged.append(wire)
        else:
            merged[merged.index(match)] = _Wire(
                (match.x + wire.x) / 2,
                min(match.top, wire.top),
                max(match.bottom, wire.bottom),
            )
    return merged


def _is_generic_label(value: str) -> bool:
    normalized = re.sub(r"[^A-Z0-9+]", "", value.upper())
    return normalized in {
        "", "M", "GND", "COM", "0V", "24V", "5V", "N", "L", "PE",
        "X1", "X2", "X3", "X4", "X5", "X6", "X7", "X8", "X9",
        "X10", "X11", "D1", "D2", "DU1", "DU2",
    }


def _split_cable_and_signal(value: str) -> tuple[str, str]:
    cleaned = re.sub(r"\s+", " ", value).strip(" \t:;|")
    match = re.match(r"^(\d{1,4})\s*[-:]\s*(.+)$", cleaned)
    if match:
        cable, signal = match.group(1), match.group(2).strip()
    else:
        cable, signal = "", cleaned
    signal = re.sub(r"^(?:DI|AI|DO|AO)\s*[_-]\s*", "", signal, flags=re.I)
    signal = re.sub(r"^(?:DI|AI|DO|AO)\s+", "", signal, flags=re.I)
    return cable, signal.strip()


def _classify_signal(text: str) -> str:
    for pattern, label in _MODE_HINTS:
        if pattern.search(text):
            return label
    return _DEFAULT_TYPE


def _deduplicate(items: list[IoConnection]) -> list[IoConnection]:
    unique: dict[tuple[str, str, str, int], IoConnection] = {}
    for item in items:
        key = (
            item.terminal,
            re.sub(r"\W+", "", item.signal.casefold()),
            item.cable,
            item.page,
        )
        old = unique.get(key)
        if old is None or (item.confidence, item.source == "PDF") > (
            old.confidence, old.source == "PDF"
        ):
            unique[key] = item
    order = {name: index for index, name in enumerate(POL648_TERMINAL_MODES)}
    return sorted(
        unique.values(),
        key=lambda item: (item.page, order.get(item.terminal, 999), item.signal.casefold()),
    )


def discover_pol648_connections(
    pdf_path: str | Path,
    *,
    enable_ocr: bool = True,
    diagnostics: dict[str, Any] | None = None,
) -> list[IoConnection]:
    """Extract only wired POL648 terminals and their labels from an electrical PDF.

    It combines PyMuPDF text/vector extraction, pdfplumber's independent edge
    model, and RapidOCR for scanned/image-based pages. A terminal is returned
    only when a nearby signal label can be associated with its wire position.
    PDF wording determines the signal type; no type is guessed from the pin's
    possible hardware capabilities.
    """
    pdf_path = Path(pdf_path)
    if not pdf_path.is_file():
        raise FileNotFoundError(pdf_path)

    stats = diagnostics if diagnostics is not None else {}
    stats.update({
        "pages_scanned": 0,
        "ocr_pages": [],
        "pdf_text_pages": [],
        "ocr_errors": [],
        "pdfplumber_edges": 0,
        "pymupdf_edges": 0,
    })

    found: list[IoConnection] = []
    doc = fitz.open(str(pdf_path))
    try:
        with pdfplumber.open(str(pdf_path)) as plumber:
            for page_index, page in enumerate(doc, start=1):
                stats["pages_scanned"] += 1
                text_items = _text_items(page)
                if text_items:
                    stats["pdf_text_pages"].append(page_index)

                wires = _vertical_wires_from_pymupdf(page)
                stats["pymupdf_edges"] += len(wires)
                if page_index <= len(plumber.pages):
                    plumber_page = plumber.pages[page_index - 1]
                    extra_wires = _vertical_wires_from_pdfplumber(plumber_page)
                    wires.extend(extra_wires)
                    stats["pdfplumber_edges"] += len(extra_wires)

                if enable_ocr and _should_run_ocr(page, text_items):
                    try:
                        ocr_items = _ocr_page(page)
                        text_items.extend(ocr_items)
                        if ocr_items:
                            stats["ocr_pages"].append({
                                "page": page_index,
                                "text_items": len(ocr_items),
                            })
                    except Exception as exc:
                        stats["ocr_errors"].append({
                            "page": page_index,
                            "error": str(exc),
                        })

                anchors = _terminal_anchors(text_items)
                if not anchors:
                    continue

                # Build a terminal-to-wire map before assigning labels. This
                # prevents a nearby label from drifting to the next terminal.
                terminal_wires: dict[str, list[_Wire]] = {}
                terminal_positions: dict[str, tuple[float, float]] = {}
                for terminal, tx, ty, _bbox, _source in anchors:
                    terminal_wires[terminal] = _wires_for_terminal(tx, ty, wires)
                    terminal_positions[terminal] = (tx, ty)

                numeric_labels: list[tuple[str, str, float, float, float]] = []
                for item in text_items:
                    value = _clean_ocr_terminal_text(item.text)
                    if re.fullmatch(r"\d{1,4}", value):
                        numeric_labels.append((value, item.source, item.confidence, item.cx, item.cy))

                for item in text_items:
                    cleaned = _clean_ocr_terminal_text(item.text)
                    if _TERMINAL_RE.search(cleaned):
                        continue
                    cable, signal = _split_cable_and_signal(cleaned)
                    if not signal or _is_generic_label(signal):
                        continue
                    is_numeric = bool(re.fullmatch(r"\d{1,4}", signal))
                    if is_numeric or len(signal) < 3:
                        continue
                    if not re.search(r"[A-Za-zÀ-ÿ]", signal):
                        continue

                    cx, cy = item.cx, item.cy
                    candidates = []
                    for terminal, tx, ty, _bbox, anchor_item in anchors:
                        dy = cy - ty
                        max_dy = min(float(page.rect.height) * 0.78, 720.0)
                        if dy < -15 or dy > max_dy:
                            continue
                        wires_for_pin = terminal_wires.get(terminal, [])
                        pin_xs = [wire.x for wire in wires_for_pin]
                        reference_x = min(pin_xs, key=lambda x: abs(cx - x)) if pin_xs else tx
                        dx = abs(cx - reference_x)
                        # A drawn vertical wire is stronger evidence than
                        # simple text proximity. Fall back only if no wire exists.
                        tolerance = 22 if pin_xs else 30
                        if dx > tolerance:
                            continue
                        score = dx + max(0.0, dy) * 0.012
                        if pin_xs:
                            score -= 3.0
                        if item.source == "OCR":
                            score += 1.5
                        candidates.append((score, terminal, dy, reference_x))
                    if not candidates:
                        continue
                    candidates.sort(key=lambda entry: entry[0])
                    best_score, terminal, dy, wire_x = candidates[0]
                    if len(candidates) > 1 and abs(candidates[1][0] - best_score) < 2.0:
                        continue

                    # A standalone red cable number is often printed beside
                    # the same conductor before the blue signal description.
                    if not cable:
                        nearby_numbers = [
                            value for value, _src, _conf, nx, ny in numeric_labels
                            if abs(nx - wire_x) <= 16
                            and -6 <= cy - ny <= 180
                        ]
                        if nearby_numbers:
                            cable = min(nearby_numbers, key=lambda value: (abs(cx - wire_x), len(value)))

                    local_context = [cleaned, signal]
                    for context_item in text_items:
                        if context_item is item:
                            continue
                        if abs(context_item.cx - wire_x) <= 28 and abs(context_item.cy - cy) <= 85:
                            local_context.append(context_item.text)
                    signal_type = _classify_signal(" ".join(local_context))
                    confidence = max(0.0, min(1.0, item.confidence - best_score / 100.0))
                    found.append(IoConnection(
                        terminal=terminal,
                        signal=signal,
                        cable=cable,
                        signal_type=signal_type,
                        page=page_index,
                        confidence=confidence,
                        source=item.source,
                    ))
    finally:
        doc.close()

    return _deduplicate(found)
