# Debt Shredder Project Handoff

Last Updated: 2026-09-23

## Project Goal

Build a DebtShredder-inspired debt optimization application that:

- Starts blank
- Accepts each user's own financial information
- Supports separate private users
- Uses deterministic debt and cash-flow calculations
- Protects liquidity before recommending extra debt payments
- Explains recommendations clearly
- Can eventually be shared or distributed to other users

## Current Phase

Phase 1: Mathematical specification and financial engine architecture.

## Completed

- GitHub repository created
- SPEC.md created
- DECISIONS.md created
- Gemini drafted SPEC.md Section 1 v2.0
- ChatGPT completed two adversarial reviews
- Seven final corrections were identified before freezing Section 1

## Current Blocking Item

Claude still needs to review ChatGPT's final seven corrections for implementation feasibility.

The schema and calculation engine are NOT final yet.

## Next Steps

1. Send ChatGPT's final SPEC.md v2.0 review to Claude.
2. Have Claude review implementation feasibility.
3. Resolve any remaining disagreements.
4. Update and freeze SPEC.md Section 1.
5. Design the data schema.
6. Review the schema.
7. Build the first deterministic calculation engine.
8. Create automated tests for interest, payment allocation, promotions, and cash-flow safety.

## Important Rules

- SPEC.md is the authoritative source of truth.
- Do not preload Wayne's personal financial data into the application.
- Do not make significant changes to financial logic without review.
- LLMs may explain financial results but must not perform authoritative calculations inside the engine.
- Actual lender terms, statements, and reconciled transactions override projections.
- If lender rules are unknown, the software must label results as estimates rather than invent precision.

## Immediate Resume Instruction

When development resumes:

Send Claude ChatGPT's final seven-correction review and ask Claude to evaluate implementation feasibility before writing the final schema.
