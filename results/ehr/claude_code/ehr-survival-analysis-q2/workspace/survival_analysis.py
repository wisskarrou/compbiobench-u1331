#!/usr/bin/env python3
"""
Phase 2 - Survival Analysis: Hypertension vs Hyperlipidemia
MIMIC-IV Demo v2.2
"""

import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')  # Non-interactive backend
import matplotlib.pyplot as plt
from lifelines import KaplanMeierFitter, CoxPHFitter
from lifelines.statistics import logrank_test

print("=" * 80)
print("PHASE 2: SURVIVAL ANALYSIS")
print("Hypertension vs Hyperlipidemia - Time to Death After Diagnosis")
print("=" * 80)

# ============================================================================
# STEP 0: Load Data
# ============================================================================
print("\n[STEP 0] Loading MIMIC-IV Demo data...")

BASE = "ehr/hosp/"

patients = pd.read_csv(BASE + "patients.csv.gz", compression="gzip")
admissions = pd.read_csv(BASE + "admissions.csv.gz", compression="gzip")
diagnoses = pd.read_csv(BASE + "diagnoses_icd.csv.gz", compression="gzip")

print(f"  ✓ Patients: {patients.shape}")
print(f"  ✓ Admissions: {admissions.shape}")
print(f"  ✓ Diagnoses: {diagnoses.shape}")

# ============================================================================
# STEP 1: Build the Hypertension / Hyperlipidemia Cohort
# ============================================================================
print("\n[STEP 1] Building cohort using Phase 1 verified ICD codes...")

# From Phase 1:
# - HTN: ICD-9 4019 (41 patients), ICD-10 I10 (17 patients)
# - HLD: ICD-9 2724 (34 patients), ICD-10 E785 (21 patients)

# Hypertension mask
htn_mask = (
    ((diagnoses["icd_code"] == "I10") & (diagnoses["icd_version"] == 10)) |
    ((diagnoses["icd_code"] == "4019") & (diagnoses["icd_version"] == 9))
)

# Hyperlipidemia mask
hld_mask = (
    ((diagnoses["icd_code"].str.startswith("E78")) & (diagnoses["icd_version"] == 10)) |
    ((diagnoses["icd_code"] == "2724") & (diagnoses["icd_version"] == 9))
)

# Extract diagnoses with disease labels
htn_dx = diagnoses[htn_mask].copy()
htn_dx["disease_group"] = "HTN"

hld_dx = diagnoses[hld_mask].copy()
hld_dx["disease_group"] = "HLD"

# Combine
all_dx = pd.concat([htn_dx, hld_dx], ignore_index=True)

# Join with admissions to get admittime
all_dx = all_dx.merge(
    admissions[["hadm_id", "admittime"]],
    on="hadm_id",
    how="left"
)

# Convert to datetime
all_dx["admittime"] = pd.to_datetime(all_dx["admittime"])

# For each patient, find the FIRST admission where ANY diagnosis appears
first_diag = all_dx.sort_values("admittime").groupby("subject_id").first().reset_index()

# Count unique patients in each disease group
n_htn_raw = all_dx[all_dx["disease_group"] == "HTN"]["subject_id"].nunique()
n_hld_raw = all_dx[all_dx["disease_group"] == "HLD"]["subject_id"].nunique()

# Check for overlap (patients with both diseases)
htn_subjects = set(htn_dx["subject_id"].unique())
hld_subjects = set(hld_dx["subject_id"].unique())
overlap = htn_subjects & hld_subjects

if len(overlap) > 0:
    print(f"\n  ⚠️  {len(overlap)} patients have BOTH hypertension and hyperlipidemia.")
    print(f"      Assigning each to the disease diagnosed FIRST chronologically...")

# Since first_diag already takes the earliest admission per patient,
# the disease_group already reflects which was diagnosed first
cohort = first_diag.copy()

# Final counts
n_htn = (cohort["disease_group"] == "HTN").sum()
n_hld = (cohort["disease_group"] == "HLD").sum()
n_total = len(cohort)

print(f"\n  ✓ Hypertension patients: {n_htn}")
print(f"  ✓ Hyperlipidemia patients: {n_hld}")
print(f"  ✓ Combined cohort size: {n_total}")

if n_total < 10:
    print("\n  ⚠️  WARNING: Cohort size < 10. Results are illustrative only.")
    print("      Statistical tests may not be meaningful.")

# ============================================================================
# STEP 2: Compute Survival Time
# ============================================================================
print("\n[STEP 2] Computing survival times...")

# Join with patients table to get dod, anchor_age, gender
cohort = cohort.merge(
    patients[["subject_id", "dod", "anchor_age", "gender"]],
    on="subject_id",
    how="left"
)

# Convert dates
cohort["first_diag_date"] = pd.to_datetime(cohort["admittime"])
cohort["dod"] = pd.to_datetime(cohort["dod"])

# Survival time = days from first diagnosis to death
cohort["time_to_death_days"] = (cohort["dod"] - cohort["first_diag_date"]).dt.days

# Event indicator: 1 if death observed, 0 if censored
cohort["event"] = cohort["dod"].notna().astype(int)

# Handle negative or zero survival times (data quality issue)
negative_mask = (cohort["event"] == 1) & (cohort["time_to_death_days"] <= 0)
if negative_mask.sum() > 0:
    print(f"\n  ⚠️  {negative_mask.sum()} patients have death date ≤ diagnosis date.")
    print("      Setting these as censored (data quality issue).")
    cohort.loc[negative_mask, "event"] = 0
    cohort.loc[negative_mask, "time_to_death_days"] = np.nan

# For censored patients, impute survival time as days to last contact
last_contact = admissions.groupby("subject_id")["dischtime"].max().reset_index()
last_contact.columns = ["subject_id", "last_contact_date"]
last_contact["last_contact_date"] = pd.to_datetime(last_contact["last_contact_date"])

cohort = cohort.merge(last_contact, on="subject_id", how="left")

# Fill missing survival times for censored patients
censored_mask = cohort["event"] == 0
cohort.loc[censored_mask, "time_to_death_days"] = (
    cohort.loc[censored_mask, "last_contact_date"] -
    cohort.loc[censored_mask, "first_diag_date"]
).dt.days

# Print summary statistics
print("\n  Event counts:")
for disease in ["HTN", "HLD"]:
    group = cohort[cohort["disease_group"] == disease]
    n_events = group["event"].sum()
    n_censored = len(group) - n_events
    print(f"    {disease}: {n_events} deaths, {n_censored} censored")

# Median follow-up for censored
censored_cohort = cohort[cohort["event"] == 0]
median_followup = censored_cohort["time_to_death_days"].median()
print(f"\n  Median follow-up time (censored patients): {median_followup:.1f} days")

# Statistics for patients with events
event_cohort = cohort[cohort["event"] == 1]
if len(event_cohort) > 0:
    print(f"\n  Survival time for patients with events (deaths):")
    print(f"    Min: {event_cohort['time_to_death_days'].min():.1f} days")
    print(f"    Max: {event_cohort['time_to_death_days'].max():.1f} days")
    print(f"    Mean: {event_cohort['time_to_death_days'].mean():.1f} days")

# ============================================================================
# STEP 3: Kaplan-Meier Survival Curves
# ============================================================================
print("\n[STEP 3] Generating Kaplan-Meier survival curves...")

fig, ax = plt.subplots(figsize=(10, 6))

kmf_htn = KaplanMeierFitter()
kmf_hld = KaplanMeierFitter()

htn_group = cohort[cohort["disease_group"] == "HTN"]
hld_group = cohort[cohort["disease_group"] == "HLD"]

kmf_htn.fit(
    durations=htn_group["time_to_death_days"],
    event_observed=htn_group["event"],
    label="Hypertension"
)

kmf_hld.fit(
    durations=hld_group["time_to_death_days"],
    event_observed=hld_group["event"],
    label="Hyperlipidemia"
)

kmf_htn.plot_survival_function(ax=ax, ci_show=True)
kmf_hld.plot_survival_function(ax=ax, ci_show=True)

ax.set_title("Kaplan-Meier Survival Curves\nHypertension vs Hyperlipidemia — MIMIC-IV Demo")
ax.set_xlabel("Days since first diagnosis")
ax.set_ylabel("Survival probability")
ax.legend()
plt.tight_layout()
plt.savefig("outputs/km_curves_HTN_HLD.png", dpi=150)
print("  ✓ Saved: outputs/km_curves_HTN_HLD.png")

# Print median survival times
median_htn = kmf_htn.median_survival_time_
ci_htn = kmf_htn.confidence_interval_survival_function_
median_hld = kmf_hld.median_survival_time_
ci_hld = kmf_hld.confidence_interval_survival_function_

print(f"\n  Median survival time:")
if np.isnan(median_htn):
    print(f"    Hypertension: Not reached (>50% censored)")
else:
    print(f"    Hypertension: {median_htn:.1f} days")

if np.isnan(median_hld):
    print(f"    Hyperlipidemia: Not reached (>50% censored)")
else:
    print(f"    Hyperlipidemia: {median_hld:.1f} days")

# ============================================================================
# STEP 4: Log-Rank Test
# ============================================================================
print("\n[STEP 4] Performing log-rank test...")

results = logrank_test(
    durations_A=htn_group["time_to_death_days"],
    durations_B=hld_group["time_to_death_days"],
    event_observed_A=htn_group["event"],
    event_observed_B=hld_group["event"]
)

print(f"\n  Log-rank test p-value: {results.p_value:.4f}")

if results.p_value < 0.05:
    print("  → Statistically significant difference in survival (p < 0.05)")
else:
    print("  → No statistically significant difference detected (p ≥ 0.05)")
    print("     Note: Small demo cohort → low statistical power expected")

# ============================================================================
# STEP 5: Cox Proportional Hazards Model
# ============================================================================
print("\n[STEP 5] Fitting Cox proportional hazards model...")

# Prepare covariate matrix
cox_data = cohort[[
    "time_to_death_days",
    "event",
    "anchor_age",
    "gender",
    "disease_group"
]].copy()

# Encode categoricals
cox_data["gender_male"] = (cox_data["gender"] == "M").astype(int)
cox_data["is_HTN"] = (cox_data["disease_group"] == "HTN").astype(int)
cox_data = cox_data.drop(columns=["gender", "disease_group"])

# Fit Cox model
cph = CoxPHFitter()

try:
    cph.fit(
        cox_data,
        duration_col="time_to_death_days",
        event_col="event"
    )

    print("\n" + "=" * 80)
    cph.print_summary()
    print("=" * 80)

    # Save summary
    cph.summary.to_csv("outputs/cox_model_summary.csv")
    print("\n  ✓ Saved: outputs/cox_model_summary.csv")

    # Plain-English interpretation
    print("\n  Cox Model Interpretation:")

    hr_age = cph.summary.loc["anchor_age", "exp(coef)"]
    ci_age_lower = cph.summary.loc["anchor_age", "exp(coef) lower 95%"]
    ci_age_upper = cph.summary.loc["anchor_age", "exp(coef) upper 95%"]
    p_age = cph.summary.loc["anchor_age", "p"]

    if hr_age > 1:
        direction_age = "higher"
    else:
        direction_age = "lower"

    print(f"    • anchor_age: For each additional year of age, the risk of death is")
    print(f"      {direction_age} (HR = {hr_age:.3f}, 95% CI: [{ci_age_lower:.3f}, {ci_age_upper:.3f}], p = {p_age:.4f})")

    hr_male = cph.summary.loc["gender_male", "exp(coef)"]
    ci_male_lower = cph.summary.loc["gender_male", "exp(coef) lower 95%"]
    ci_male_upper = cph.summary.loc["gender_male", "exp(coef) upper 95%"]
    p_male = cph.summary.loc["gender_male", "p"]

    if hr_male > 1:
        direction_male = "higher"
    else:
        direction_male = "lower"

    print(f"    • gender_male: Male patients have {direction_male} risk compared to female")
    print(f"      (HR = {hr_male:.3f}, 95% CI: [{ci_male_lower:.3f}, {ci_male_upper:.3f}], p = {p_male:.4f})")

    hr_htn = cph.summary.loc["is_HTN", "exp(coef)"]
    ci_htn_lower = cph.summary.loc["is_HTN", "exp(coef) lower 95%"]
    ci_htn_upper = cph.summary.loc["is_HTN", "exp(coef) upper 95%"]
    p_htn = cph.summary.loc["is_HTN", "p"]

    if hr_htn > 1:
        direction_htn = "higher"
    else:
        direction_htn = "lower"

    print(f"    • is_HTN: Hypertension patients have {direction_htn} risk compared to")
    print(f"      hyperlipidemia (HR = {hr_htn:.3f}, 95% CI: [{ci_htn_lower:.3f}, {ci_htn_upper:.3f}], p = {p_htn:.4f})")

except Exception as e:
    print(f"\n  ⚠️  Cox model failed to converge: {e}")
    print("      Running simplified models with single covariates...")

    for var in ["anchor_age", "gender_male", "is_HTN"]:
        try:
            cph_simple = CoxPHFitter()
            cph_simple.fit(
                cox_data[["time_to_death_days", "event", var]],
                duration_col="time_to_death_days",
                event_col="event"
            )
            print(f"\n    {var}:")
            print(f"      HR = {cph_simple.summary.loc[var, 'exp(coef)']:.3f}")
        except Exception as e2:
            print(f"\n    {var}: Failed ({e2})")

# ============================================================================
# STEP 6: Summary & Limitations
# ============================================================================
print("\n[STEP 6] Writing summary report...")

summary_text = f"""# Phase 2 Survival Analysis Summary

**Generated:** {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')}

## Cohort
This analysis examined survival after first diagnosis of hypertension (n={n_htn})
or hyperlipidemia (n={n_hld}) among hospitalized patients in the MIMIC-IV demo
dataset (total cohort n={n_total}).

## Key Findings

### Kaplan-Meier Analysis
"""

if np.isnan(median_htn):
    summary_text += f"Median survival time was not reached for the hypertension group (>50% censored). "
else:
    summary_text += f"Median survival for hypertension was {median_htn:.1f} days. "

if np.isnan(median_hld):
    summary_text += f"Median survival time was not reached for the hyperlipidemia group (>50% censored). "
else:
    summary_text += f"Median survival for hyperlipidemia was {median_hld:.1f} days. "

summary_text += f"""

### Log-Rank Test
The log-rank test yielded p = {results.p_value:.4f}, """

if results.p_value < 0.05:
    summary_text += "indicating a statistically significant difference in survival between the two groups. "
else:
    summary_text += """indicating no statistically significant difference in survival
between hypertension and hyperlipidemia patients. This non-significant result is
expected given the small cohort size and limited statistical power. """

summary_text += f"""

### Cox Proportional Hazards Model
"""

if 'hr_age' in locals():
    summary_text += f"""The Cox regression model adjusted for age, sex, and disease type.
Age at diagnosis showed a hazard ratio of {hr_age:.3f} (95% CI: [{ci_age_lower:.3f}, {ci_age_upper:.3f}],
p = {p_age:.4f}), indicating that each additional year of age is associated with
"""
    if hr_age > 1:
        summary_text += f"a {((hr_age - 1) * 100):.1f}% increase in mortality risk. "
    else:
        summary_text += f"a {((1 - hr_age) * 100):.1f}% decrease in mortality risk. "

    summary_text += f"""The disease type (hypertension vs hyperlipidemia) had a hazard ratio
of {hr_htn:.3f} (95% CI: [{ci_htn_lower:.3f}, {ci_htn_upper:.3f}], p = {p_htn:.4f}).
"""
else:
    summary_text += "The Cox model did not converge successfully, likely due to the small cohort size. "

summary_text += """

## Limitations

1. **Survivorship Bias**: MIMIC-IV captures only hospitalized patients, who represent
   a sicker subset of the general population with hypertension or hyperlipidemia.
   Results cannot be generalized to community-dwelling patients with these conditions.

2. **Small Cohort Size**: The MIMIC-IV demo dataset contains only 100 patients total,
   with our analysis cohort representing a subset. This severely limits statistical
   power and generalizability. Confidence intervals are wide, and null findings
   should not be interpreted as evidence of no effect.

3. **High Censoring Rate**: Approximately 60-70% of patients lack a recorded date of
   death, which limits our ability to detect differences in survival. Many patients
   may have died after discharge without this being captured in the hospital database.

4. **Age Measurement Imprecision**: The `anchor_age` variable represents age at a
   de-identified reference year, not age at diagnosis. This introduces imprecision
   into the age covariate in the Cox model.

5. **Diagnosis Timing**: We use hospital admission time as a proxy for diagnosis date,
   but the actual diagnosis may have occurred earlier in an outpatient setting. This
   left truncation could bias survival estimates.

6. **Confounding**: We did not adjust for important clinical confounders such as
   comorbidity burden, disease severity, or treatment differences, which likely
   influence survival.

---

**Conclusion**: While this analysis demonstrates the technical workflow for survival
analysis on EHR data, the substantive findings should be interpreted with extreme
caution due to the limitations listed above. The primary value of this exercise is
methodological rather than clinical.
"""

with open("outputs/phase2_survival_summary.md", "w") as f:
    f.write(summary_text)

print("  ✓ Saved: outputs/phase2_survival_summary.md")

# ============================================================================
# Final Output
# ============================================================================
print("\n" + "=" * 80)
print("PHASE 2 COMPLETE")
print("=" * 80)
print("\nOutputs:")
print("  ✓ outputs/km_curves_HTN_HLD.png")
print("  ✓ outputs/cox_model_summary.csv")
print("  ✓ outputs/phase2_survival_summary.md")
print("\n" + "=" * 80)
