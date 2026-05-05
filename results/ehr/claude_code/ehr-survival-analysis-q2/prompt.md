# Prompt: ehr-survival-analysis-q2

| Field | Value |
|-------|-------|
| **Model** | claude-sonnet-4-5 |
| **Timeout** | 120 min |
| **Difficulty** | 4.0 |
| **Original Files** | `data/CLAUDE_phase2_survival.md,data/ehr,data/outputs` |
| **Workspace Files** | `CLAUDE_phase2_survival.md, ehr, outputs` |

## Prompt

```
QUESTION: Answer the request detailed in data/CLAUDE_phase2_survival.md

FILES: CLAUDE_phase2_survival.md, ehr, outputs

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
