# Electrical project samples

This folder contains the electrical PDF samples used to validate Siemens POL648.10 input discovery.

- `AHU-01.pdf` and `AHU_01_root.pdf`: root-level source PDFs moved here without changing their bytes.
- `AHU_01/` through `AHU_04/`: individual AHU project samples.
- `mer/`: MER AHU and DAV_THF project samples.

Run the repeatable extraction from the repository root:

```bash
python analyze_io_samples.py
```

The discovery pipeline uses:
- PyMuPDF for character-level text coordinates and vector wire geometry.
- pdfplumber as a second vector-edge/text-position source.
- RapidOCR + ONNX Runtime for image-only or scanned pages, including rotated label passes.

The extraction first identifies a page containing a POL648 controller label, then checks only its input-capable terminal labels (X1–X11, D1/D2 and DU1/DU2). Output terminals and unrelated field-device sheets are excluded. Title-block names, drawing metadata, cable references and component tags are filtered to reduce false matches.

The script writes `io_discovery_results/results.json`, `connections.csv` and `REPORT.md`. Each row shows the source PDF, page, terminal, signal label, type candidate, cable number, source and confidence score.

A result is still a PDF-derived candidate, not a verified electrical fact. DI/AI classification is shown only when explicit electrical notation or a recognizable signal label supports it; unknown labels remain unclassified. Compare each row with the original drawing before treating it as correct. The PDF does not always prove the active configuration of a universal X1–X8 channel.


Regression tests cover adjacent X1/X2 terminal labels, non-POL648 field-device sheets, and DI/AI versus output-label filtering.
