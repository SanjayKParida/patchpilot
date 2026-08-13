# PatchPilot

## Problem
LLMs can reason about code and generate patches, but their outputs are probabilistic and can be incorrect, incomplete, or unsafe to execute without verification.

## Goal
Build a controlled software-engineering agent that can investigate a GitHub issue, propose a change, implement it in an isolated environment, verify it with tests, and produce an evidence-backed draft patch.

## Non-goals
- I won't be supporting multiple repositories for the MVP
- I won't allow the agent to merge PRs by themselves
- This project won't support multiple languages at first
- It's not a general purpose coding agent, it will take in github issues, ponder on it, go through the repository at first and then provide a solution for it

## MVP


## User Flow
1. GitHub issue is created.
2. Client fetches issues through GitHub API.
3. User selects an issue and clicks Analyze.
4. Backend analyzes the issue.
5. PatchPilot identifies relevant repository files.
6. PatchPilot searches and reads relevant code.
7. Agent generates a structured fix proposal.
8. Client displays the proposed fix to the user.
9. User approves or rejects the proposal.
10. If approved, PatchPilot applies the fix in an isolated workspace.
11. PatchPilot runs tests/verification.
12. Client displays the resulting diff and verification status.

## Agent Tools
- fetch_isses()
- list_files()
- search_code()
- read_files()
- run_tests()
- apply_fixes()

## Agent State


## Architecture
GitHub Issue
     │
     ▼
GitHub API
     │
     ▼
Flutter Client
     │
     │ User clicks Analyze
     ▼
Backend API
     │
     ▼
Issue Analyzer
     │
     ├── Understand issue
     ├── Identify related files
     ├── Search repository
     └── Build relevant context
              │
              ▼
        Agent / Fix Planner
              │
              ▼
       Proposed Fix + Plan
              │
              ▼
        Flutter UI shows:
        ├── Why this fix?
        ├── Files affected
        ├── Changes proposed
        └── Confidence/evidence
              │
        User approves
              │
              ▼
        Apply Fix
              │
              ▼
      Run Tests / Verification
              │
        ┌─────┴─────┐
        ▼           ▼
      PASS         FAIL
        │           │
        ▼           ▼
   Show result   Show failure

## Security

## Evaluation

## Open Questions