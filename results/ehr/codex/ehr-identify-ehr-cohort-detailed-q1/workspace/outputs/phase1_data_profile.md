# Phase 1 — Data Profile Report
Generated: 2026-05-02 17:40:05

## 1. Table shapes and columns (Step 1)
- `patients.csv.gz` → shape: (100, 6) ✓
- Columns: subject_id, gender, anchor_age, anchor_year, anchor_year_group, dod
- `admissions.csv.gz` → shape: (275, 16) ✓
- Columns: subject_id, hadm_id, admittime, dischtime, deathtime, admission_type, admit_provider_id, admission_location, discharge_location, insurance, language, marital_status, race, edregtime, edouttime, hospital_expire_flag
- `diagnoses_icd.csv.gz` → shape: (4506, 5) ✓
- Columns: subject_id, hadm_id, seq_num, icd_code, icd_version
- `d_icd_diagnoses.csv.gz` → shape: (109775, 3) ✓
- Columns: icd_code, icd_version, long_title

## 2. Patient demographics (Step 2)
- Total patients: 100
- Gender distribution:
  - M: 57 (57.0%)
  - F: 43 (43.0%)
- anchor_age summary: min=21, max=91, mean=61.75, median=63.00, std=16.17
- dod missingness: missing=69, non-missing=31, % missing=69.0%
- anchor_year_group counts:
  - 2014 - 2016: 57
  - 2011 - 2013: 43

## 3. Admissions overview (Step 3)
- Total admissions: 275
- Unique patients in admissions: 100
- Average admissions per patient: 2.75
- admission_type counts:
  - EW EMER.: 104
  - OBSERVATION ADMIT: 45
  - URGENT: 38
  - EU OBSERVATION: 30
  - SURGICAL SAME DAY ADMISSION: 18
  - DIRECT EMER.: 15
  - ELECTIVE: 13
  - DIRECT OBSERVATION: 7
  - AMBULATORY OBSERVATION: 5
- hospital_expire_flag counts:
  - 0: 260
  - 1: 15
- In-hospital death rate (hospital_expire_flag == 1): 5.45%
- deathtime missingness: missing=260, % missing=94.55%
- Admission date range (admittime): 2110-04-11 15:08:00 to 2201-12-11 12:00:00

## 4. Disease cohort identification (Step 4)
### 4a. ICD version breakdown
- ICD-9: 2193 rows (48.67%)
- ICD-10: 2313 rows (51.33%)

### 4b. Disease ranking by patient prevalence (top 10)
| rank | icd_code | icd_version | long_title | patient_count | row_count |
|---:|---|---:|---|---:|---:|
| 1 | 4019 | 9 | Unspecified essential hypertension | 41 | 68 |
| 2 | 2724 | 9 | Other and unspecified hyperlipidemia | 34 | 55 |
| 3 | E785 | 10 | Hyperlipidemia, unspecified | 21 | 57 |
| 4 | 25000 | 9 | Diabetes mellitus without mention of complication, type II or unspecified type, not stated as uncontrolled | 21 | 33 |
| 5 | V1582 | 9 | Personal history of tobacco use | 20 | 31 |
| 6 | 41401 | 9 | Coronary atherosclerosis of native coronary artery | 19 | 28 |
| 7 | 42731 | 9 | Atrial fibrillation | 18 | 34 |
| 8 | 3051 | 9 | Tobacco use disorder | 18 | 24 |
| 9 | 2859 | 9 | Anemia, unspecified | 18 | 23 |
| 10 | I10 | 10 | Essential (primary) hypertension | 17 | 32 |
- Unmatched diagnosis rows after join on (icd_code, icd_version): 0

### 4c. Selected Disease A and Disease B
- Disease A: ICD-9 | 4019 | Unspecified essential hypertension
- Disease B: ICD-9 | 2724 | Other and unspecified hyperlipidemia

### 4d. Cohort profiles
- Disease A rows in diagnoses_icd: 68
- Disease A unique patients: 41
- Disease B rows in diagnoses_icd: 55
- Disease B unique patients: 34

### 4e. Overlap (patients with both diseases)
- Patients with BOTH Disease A and Disease B: 22

### 4f. seq_num distribution
- Disease A seq_num distribution:
  - seq_num=2: 4
  - seq_num=3: 6
  - seq_num=4: 5
  - seq_num=5: 7
  - seq_num=6: 5
  - seq_num=7: 7
  - seq_num=8: 6
  - seq_num=9: 1
  - seq_num=10: 5
  - seq_num=11: 5
  - seq_num=12: 3
  - seq_num=13: 4
  - seq_num=14: 3
  - seq_num=15: 2
  - seq_num=16: 1
  - seq_num=17: 1
  - seq_num=19: 1
  - seq_num=21: 1
  - seq_num=25: 1
- Disease A primary diagnoses (seq_num == 1): 0
- Disease B seq_num distribution:
  - seq_num=2: 2
  - seq_num=3: 2
  - seq_num=4: 4
  - seq_num=5: 6
  - seq_num=6: 2
  - seq_num=7: 7
  - seq_num=8: 5
  - seq_num=9: 2
  - seq_num=10: 3
  - seq_num=11: 2
  - seq_num=12: 2
  - seq_num=13: 2
  - seq_num=14: 3
  - seq_num=15: 1
  - seq_num=16: 2
  - seq_num=17: 4
  - seq_num=18: 2
  - seq_num=22: 2
  - seq_num=23: 1
  - seq_num=26: 1
- Disease B primary diagnoses (seq_num == 1): 0

## 5. ICD code verification (Step 5)
Disease A: ICD-9 | 4019 → "Unspecified essential hypertension"
Disease B: ICD-9 | 2724 → "Other and unspecified hyperlipidemia"

## 6. Survival data availability (Step 6)
- Disease A patients WITH dod: 14
- Disease A patients WITHOUT dod: 27
- Disease A % censored: 65.85%
- Disease B patients WITH dod: 14
- Disease B patients WITHOUT dod: 20
- Disease B % censored: 58.82%
- Disease A patient-level first/last admittime range: 2111-01-15 14:55:00 to 2201-12-11 12:00:00
- Disease B patient-level first/last admittime range: 2111-01-15 14:55:00 to 2201-07-07 18:15:00

## 7. Summary & warnings
- Warnings raised during exploration: none
- Selected Disease A: ICD-9 4019 (Unspecified essential hypertension)
- Selected Disease B: ICD-9 2724 (Other and unspecified hyperlipidemia)
- Phase 2 feasibility: Yes
- Recommended adjustment: proceed with Phase 2; account for 22-patient overlap and high censoring in both cohorts.