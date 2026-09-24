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

Phase 2: Data schema and automated validation design.

## Completed

- GitHub repository created
- SPEC.md created
- DECISIONS.md created
- HANDOFF.md created
- Gemini drafted the mathematical architecture
- ChatGPT completed multiple adversarial reviews
- Claude reviewed implementation feasibility
- Remaining architectural issues were resolved
- SPEC.md Section 1 frozen at v2.4 on 2026-09-23

## Frozen Architecture

SPEC.md Section 1 v2.4 is the authoritative mathematical and financial-engine specification.

Do not modify the frozen Section 1 during schema implementation unless a concrete implementation contradiction is discovered.

If a contradiction is found:
1. Document it.
2. Stop implementation of the affected component.
3. Review the proposed change before modifying SPEC.md.

## Current Development Task

Claude should now design the data schema and initial automated tests that implement the frozen specification.

Initial deliverables:

1. `SCHEMA.py`
   - Pydantic models
   - Enumerations
   - Validation rules
   - Decimal-safe financial fields
   - Account and balance-segment relationships
   - Billing cycles
   - Installment loan terms
   - Payment lifecycle
   - Liquidity accounts
   - Sinking fund allocations
   - Parameter provenance

2. Initial pytest suite
   - Schema validation
   - Decimal precision protections
   - Invalid balance/account relationships
   - Promotional-term validation
   - Billing-cycle validation
   - Liquidity reserve validation
   - Internal-transfer conservation
   - Contract-term provenance requirements

## Important Implementation Notes

- Transfer-eligible secondary accounts must respect actual transfer settlement timing.
- Account-level liquidity floors must be represented in the schema because SPEC.md uses `Floor_A,min`.
- Internal transfers must never be counted as external income or expense.
- Reserved sinking-fund money must remain attached to the physical account holding it.
- Unknown contractual terms must use explicit `ASSUMED_DEFAULT` provenance.
- LLMs may explain results but must not perform authoritative financial arithmetic.

## Next Review Gate

Claude should produce the schema and test design first.

ChatGPT will review the schema against frozen SPEC.md v2.4 before the calculation engine is implemented.

Gemini may then review the schema for mathematical completeness.

No production calculation engine should be considered stable until the schema and tests pass review.
