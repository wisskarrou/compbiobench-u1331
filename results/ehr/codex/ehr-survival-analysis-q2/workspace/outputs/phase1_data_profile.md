# Phase 1 — Data Profile Report
Generated: 2026-05-02 15:36:43

## 1. Table shapes and columns (Step 1)
  patients.csv.gz → shape: (100, 6) ✓
  Columns: subject_id, gender, anchor_age, anchor_year, anchor_year_group, dod ✓
  admissions.csv.gz → shape: (275, 16) ✓
  Columns: subject_id, hadm_id, admittime, dischtime, deathtime, admission_type, admit_provider_id, admission_location, discharge_location, insurance, language, marital_status, race, edregtime, edouttime, hospital_expire_flag ✓
  diagnoses_icd.csv.gz → shape: (4506, 5) ✓
  Columns: subject_id, hadm_id, seq_num, icd_code, icd_version ✓
  d_icd_diagnoses.csv.gz → shape: (109775, 3) ✓
  Columns: icd_code, icd_version, long_title ✓

## 2. Patient demographics (Step 2)
**Total number of patients:** 100

**Gender distribution:**
```
        count  percentage
gender                   
M          57        57.0
F          43        43.0
```

**anchor_age statistics:**
- Min: 21
- Max: 91
- Mean: 61.75
- Median: 63.00
- Std: 16.17

**dod (date of death) missingness:**
- Missing: 69 (69.0%)
- Non-missing: 31 (31.0%)

**anchor_year_group distribution:**
```
anchor_year_group
2011 - 2013    43
2014 - 2016    57
```

## 3. Admissions overview (Step 3)
**Total admissions:** 275
**Unique patients:** 100
**Average admissions per patient:** 2.75

**admission_type distribution:**
```
admission_type
EW EMER.                       104
OBSERVATION ADMIT               45
URGENT                          38
EU OBSERVATION                  30
SURGICAL SAME DAY ADMISSION     18
DIRECT EMER.                    15
ELECTIVE                        13
DIRECT OBSERVATION               7
AMBULATORY OBSERVATION           5
```

**hospital_expire_flag distribution:**
- 0 (did not expire): 260
- 1 (expired): 15 (5.5%)

**deathtime missingness:**
- Missing: 260 (94.5%)

**Date range of admissions:**
- Min: 2110-04-11 15:08:00
- Max: 2201-12-11 12:00:00

## 4. Disease cohort identification (Step 4)

### 4a. ICD version breakdown
- ICD-9: 2193 rows (48.7%)
- ICD-10: 2313 rows (51.3%)

### 4b. Disease ranking by patient prevalence (top 10)

**Top 10 diseases by patient prevalence:**
```
 rank icd_code  icd_version                                                                                                 long_title  patient_count  row_count
    1     4019            9                                                                         Unspecified essential hypertension             41         68
    2     2724            9                                                                       Other and unspecified hyperlipidemia             34         55
    3     E785           10                                                                                Hyperlipidemia, unspecified             21         57
    4    25000            9 Diabetes mellitus without mention of complication, type II or unspecified type, not stated as uncontrolled             21         33
    5    V1582            9                                                                            Personal history of tobacco use             20         31
    6    41401            9                                                         Coronary atherosclerosis of native coronary artery             19         28
    7    42731            9                                                                                        Atrial fibrillation             18         34
    8     3051            9                                                                                       Tobacco use disorder             18         24
    9     2859            9                                                                                        Anemia, unspecified             18         23
   10      I10           10                                                                           Essential (primary) hypertension             17         32
```

### 4c. Selected Disease A and Disease B

**Disease A:**
- ICD Code: 4019
- ICD Version: 9
- Long Title: Unspecified essential hypertension
- Diagnosis rows: 68
- Unique patients: 41

### 4d. Cohort profiles

**Disease B:**
- ICD Code: 2724
- ICD Version: 9
- Long Title: Other and unspecified hyperlipidemia
- Diagnosis rows: 55
- Unique patients: 34

### 4e. Overlap (patients with both diseases)
**Patients with both Disease A and Disease B:** 22

⚠️ Note: These 22 patients will need special handling in Phase 2.

### 4f. seq_num distribution

**Disease A seq_num distribution:**
```
seq_num
2     4
3     6
4     5
5     7
6     5
7     7
8     6
9     1
10    5
11    5
12    3
13    4
14    3
15    2
16    1
17    1
19    1
21    1
25    1
```
- Primary diagnoses (seq_num == 1): 0

**Disease B seq_num distribution:**
```
seq_num
2     2
3     2
4     4
5     6
6     2
7     7
8     5
9     2
10    3
11    2
12    2
13    2
14    3
15    1
16    2
17    4
18    2
22    2
23    1
26    1
```
- Primary diagnoses (seq_num == 1): 0

## 5. ICD code verification (Step 5)

**Disease A:** ICD-9 | 4019 → "Unspecified essential hypertension"

**Disease B:** ICD-9 | 2724 → "Other and unspecified hyperlipidemia"

## 6. Survival data availability (Step 6)

**Disease A survival data:**
- Patients with dod (events): 14
- Patients without dod (censored): 27
- % censored: 65.9%

**Disease B survival data:**
- Patients with dod (events): 14
- Patients without dod (censored): 20
- % censored: 58.8%

**Disease A admission date range:** 2111-01-15 14:55:00 to 2201-12-11 12:00:00

**Disease B admission date range:** 2111-01-15 14:55:00 to 2201-07-07 18:15:00

## 7. Summary & warnings

**All warnings raised during exploration:**
- No warnings ✓

**Selected diseases:**
- Disease A: ICD-9 4019 - Unspecified essential hypertension
- Disease B: ICD-9 2724 - Other and unspecified hyperlipidemia

**Phase 2 (survival analysis) feasible:** True
