# CLAUDE.md — Phase 2: Survival Analysis
# Hypertension & Hyperlipidemia — Time to Death After Diagnosis
# MIMIC-IV Demo v2.2

---

## Prerequisites — Read Before Starting
Before running any analysis, read the file `outputs/phase1_data_profile.md`.
This file was produced in Phase 1 and contains:
- Verified column names and table shapes
- Exact ICD codes confirmed to exist in this dataset
- Cohort sizes for hypertension and hyperlipidemia
- Known data quality warnings

**Do not assume any column names or cohort sizes. Use only what Phase 1 confirmed.**
If `outputs/phase1_data_profile.md` does not exist, stop and ask the user to
run Phase 1 first.

---

## Your Role
You are a biomedical data analyst performing a survival analysis on
electronic health records from the MIMIC-IV demo dataset. You will:
1. Build a cohort of patients diagnosed with hypertension or hyperlipidemia
2. Compute time from first diagnosis to death (or censoring)
3. Produce Kaplan-Meier survival curves and a Cox regression model
4. Interpret the results clearly, including their limitations

Always explain what you are doing before each code block. After each step,
print a summary of the results before moving on.

---

## Research Question
**"What is the survival trajectory of patients diagnosed with hypertension or
hyperlipidemia in this hospital dataset? Does disease type, age at
diagnosis, or sex predict time to death?"**

---

## Data Location & Loading
```python
import pandas as pd

# Adjust base path if needed
BASE = "physionet.org/files/mimic-iv-demo/2.2/hosp/"

patients     = pd.read_csv(BASE + "patients.csv.gz",      compression="gzip")
admissions   = pd.read_csv(BASE + "admissions.csv.gz",    compression="gzip")
diagnoses    = pd.read_csv(BASE + "diagnoses_icd.csv.gz", compression="gzip")
```

---

## Required Libraries
```python
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from lifelines import KaplanMeierFitter, CoxPHFitter
from lifelines.statistics import logrank_test
```
Install if needed: `pip install lifelines matplotlib`

---

## Step-by-Step Analysis

### STEP 1 — Build the Hypertension / Hyperlipidemia Cohort

Use the EXACT ICD codes confirmed in Phase 1. Do not guess or add new codes.

```python
# Hypertension: use exact codes confirmed in Phase 1 (examples shown below —
# replace with the codes reported in outputs/phase1_data_profile.md)
htn_mask = (
    ((diagnoses["icd_code"].str.startswith("I10")) & (diagnoses["icd_version"] == 10)) |
    ((diagnoses["icd_code"] == "4019") & (diagnoses["icd_version"] == 9))
)

# Hyperlipidemia: use exact codes confirmed in Phase 1 (examples shown below —
# replace with the codes reported in outputs/phase1_data_profile.md)
hld_mask = (
    ((diagnoses["icd_code"].str.startswith("E78")) & (diagnoses["icd_version"] == 10)) |
    ((diagnoses["icd_code"] == "2724") & (diagnoses["icd_version"] == 9))
)
```

**1a.** For each patient, find the **first admission** where the diagnosis appears:
- Join diagnoses with admissions on `hadm_id` to get `admittime`
- Keep only the row with the earliest `admittime` per patient
- This `admittime` = proxy for "date of first diagnosis" in this dataset

**1b.** Assign disease group labels:
- `"HTN"` for hypertension patients
- `"HLD"` for hyperlipidemia patients
- If a patient has both (flagged in Phase 1): assign to the FIRST diagnosed
  disease, and print a note

**Print after this step:**
- Number of hypertension patients
- Number of hyperlipidemia patients
- Combined cohort size

> ⚠️ If cohort size < 10 total patients: print a warning that results are
> illustrative only and statistical tests may not be meaningful.
> Continue the analysis anyway — this is a demo dataset.

---

### STEP 2 — Compute Survival Time

**2a.** Join cohort with `patients` table on `subject_id` to get `dod` and
`anchor_age`.

**2b.** Compute `time_to_death_days`:
```python
# Convert to datetime first
cohort["first_diag_date"] = pd.to_datetime(cohort["admittime"])
cohort["dod"] = pd.to_datetime(cohort["dod"])

# Survival time = days from first diagnosis to death
cohort["time_to_death_days"] = (cohort["dod"] - cohort["first_diag_date"]).dt.days
```

**2c.** Create the `event` (death indicator) column:
```python
# event = 1 if death observed, 0 if censored (dod is null)
cohort["event"] = cohort["dod"].notna().astype(int)
```

**2d.** Handle negative or zero survival times:
- If `time_to_death_days <= 0` for any patient with `event == 1`:
  this likely means the death date predates or equals the diagnosis date
  (data quality issue). Print a ⚠️ warning and set those patients as censored.

**2e.** For censored patients (`event == 0`), impute `time_to_death_days`
as days from first diagnosis to their LAST admission's `dischtime`:
```python
# Get last discharge time per patient from admissions
last_contact = admissions.groupby("subject_id")["dischtime"].max().reset_index()
last_contact.columns = ["subject_id", "last_contact_date"]
last_contact["last_contact_date"] = pd.to_datetime(last_contact["last_contact_date"])
# Fill missing survival times for censored patients
```

**Print after this step:**
- Count of events (deaths observed) vs censored per disease group
- Median follow-up time in days (for censored patients)
- Min, max, mean `time_to_death_days` for patients with events

---

### STEP 3 — Kaplan-Meier Survival Curves

```python
from lifelines import KaplanMeierFitter
import matplotlib.pyplot as plt

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
plt.show()
```

**Print after this step:**
- Median survival time in days for hypertension group (with 95% CI)
- Median survival time in days for hyperlipidemia group (with 95% CI)
- Note: if median is NaN, it means >50% of patients are still censored

---

### STEP 4 — Log-Rank Test

```python
from lifelines.statistics import logrank_test

results = logrank_test(
    durations_A=htn_group["time_to_death_days"],
    durations_B=hld_group["time_to_death_days"],
    event_observed_A=htn_group["event"],
    event_observed_B=hld_group["event"]
)

print(f"Log-rank test p-value: {results.p_value:.4f}")
```

**Interpret the p-value:**
- p < 0.05 → statistically significant difference in survival between hypertension and hyperlipidemia
- p ≥ 0.05 → no statistically significant difference detected
- **Always note**: with a small demo cohort, low statistical power is expected.
  A non-significant result does NOT mean the diseases have the same prognosis.

---

### STEP 5 — Cox Proportional Hazards Model

**5a.** Prepare the covariate matrix:
```python
cox_data = cohort[[
    "time_to_death_days",
    "event",
    "anchor_age",       # age at anchor year (proxy for age at diagnosis)
    "gender",           # binary: M / F
    "disease_group"     # HTN or HLD
]].copy()

# Encode categoricals
cox_data["gender_male"] = (cox_data["gender"] == "M").astype(int)
cox_data["is_HTN"] = (cox_data["disease_group"] == "HTN").astype(int)
cox_data = cox_data.drop(columns=["gender", "disease_group"])
```

**5b.** Fit the Cox model:
```python
from lifelines import CoxPHFitter

cph = CoxPHFitter()
cph.fit(
    cox_data,
    duration_col="time_to_death_days",
    event_col="event"
)
cph.print_summary()
```

**5c.** Save the summary table:
```python
cph.summary.to_csv("outputs/cox_model_summary.csv")
```

**5d.** Print a plain-English interpretation for each covariate:
- `anchor_age`: "For each additional year of age, the risk of death is X times
  higher/lower (HR = ...)"
- `gender_male`: "Male patients have X times higher/lower risk compared to
  female patients (HR = ...)"
- `is_HTN`: "Hypertension patients have X times higher/lower risk compared to
  hyperlipidemia patients (HR = ...)"

> ⚠️ If the model fails to converge (common with very small cohorts):
> print the error, then run a simplified model with only 1 covariate at a time.

---

### STEP 6 — Summary & Limitations

Write a short paragraph (5–8 sentences) that:
1. States the cohort size (hypertension n=X, hyperlipidemia n=Y)
2. Reports key KM findings (median survival, which group survived longer)
3. Reports the log-rank test result
4. Reports the most meaningful Cox HR with its 95% CI
5. Lists at least 3 limitations:
   - **Survivorship bias**: MIMIC captures hospitalized patients only —
     these are sicker than the general population with these conditions
   - **Small cohort**: MIMIC-IV demo has only 100 patients total;
     results are not generalizable
   - **Censoring**: ~69% of patients have no recorded death date —
     this limits statistical power
   - **Age proxy**: `anchor_age` is age at a reference year, not age at
     diagnosis — this introduces imprecision

---

## Outputs to Produce
Save all of the following:

| File | Content |
|---|---|
| `outputs/km_curves_HTN_HLD.png` | Kaplan-Meier plot with confidence intervals |
| `outputs/cox_model_summary.csv` | Cox regression coefficients table |
| `outputs/phase2_survival_summary.md` | Full narrative summary (Step 6) |

---

## Instructor Validation Checklist
Use this to verify the agent's output is correct:

| Check | What to verify |
|---|---|
| Cohort size | Hypertension + hyperlipidemia total should be < 100 (subset of 100 patients) |
| Event rate | Should match Phase 1 `dod` non-null count for these patients |
| KM curves | Should not cross early; confidence intervals will be wide (small n) |
| Cox HR for age | Should be > 1.0 (older = higher mortality risk) |
| Censoring rate | Should be high (~60–80%) given only 31/100 patients have `dod` |
| p-value | Likely non-significant (p > 0.05) due to small cohort — this is expected |
