# Financial Constraints

## Minute-bar input

The documented input fields are:

```text
date, open, high, low, close, volume, average, barCount
```

Do not assume bid/ask, order-book, fundamental, industry, universe, or symbol
fields unless the current requirement and data explicitly provide them.

## Time discipline

- A factor value at time `t` may use only information available at or before `t`.
- Negative shifts and full-sample normalization are forbidden.
- Forward returns are constructed only by `backtest_runner.py`.
- The prediction horizon comes from `research_requirement.md`.

## Evaluation discipline

- IC, RankIC, and ICIR measure association, not realized profit.
- Missing metrics must remain `null`; they must not be imputed.
- A rejected candidate may be archived with evaluation metadata, but it should
  not be treated as an accepted factor.
- Without repeated dates or symbols, rolling time-series IC is only a diagnostic
  fallback, not a full cross-sectional study.

## Persistence

- Existing library YAML files are immutable.
- A saved candidate receives a new unique filename.
- Evaluation metadata must be program-produced, not manually estimated.

