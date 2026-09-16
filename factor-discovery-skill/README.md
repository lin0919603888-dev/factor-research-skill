# factor-discovery-skill

A minimal factor-discovery skill for YAML factor libraries and minute-bar
market data. It emphasizes provenance, deterministic evolution operations,
program-computed metrics, and non-overwriting persistence.

## Requirements

- Python 3.10+
- pandas
- numpy
- PyYAML

## Directory contract

Prepare files outside or beside this skill:

```text
research_requirement.md
factor_library/
data/
```

`factor_library/` may contain any number of YAML/YML files in nested
subdirectories.

## Quick workflow

From this directory:

```powershell
python tools/factor_loader.py --library ../factor_library --output-json ../library_summary.json

python tools/factor_generator.py --requirement ../research_requirement.md --library ../factor_library --strategy mutation --parent Mined_close_open_ratio_1 --operation rolling_zscore --reason "Test a scale-stable variation." --output-yaml ../candidates/candidate.yaml

python tools/factor_executor.py --factor-yaml ../candidates/candidate.yaml --validate-only --result-json ../candidates/validation.json

python tools/factor_executor.py --factor-yaml ../candidates/candidate.yaml --market-csv ../data/market.csv --output-csv ../candidates/factor_values.csv --result-json ../candidates/execution.json

python tools/backtest_runner.py --factor-csv ../candidates/factor_values.csv --market-csv ../data/market.csv --horizon 1 --output-json ../candidates/backtest.json

python tools/evaluator.py --metrics-json ../candidates/backtest.json --requirement ../research_requirement.md --output-json ../candidates/evaluation.json

python tools/factor_saver.py --factor-yaml ../candidates/candidate.yaml --library ../factor_library --metrics-json ../candidates/backtest.json --evaluation-json ../candidates/evaluation.json --output-json ../candidates/save_result.json
```

Only save when `evaluation.json` reports `gate: pass`.

## Factor formats

Existing expression factors use:

```yaml
name: Mined_close_open_ratio_1
code: "((close / open) * 1.5 + close / 2)"
category: custom
description: Mined price-ratio factor.
formula_type: expression
```

Expression code supports arithmetic over column names only. Calls, attributes,
subscripts, imports, and function invocation are rejected.

Python factors use `formula_type: python` and define one function named after
`name`:

```python
import pandas as pd

def Candidate_Factor_Name(df: pd.DataFrame) -> pd.Series:
    factor = ...
    factor.name = "Candidate_Factor_Name"
    return factor.astype(float)
```

Negative shifts are rejected as obvious lookahead.

## Metrics

`backtest_runner.py` computes:

- IC
- RankIC
- ICIR
- RankICIR
- observation counts
- IC positive ratio

When repeated dates contain multiple observations, metrics use conventional
cross-sectional correlations. Otherwise, the runner uses an explicitly labeled
rolling time-series diagnostic mode.

Return performance is always `null`. There is no portfolio simulator, execution
model, slippage model, fee model, or risk model in this version.

## Extending

- Add deterministic mutation operations in `tools/factor_mutator.py`.
- Add crossover normalization methods in `tools/factor_crossover.py`.
- Extend requirement evaluation rules in `tools/evaluator.py`.
- Keep every generated YAML traceable through `metadata.lineage`.

## Security note

Python factor execution dynamically runs source from YAML. Validate and execute
only trusted files in a controlled environment. The validator is not a sandbox.

