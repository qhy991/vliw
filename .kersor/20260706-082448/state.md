---
schema_version: 1
kersor_version: "1.21.0"
phase: optimizing
current_round: 1
max_workflows: 24
target_speedup: 1.134
target_override: true
mode: "explore"
workflows_filter: "vliw-d3d4-joint-anneal"
session_id: "088eded4-6349-4a59-9c3b-c77010c7f0a2"
input_mode: "kernel_file"
task_dir: ""
kernel_path: "/mnt/user_dir/shihaichao/qinhaiyan/vliw-v120-d3d4-joint/perf_takehome.py"
seed_origin: provided_kernel
kernel_language: python
backend: python
user_note: ""
seed_analysis_path: ""
yolo: "true"
retrieval_mode: "on"
transfer_mode: "full"
kernelwiki_root: "/home/qinhaiyan/KernelWiki-Q"
context_hub_root: "/home/qinhaiyan/context-hub"
experience_mode: "on"
experience_bank_path: ""
kernelwiki_experience_export_mode: "off"
kernelwiki_experience_export_root: "/home/qinhaiyan/KernelWiki-Q"
workflow_dir: "/home/qinhaiyan/KerSor/workflows/Awesome-Kernel-Workflows"
workflow_catalog: ".kersor/20260706-082448/workflow-catalog.json"
allow_workflow_evolution: "true"
workflow_evolution_budget: "10"
workflow_lab_dir: ".kersor/20260706-082448/workflow-lab"
allow_workflow_authoring: "true"
workflow_authoring_budget: 4
workflow_authoring_lab_dir: ".kersor/20260706-082448/workflow-authoring"
explore_stall_threshold: 4
started_at: "2026-07-06T08:25:11+08:00"
integration_pattern: standalone
prepared: true
---

# KerSor State

This file is the single control state for the optimization loop. It records
only loop control fields. Per-round facts live in round summaries and run
artifacts, and the next workflow is selected one round at a time from those
artifacts.

## State Rules

- Do not pre-plan a full workflow queue at session start.
- Select exactly one workflow for the active round.
- Derive handoff context from prior `round-*-summary.md` and `run-*/analysis.md`.
- Do not store derived fields such as current best, completed workflows, or cross-run insight lists here.
