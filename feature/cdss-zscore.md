# CDSS Zscore / IZscore — Feature Specification

| Field | Value |
|-------|-------|
| **Status** | Implemented |
| **Branch target** | `feature/adv_merge_calc` (or follow-up) |
| **Related** | WHO smart-ccc anthro CQL; XLSFormCDSSStrategy |
| **Authoring surface** | Calculate expressions: `Zscore(...)` / `Izscore(...)` (CQL or TRICC ops) |

Valid status values: `Draft` → `Approved` → `Implemented` → `Superseded`.

---

# Part I — Business Description

*Audience: clinical authors, guideline developers, implementers evaluating TRICC workflows.*

## 1. Overview

**Zscore** and **Izscore** let a CDSS form compute WHO anthropometric indicators in pure ODK XPath, without custom apps or JavaScript.

- **Zscore** — given sex, an independent measure (e.g. age in days), and a measured value (e.g. weight in kg), returns the **Z-score** for a named chart (e.g. weight-for-age).
- **Izscore** — given sex, the same independent measure, and a target Z, returns the **expected measured value** (e.g. weight for that Z at that age). Useful for estimating weight from a previous Z-score.

Phase 1 supports **weight-for-age (`wfa`)**. Other charts (weight-for-length, length-for-age, …) use the same operators with a different table name when data is added later.

## 2. Clinical problem

Growth standards (WHO child growth) are tables of LMS parameters by sex and age (or length). Mobile forms need these tables at runtime. Dumping every chart into every form bloats the choice list. This feature embeds **only the tables the form actually uses**.

## 3. What authors write

In a calculate expression (CQL-style):

```text
Zscore('wfa', sex, age_in_days, weight_kg)
Izscore('wfa', sex, age_in_days, z)
```

| Argument | Meaning for `wfa` | Notes |
|----------|-------------------|--------|
| table | `'wfa'` | Chart id |
| sex | `'male'` or `'female'` | WHO string form |
| x | Age in **days** | Independent axis |
| y / z | Weight (kg) or Z | Measured Y or target Z |

Forms that never call these operators do **not** receive anthro choice rows.

## 4. Benefits and limitations

**Benefits**

- Offline ODK/CDSS compatible (secondary instances + XPath)
- No choice pollution when unused
- Aligned with WHO smart-ccc LMS math

**Limitations**

- Phase 1: `wfa` only
- Sex values must match `'male'` / `'female'`
- Age must be in days for WFA
- Very large tables increase XLSX size when used

---

# Part II — Technical Specification

## 1. Semantics

```text
Zscore(table, sex, x, y)  →  ((y/m)^l - 1) / (s * l)
Izscore(table, sex, x, z) →  m * (z*s*l + 1)^(1/l)
```

`l`, `m`, `s` come from the LMS row matching `sex` and `x` via half-open range filter:

```xpath
instance('wfa')/root/item[sex=… and y_min <= x and y_max > x]
```

## 2. Choice schema

| Column | Role |
|--------|------|
| `list_name` | Table id (`wfa`) |
| `value` | Unique row id |
| `sex` | `male` / `female` |
| `y_min` | Inclusive lower bound of independent axis |
| `y_max` | Exclusive upper bound |
| `l`, `m`, `s` | LMS |

## 3. Lazy injection

During expression emission, record used table ids. On Excel export, inject only those rows into `df_choice`. Unknown table → error.

## 4. Implementation checklist

- [x] Feature MD
- [x] `tricc_oo/data/anthro/` registry + `wfa.json` + range builder
- [x] `CHOICE_MAP` + `sex`
- [x] Fix `get_zscore_params` (`y_min`/`y_max`) and LMS formulas
- [x] CDSS: track tables, inject, override ops
- [x] Tests (`tests/test_cdss_zscore.py`)

## 5. Acceptance criteria

1. No zscore usage → no anthro list_names on choices.
2. `Zscore('wfa', …)` → `instance('wfa')` with `y_min`/`y_max` filter; `wfa` rows present.
3. WHO LMS formulas (not legacy wrong divisor/sign).
4. Registry ready for later XForY tables.

## 6. Implementation phases

| Phase | Content |
|-------|---------|
| 1 | `wfa` + lazy CDSS export (this feature) |
| 2+ | `wfl`, `wfh`, `lfa`, `bfa`, … data packs |
