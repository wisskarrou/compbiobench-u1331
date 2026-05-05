#!/usr/bin/env python3
"""
Phase 1: Data Grounding & Exploration
Top-2 Most Prevalent Disease Cohort — MIMIC-IV Demo v2.2
"""

import pandas as pd
import numpy as np
from datetime import datetime
import os

# Create outputs directory
os.makedirs("outputs", exist_ok=True)

# Open report file for writing
report = []

def add_section(title, level=2):
    """Add a section header to the report"""
    report.append("\n" + "#" * level + " " + title + "\n")

def add_text(text):
    """Add text to the report"""
    report.append(text + "\n")

# Header
report.append("# Phase 1 — Data Profile Report\n")
report.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

print("=" * 80)
print("PHASE 1: DATA GROUNDING & EXPLORATION")
print("=" * 80)

# =============================================================================
# STEP 1 — Load and verify all 4 tables
# =============================================================================
add_section("1. Table shapes and columns (Step 1)")

print("\n" + "=" * 80)
print("STEP 1 — Load and verify all 4 tables")
print("=" * 80)

# Define expected columns for each table
expected_columns = {
    "patients": ["subject_id", "gender", "anchor_age", "anchor_year", "anchor_year_group", "dod"],
    "admissions": ["subject_id", "hadm_id", "admittime", "dischtime", "deathtime",
                   "admission_type", "admit_provider_id", "admission_location",
                   "discharge_location", "insurance", "language", "marital_status", "race",
                   "edregtime", "edouttime", "hospital_expire_flag"],
    "diagnoses_icd": ["subject_id", "hadm_id", "seq_num", "icd_code", "icd_version"],
    "d_icd_diagnoses": ["icd_code", "icd_version", "long_title"]
}

# Load tables
tables = {}
warnings = []

for table_name, cols in expected_columns.items():
    file_path = f"ehr/hosp/{table_name}.csv.gz"
    print(f"\nLoading {table_name}.csv.gz...")

    df = pd.read_csv(file_path, compression="gzip")
    tables[table_name] = df

    shape_str = f"  {table_name}.csv.gz → shape: {df.shape} ✓"
    print(shape_str)
    add_text(shape_str)

    # Check columns
    actual_cols = df.columns.tolist()
    cols_str = f"  Columns: {', '.join(actual_cols)} ✓"
    print(cols_str)
    add_text(cols_str)

    # Verify expected columns are present
    missing_cols = set(cols) - set(actual_cols)
    if missing_cols:
        warning = f"⚠️ WARNING: Missing columns in {table_name}: {missing_cols}"
        print(warning)
        add_text(warning)
        warnings.append(warning)
        raise ValueError(f"Missing columns in {table_name}: {missing_cols}")

    print(f"  All expected columns present ✓")

# =============================================================================
# STEP 2 — Profile patients.csv.gz
# =============================================================================
add_section("2. Patient demographics (Step 2)")

print("\n" + "=" * 80)
print("STEP 2 — Profile patients.csv.gz")
print("=" * 80)

patients = tables["patients"]

# Total number of patients
total_patients = len(patients)
print(f"\nTotal number of patients: {total_patients}")
add_text(f"**Total number of patients:** {total_patients}")

# Gender distribution
print("\nGender distribution:")
gender_counts = patients["gender"].value_counts()
gender_pct = patients["gender"].value_counts(normalize=True) * 100
gender_df = pd.DataFrame({
    "count": gender_counts,
    "percentage": gender_pct.round(2)
})
print(gender_df)
add_text("\n**Gender distribution:**")
add_text(f"```\n{gender_df.to_string()}\n```")

# anchor_age statistics
print("\nanchor_age statistics:")
age_stats = patients["anchor_age"].describe()
print(age_stats)
add_text("\n**anchor_age statistics:**")
add_text(f"- Min: {patients['anchor_age'].min()}")
add_text(f"- Max: {patients['anchor_age'].max()}")
add_text(f"- Mean: {patients['anchor_age'].mean():.2f}")
add_text(f"- Median: {patients['anchor_age'].median():.2f}")
add_text(f"- Std: {patients['anchor_age'].std():.2f}")

# dod missingness
dod_missing = patients["dod"].isna().sum()
dod_non_missing = patients["dod"].notna().sum()
dod_missing_pct = (dod_missing / len(patients)) * 100
print(f"\ndod missingness:")
print(f"  Missing: {dod_missing} ({dod_missing_pct:.1f}%)")
print(f"  Non-missing: {dod_non_missing} ({100-dod_missing_pct:.1f}%)")
add_text(f"\n**dod (date of death) missingness:**")
add_text(f"- Missing: {dod_missing} ({dod_missing_pct:.1f}%)")
add_text(f"- Non-missing: {dod_non_missing} ({100-dod_missing_pct:.1f}%)")

# anchor_year_group
print("\nanchor_year_group distribution:")
year_group_counts = patients["anchor_year_group"].value_counts().sort_index()
print(year_group_counts)
add_text(f"\n**anchor_year_group distribution:**")
add_text(f"```\n{year_group_counts.to_string()}\n```")

# =============================================================================
# STEP 3 — Profile admissions.csv.gz
# =============================================================================
add_section("3. Admissions overview (Step 3)")

print("\n" + "=" * 80)
print("STEP 3 — Profile admissions.csv.gz")
print("=" * 80)

admissions = tables["admissions"]

# Total admissions and unique patients
total_admissions = len(admissions)
unique_patients_in_admissions = admissions["subject_id"].nunique()
avg_admissions = total_admissions / unique_patients_in_admissions
print(f"\nTotal admissions: {total_admissions}")
print(f"Unique patients: {unique_patients_in_admissions}")
print(f"Average admissions per patient: {avg_admissions:.2f}")
add_text(f"**Total admissions:** {total_admissions}")
add_text(f"**Unique patients:** {unique_patients_in_admissions}")
add_text(f"**Average admissions per patient:** {avg_admissions:.2f}")

# admission_type
print("\nadmission_type distribution:")
admission_type_counts = admissions["admission_type"].value_counts()
print(admission_type_counts)
add_text(f"\n**admission_type distribution:**")
add_text(f"```\n{admission_type_counts.to_string()}\n```")

# hospital_expire_flag
print("\nhospital_expire_flag distribution:")
expire_counts = admissions["hospital_expire_flag"].value_counts()
expire_pct = (expire_counts[1] / len(admissions)) * 100 if 1 in expire_counts else 0
print(f"  0 (did not expire): {expire_counts.get(0, 0)}")
print(f"  1 (expired): {expire_counts.get(1, 0)} ({expire_pct:.1f}%)")
add_text(f"\n**hospital_expire_flag distribution:**")
add_text(f"- 0 (did not expire): {expire_counts.get(0, 0)}")
add_text(f"- 1 (expired): {expire_counts.get(1, 0)} ({expire_pct:.1f}%)")

# deathtime missingness
deathtime_missing = admissions["deathtime"].isna().sum()
deathtime_missing_pct = (deathtime_missing / len(admissions)) * 100
print(f"\ndeathtime missingness:")
print(f"  Missing: {deathtime_missing} ({deathtime_missing_pct:.1f}%)")
add_text(f"\n**deathtime missingness:**")
add_text(f"- Missing: {deathtime_missing} ({deathtime_missing_pct:.1f}%)")

# Date range
admissions["admittime"] = pd.to_datetime(admissions["admittime"])
min_admit = admissions["admittime"].min()
max_admit = admissions["admittime"].max()
print(f"\nDate range of admissions:")
print(f"  Min: {min_admit}")
print(f"  Max: {max_admit}")
add_text(f"\n**Date range of admissions:**")
add_text(f"- Min: {min_admit}")
add_text(f"- Max: {max_admit}")

# =============================================================================
# STEP 4 — Discover the 2 most prevalent diseases
# =============================================================================
add_section("4. Disease cohort identification (Step 4)")

print("\n" + "=" * 80)
print("STEP 4 — Discover the 2 most prevalent diseases")
print("=" * 80)

diagnoses_icd = tables["diagnoses_icd"]
d_icd_diagnoses = tables["d_icd_diagnoses"]

# 4a. ICD version breakdown
add_section("4a. ICD version breakdown", level=3)
print("\n4a. ICD version breakdown")
version_counts = diagnoses_icd["icd_version"].value_counts()
version_pct = diagnoses_icd["icd_version"].value_counts(normalize=True) * 100
print(f"  ICD-9: {version_counts.get(9, 0)} rows ({version_pct.get(9, 0):.1f}%)")
print(f"  ICD-10: {version_counts.get(10, 0)} rows ({version_pct.get(10, 0):.1f}%)")
add_text(f"- ICD-9: {version_counts.get(9, 0)} rows ({version_pct.get(9, 0):.1f}%)")
add_text(f"- ICD-10: {version_counts.get(10, 0)} rows ({version_pct.get(10, 0):.1f}%)")

# 4b. Join diagnoses with lookup table
add_section("4b. Disease ranking by patient prevalence (top 10)", level=3)
print("\n4b. Join diagnoses with lookup table")
diagnoses_with_labels = diagnoses_icd.merge(
    d_icd_diagnoses,
    on=["icd_code", "icd_version"],
    how="left"
)

# Check for unmatched rows
unmatched = diagnoses_with_labels["long_title"].isna().sum()
if unmatched > 0:
    warning = f"⚠️ WARNING: {unmatched} diagnosis rows failed to match with lookup table"
    print(warning)
    add_text(warning)
    warnings.append(warning)
else:
    print(f"  All diagnosis rows matched successfully ✓")

# 4c. Rank diseases by patient prevalence
print("\n4c. Rank diseases by patient prevalence")
disease_prevalence = diagnoses_icd.groupby(["icd_code", "icd_version"]).agg({
    "subject_id": "nunique",  # Number of unique patients
}).reset_index()
disease_prevalence.columns = ["icd_code", "icd_version", "patient_count"]

# Also count total rows for tie-breaking
row_counts = diagnoses_icd.groupby(["icd_code", "icd_version"]).size().reset_index(name="row_count")
disease_prevalence = disease_prevalence.merge(row_counts, on=["icd_code", "icd_version"])

# Merge with labels
disease_prevalence = disease_prevalence.merge(
    d_icd_diagnoses,
    on=["icd_code", "icd_version"],
    how="left"
)

# Sort by patient count (descending), then by row count for tie-breaking
disease_prevalence = disease_prevalence.sort_values(
    ["patient_count", "row_count"],
    ascending=[False, False]
).reset_index(drop=True)

# Add rank
disease_prevalence["rank"] = range(1, len(disease_prevalence) + 1)

# Print top 10
print("\nTop 10 diseases by patient prevalence:")
top_10 = disease_prevalence.head(10)[["rank", "icd_code", "icd_version", "long_title", "patient_count", "row_count"]]
print(top_10.to_string(index=False))
add_text("\n**Top 10 diseases by patient prevalence:**")
add_text(f"```\n{top_10.to_string(index=False)}\n```")

# Check for ties at rank 2/3 boundary
rank2_count = disease_prevalence.loc[1, "patient_count"]
rank3_count = disease_prevalence.loc[2, "patient_count"]
if rank2_count == rank3_count:
    tie_warning = f"⚠️ Tie detected at rank 2/3 boundary (both have {rank2_count} patients). Tie broken by total row count."
    print(tie_warning)
    add_text(tie_warning)
    warnings.append(tie_warning)

# 4d. Select Disease A and Disease B
add_section("4c. Selected Disease A and Disease B", level=3)
disease_a = disease_prevalence.iloc[0]
disease_b = disease_prevalence.iloc[1]

print("\n4d. Profile Disease A and Disease B cohorts")
print("\nDisease A:")
print(f"  ICD Code: {disease_a['icd_code']}")
print(f"  ICD Version: {disease_a['icd_version']}")
print(f"  Long Title: {disease_a['long_title']}")
print(f"  Diagnosis rows: {disease_a['row_count']}")
print(f"  Unique patients: {disease_a['patient_count']}")

add_text(f"\n**Disease A:**")
add_text(f"- ICD Code: {disease_a['icd_code']}")
add_text(f"- ICD Version: {disease_a['icd_version']}")
add_text(f"- Long Title: {disease_a['long_title']}")
add_text(f"- Diagnosis rows: {disease_a['row_count']}")
add_text(f"- Unique patients: {disease_a['patient_count']}")

print("\nDisease B:")
print(f"  ICD Code: {disease_b['icd_code']}")
print(f"  ICD Version: {disease_b['icd_version']}")
print(f"  Long Title: {disease_b['long_title']}")
print(f"  Diagnosis rows: {disease_b['row_count']}")
print(f"  Unique patients: {disease_b['patient_count']}")

add_section("4d. Cohort profiles", level=3)
add_text(f"\n**Disease B:**")
add_text(f"- ICD Code: {disease_b['icd_code']}")
add_text(f"- ICD Version: {disease_b['icd_version']}")
add_text(f"- Long Title: {disease_b['long_title']}")
add_text(f"- Diagnosis rows: {disease_b['row_count']}")
add_text(f"- Unique patients: {disease_b['patient_count']}")

# 4e. Overlap check
add_section("4e. Overlap (patients with both diseases)", level=3)
print("\n4e. Overlap check")
patients_a = set(diagnoses_icd[
    (diagnoses_icd["icd_code"] == disease_a["icd_code"]) &
    (diagnoses_icd["icd_version"] == disease_a["icd_version"])
]["subject_id"].unique())

patients_b = set(diagnoses_icd[
    (diagnoses_icd["icd_code"] == disease_b["icd_code"]) &
    (diagnoses_icd["icd_version"] == disease_b["icd_version"])
]["subject_id"].unique())

overlap = patients_a & patients_b
print(f"  Patients with both Disease A and Disease B: {len(overlap)}")
add_text(f"**Patients with both Disease A and Disease B:** {len(overlap)}")
if len(overlap) > 0:
    add_text(f"\n⚠️ Note: These {len(overlap)} patients will need special handling in Phase 2.")

# 4f. seq_num distribution
add_section("4f. seq_num distribution", level=3)
print("\n4f. seq_num distribution")

# For Disease A
disease_a_rows = diagnoses_icd[
    (diagnoses_icd["icd_code"] == disease_a["icd_code"]) &
    (diagnoses_icd["icd_version"] == disease_a["icd_version"])
]
seq_num_a = disease_a_rows["seq_num"].value_counts().sort_index()
primary_a = (disease_a_rows["seq_num"] == 1).sum()

print(f"\nDisease A seq_num distribution:")
print(seq_num_a)
print(f"  Primary diagnoses (seq_num == 1): {primary_a}")

add_text(f"\n**Disease A seq_num distribution:**")
add_text(f"```\n{seq_num_a.to_string()}\n```")
add_text(f"- Primary diagnoses (seq_num == 1): {primary_a}")

# For Disease B
disease_b_rows = diagnoses_icd[
    (diagnoses_icd["icd_code"] == disease_b["icd_code"]) &
    (diagnoses_icd["icd_version"] == disease_b["icd_version"])
]
seq_num_b = disease_b_rows["seq_num"].value_counts().sort_index()
primary_b = (disease_b_rows["seq_num"] == 1).sum()

print(f"\nDisease B seq_num distribution:")
print(seq_num_b)
print(f"  Primary diagnoses (seq_num == 1): {primary_b}")

add_text(f"\n**Disease B seq_num distribution:**")
add_text(f"```\n{seq_num_b.to_string()}\n```")
add_text(f"- Primary diagnoses (seq_num == 1): {primary_b}")

# Check cohort size
if disease_a['patient_count'] < 10 or disease_b['patient_count'] < 10:
    cohort_warning = "⚠️ Cohort may be too small for reliable survival analysis — results will be illustrative only."
    print(f"\n{cohort_warning}")
    add_text(f"\n{cohort_warning}")
    warnings.append(cohort_warning)

# =============================================================================
# STEP 5 — Verify ICD codes in lookup table
# =============================================================================
add_section("5. ICD code verification (Step 5)")

print("\n" + "=" * 80)
print("STEP 5 — Verify ICD codes in lookup table")
print("=" * 80)

print(f"\nDisease A: ICD-{disease_a['icd_version']} | {disease_a['icd_code']} → \"{disease_a['long_title']}\"")
print(f"Disease B: ICD-{disease_b['icd_version']} | {disease_b['icd_code']} → \"{disease_b['long_title']}\"")

add_text(f"\n**Disease A:** ICD-{disease_a['icd_version']} | {disease_a['icd_code']} → \"{disease_a['long_title']}\"")
add_text(f"\n**Disease B:** ICD-{disease_b['icd_version']} | {disease_b['icd_code']} → \"{disease_b['long_title']}\"")

# Verify in lookup table
lookup_a = d_icd_diagnoses[
    (d_icd_diagnoses["icd_code"] == disease_a["icd_code"]) &
    (d_icd_diagnoses["icd_version"] == disease_a["icd_version"])
]
lookup_b = d_icd_diagnoses[
    (d_icd_diagnoses["icd_code"] == disease_b["icd_code"]) &
    (d_icd_diagnoses["icd_version"] == disease_b["icd_version"])
]

if len(lookup_a) == 0:
    warning = f"⚠️ WARNING: Disease A code not found in lookup table"
    print(warning)
    add_text(warning)
    warnings.append(warning)
else:
    print("  Disease A verified in lookup table ✓")

if len(lookup_b) == 0:
    warning = f"⚠️ WARNING: Disease B code not found in lookup table"
    print(warning)
    add_text(warning)
    warnings.append(warning)
else:
    print("  Disease B verified in lookup table ✓")

# =============================================================================
# STEP 6 — Assess survival data availability
# =============================================================================
add_section("6. Survival data availability (Step 6)")

print("\n" + "=" * 80)
print("STEP 6 — Assess survival data availability")
print("=" * 80)

# For Disease A
print("\nDisease A survival data:")
patients_a_df = patients[patients["subject_id"].isin(patients_a)]
dod_a_with = patients_a_df["dod"].notna().sum()
dod_a_without = patients_a_df["dod"].isna().sum()
censored_pct_a = (dod_a_without / len(patients_a_df)) * 100

print(f"  Patients with dod (events): {dod_a_with}")
print(f"  Patients without dod (censored): {dod_a_without}")
print(f"  % censored: {censored_pct_a:.1f}%")

add_text(f"\n**Disease A survival data:**")
add_text(f"- Patients with dod (events): {dod_a_with}")
add_text(f"- Patients without dod (censored): {dod_a_without}")
add_text(f"- % censored: {censored_pct_a:.1f}%")

# For Disease B
print("\nDisease B survival data:")
patients_b_df = patients[patients["subject_id"].isin(patients_b)]
dod_b_with = patients_b_df["dod"].notna().sum()
dod_b_without = patients_b_df["dod"].isna().sum()
censored_pct_b = (dod_b_without / len(patients_b_df)) * 100

print(f"  Patients with dod (events): {dod_b_with}")
print(f"  Patients without dod (censored): {dod_b_without}")
print(f"  % censored: {censored_pct_b:.1f}%")

add_text(f"\n**Disease B survival data:**")
add_text(f"- Patients with dod (events): {dod_b_with}")
add_text(f"- Patients without dod (censored): {dod_b_without}")
add_text(f"- % censored: {censored_pct_b:.1f}%")

# Admission dates per patient
print("\nAdmission date ranges:")
admissions_a = admissions[admissions["subject_id"].isin(patients_a)]
admissions_b = admissions[admissions["subject_id"].isin(patients_b)]

if len(admissions_a) > 0:
    min_admit_a = admissions_a["admittime"].min()
    max_admit_a = admissions_a["admittime"].max()
    print(f"  Disease A: {min_admit_a} to {max_admit_a}")
    add_text(f"\n**Disease A admission date range:** {min_admit_a} to {max_admit_a}")

if len(admissions_b) > 0:
    min_admit_b = admissions_b["admittime"].min()
    max_admit_b = admissions_b["admittime"].max()
    print(f"  Disease B: {min_admit_b} to {max_admit_b}")
    add_text(f"\n**Disease B admission date range:** {min_admit_b} to {max_admit_b}")

# =============================================================================
# STEP 7 — Summary & warnings
# =============================================================================
add_section("7. Summary & warnings")

print("\n" + "=" * 80)
print("STEP 7 — Summary & warnings")
print("=" * 80)

print("\nAll warnings raised during exploration:")
if len(warnings) == 0:
    print("  No warnings ✓")
    add_text("\n**All warnings raised during exploration:**")
    add_text("- No warnings ✓")
else:
    for w in warnings:
        print(f"  {w}")
    add_text("\n**All warnings raised during exploration:**")
    for w in warnings:
        add_text(f"- {w}")

print(f"\nSelected diseases:")
print(f"  Disease A: ICD-{disease_a['icd_version']} {disease_a['icd_code']} - {disease_a['long_title']}")
print(f"  Disease B: ICD-{disease_b['icd_version']} {disease_b['icd_code']} - {disease_b['long_title']}")

add_text(f"\n**Selected diseases:**")
add_text(f"- Disease A: ICD-{disease_a['icd_version']} {disease_a['icd_code']} - {disease_a['long_title']}")
add_text(f"- Disease B: ICD-{disease_b['icd_version']} {disease_b['icd_code']} - {disease_b['long_title']}")

# Assess feasibility
feasible = True
recommendations = []

if disease_a['patient_count'] < 10 or disease_b['patient_count'] < 10:
    feasible = False
    recommendations.append("Consider pooling Disease A and Disease B cohorts due to small sample sizes.")

if dod_a_with < 3 or dod_b_with < 3:
    event_warning = "⚠️ Very few death events in one or both cohorts — survival analysis may not be meaningful."
    print(f"\n{event_warning}")
    warnings.append(event_warning)
    recommendations.append("Event counts are very low. Results will be illustrative only.")

print(f"\nPhase 2 (survival analysis) feasible: {feasible}")
add_text(f"\n**Phase 2 (survival analysis) feasible:** {feasible}")

if recommendations:
    print("\nRecommendations:")
    for rec in recommendations:
        print(f"  - {rec}")
    add_text(f"\n**Recommendations:**")
    for rec in recommendations:
        add_text(f"- {rec}")

# Save report
report_path = "outputs/phase1_data_profile.md"
with open(report_path, "w") as f:
    f.write("".join(report))

print("\n" + "=" * 80)
print(f"Report saved to: {report_path}")
print("=" * 80)

# Save the disease codes for the final answer
print("\n" + "=" * 80)
print("FINAL ANSWER:")
print("=" * 80)
print(f"Disease A: ICD-{disease_a['icd_version']} code {disease_a['icd_code']}")
print(f"Disease B: ICD-{disease_b['icd_version']} code {disease_b['icd_code']}")
print("=" * 80)

# Save the answer in a machine-readable format
answer = f"Disease A: ICD-{disease_a['icd_version']} code {disease_a['icd_code']}, Disease B: ICD-{disease_b['icd_version']} code {disease_b['icd_code']}"
with open("outputs/answer.txt", "w") as f:
    f.write(answer)
print(f"\nAnswer saved to: outputs/answer.txt")
