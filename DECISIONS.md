# Debt Shredder Decisions Log

This file records major project decisions so ChatGPT, Claude, and Gemini stay aligned.

## 2026-09-23

### Application starts blank
The application will not preload the owner's personal financial information.

Users will enter their own accounts, debts, income, bills, reserves, and preferences.

### Multi-user support
The architecture should support separate private user accounts rather than assuming a single permanent user.

### Deterministic financial engine
All debt calculations, interest accrual, payment allocation, cash-flow projections, and optimization logic must be deterministic and testable.

LLMs may explain results but must not perform authoritative financial calculations inside the computation engine.

### Contract-aware modeling
The engine must support lender-specific rules where necessary, including:
- APR and interest methods
- Balance segments
- Promotional balances
- Deferred interest
- Grace periods
- Payment allocation
- Minimum-payment formulas
- Loan prepayment behavior

### Cash-flow protection
Debt acceleration recommendations must not sacrifice required liquidity.

The engine must protect:
- Mandatory bills
- Minimum debt payments
- Pending committed payments
- User-defined cash buffers
- Protected sinking-fund balances

### Shared calculation engine
Avalanche, snowball, promotional protection, and hybrid strategies should use the same underlying financial engine.

### Explainable recommendations
Every recommended debt payment should include a reproducible explanation of why that amount and destination were selected.

### Specification authority
SPEC.md is the source of truth for implementation requirements.

Significant financial or architectural changes should be reviewed before implementation.
