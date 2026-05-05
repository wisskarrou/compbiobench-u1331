# Phase 1 Minimal Report

## Dataset structure explored
Data source: MIMIC-IV demo v2.2 under `ehr/`.

Most relevant hospital tables for this task:
- `ehr/hosp/diagnoses_icd.csv.gz`: diagnosis events (`subject_id`, `hadm_id`, `icd_code`, `icd_version`).
- `ehr/hosp/d_icd_diagnoses.csv.gz`: ICD diagnosis dictionary (`icd_code`, `icd_version`, `long_title`).
- `ehr/hosp/patients.csv.gz`: patient-level demographics and date of death (`dod`).
- `ehr/hosp/admissions.csv.gz`: hospital stay timing and in-hospital death time (`deathtime`).

Quick size checks:
- Patients: 100 unique `subject_id`.
- Admissions: 275 rows, 100 unique patients.
- Diagnosis rows: 4,506 rows.

## How top 2 diseases were determined
Method:
1. Join `diagnoses_icd` to `d_icd_diagnoses` on (`icd_code`, `icd_version`).
2. Group by diagnosis code/version/title.
3. Count unique `subject_id` per diagnosis.
4. Rank descending by unique-patient count.

## Two most prevalent diseases (unique patients diagnosed)
1. ICD-9 `4019` — **Unspecified essential hypertension**: **41** patients.
2. ICD-9 `2724` — **Other and unspecified hyperlipidemia**: **34** patients.

Additional cohort context for these two diagnoses:
- Overlap (patients with both diagnoses): 22.
- Union cohort (patients with either diagnosis): 53.

## Survival analysis feasibility
A survival analysis is feasible at a basic level because:
- Time variables are available in `admissions` (`admittime`, `dischtime`, `deathtime`).
- Mortality/censoring signal is available in `patients.dod` and `admissions.deathtime`.

Observed event availability in the top-2 union cohort (53 patients):
- 21 patients have non-null `dod`.
- Across their admissions, 9 admissions have non-null `deathtime`.

Implication:
- A cohort-level time-to-death analysis can be performed, but sample size is small (demo dataset) and endpoint definitions (e.g., index admission/diagnosis date, handling multiple admissions, censoring date) must be specified carefully.
