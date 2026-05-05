# Prompt: predict-treatment-effect-q1

| Field | Value |
|-------|-------|
| **Model** | claude-opus-4-6 |
| **Timeout** | 120 min |
| **Difficulty** | 4.0 |
| **Original Files** | `data/Larsson_data/Sample4,data/Larsson_data/Sample1,data/pubchem_cid_5394_consolidatedcompoundtarget.json` |
| **Workspace Files** | `Sample4, Sample1, pubchem_cid_5394_consolidatedcompoundtarget.json` |

## Prompt

```
QUESTION: Knowing the single-cell RNA-seq of the patient at day zero (data/Larsson_data/Sample4), the scRNA-seq of the untreated patient at day 8 (data/Larsson_data/Sample1) and drug-target interactions of Temozolomide (data/pubchem_cid_5394_consolidatedcompoundtarget.json), predict the scRNA-seq of the patient treated with Temozolomide at day 9

FILES: Sample4, Sample1, pubchem_cid_5394_consolidatedcompoundtarget.json

Note: All files are located in your current working directory (workspace).

INSTRUCTIONS:
- You have 120 minutes to complete this task
- Do not read/access any other files outside the workspace.
- Get any files or tools you need from the internet.
- You are free to modify the current conda environment as needed.
- Keep all scripts and intermediate data in the workspace only.

OUTPUT CONTRACT (IMPORTANT):
- Your final response will be graded by exact string match.
- Return EXACTLY ONE LINE containing **ONLY** the final answer in the format required by the question.
- Do NOT include any explanation, reasoning, labels, prefixes, markdown, code fences, citations, or extra whitespace lines.
- Any extra text before or after the answer is incorrect.
- Before sending your final response, verify it is exactly one line and nothing else.

```
