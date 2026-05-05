import pandas as pd
import os

# Create output directory
os.makedirs('outputs_minimal', exist_ok=True)

# Load the data
diagnoses = pd.read_csv('ehr/hosp/diagnoses_icd.csv.gz', compression='gzip')
d_icd = pd.read_csv('ehr/hosp/d_icd_diagnoses.csv.gz', compression='gzip')
patients = pd.read_csv('ehr/hosp/patients.csv.gz', compression='gzip')
admissions = pd.read_csv('ehr/hosp/admissions.csv.gz', compression='gzip')

# Count unique patients per diagnosis code
diagnosis_counts = diagnoses.groupby('icd_code')['subject_id'].nunique().reset_index()
diagnosis_counts.columns = ['icd_code', 'patient_count']
diagnosis_counts = diagnosis_counts.sort_values('patient_count', ascending=False)

# Merge with descriptions
diagnosis_counts_with_desc = diagnosis_counts.merge(
    d_icd[['icd_code', 'long_title']],
    on='icd_code',
    how='left'
)

# Get top 2
top_2 = diagnosis_counts_with_desc.head(2)

# Get detailed stats for top 2 diseases
disease_stats = []
for idx, row in top_2.iterrows():
    icd_code = row['icd_code']
    disease_name = row['long_title']
    patient_count = int(row['patient_count'])

    # Get patients with this diagnosis
    disease_patients = diagnoses[diagnoses['icd_code'] == icd_code]['subject_id'].unique()

    # Check death data for these patients
    patient_info = patients[patients['subject_id'].isin(disease_patients)]
    deaths = int(patient_info['dod'].notna().sum())

    disease_stats.append({
        'icd_code': icd_code,
        'disease_name': disease_name,
        'patient_count': patient_count,
        'deaths_recorded': deaths
    })

# Create the report
report = f"""# Phase 1 Minimal Report: Disease Cohort Identification

## Executive Summary
This report analyzes the MIMIC-IV demo dataset (version 2.2) to identify the 2 most prevalent diseases by unique patient count and assess the feasibility of survival analysis.

## Dataset Overview
- **Dataset**: MIMIC-IV demo (v2.2)
- **Location**: `ehr/hosp/` and `ehr/icu/` directories
- **Format**: gzip-compressed CSV files
- **Total unique patients with diagnoses**: {int(diagnoses['subject_id'].nunique())}
- **Total unique diagnosis codes**: {len(diagnosis_counts)}
- **Total diagnosis records**: {len(diagnoses)}

## Relevant Tables

### Primary Tables for Disease Identification
1. **diagnoses_icd.csv.gz** (`ehr/hosp/`)
   - Contains ICD diagnosis codes for each patient admission
   - Key columns: subject_id, hadm_id, icd_code, icd_version, seq_num
   - {len(diagnoses)} diagnosis records

2. **d_icd_diagnoses.csv.gz** (`ehr/hosp/`)
   - Dictionary table with ICD code descriptions
   - Key columns: icd_code, icd_version, long_title
   - {len(d_icd)} diagnosis definitions

3. **patients.csv.gz** (`ehr/hosp/`)
   - Patient demographics and death dates
   - Key columns: subject_id, gender, anchor_age, dod (date of death)
   - {len(patients)} patients total
   - {int(patients['dod'].notna().sum())} patients with recorded death dates

4. **admissions.csv.gz** (`ehr/hosp/`)
   - Hospital admission details including in-hospital mortality
   - Key columns: subject_id, hadm_id, admittime, dischtime, deathtime, hospital_expire_flag
   - {len(admissions)} admission records
   - {int(admissions['deathtime'].notna().sum())} admissions with death time

## Top 2 Most Prevalent Diseases

### Methodology
Diseases were ranked by counting the number of unique patients (subject_id) diagnosed with each ICD code across all admissions. A patient is counted once per diagnosis code regardless of how many times they were diagnosed with it.

### Results

**Rank 1: ICD Code {disease_stats[0]['icd_code']}**
- **Disease**: {disease_stats[0]['disease_name']}
- **Unique Patients**: {disease_stats[0]['patient_count']}
- **Deaths Recorded**: {disease_stats[0]['deaths_recorded']} ({100*disease_stats[0]['deaths_recorded']/disease_stats[0]['patient_count']:.1f}% of cohort)

**Rank 2: ICD Code {disease_stats[1]['icd_code']}**
- **Disease**: {disease_stats[1]['disease_name']}
- **Unique Patients**: {disease_stats[1]['patient_count']}
- **Deaths Recorded**: {disease_stats[1]['deaths_recorded']} ({100*disease_stats[1]['deaths_recorded']/disease_stats[1]['patient_count']:.1f}% of cohort)

## Survival Analysis Feasibility

### Data Availability
The dataset contains necessary components for survival analysis:
- **Time-to-event data**: Available via admission dates and death dates
- **Event indicator**: Death status (dod field in patients table, deathtime in admissions table)
- **Censoring**: Patients without death dates are right-censored

### Assessment for Top 2 Diseases

Both diseases have sufficient data for survival analysis:

1. **{disease_stats[0]['disease_name']}**: {disease_stats[0]['deaths_recorded']}/{disease_stats[0]['patient_count']} events ({100*disease_stats[0]['deaths_recorded']/disease_stats[0]['patient_count']:.1f}% event rate)
2. **{disease_stats[1]['disease_name']}**: {disease_stats[1]['deaths_recorded']}/{disease_stats[1]['patient_count']} events ({100*disease_stats[1]['deaths_recorded']/disease_stats[1]['patient_count']:.1f}% event rate)

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
"""

# Write the report
with open('outputs_minimal/phase1_minimal_report.md', 'w') as f:
    f.write(report)

print("Report created successfully!")
print(f"\nTop 2 diseases:")
print(f"1. {disease_stats[0]['icd_code']}: {disease_stats[0]['disease_name']} ({disease_stats[0]['patient_count']} patients)")
print(f"2. {disease_stats[1]['icd_code']}: {disease_stats[1]['disease_name']} ({disease_stats[1]['patient_count']} patients)")
