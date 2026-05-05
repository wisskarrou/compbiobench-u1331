# Phase 1 Minimal Report: Disease Cohort Identification

## Executive Summary
This report analyzes the MIMIC-IV demo dataset (version 2.2) to identify the 2 most prevalent diseases by unique patient count and assess the feasibility of survival analysis.

## Dataset Overview
- **Dataset**: MIMIC-IV demo (v2.2)
- **Location**: `ehr/hosp/` and `ehr/icu/` directories
- **Format**: gzip-compressed CSV files
- **Total unique patients with diagnoses**: 100
- **Total unique diagnosis codes**: 1472
- **Total diagnosis records**: 4506

## Relevant Tables

### Primary Tables for Disease Identification
1. **diagnoses_icd.csv.gz** (`ehr/hosp/`)
   - Contains ICD diagnosis codes for each patient admission
   - Key columns: subject_id, hadm_id, icd_code, icd_version, seq_num
   - 4506 diagnosis records

2. **d_icd_diagnoses.csv.gz** (`ehr/hosp/`)
   - Dictionary table with ICD code descriptions
   - Key columns: icd_code, icd_version, long_title
   - 109775 diagnosis definitions

3. **patients.csv.gz** (`ehr/hosp/`)
   - Patient demographics and death dates
   - Key columns: subject_id, gender, anchor_age, dod (date of death)
   - 100 patients total
   - 31 patients with recorded death dates

4. **admissions.csv.gz** (`ehr/hosp/`)
   - Hospital admission details including in-hospital mortality
   - Key columns: subject_id, hadm_id, admittime, dischtime, deathtime, hospital_expire_flag
   - 275 admission records
   - 15 admissions with death time

## Top 2 Most Prevalent Diseases

### Methodology
Diseases were ranked by counting the number of unique patients (subject_id) diagnosed with each ICD code across all admissions. A patient is counted once per diagnosis code regardless of how many times they were diagnosed with it.

### Results

**Rank 1: ICD Code 4019**
- **Disease**: Unspecified essential hypertension
- **Unique Patients**: 41
- **Deaths Recorded**: 14 (34.1% of cohort)

**Rank 2: ICD Code 2724**
- **Disease**: Other and unspecified hyperlipidemia
- **Unique Patients**: 34
- **Deaths Recorded**: 14 (41.2% of cohort)

## Survival Analysis Feasibility

### Data Availability
The dataset contains necessary components for survival analysis:
- **Time-to-event data**: Available via admission dates and death dates
- **Event indicator**: Death status (dod field in patients table, deathtime in admissions table)
- **Censoring**: Patients without death dates are right-censored

### Assessment for Top 2 Diseases

Both diseases have sufficient data for survival analysis:

1. **Unspecified essential hypertension**: 14/41 events (34.1% event rate)
2. **Other and unspecified hyperlipidemia**: 14/34 events (41.2% event rate)

### Conclusion
**Yes, survival analysis is feasible** for both diseases. The dataset provides:
- Adequate event rates (>30% for both cohorts)
- Time-to-event data via admission and death timestamps
- Proper censoring for patients still alive at last observation
- Sufficient sample sizes for basic survival modeling

### Recommended Analyses
- Kaplan-Meier survival curves for each disease
- Log-rank tests to compare survival between the two cohorts
- Cox proportional hazards regression with covariates (age, gender, comorbidities)
- Time-varying analyses using multiple admissions per patient

## Data Quality Notes
- ICD codes use both version 9 and version 10
- The demo dataset is a subset for testing/education purposes
- Timestamp data allows for time-to-event calculations
- Multiple admissions per patient enable longitudinal analysis
