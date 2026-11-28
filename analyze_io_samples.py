from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

from io_discovery import discover_pol648_connections


ROOT = Path(__file__).resolve().parent
SAMPLES = ROOT / "examples" / "electrical_projects"
OUT = ROOT / "io_discovery_results"


def main() -> int:
    pdfs = sorted(SAMPLES.rglob("*.pdf"))
    OUT.mkdir(parents=True, exist_ok=True)
    all_rows: list[dict] = []
    summary: list[dict] = []
    if not pdfs:
        print(f"No PDF samples found in {SAMPLES}", file=sys.stderr)
        return 2

    for pdf in pdfs:
        rel = pdf.relative_to(SAMPLES).as_posix()
        diagnostics: dict = {}
        try:
            items = discover_pol648_connections(pdf, diagnostics=diagnostics)
            rows = [{
                "project": rel,
                "terminal": item.terminal,
                "signal_type": item.signal_type,
                "signal": item.signal,
                "cable": item.cable,
                "page": item.page,
                "confidence": round(item.confidence, 3),
                "source": item.source,
            } for item in items]
            all_rows.extend(rows)
            summary.append({
                "project": rel,
                "status": "ok",
                "pages_scanned": diagnostics.get("pages_scanned", 0),
                "pol648_pages": diagnostics.get("pol648_pages", []),
                "connections_found": len(rows),
                "terminals": sorted({row["terminal"] for row in rows}),
                "ocr_pages": diagnostics.get("ocr_pages", []),
                "ocr_errors": diagnostics.get("ocr_errors", []),
                "pdf_text_pages": diagnostics.get("pdf_text_pages", []),
                "geometry": {
                    "pymupdf_vertical_edges": diagnostics.get("pymupdf_edges", 0),
                    "pdfplumber_vertical_edges": diagnostics.get("pdfplumber_edges", 0),
                },
                "connections": rows,
            })
            print(
                f"{rel}: {len(rows)} input candidate(s), "
                f"POL648 page(s)={diagnostics.get('pol648_pages', [])}, "
                f"OCR page(s)={len(diagnostics.get('ocr_pages', []))}"
            )
            for row in rows:
                print(
                    "  {terminal:>4} | {signal_type} | {signal} | "
                    "cable={cable} | page={page} | source={source} | "
                    "confidence={confidence}".format(**row)
                )
        except Exception as exc:
            summary.append({
                "project": rel,
                "status": "error",
                "error": str(exc),
                "diagnostics": diagnostics,
            })
            print(f"{rel}: ERROR: {exc}", file=sys.stderr)

    fields = [
        "project", "terminal", "signal_type", "signal", "cable",
        "page", "confidence", "source",
    ]
    with (OUT / "connections.csv").open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(all_rows)

    payload = {
        "sample_count": len(pdfs),
        "successful_projects": sum(item["status"] == "ok" for item in summary),
        "failed_projects": sum(item["status"] == "error" for item in summary),
        "total_connections": len(all_rows),
        "ocr_connection_count": sum(row["source"] == "OCR" for row in all_rows),
        "projects": summary,
        "method": [
            "PyMuPDF text spans and vector drawings",
            "pdfplumber vector-edge cross-check",
            "RapidOCR ONNX for scanned/image-based pages",
        ],
        "warning": (
            "These are PDF-derived candidates only. They are not verified PLC "
            "runtime values or confirmed terminal configuration."
        ),
    }
    (OUT / "results.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    lines = [
        "# POL648.10 PDF I/O discovery",
        "",
        f"- PDFs scanned: {payload['sample_count']}",
        f"- Projects read: {payload['successful_projects']}",
        f"- Read errors: {payload['failed_projects']}",
        f"- Candidate input connections: {payload['total_connections']}",
        f"- OCR-sourced labels: {payload['ocr_connection_count']}",
        "",
        "| Project | Page | Terminal | PDF type | Connected signal | Cable | Source | Confidence |",
        "|---|---:|---|---|---|---|---|---:|",
    ]
    for row in all_rows:
        safe = lambda value: str(value).replace("|", "\\|").replace("\n", " ")
        lines.append(
            "| " + " | ".join(safe(row[key]) for key in (
                "project", "page", "terminal", "signal_type", "signal",
                "cable", "source", "confidence",
            )) + " |"
        )
    lines.extend([
        "",
        "Unknown signal types remain explicitly unclassified; terminal capabilities are not treated as the active configuration.",
        "",
        "Compare each row against the original drawing before treating it as correct.",
    ])
    (OUT / "REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(
        f"SUMMARY: {payload['sample_count']} PDFs, "
        f"{payload['total_connections']} connections, "
        f"{payload['failed_projects']} errors"
    )
    return 1 if payload["failed_projects"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
