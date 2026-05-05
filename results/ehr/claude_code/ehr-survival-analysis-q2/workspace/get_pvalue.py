#!/usr/bin/env python3
import pandas as pd
import numpy as np
from lifelines.statistics import logrank_test

# Load data
BASE = "ehr/hosp/"
patients = pd.read_csv(BASE + "patients.csv.gz", compression="gzip")
admissions = pd.read_csv(BASE + "admissions.csv.gz", compression="gzip")
diagnoses = pd.read_csv(BASE + "diagnoses_icd.csv.gz", compression="gzip")

# Build cohort (same as before)
htn_mask = (
    ((diagnoses["icd_code"] == "I10") & (diagnoses["icd_version"] == 10)) |
    ((diagnoses["icd_code"] == "4019") & (diagnoses["icd_version"] == 9))
)
hld_mask = (
    ((diagnoses["icd_code"].str.startswith("E78")) & (diagnoses["icd_version"] == 10)) |
    ((diagnoses["icd_code"] == "2724") & (diagnoses["icd_version"] == 9))
)

htn_dx = diagnoses[htn_mask].copy()
htn_dx["disease_group"] = "HTN"
hld_dx = diagnoses[hld_mask].copy()
hld_dx["disease_group"] = "HLD"

all_dx = pd.concat([htn_dx, hld_dx], ignore_index=True)
all_dx = all_dx.merge(admissions[["hadm_id", "admittime"]], on="hadm_id", how="left")
all_dx["admittime"] = pd.to_datetime(all_dx["admittime"])

first_diag = all_dx.sort_values("admittime").groupby("subject_id").first().reset_index()
cohort = first_diag.copy()

cohort = cohort.merge(patients[["subject_id", "dod", "anchor_age", "gender"]], on="subject_id", how="left")
cohort["first_diag_date"] = pd.to_datetime(cohort["admittime"])
cohort["dod"] = pd.to_datetime(cohort["dod"])
cohort["time_to_death_days"] = (cohort["dod"] - cohort["first_diag_date"]).dt.days
cohort["event"] = cohort["dod"].notna().astype(int)

negative_mask = (cohort["event"] == 1) & (cohort["time_to_death_days"] <= 0)
cohort.loc[negative_mask, "event"] = 0
cohort.loc[negative_mask, "time_to_death_days"] = np.nan

last_contact = admissions.groupby("subject_id")["dischtime"].max().reset_index()
last_contact.columns = ["subject_id", "last_contact_date"]
last_contact["last_contact_date"] = pd.to_datetime(last_contact["last_contact_date"])
cohort = cohort.merge(last_contact, on="subject_id", how="left")

censored_mask = cohort["event"] == 0
cohort.loc[censored_mask, "time_to_death_days"] = (
    cohort.loc[censored_mask, "last_contact_date"] - cohort.loc[censored_mask, "first_diag_date"]
).dt.days

htn_group = cohort[cohort["disease_group"] == "HTN"]
hld_group = cohort[cohort["disease_group"] == "HLD"]

# Log-rank test
results = logrank_test(
    durations_A=htn_group["time_to_death_days"],
    durations_B=hld_group["time_to_death_days"],
    event_observed_A=htn_group["event"],
    event_observed_B=hld_group["event"]
)

print(f"{results.p_value:.10f}")
