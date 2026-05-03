# CompBioBench — U1331 Edition

A benchmarking framework for evaluating LLM coding agents on computational biology tasks, adapted and extended by the U1331 research unit.

---

## Running the Agents

Three benchmarks are available. Each is run through the same `run_benchmark.py` harness. Before running, authenticate your CLI:

- **Claude:** `claude login`
- **Codex:** `codex auth`

---

### Introductory Benchmark

Taken from the original CompBioBench benchmark developed by the Roche/Genentech teams. The task asks the agent to identify which retinal cell type is inflamed in one eye vs. the other, given raw scRNA count matrices from two eyes of the same individual.

**Run with Claude:**
```bash
claude login
python run_benchmark.py run -i intro_benchmark.csv --llm claude --model claude-opus-4-7 --model-reasoning-effort max
```

**Run with Codex:**
```bash
codex auth
python run_benchmark.py run -i intro_benchmark.csv --llm codex --model gpt-5 --model-reasoning-effort max
```

You can vary `--model` (e.g. `claude-sonnet-4-6`, `gpt-4o`) and `--model-reasoning-effort` (Claude: `low|medium|high|max`; Codex: `minimal|low|medium|high|xhigh`) to compare configurations.

---

### Single-Cell Benchmark

Proposed by U1331 members working on single-cell transcriptomics. The task asks the agent to predict the treatment effect on scRNA-seq data: given the scRNA profile of an untreated patient and the drug–gene associations of a treatment, predict the post-treatment gene expression.

**Run with Claude:**
```bash
claude login
python run_benchmark.py run -i single_cell_benchmark.csv --llm claude --model claude-opus-4-7 --model-reasoning-effort max
```

**Run with Codex:**
```bash
codex auth
python run_benchmark.py run -i single_cell_benchmark.csv --llm codex --model gpt-5 --model-reasoning-effort max
```

You can vary `--model` and `--model-reasoning-effort` to compare configurations.

---

### EHR Benchmark

Proposed by U1331 members working on electronic health records. The tasks ask the agent to analyze a patient cohort and perform survival analysis. Two phases are available: phase 1 (cohort exploration) and phase 2 (survival modeling).

**Run with Claude:**
```bash
claude login
python run_benchmark.py run -i ehr_phase1_benchmark.csv --llm claude --model claude-opus-4-7 --model-reasoning-effort max
python run_benchmark.py run -i ehr_phase2_benchmark.csv --llm claude --model claude-opus-4-7 --model-reasoning-effort max
```

**Run with Codex:**
```bash
codex auth
python run_benchmark.py run -i ehr_phase1_benchmark.csv --llm codex --model gpt-5 --model-reasoning-effort max
python run_benchmark.py run -i ehr_phase2_benchmark.csv --llm codex --model gpt-5 --model-reasoning-effort max
```

You can vary `--model` and `--model-reasoning-effort` to compare configurations.

---

## Analyzing the Results

### Raw Run Output (`results/`)

Every benchmark run writes its output under `results/`, organized by benchmark domain:

```
results/
├── single_cell/     # Raw run outputs for the single-cell benchmark
└── ehr/             # Raw run outputs for the EHR benchmark
```

Each run directory contains per-question subdirectories with the prompt sent to the agent, the agent's answer, a formatted reasoning trace, and raw stdout/stderr logs:

```
results/<domain>/<llm>_<model>_<timestamp>/
├── run_metadata.json
├── benchmark.log
└── questions/
    └── <question_id>/
        ├── prompt.md
        ├── result.json
        ├── trace.md
        ├── raw_stdout.jsonl
        └── raw_stderr.txt
```

### Single-Cell Benchmark Evaluation (`evaluation/single_cell_experiment/`)

Evaluation artifacts for the single-cell benchmark are organized as follows:

```
evaluation/single_cell_experiment/
├── predictions/                  # Agent-generated predicted expression matrices (one file per model run)
├── prediction_scripts/           # Scripts written by the agents to produce their predictions
└── perturbation_eval_results/    # Evaluation metrics and plots comparing predictions to ground truth
```

- **`predictions/`** — each file is the predicted post-treatment expression produced by a model, ready to be compared against ground truth.
- **`prediction_scripts/`** — the actual code the agents wrote and executed to generate their predictions; useful for understanding the agent's reasoning and approach.
- **`perturbation_eval_results/`** — quantitative metrics (Pearson correlation, Wasserstein distance, DEG overlap, etc.) and plots (UMAPs, scatter plots, violin plots) comparing each model's predictions to the ground truth.

To re-run the evaluation on existing predictions:
```bash
python evaluation/single_cell_experiment/evaluate_perturbation.py
```
