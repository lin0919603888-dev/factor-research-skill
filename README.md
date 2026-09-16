# factor-research-skill

A minimal, programmatically validated factor research skill. It does not attempt
to be a quantitative trading platform.

## Requirements

- Python 3.10+
- pandas
- numpy

Install pandas with your preferred environment manager. No other third-party
dependency is introduced by this skill.

## Repository layout

```text
factor-research-skill/
├── SKILL.md                     # Agent-facing workflow and tool invocation contract
├── manifest.json                # Skill metadata
├── schemas/                     # Input, factor, and validation JSON schemas
├── prompts/                     # Agent prompts for generation, analysis, reporting
├── tools/                       # Deterministic check, execution, metric, gate code
├── references/                  # Factor, financial, and evaluation constraints
├── templates/                   # Output templates
├── examples/                    # Minimal valid examples
└── tests/                       # End-to-end smoke tests
```

## Minimal command sequence

From this directory:

```powershell
python tools/factor_checker.py --factor-json examples/factor_example.json --output-json check.json
python tools/factor_executor.py --factor-json examples/factor_example.json --market-csv <market.csv> --output-csv factor_values.csv
python tools/backtest_runner.py --factor-csv factor_values.csv --market-csv <market.csv> --horizon 1 --output-json backtest.json
python tools/gate_checker.py --metrics-json backtest.json --output-json gate_result.json
```

The market CSV must contain at least `date` and `close`; the documented minute
format also contains `open`, `high`, `low`, `volume`, `average`, and `barCount`.

## Metric behavior

With repeated dates and multiple observations per date, `metric_calculator.py`
uses conventional cross-sectional IC and RankIC. For a single time series, it
uses rolling correlations and labels the method `rolling_time_series`.

Return-based performance is intentionally returned as `null`. There is no
portfolio simulator, cost model, execution model, or universe construction in
this first stage.

## Extending the skill

- Add new data checks to `tools/factor_checker.py`.
- Add execution guardrails in `tools/factor_executor.py`.
- Extend metrics in `tools/metric_calculator.py`.
- Add portfolio evaluation behind `run_backtest`, keeping the output protocol
  compatible with `schemas/validation_schema.json`.
- Add gate thresholds through a JSON file rather than hard-coding policy.

## Security note

Factor execution dynamically runs generated Python source. Run this skill only
on trusted or isolated inputs, and always invoke `factor_checker.py` first. The
checker is not a security sandbox.

