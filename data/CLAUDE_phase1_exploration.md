# CLAUDE.md — Phase 1: Data Grounding & Exploration
# Top-2 Most Prevalent Disease Cohort — MIMIC-IV Demo v2.2

---

## Your Role
You are a biomedical data analyst. Your task in this phase is NOT to run any
analysis yet. Your only goal is to **explore and profile the 4 tables needed
for the survival analysis**, then produce a structured report that will be
used as verified context for Phase 2.

Be rigorous and transparent. Print intermediate results after every sub-step.
If something is unexpected (e.g. very small cohort, missing columns, encoding
issues), flag it explicitly with a ⚠️ warning.

---

## Data Location & Format
All files are gzip-compressed CSV files (.csv.gz). Load them with:
```python
import pandas as pd
df = pd.read_csv("path/to/file.csv.gz", compression="gzip")
```

### Files to use in this phase (and ONLY these)
| Variable name | Path | Description |
|---|---|---|
| `patients` | `hosp/patients.csv.gz` | One row per patient — demographics + death date |
| `admissions` | `hosp/admissions.csv.gz` | One row per hospital admission |
| `diagnoses_icd` | `hosp/diagnoses_icd.csv.gz` | Diagnoses per admission (ICD-9 & ICD-10) |
| `d_icd_diagnoses` | `hosp/d_icd_diagnoses.csv.gz` | ICD code lookup table (human-readable labels) |

---

## Known Schema (verify against actual data)
These column names were confirmed in prior exploration. Verify they exist
exactly as written — column names are case-sensitive.

### patients.csv.gz
`subject_id`, `gender`, `anchor_age`, `anchor_year`, `anchor_year_group`, `dod`
> ⚠️ Note: age is stored as `anchor_age`, NOT `age`. `dod` (date of death)
> is expected to be missing for ~69% of patients (they were censored / alive
> at last contact). This is NORMAL — do not treat it as a data quality issue.

### admissions.csv.gz
`subject_id`, `hadm_id`, `admittime`, `dischtime`, `deathtime`,
`admission_type`, `admit_provider_id`, `admission_location`,
`discharge_location`, `insurance`, `language`, `marital_status`, `race`,
`edregtime`, `edouttime`, `hospital_expire_flag`
> ⚠️ Note: There are TWO death-related columns across tables:
> - `deathtime` (in admissions): death during that specific admission (~94.5% missing)
> - `dod` (in patients): overall date of death (~69% missing)
> For survival analysis, use `dod` from patients as the primary outcome.
> Use `hospital_expire_flag` as a secondary binary outcome check.

### diagnoses_icd.csv.gz
`subject_id`, `hadm_id`, `seq_num`, `icd_code`, `icd_version`
> ⚠️ Note: `icd_version` is either 9 or 10 (integer). Both coexist in this
> table. Always filter by BOTH `icd_code` AND `icd_version` together to avoid
> matching the wrong version.

### d_icd_diagnoses.csv.gz
`icd_code`, `icd_version`, `long_title`
> ⚠️ Note: One `icd_code` can have DIFFERENT descriptions depending on
> `icd_version`. Always join on BOTH columns: `icd_code` + `icd_version`.

---

## Step-by-Step Exploration Tasks

### STEP 1 — Load and verify all 4 tables
For each table:
1. Load the file
2. Print: shape (rows × columns)
3. Print: list of column names
4. Assert that the expected columns (from schema above) are all present
5. If any expected column is MISSING → print a ⚠️ warning and stop

```
Expected output example:
  patients.csv.gz → shape: (100, 6) ✓
  Columns: subject_id, gender, anchor_age, anchor_year, anchor_year_group, dod ✓
```

---

### STEP 2 — Profile `patients.csv.gz`
Report the following statistics:
- Total number of patients
- Gender distribution: count and % for each value
- `anchor_age`: min, max, mean, median, std
- `dod` missingness: count missing, count non-missing, % missing
- `anchor_year_group`: value counts (to understand the time period)

---

### STEP 3 — Profile `admissions.csv.gz`
Report the following:
- Total admissions and unique patients
- Average number of admissions per patient (total_admissions / unique_patients)
- `admission_type`: value counts
- `hospital_expire_flag`: count of 0 vs 1, and % of in-hospital deaths
- `deathtime` missingness: count missing and % missing
- Date range of admissions: min and max of `admittime`

---

### STEP 4 — Discover the 2 most prevalent diseases in `diagnoses_icd.csv.gz`
This is the most critical step. Proceed carefully.

**4a. ICD version breakdown**
- Count rows where `icd_version == 9` vs `icd_version == 10`
- Report % of each version

**4b. Join diagnoses with the lookup table**
- Join `diagnoses_icd` with `d_icd_diagnoses` on BOTH `icd_code` AND
  `icd_version` to obtain human-readable `long_title` for every diagnosis row.
- If any rows fail to match, report the count and a ⚠️ warning.

**4c. Rank diseases by patient prevalence**
- For each unique (`icd_code`, `icd_version`) pair, count the number of
  **unique `subject_id`** values (= number of distinct patients with that code).
- Sort descending by patient count.
- Print the top 10 results as a table: rank, `icd_code`, `icd_version`,
  `long_title`, patient count.
- **Select the top 2 as Disease A and Disease B** for all subsequent steps.

> ⚠️ IMPORTANT: If two codes have the same patient count at rank 2/3 boundary,
> break the tie by selecting the code with the higher total row count in
> `diagnoses_icd`. Report any tie-breaking applied.

**4d. Profile Disease A and Disease B cohorts**
For each of Disease A and Disease B:
- Report the exact `icd_code`, `icd_version`, and `long_title`
- Count of diagnosis rows in `diagnoses_icd`
- Count of unique patients (`subject_id`)

**4e. Overlap check**
- Are there any patients diagnosed with BOTH Disease A and Disease B? Report count.
- These patients will need special handling in Phase 2.

**4f. seq_num distribution**
- For the Disease A and Disease B rows, what is the distribution of `seq_num`?
- How many of these are primary diagnoses (`seq_num == 1`)?

> ⚠️ IMPORTANT: With only 100 patients total, verify that each disease cohort
> is large enough for survival analysis. If fewer than 10 patients are found
> for either disease, print a ⚠️ warning:
> "Cohort may be too small for reliable survival analysis — results will be
> illustrative only."

---

### STEP 5 — Verify selected ICD codes in lookup table `d_icd_diagnoses.csv.gz`
For each of Disease A and Disease B, look up the code in `d_icd_diagnoses`
and print its `long_title`. This allows non-expert validation that the agent
selected meaningful, distinct diseases.

Expected output format:
```
Disease A: ICD-{version} | {icd_code} → "{long_title}"
Disease B: ICD-{version} | {icd_code} → "{long_title}"
```
If a code is NOT found in the lookup table, print a ⚠️ warning.

---

### STEP 6 — Assess survival data availability
Now join the Disease A + Disease B patient lists with `patients.csv.gz`:
- For each disease group, report:
  - Count of patients WITH `dod` (will be "events" in survival analysis)
  - Count of patients WITHOUT `dod` (will be "censored")
  - % censored per group
- Join with `admissions.csv.gz` and report the first and last admission date
  per patient (to estimate the observation window)

---

## Output to Produce
Save a single file: `outputs/phase1_data_profile.md`

It must contain ALL of the following sections:
```
# Phase 1 — Data Profile Report
Generated: [date]

## 1. Table shapes and columns (Step 1)
## 2. Patient demographics (Step 2)
## 3. Admissions overview (Step 3)
## 4. Disease cohort identification (Step 4)
   ### 4a. ICD version breakdown
   ### 4b. Disease ranking by patient prevalence (top 10)
   ### 4c. Selected Disease A and Disease B
   ### 4d. Cohort profiles
   ### 4e. Overlap (patients with both diseases)
   ### 4f. seq_num distribution
## 5. ICD code verification (Step 5)
## 6. Survival data availability (Step 6)
## 7. Summary & warnings
   - List ALL ⚠️ warnings raised during exploration
   - State the selected Disease A and Disease B with their ICD codes
   - State whether Phase 2 (survival analysis) is feasible
   - Recommend any adjustments (e.g. pool Disease A + B if cohorts are too small)
```

---

## Validation Checkpoint for the Instructor
After the agent produces `phase1_data_profile.md`, compare its output
against the known ground truth:

| Metric | Expected value (from prior exploration) |
|---|---|
| `patients.csv` rows | **100** |
| `admissions.csv` rows | **275** |
| `diagnoses_icd.csv` rows | **4,506** |
| `d_icd_diagnoses.csv` rows | **109,775** |
| Patients with `dod` non-null | **~31 out of 100** |
| `hospital_expire_flag == 1` rate | **~5.5% of 275 admissions** |
| ICD versions present | **Both 9 and 10** |
| Total unique patients in dataset | **100** |

If the agent's numbers match → Phase 1 is validated. Proceed to Phase 2.
If they diverge → investigate before running the survival analysis.
