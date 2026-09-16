---
name: factor-research-skill
description: Run a minimal AI factor research loop from a research hypothesis to code validation, execution, predictive-metric evaluation, rule gating, and reporting.
version: 0.1.0
---

# Factor Research Skill

## 1. Purpose

This skill organizes a minimal factor research workflow:

```text
Receive Task
    ↓
Generate Factor
    ↓
Validate Code
    ↓
Execute Factor
    ↓
Run Backtest
    ↓
Evaluate Metrics
    ↓
Check Gate
    ↓
Generate Report
```

It is suitable when the caller supplies a research hypothesis and minute-bar market
data, and wants a candidate factor to be checked, executed, and evaluated by
programs instead of by simulated model output.

## 2. Responsibility boundary

### The agent/LLM does

- Understand `research_hypothesis`.
- Design one clearly explained factor mechanism.
- Generate a JSON factor definition and Python factor function.
- Explain the financial mechanism, assumptions, and risks.
- Generate the final report from program-produced validation results.

### The Python tools do

- Static syntax and function-shape checks.
- Factor execution against a market DataFrame.
- Forward-return construction when a market CSV is supplied.
- IC, RankIC, and ICIR calculation.
- Configurable pass/reject gating.

The agent must never invent metric values. Every reported number must come from
`backtest_runner.py` or `metric_calculator.py`.

## 3. Input

The caller supplies a JSON object conforming to `schemas/input_schema.json`:

```json
{
  "research_hypothesis": "Volume-expanded price strength has short-term continuation.",
  "task_type": "initial",
  "frequency": "minute"
}
```

Required fields:

- `research_hypothesis`: non-empty research statement.
- `task_type`: one of `initial`, `mutation`, `crossover`, `refinement`.

Common optional fields:

- `frequency`: normally `minute`.
- `market_data_path`: minute CSV with `date`, `open`, `high`, `low`, `close`,
  `volume`, `average`, and `barCount`.
- `parent_factor`: object describing the parent factor for mutation, crossover,
  or refinement tasks.
- `forward_horizon`: positive number of bars used to construct forward returns.

Do not assume data fields beyond those supplied by the caller. The current minute
format is:

```text
date, open, high, low, close, volume, average, barCount
```

## 4. Factor contract

The generated factor JSON must conform to `schemas/factor_output_schema.json`.
The Python function must accept one `pandas.DataFrame` and return one
`pandas.Series` with the same index length:

```python
import pandas as pd


def factor_name(df: pd.DataFrame) -> pd.Series:
    factor = ...
    factor.name = "factor_name"
    return factor.astype(float)
```

Use only the columns available in the supplied DataFrame. Do not use negative
shifts or other obvious lookahead logic.

## 5. Tool invocation

Run commands from this `factor-research-skill` directory. Replace paths in angle
brackets with actual paths.

### 5.1 Generate factor

This is an agent step, not a deterministic program. Follow
`prompts/factor_generator.md` and write the result as UTF-8 JSON.

### 5.2 Validate code

```powershell
python tools/factor_checker.py --factor-json <factor.json> --output-json <check.json>
```

Call before execution. Stop when `status` is not `pass`.

### 5.3 Execute factor

```powershell
python tools/factor_executor.py --factor-json <factor.json> --market-csv <market.csv> --output-csv <factor_values.csv>
```

Call only after `factor_checker.py` passes. Stop when execution fails.

### 5.4 Run backtest and calculate metrics

With minute market data, this computes forward returns from `close`:

```powershell
python tools/backtest_runner.py --factor-csv <factor_values.csv> --market-csv <market.csv> --horizon 1 --output-json <backtest.json>
```

Alternatively, supply precomputed aligned returns with columns
`date` and `forward_return` (plus `symbol` for a panel):

```powershell
python tools/backtest_runner.py --factor-csv <factor_values.csv> --returns-csv <returns.csv> --output-json <backtest.json>
```

This tool calls `metric_calculator.py`. Do not manually replace its metrics.

### 5.5 Apply gate

```powershell
python tools/gate_checker.py --metrics-json <backtest.json> --config <gate.json> --output-json <gate.json.out>
```

A default rule set is used when `--config` is omitted. See
`references/evaluation_rules.md` for metric definitions.

### 5.6 Analyze and report

Use `prompts/factor_analyzer.md` to interpret the factor mechanism, then use
`prompts/report_generator.md` and `templates/report_template.md` to produce the
report. Quote only metric values present in the program-generated JSON.

## 6. Final response contract

The final response should contain:

1. Factor JSON path or inline factor definition.
2. Code-check result.
3. Execution status.
4. Program-produced backtest metrics.
5. Gate result and failed rules, if any.
6. Research report, including limitations and next steps.
7. Explicit disclosure that return performance beyond predictive metrics is not
   simulated by this minimal version.
