# Evaluation Rules

## Metrics

### IC

Information Coefficient: mean Pearson correlation between factor values and
subsequent forward returns.

### RankIC

Mean Spearman rank correlation between factor values and subsequent forward
returns. It is less sensitive to extreme values than Pearson IC.

### ICIR

Mean IC divided by the standard deviation of the IC samples. It describes
stability of the predictive relationship, not investment return.

### IC positive ratio

Fraction of non-null IC samples greater than zero. It is descriptive and is not
sufficient for gating in the default rules.

## Calculation modes

### Cross-sectional mode

When observations contain repeated `date` values, the calculator computes a
factor/return correlation for each date. This is the conventional IC definition
for a multi-asset panel.

### Rolling time-series fallback

When no cross-section is supplied, the calculator computes rolling Pearson and
Spearman correlations over `--rolling-window` observations. This is explicitly a
time-series diagnostic, not a replacement for cross-sectional IC.

## Missing metric handling

Missing IC values are reported as JSON `null`, never imputed or invented. The
default gate rejects missing required metrics.

