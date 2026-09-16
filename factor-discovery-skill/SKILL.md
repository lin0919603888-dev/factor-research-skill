---
name: factor-discovery-skill
description: Discover minute-bar factors by loading a research requirement and YAML factor library, evolving recorded candidates, evaluating them with program metrics, and persisting survivors.
version: 1.0.0
---

# Factor Discovery Skill

## 1. Purpose

This skill runs a recorded factor-discovery loop:

```text
Load Requirement
    ↓
Load Factor Library
    ↓
Analyze Existing Factors
    ↓
Generate Candidates
    ↓
Validate
    ↓
Execute Factor
    ↓
Backtest
    ↓
Evaluate
    ↓
Save Surviving Factor
```

It is designed for users who supply:

```text
research_requirement.md
factor_library/
data/
```

The current minute format is:

```text
date, open, high, low, close, volume, average, barCount
```

## 2. Inputs

### `research_requirement.md`

This file is experiment-specific and must remain external to the skill. Use
Markdown sections or YAML keys:

```markdown
# Research Goal
Improve short-term continuation signals.

# Data Frequency
minute

# Prediction Horizon
1

# Research Direction
Study volume-supported price behavior.

# Constraints
- Use only the supplied minute-bar fields.
- Avoid turnover driven only by extreme outliers.

# Evaluation
- min_rank_ic: 0.02
- min_icir: 0.20
- min_ic_observations: 20
```

Do not hard-code a research goal in the skill. The required top-level fields are
defined in `schemas/research_requirement_schema.json`.

### `factor_library/`

The library is a directory, not one fixed file. `factor_loader.py` recursively
scans all `.yaml` and `.yml` files. The minimum existing-factor format is:

```yaml
name: Mined_close_open_ratio_1
code: "((close / open) * 1.5 + close / 2)"
category: 自定义
description: 通过遗传算法挖掘的因子
formula_type: expression
```

Candidate factors use `schemas/candidate_factor_schema.yaml` and add
`metadata.source`, `metadata.generation`, `metadata.lineage`, and later
`metadata.evaluation`.

## 3. Workflow and tool calls

Run all commands from `factor-discovery-skill`.

### 3.1 Load requirement

The requirement is loaded automatically by `factor_generator.py` and
`evaluator.py`. For a separate structural check, inspect it against
`schemas/research_requirement_schema.json`.

### 3.2 Load and analyze factor library

```powershell
python tools/factor_loader.py --library <factor_library> --output-json library_summary.json
```

Use the summary to review:

- number of YAML files found and loaded
- invalid YAML files
- categories and formula types
- candidate parent factors

Do not choose parents from a file count alone; use names, descriptions, lineage,
and relevance to `Research Direction`.

### 3.3 Generate one candidate

Mutation:

```powershell
python tools/factor_generator.py --requirement <research_requirement.md> --library <factor_library> --strategy mutation --parent <factor_name_or_yaml_path> --operation rolling_zscore --reason "Test a scale-stable form of the parent signal." --output-yaml candidates/candidate.yaml
```

Crossover:

```powershell
python tools/factor_generator.py --requirement <research_requirement.md> --library <factor_library> --strategy crossover --parent <parent_1> --parent <parent_2> --weight 1.0 --weight 1.0 --reason "Test agreement between two complementary mechanisms." --output-yaml candidates/candidate.yaml
```

Refinement:

```powershell
python tools/factor_generator.py --requirement <research_requirement.md> --library <factor_library> --strategy refinement --parent <factor_name_or_yaml_path> --operation rolling_rank --reason "Preserve the mechanism while reducing scale sensitivity." --output-yaml candidates/candidate.yaml
```

Initial:

1. The agent designs one Python or arithmetic-expression factor from the
   requirement.
2. Save that source to a temporary code file.
3. Call:

```powershell
python tools/factor_generator.py --requirement <research_requirement.md> --library <factor_library> --strategy initial --parent Candidate_Name --code-file <candidate_source.py> --reason "Introduce a mechanism absent from the current library." --output-yaml candidates/candidate.yaml
```

`factor_mutator.py` and `factor_crossover.py` can also be called directly when
the agent needs a narrower operation.

### 3.4 Validate

```powershell
python tools/factor_executor.py --factor-yaml candidates/candidate.yaml --validate-only --result-json validation.json
```

Stop if `status` is not `pass`.

### 3.5 Execute

```powershell
python tools/factor_executor.py --factor-yaml candidates/candidate.yaml --market-csv <data/market.csv> --output-csv candidates/factor_values.csv --result-json execution.json
```

### 3.6 Backtest

```powershell
python tools/backtest_runner.py --factor-csv candidates/factor_values.csv --market-csv <data/market.csv> --horizon <prediction_horizon> --output-json backtest.json
```

The horizon must come from the research requirement. Metrics are computed by
this program; the agent must not estimate or alter them.

### 3.7 Evaluate

```powershell
python tools/evaluator.py --metrics-json backtest.json --requirement <research_requirement.md> --output-json evaluation.json
```

Read `gate`. Only a `pass` candidate should be promoted to the library.

### 3.8 Save

```powershell
python tools/factor_saver.py --factor-yaml candidates/candidate.yaml --library <factor_library> --metrics-json backtest.json --evaluation-json evaluation.json --output-json save_result.json
```

`factor_saver.py` never overwrites an existing YAML. It creates a unique file
and records program metrics and gate results in `metadata.evaluation`.

## 4. Responsibility boundary

### Agent/LLM decides

- Which parent factors are relevant.
- Which evolution strategy is appropriate.
- The research reason for every mutation, crossover, refinement, or initial
  design.
- How to interpret program output.

### Program enforces

- Directory scanning and YAML structure.
- Candidate provenance.
- Expression or Python factor validation.
- Minute-data field checks.
- Forward-return and metric calculation.
- Requirement-driven pass/reject rules.
- Unique, non-overwriting persistence.

## 5. Final response

For each discovery run, report:

1. Research goal and selected strategy.
2. Parent factor(s) and reason.
3. Validation and execution status.
4. Program-produced IC, RankIC, ICIR, and observation count.
5. Evaluator gate result.
6. Saved YAML path, or the reason no factor was saved.
7. Current limitations, especially missing transaction-cost and portfolio testing.

