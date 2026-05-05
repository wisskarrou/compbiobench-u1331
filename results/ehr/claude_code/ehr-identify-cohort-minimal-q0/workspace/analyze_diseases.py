import pandas as pd
import gzip
import os

# Load the diagnoses data
print("Loading diagnoses data...")
diagnoses = pd.read_csv('ehr/hosp/diagnoses_icd.csv.gz', compression='gzip')
print(f"Diagnoses shape: {diagnoses.shape}")
print(f"Diagnoses columns: {diagnoses.columns.tolist()}")
print(f"First few rows:\n{diagnoses.head()}\n")

# Load the diagnosis descriptions
print("Loading diagnosis descriptions...")
d_icd = pd.read_csv('ehr/hosp/d_icd_diagnoses.csv.gz', compression='gzip')
print(f"D_ICD shape: {d_icd.shape}")
print(f"D_ICD columns: {d_icd.columns.tolist()}")
print(f"First few rows:\n{d_icd.head()}\n")

# Count unique patients per diagnosis code
print("Counting unique patients per diagnosis...")
diagnosis_counts = diagnoses.groupby('icd_code')['subject_id'].nunique().reset_index()
diagnosis_counts.columns = ['icd_code', 'patient_count']
diagnosis_counts = diagnosis_counts.sort_values('patient_count', ascending=False)

print(f"Top 20 diagnoses by patient count:")
print(diagnosis_counts.head(20))
print()

# Merge with descriptions to get readable names
diagnosis_counts_with_desc = diagnosis_counts.merge(
    d_icd[['icd_code', 'long_title']],
    on='icd_code',
    how='left'
)

print("Top 10 diagnoses with descriptions:")
print(diagnosis_counts_with_desc.head(10))
print()

# Get the top 2
top_2 = diagnosis_counts_with_desc.head(2)
print("\n=== TOP 2 MOST PREVALENT DISEASES ===")
for idx, row in top_2.iterrows():
    print(f"{row['icd_code']}: {row['long_title']} - {row['patient_count']} patients")

# Check for survival analysis feasibility
print("\n=== SURVIVAL ANALYSIS FEASIBILITY ===")
patients = pd.read_csv('ehr/hosp/patients.csv.gz', compression='gzip')
print(f"Patients columns: {patients.columns.tolist()}")
print(f"First few rows:\n{patients.head()}\n")

admissions = pd.read_csv('ehr/hosp/admissions.csv.gz', compression='gzip')
print(f"Admissions columns: {admissions.columns.tolist()}")
print(f"First few rows:\n{admissions.head()}\n")

# Check if we have death data
print(f"Patients with death time: {patients['dod'].notna().sum()}")
print(f"Admissions with death time: {admissions['deathtime'].notna().sum()}")

# For top 2 diseases, get patient lists
print("\n=== PATIENT DETAILS FOR TOP 2 DISEASES ===")
for idx, row in top_2.iterrows():
    icd_code = row['icd_code']
    disease_name = row['long_title']
    patient_count = row['patient_count']

    # Get patients with this diagnosis
    disease_patients = diagnoses[diagnoses['icd_code'] == icd_code]['subject_id'].unique()

    # Check death data for these patients
    patient_info = patients[patients['subject_id'].isin(disease_patients)]
    deaths = patient_info['dod'].notna().sum()

    print(f"\n{icd_code} - {disease_name}")
    print(f"  Total patients: {patient_count}")
    print(f"  Deaths recorded: {deaths}")
    print(f"  Survival analysis feasible: {'Yes' if deaths > 0 else 'Limited'}")

# Save results for report
results = {
    'top_2': top_2.to_dict('records'),
    'total_diagnoses': len(diagnosis_counts),
    'total_patients': diagnoses['subject_id'].nunique(),
    'patients_with_dod': patients['dod'].notna().sum(),
    'total_patients_in_db': len(patients)
}

import json
with open('results.json', 'w') as f:
    json.dump(results, f, indent=2)

print("\n=== RESULTS SAVED ===")
print(f"Total unique diagnoses: {results['total_diagnoses']}")
print(f"Total unique patients with diagnoses: {results['total_patients']}")
print(f"Total patients in database: {results['total_patients_in_db']}")
