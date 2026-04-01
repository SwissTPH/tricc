# Visual Authoring Concepts

This page summarizes the conceptual model from your WHO visual authoring material and aligns it with TRICC implementation.

## Why visual CDSS authoring

- Transforms static, paper-like guidance into dynamic and computable decision support.
- Supports local customization (protocols, endemicity, drug availability).
- Clarifies calculations by formalizing inputs and algorithm logic.
- Supports comorbidities and more integrated patient-centered logic.

## Authoring roles

- Subject matter experts (SME/clinicians): own clinical content and final decisions.
- End users: provide workflow and usability feedback.
- IT specialists: ensure implementability and technical consistency.
- Other stakeholders (MoH, implementers, sponsors): ensure contextual fit.

## Core challenge themes

- Collaboration and shared ownership across stakeholders.
- Balancing technical precision with readability.
- Treatment modeling with prioritization and safety.
- Reusable activity design without duplication.
- Sequence logic without loops/dead ends.
- Controlled starts by segment/process.
- Reliable conversion with low regression risk.

## Segmented approach

Authoring is split into care/process segments so teams can:

- decide when each segment should run,
- merge several guideline segments coherently,
- jump between segments when needed.

This aligns with process-based starts and modular activity linking in TRICC.

## Layered approach

The material describes layered authoring:

- Layer 1: Segment overview (WHAT should happen).
- Layer 2+: Activities (HOW a segment executes).
- Layer 3+: Nodes/tasks (specific actions and logic).

TRICC implements this through start/process orchestration, activity diagrams, and typed nodes.

## How this maps to TRICC

- Segment-level orchestration maps to process starts (`start` with `process`).
- Activity-level logic maps to activity diagrams (`activity_start`, `activity_end`, `goto`).
- Task-level logic maps to node types (inputs, messages, calculations, sequence nodes).

## Practical recommendations from implementation slides

- Keep diagrams readable; move dense logic into CQL when appropriate.
- Maintain a concept/code-driven data dictionary.
- Work in small iterations: change, convert, test.
- Keep at least one file per segment for parallel authoring.
- Treat warnings/errors as first-class signals before debugging assumptions.
