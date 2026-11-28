# Electrical project samples

This folder contains the PDF electrical projects used to validate POL648.10 terminal discovery.

- `AHU-01.pdf` and `AHU_01_root.pdf`: root-level source PDFs moved here without changing their bytes.
- `AHU_01/` through `AHU_04/`: individual AHU project samples.
- `mer/`: additional MER AHU_02 and AHU_03 samples.

Run the repeatable extraction from the repository root:

```bash
python analyze_io_samples.py
```

The script writes `io_discovery_results/results.json` and `connections.csv`.
A discovered row means the current PDF text/geometry heuristic associated a label with a POL648 terminal; it is not yet a verified electrical truth. Compare each result with the actual drawing before treating it as correct.

The controller's supported terminal classes must be read from Siemens POL648.10 documentation. The PDF determines what is wired in a specific project; it does not automatically prove the configured channel mode when the drawing omits that detail.
