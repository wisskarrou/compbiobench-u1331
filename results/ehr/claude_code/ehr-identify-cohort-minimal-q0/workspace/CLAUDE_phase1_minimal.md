# CLAUDE.md — Minimal Agent (Autonomy Test)

## Context
You have access to a folder of electronic health records from the
MIMIC-IV demo dataset (version 2.2). The data is in
`physionet.org/files/mimic-iv-demo/2.2/`. Files are gzip-compressed CSVs.

## Task
Explore the dataset to understand its structure, then identify the **2 most
prevalent diseases** in the dataset (by number of unique patients diagnosed).
Once identified, focus all subsequent analysis on those 2 diseases.

Produce a summary report in `outputs_minimal/phase1_minimal_report.md`
describing what you found: which tables are relevant, how the top 2 diseases
were determined, how many patients have these diagnoses, and whether a
survival analysis would be feasible with this data.
