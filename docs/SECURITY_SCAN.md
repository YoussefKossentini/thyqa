# Pre-freeze security scans

Run on 2026-11-08 against `thiqa/`, `tools/` and `wazuh/` (5,472 lines of Python).

## Bandit 1.9.4

First pass: 1 high, 4 medium, 15 low.

| Finding | What we did |
|---|---|
| High, B613: invisible bidi control characters inside a source file (Trojan Source) | they were real characters in the input guard's tables; replaced by `\u` escapes everywhere, same behaviour, tests still green |
| Medium, B608 × 3: SQL built with an f-string | reviewed: the fragments are constants chosen in code, values are bound parameters; annotated `# nosec B608` with the reason |
| Medium, B310: `urlopen` in the Wazuh bridge | the bridge now refuses any URL that is not http(s) |
| Low, B101 × 10: `assert` used for control flow | replaced by explicit checks (asserts disappear under `python -O`) |
| Low, B110 / B112: exception swallowed in two background loops | now logged; the loops still survive a failure |
| Low, B311 / B105: `random` and a "hardcoded password" | reviewed: simulation seed for synthetic clients, and a sandbox token name; annotated |

Second pass: **0 findings**.

## gitleaks 8.21.2

1 finding: the fake key used as bait in Sarrak's output-guard tests, inside a
compiled `.pyc`. The bait string is now built at runtime and generated folders are
ignored (`.gitleaks.toml`). Second pass: **0 findings**. Real keys live only in
`.env`, which is git-ignored and never logged.

## Reproduce

```
pip install bandit
bandit -r thiqa tools wazuh -q
gitleaks detect --no-git --source . --config .gitleaks.toml --redact
python -m pytest
```
