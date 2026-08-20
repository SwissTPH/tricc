PROCESSES = [
    "triage",
    "emergency-care",
    "registration",
    "history-and-physical",
    "local-urgent-care",
    "acute-tertiary-care",
    "diagnostic-testing",
    "determine-diagnosis",
    "provide-counseling",
    "dispense-medications",
    "monitor-and-follow-up-of-patient",
    "alerts-reminders-education",
    "discharge-referral-of-patient",
    "charge-for-service",
    "record-and-report",
]

# Canonical cpg-common-process ordering: first process = 10, each subsequent += 10.
# Comparable across different exported PlanDefinitions (see
# feature/20260812-intervention-order-and-dedup.md) — process names not in PROCESSES
# get the next free slot after the highest known order, assigned in discovery order
# by the caller (see OpenSRPStrategy.generate_intervention_plandefinition).
PROCESS_ORDER = {name: (i + 1) * 10 for i, name in enumerate(PROCESSES)}
