# TRICC Input/Populate Types

This document explains the different kinds of input/populate nodes available in TRICC for drawio authors and content creators. These nodes allow fetching and managing data from previous encounters, patient records, or encounter context.

## Overview

TRICC supports three main populate/input types with distinct behaviors:

### 1\. **Persistent** (`persistent`)

- **Purpose**: Stable data with one current value (updates in place).
- **Use Case**: Patient-level data like facility context demographics that persist across encounters.
- **Attribute** `context`:
    - **Default Context**: `patient` (`facility` for CHT HF strategy)
    - **Other Contexts**: `practitioner`, `facility`, `location`
- **Behavior**: Supports inheritance, last version, default value, relevance.
- **Drawio Usage**: Set `odk_type="persistent"` or use the dedicated persistent shape. Add `context` attribute if needed.

### 2\. **Active** (`active`)

- **Purpose**: Current/active data that can be skipped if already known (`skip_or_new` update mode).
- **Use Case**: Encounter-specific data like current symptoms or measurements that may carry over or be updated.
- **Attribute** `from`:
    - **Default** : `encounter`
    - **Other**: ISO duration like `P14D` (14 days), `P1M` (1 month).
- **Behavior**: Supports inheritance, last version, default, relevance.
- **Drawio Usage**: Set `odk_type="active"` or dedicated shape. Use `from` attribute for lookup scope.

### 3\. **Repeated** (`repeated`)

- **Purpose**: Repeated/chartable data that **always creates a new entry** (`always_new`).
- **Use Case**: Serial measurements, visit history, or chartable events (e.g., blood pressure readings over time).
- **Attribute** `from`:
    - **Default**: `encounter`
    - **Other**: ISO duration like `P14D` (14 days), `P1M` (1 month).
- **Behavior**: **No** inheritance, last-version, default value, or relevance based on last version. **Mandatory** `last.` prefix in calculations.
- **Drawio Usage**: Set `odk_type="repeated"` or dedicated shape. Use `from` attribute.

**Backward Compatibility**: `odk_type="input"` or old `history` maps to `persistent`.

## Core Behavior Matrix

| Type | Update Mode | Inheritance | Last Version | Default | Relevance | Calc Prefix |
| --- | --- | --- | --- | --- | --- | --- |
| persistent | update_existing | Yes | Yes | Yes | Yes | No |
| active | skip_or_new | Yes | Yes | Yes | Yes | No |
| repeated | always_new | **No** | **No** | **No** | **No** | `last.` (mandatory) |

**Note**: Repeated nodes are completely excluded from version inheritance and last-version logic to ensure new entries.

## Attributes

- **context** (persistent): patient (default), practitioner, facility, location. Used for lookup/storage.
- **from** (active/repeated): encounter (default) or ISO duration string (e.g., `P1Y` for 1 year). Note: XML uses `from`, mapped to `from_` in model.

## How to Use in Drawio

1.  Use the TRICC tools shapes or set the object type/semantic in properties.
2.  For persistent/active/repeated, set the `odk_type` property or use the corresponding object in TYPE_MAP.
3.  Add attributes like `context="location"` or `from="P14D"` in the shape properties.
4.  For calculations referencing them, the expression builder automatically applies the correct prefix ( `last.`).
5.  In CHT outputs:
    - Persistent: appears in Contact Summary.
    - Active/Repeated: in calculated contact summary and CHT tasks (see `imci-task.js` patterns for task generation).

## Examples

- **Patient Name**: semantic=persistent, context=patient, name=name.
- **Active Encounter BP**: semantic=active, from=encounter, name=bp_reading.
- **Repeated Measurements**: semantic=repeated, from=P7D, name=weight (creates new entry each time).

See `docs/tricc-elements.md` for shape details and `tests/data/` for example drawio files with these nodes.

For XLSForm/CHT/HF outputs, the types map to appropriate fields, calculations, and task configurations.

**Author Tip**: Use the new types to reduce duplication in forms. Persistent for core patient data, active for current state, repeated for longitudinal tracking.