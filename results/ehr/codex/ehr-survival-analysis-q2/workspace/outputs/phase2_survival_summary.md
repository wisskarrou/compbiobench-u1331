# Phase 2 — Survival Analysis Summary

Cohort included 53 patients after first-diagnosis assignment: hypertension n=41, hyperlipidemia n=12.
22 patients had both diagnoses historically and were assigned by earliest diagnosis admission.
Observed deaths/events were HTN=14 and HLD=7; censored counts were HTN=27 and HLD=5.
Median follow-up among censored patients was 11.5 days; event-time range was 14 to 2537 days (mean 604.0).
Kaplan-Meier median survival was 1183.0 days for HTN and 531.0 days for HLD (NaN indicates >50% censored).
Log-rank test comparing HTN vs HLD yielded p=0.2398, indicating no statistically significant difference at alpha=0.05 in this small demo cohort.
In Cox modeling, the strongest signal by p-value was gender_male with HR=2.114 (95% CI 0.850-5.260, p=0.1073).
Interpretation is constrained by survivorship bias (hospitalized-only population), very small sample size in the demo dataset, heavy right-censoring, and use of anchor_age as a proxy rather than exact age at diagnosis.
