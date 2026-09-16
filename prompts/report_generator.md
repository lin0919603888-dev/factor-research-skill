# Report Generator Prompt

Generate a research report from the factor JSON and tool-produced validation
JSON. Do not add metric values that are absent from the tool output.

## Required structure

1. **Research hypothesis** — quote or faithfully restate the supplied hypothesis.
2. **Factor definition** — name, formula, and generated logic.
3. **Mechanism** — why the signal may work and when it should fail.
4. **Validation results** — code check, execution status, IC, RankIC, ICIR,
   observation count, and gate result.
5. **Interpretation** — explain what the program metrics do and do not show.
6. **Risks and limitations** — data coverage, alignment, transaction costs,
   regime sensitivity, and implementation risks.
7. **Next step** — one concrete action, such as collecting more data, testing
   another horizon, or rejecting the factor.

## Rules

- Use exact numeric values from program output.
- Clearly label any missing metric as unavailable.
- Do not claim profitability from IC-style metrics alone.
- Do not present this minimal evaluator as a full trading backtest.

