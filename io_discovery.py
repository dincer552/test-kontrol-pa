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
    r"(?<![A-Z0-9])(?P<terminal>DU\s*[12]|X\s*(?:[1-9]|1[01])|D\s*[12])(?![A-Z0-9])",
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
    char_boxes: tuple[tuple[float, float, float, float] | None, ...] = ()

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
    data = page.get_text("rawdict")
    for block in data.get("blocks", []):
        for line in block.get("lines", []):
            spans = line.get("spans", [])
            line_text_parts: list[str] = []
            line_char_boxes: list[tuple[float, float, float, float] | None] = []
            line_boxes: list[tuple[float, float, float, float]] = []

            for span_index, span in enumerate(spans):
                chars = span.get("chars", [])
                if chars:
                    text = "".join(str(char.get("c", "")) for char in chars)
                    boxes = tuple(
                        tuple(float(v) for v in char.get("bbox", (0, 0, 0, 0)))
                        if char.get("bbox") else None
                        for char in chars
                    )
                    valid_boxes = [box for box in boxes if box is not None]
                    if text and valid_boxes:
                        items.append(_TextItem(
                            text,
                            (
                                min(box[0] for box in valid_boxes),
                                min(box[1] for box in valid_boxes),
                                max(box[2] for box in valid_boxes),
                                max(box[3] for box in valid_boxes),
                            ),
                            char_boxes=boxes,
                        ))
                    line_text_parts.append(text)
                    line_char_boxes.extend(boxes)
                    line_boxes.extend(valid_boxes)
                else:
                    text = str(span.get("text", "")).strip()
                    bbox = span.get("bbox")
                    if text and bbox and len(bbox) == 4:
                        box = tuple(float(v) for v in bbox)
                        items.append(_TextItem(text, box))
                        line_text_parts.append(text)
                        line_char_boxes.extend([box] * len(text))
                        line_boxes.append(box)

                if span_index < len(spans) - 1:
                    line_text_parts.append(" ")
                    line_char_boxes.append(None)

            raw_line_text = "".join(line_text_parts)
            line_text = raw_line_text.strip()
            if line_text and line_boxes:
                trim_offset = len(raw_line_text) - len(raw_line_text.lstrip())
                aligned_char_boxes = tuple(
                    line_char_boxes[trim_offset:trim_offset + len(line_text)]
                )
                items.append(_TextItem(
                    line_text,
                    (
                        min(box[0] for box in line_boxes),
                        min(box[1] for box in line_boxes),
                        max(box[2] for box in line_boxes),
                        max(box[3] for box in line_boxes),
                    ),
                    char_boxes=aligned_char_boxes if len(aligned_char_boxes) == len(line_text) else (),
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


def _ocr_page(page: fitz.Page, dpi: int = 300, rotation: int = 0) -> list[_TextItem]:
    """Read a drawing with RapidOCR using original and enhanced image variants.

    The vector/text path remains primary. These image passes are used only for
    scanned or image-heavy controller sheets. All variants keep the same pixel
    dimensions so OCR boxes map back to the original PDF coordinates.
    """
    import cv2
    import numpy as np

    pix = page.get_pixmap(dpi=dpi, colorspace=fitz.csRGB, alpha=False)
    rgb = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
    if pix.n == 4:
        rgb = rgb[:, :, :3]
    bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    original_width, original_height = pix.width, pix.height
    rotation = rotation % 360
    if rotation == 90:
        bgr = cv2.rotate(bgr, cv2.ROTATE_90_COUNTERCLOCKWISE)
    elif rotation == 270:
        bgr = cv2.rotate(bgr, cv2.ROTATE_90_CLOCKWISE)
    elif rotation == 180:
        bgr = cv2.rotate(bgr, cv2.ROTATE_180)
    elif rotation != 0:
        raise ValueError("OCR rotation must be 0, 90, 180, or 270 degrees.")

    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    # Engineering drawings often contain pale grey CAD text and thin wires.
    # CLAHE improves local contrast; adaptive threshold helps faint scans.
    clahe = cv2.createCLAHE(clipLimit=2.2, tileGridSize=(8, 8)).apply(gray)
    sharpen_kernel = np.array(
        [[0, -1, 0], [-1, 5, -1], [0, -1, 0]], dtype=np.float32
    )
    sharpened = cv2.filter2D(clahe, -1, sharpen_kernel)
    adaptive = cv2.adaptiveThreshold(
        clahe, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY, 31, 11,
    )
    variants = (
        ("original", bgr),
        ("contrast_sharpen", cv2.cvtColor(sharpened, cv2.COLOR_GRAY2BGR)),
        ("adaptive_threshold", cv2.cvtColor(adaptive, cv2.COLOR_GRAY2BGR)),
    )

    engine = _get_ocr_engine()
    scale = 72.0 / float(dpi)
    detected: list[_TextItem] = []
    errors: list[str] = []
    for variant_name, image in variants:
        try:
            result = engine(image)
        except Exception as exc:
            errors.append(f"{variant_name}: {exc}")
            continue
        if result is None:
            continue

        boxes = getattr(result, "boxes", None)
        texts = getattr(result, "txts", None)
        scores = getattr(result, "scores", None)
        if boxes is None:
            boxes = []
        if texts is None:
            texts = []
        if scores is None:
            scores = []
        for index, (box, text) in enumerate(zip(boxes, texts)):
            value = str(text).strip()
            score = float(scores[index]) if index < len(scores) else 0.5
            if not value or score < 0.30:
                continue
            points = []
            for point in list(box):
                x, y = float(point[0]), float(point[1])
                if rotation == 90:
                    x, y = original_width - y, x
                elif rotation == 270:
                    x, y = y, original_height - x
                elif rotation == 180:
                    x, y = original_width - x, original_height - y
                points.append((x, y))
            xs = [point[0] for point in points]
            ys = [point[1] for point in points]
            bbox = (
                max(0.0, min(xs)) * scale,
                max(0.0, min(ys)) * scale,
                min(float(original_width), max(xs)) * scale,
                min(float(original_height), max(ys)) * scale,
            )
            detected.append(_TextItem(value, bbox, "OCR", score))

    if not detected and errors:
        raise RuntimeError("; ".join(errors))

    # Multi-pass OCR sees the same text more than once. Keep the strongest
    # recognition at each location, but preserve repeated labels elsewhere.
    detected.sort(key=lambda item: item.confidence, reverse=True)
    unique: list[_TextItem] = []
    for item in detected:
        normalized = re.sub(r"[^A-Z0-9]", "", item.text.upper())
        if not normalized:
            continue
        duplicate = any(
            normalized == re.sub(r"[^A-Z0-9]", "", old.text.upper())
            and abs(item.cx - old.cx) <= 10
            and abs(item.cy - old.cy) <= 10
            for old in unique
        )
        if not duplicate:
            unique.append(item)
    return unique

def _terminal_anchors(items: list[_TextItem]) -> list[tuple[str, float, float, tuple[float, float, float, float], _TextItem]]:
    anchors = []
    for item in items:
        candidate = _clean_ocr_terminal_text(item.text)
        for match in _TERMINAL_RE.finditer(candidate):
            terminal = re.sub(r"\s+", "", match.group("terminal")).upper()
            bbox = item.bbox
            # Character boxes separate X1 and X2 even when CAD exports a
            # complete terminal row as one text span.
            if item.char_boxes and len(item.char_boxes) == len(item.text):
                selected = [
                    box for box in item.char_boxes[match.start():match.end()]
                    if box is not None
                ]
                if selected:
                    bbox = (
                        min(box[0] for box in selected),
                        min(box[1] for box in selected),
                        max(box[2] for box in selected),
                        max(box[3] for box in selected),
                    )
            anchor_item = _TextItem(
                match.group("terminal"), bbox, item.source, item.confidence
            )
            anchors.append((
                terminal,
                (bbox[0] + bbox[2]) / 2,
                (bbox[1] + bbox[3]) / 2,
                bbox,
                anchor_item,
            ))

    # Collapse overlapping matches from a span and its enclosing line.
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
        and wire.top <= terminal_y + 180
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


_NOISE_LABELS = {
    "APPR", "APPROVED", "DATE", "ED", "ORIGINAL", "DRAWN", "CHECKED",
    "ONAYLAYAN", "TARIH", "ÇIZEN", "HARUN PAK", "YUSUF UÇAR",
    "SYSTEMAIR", "TEGETA OFFICE", "GENERAL RUN", "GENERAL ALARM",
    "SPARE", "ILLUMINATION",
}


def _is_generic_label(value: str) -> bool:
    cleaned = re.sub(r"^[-+\s]+", "", value).strip()
    normalized = re.sub(r"[^A-Z0-9+]", "", cleaned.upper())
    if normalized in {
        "", "M", "GND", "COM", "0V", "24V", "5V", "N", "L", "PE",
        "DIP", "G+", "SLCH", "LIHCH", "POL648A", "POL648B",
        "24V", "24VAC", "24VDC", "24VACDC", "230VAC", "230V",
    }:
        return True
    # Supply rails and voltage legends are not connected I/O signal names.
    if re.fullmatch(
        r"\d+(?:[.,]\d+)?\s*V(?:\s*(?:AC|DC)(?:\s*/\s*(?:AC|DC))?)?",
        cleaned, re.I,
    ):
        return True
    normalized_noise = re.sub(r"[^A-Z0-9]", "", cleaned.upper())
    known_noise = {
        re.sub(r"[^A-Z0-9]", "", item.upper())
        for item in _NOISE_LABELS
    }
    if normalized_noise in known_noise:
        return True
    if re.fullmatch(r"\d{2}[A-Z]{2,}\d{2,}", cleaned, re.I):
        return True
    if re.match(r"^(?:W|R|U|TS|HA)\d", cleaned, re.I):
        return True
    if re.match(r"^(?:POL648|AHU[_ -]?\d|DAV[_ -]THF)", cleaned, re.I):
        return True
    if re.search(r"(?:fax:|tel:|www\.|https?://|@)", cleaned, re.I):
        return True
    if re.search(r"\b\d+(?:[.,]\d+)?\s*(?:kw|w)\b|mm[²2]", cleaned, re.I):
        return True
    signal_terms = r"SW|SWITCH|ALARM|EMERGENCY|STOP|FIRE|PHASE|FEEDBACK|TEMP|TEMPERATURE|HUM|CO2|PRESS|FILTER|VALVE|SENSOR|CONTROL|ROTARY|FROST|FRST"
    if len(cleaned.split()) >= 3 and not re.search(signal_terms, cleaned, re.I):
        return True
    return False


def _split_cable_and_signal(value: str) -> tuple[str, str]:
    cleaned = re.sub(r"\s+", " ", value).strip(" \t:;|")
    match = re.match(r"^(\d{1,4})\s*[-:]\s*(.+)$", cleaned)
    if match:
        cable, signal = match.group(1), match.group(2).strip()
    else:
        cable, signal = "", cleaned
    signal = re.sub(r"^(?:DI|AI|DO|AO)\s*[_-]\s*", "", signal, flags=re.I)
    signal = re.sub(r"^(?:DI|AI|DO|AO)\s+", "", signal, flags=re.I)
    signal = re.sub(r"^-(?=[A-Za-zÀ-ÿ])", "", signal)
    return cable, signal.strip()


def _classify_signal(text: str, terminal: str = "") -> str:
    upper = text.upper()
    if terminal in {"D1", "D2", "DU1", "DU2"}:
        return "DI"
    # Explicit electrical notation takes precedence over semantic label hints.
    for pattern, label in _MODE_HINTS:
        if pattern.search(text):
            if label == "DI":
                return "DI"
            if label.startswith("4–20") or label.startswith("0–10") or label.endswith("AI"):
                return "AI"
            if label == "AO" or label.startswith("Analog output"):
                return "AO"
            if label == "DO":
                return "DO"
    if re.search(r"(?:^|[_\s-])SW(?:[_\s-]|$)|SWITCH|ALARM|EMERGENCY|STOP|FIRE|PHASE PROTECTION|FILTER|FRST", upper):
        return "DI"
    if re.search(r"(?:^|[_\s-])FEEDBACK(?:[_\s-]|$)|CO2|HUM(?:IDITY)?|TEMP|TEMPERATURE|PRESSURE|SENSOR", upper):
        return "AI"
    if re.search(r"VALVE[_ ]?POS|ACTUATOR|COMMAND|(?:^|[_\s-])CONTROL(?:[_\s-]|$)", upper):
        return "AO"
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
        "pol648_pages": [],
        "ocr_preprocessing": [
            "original RGB-to-BGR render",
            "CLAHE local contrast + sharpening",
            "adaptive Gaussian threshold",
        ],
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

                page_text = page.get_text("text")
                controller_found = bool(re.search(r"POL\s*648", page_text, re.I))
                ocr_items: list[_TextItem] = []
                ocr_attempted = False
                should_ocr = enable_ocr and _should_run_ocr(page, text_items)

                # On text-based drawings, skip OCR entirely for unrelated sheets.
                # On image-only pages, one normal pass is used to look for the
                # POL648 title; rotated passes are reserved for confirmed controller
                # pages so a large multi-page project does not OCR every sheet thrice.
                if not controller_found and should_ocr:
                    try:
                        ocr_items = _ocr_page(page)
                        ocr_attempted = True
                        text_items.extend(ocr_items)
                        controller_found = bool(re.search(
                            r"POL\s*648",
                            " ".join(item.text for item in ocr_items),
                            re.I,
                        ))
                        # A fully scanned page may itself be rotated.
                        if not controller_found and not page_text.strip():
                            for rotation in (90, 270):
                                rotated_items = _ocr_page(page, rotation=rotation)
                                if rotated_items:
                                    text_items.extend(rotated_items)
                                    controller_found = bool(re.search(
                                        r"POL\s*648",
                                        " ".join(item.text for item in rotated_items),
                                        re.I,
                                    ))
                                if controller_found:
                                    break
                    except Exception as exc:
                        stats["ocr_errors"].append({
                            "page": page_index,
                            "error": str(exc),
                        })

                if not controller_found:
                    continue
                stats["pol648_pages"].append(page_index)

                if should_ocr:
                    try:
                        if not ocr_attempted:
                            ocr_items = _ocr_page(page)
                            text_items.extend(ocr_items)
                        rotations_used = [0] if ocr_items else []
                        if not _terminal_anchors(text_items) or len(ocr_items) < 8:
                            for rotation in (90, 270):
                                rotated_items = _ocr_page(page, rotation=rotation)
                                if rotated_items:
                                    text_items.extend(rotated_items)
                                    rotations_used.append(rotation)
                        if rotations_used:
                            stats["ocr_pages"].append({
                                "page": page_index,
                                "text_items": len(ocr_items),
                                "rotations": rotations_used,
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
                terminal_wires: dict[str, list[_Wire]] = {
                    terminal: [] for terminal, _tx, _ty, _bbox, _source in anchors
                }
                terminal_positions: dict[str, tuple[float, float]] = {
                    terminal: (tx, ty)
                    for terminal, tx, ty, _bbox, _source in anchors
                }
                # Each physical conductor belongs to its nearest terminal
                # anchor only. Without this global assignment, two close
                # terminals can both claim the same vertical wire.
                for wire in wires:
                    wire_candidates = []
                    for terminal, tx, ty, _bbox, _source in anchors:
                        if wire.bottom <= ty or wire.top > ty + 180:
                            continue
                        dx = abs(wire.x - tx)
                        if dx <= 28:
                            wire_candidates.append((dx, terminal))
                    if wire_candidates:
                        wire_candidates.sort(key=lambda entry: entry[0])
                        if (
                            len(wire_candidates) == 1
                            or wire_candidates[1][0] - wire_candidates[0][0] > 1.5
                        ):
                            terminal_wires[wire_candidates[0][1]].append(wire)

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
                        if abs(context_item.cx - wire_x) <= 14 and abs(context_item.cy - cy) <= 85:
                            local_context.append(context_item.text)
                    signal_type = _classify_signal(" ".join(local_context), terminal)
                    if signal_type in {"AO", "DO"}:
                        continue
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
