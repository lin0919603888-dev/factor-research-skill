# Financial Research Constraints

## Time discipline

- A signal at time `t` may use information available no later than `t`.
- Forward returns must start after the signal timestamp and be produced by the
  evaluation program.
- Align signal timestamps, return timestamps, and any symbols before calculating
  metrics.

## Leakage risks

- Negative shifts are forbidden.
- Do not normalize using the entire sample.
- Do not use future volume, future high/low ranges, or future bar counts.
- Do not use future market regimes or future labels.

## Research discipline

- IC-style association is not profit after costs.
- A single path through history is not proof of robustness.
- Sparse or highly clustered observations can overstate stability.
- Outliers and illiquid bars can dominate correlations.
- Survivorship and universe-selection bias cannot be assessed when no universe
  metadata is supplied.

## Minimal version boundary

This implementation evaluates predictive association only. It does not model
order placement, slippage, fees, position limits, execution delays beyond the
forward horizon, funding, or risk constraints.

