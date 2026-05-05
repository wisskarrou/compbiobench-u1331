# Phase 2 Survival Analysis Summary

**Generated:** 2026-05-02 16:01:43

## Cohort
This analysis examined survival after first diagnosis of hypertension (n=38)
or hyperlipidemia (n=32) among hospitalized patients in the MIMIC-IV demo
dataset (total cohort n=70).

## Key Findings

### Kaplan-Meier Analysis
Median survival for hypertension was 1194.0 days. Median survival for hyperlipidemia was 367.0 days. 

### Log-Rank Test
The log-rank test yielded p = 0.0664, indicating no statistically significant difference in survival
between hypertension and hyperlipidemia patients. This non-significant result is
expected given the small cohort size and limited statistical power. 

### Cox Proportional Hazards Model
The Cox regression model adjusted for age, sex, and disease type.
Age at diagnosis showed a hazard ratio of 1.027 (95% CI: [0.994, 1.061],
p = 0.1143), indicating that each additional year of age is associated with
a 2.7% increase in mortality risk. The disease type (hypertension vs hyperlipidemia) had a hazard ratio
of 0.501 (95% CI: [0.216, 1.164], p = 0.1081).


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
