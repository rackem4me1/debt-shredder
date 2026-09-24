# Debt Shredder Specification

## Project Objective

Build a cash-flow-aware debt optimization application that:

- Starts blank with no owner financial data preloaded
- Supports separate private users
- Accurately models debt balances, APRs, payments, promotions, and cash flow
- Protects required liquidity before recommending extra debt payments
- Explains every recommendation in understandable language
- Uses deterministic financial calculations rather than LLM-generated math

## Source of Truth

This file is the authoritative specification for the project.

Significant changes to architecture, financial calculations, or payoff logic must be reviewed before implementation.

## Current Development Phase

Phase 1: Core mathematical rules, debt modeling, cash-flow safety, and calculation architecture.

## Status

Gemini drafted Section 1 v2.0.

ChatGPT completed a second adversarial review and identified seven final corrections before Section 1 should be frozen.

Claude still needs to review those corrections for implementation feasibility before the schema and calculation engine are finalized.
