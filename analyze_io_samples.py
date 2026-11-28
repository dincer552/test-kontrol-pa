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
    all_rows = []
    summary = []
    for pdf in pdfs:
        rel = pdf.relative_to(SAMPLES).as_posix()
        try:
            items = discover_pol648_connections(pdf)
            rows = [{
                "project": rel,
                "terminal": item.terminal,
                "signal_type": item.signal_type,
                "signal": item.signal,
                "cable": item.cable,
                "page": item.page,
            } for item in items]
            all_rows.extend(rows)
            summary.append({
                "project": rel,
                "status": "ok",
                "connections_found": len(rows),
                "terminals": sorted({row["terminal"] for row in rows}),
                "connections": rows,
            })
            print(f"{rel}: {len(rows)} connection(s)")
            for row in rows:
                print("  {terminal:>4} | {signal_type} | {signal} | cable={cable} | page={page}".format(**row))
        except Exception as exc:
            summary.append({"project": rel, "status": "error", "error": str(exc)})
            print(f"{rel}: ERROR: {exc}", file=sys.stderr)

    with (OUT / "connections.csv").open("w", newline="", encoding="utf-8-sig") as stream:
        fields = ["project", "terminal", "signal_type", "signal", "cable", "page"]
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(all_rows)

    payload = {
        "sample_count": len(pdfs),
        "successful_projects": sum(item["status"] == "ok" for item in summary),
        "failed_projects": sum(item["status"] == "error" for item in summary),
        "total_connections": len(all_rows),
        "projects": summary,
        "warning": "PDF text/geometry discovery only. No physical I/O state or controller configuration is inferred.",
    }
    (OUT / "results.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"SUMMARY: {payload['sample_count']} PDFs, {payload['total_connections']} connections, {payload['failed_projects']} errors")
    return 1 if payload["failed_projects"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
