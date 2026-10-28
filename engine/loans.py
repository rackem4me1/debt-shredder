from datetime import date
from decimal import Decimal
from SCHEMA import StrictModel, InstallmentLoan, LoanType, PrepaymentBehavior, CompoundingMethod
from engine.common import ZERO, CENT, Nonnegative, decimal_input, decimal_context, MissingTerms, posting
from engine.interest import accrue_constant

class LoanPaymentResult(StrictModel):
    fees_paid: Nonnegative
    interest_paid: Nonnegative
    principal_paid: Nonnegative
    unapplied: Nonnegative
    principal_remaining: Nonnegative
    interest_remaining: Nonnegative
    fees_remaining: Nonnegative
    next_due_date: date
    interest_posting_adjustment: Decimal


@decimal_context
def accrue_loan(loan: InstallmentLoan, start: date, end: date) -> Decimal:
    if loan.loan_type != LoanType.SIMPLE_INTEREST:
        raise MissingTerms('precomputed interest requires original finance charge and rebate schedule')
    return accrue_constant(loan.principal_balance,loan.contract_note_rate.value,start,end,
        loan.day_count_convention.value,CompoundingMethod.SIMPLE_DAILY,loan.accrued_interest)


@decimal_context
def pay_loan(loan: InstallmentLoan, amount: Decimal, *, next_contractual_due_date: date | None = None) -> LoanPaymentResult:
    """Apply at credit time after accrued_interest has been calculated to that time.

    Paid-ahead date advancement must be supplied from a validated servicer schedule,
    not inferred as an arbitrary number of 30-day months.
    """
    amount=decimal_input(amount)
    if amount<0 or amount % CENT:raise ValueError('payment must be nonnegative cents')
    if loan.loan_type != LoanType.SIMPLE_INTEREST:
        raise MissingTerms('precomputed payoff requires original finance charge and contractual rebate schedule')
    next_due=loan.next_due_date
    if loan.prepayment_behavior.value == PrepaymentBehavior.PAID_AHEAD and amount>loan.contractual_payment_amount.value:
        if next_contractual_due_date is None or next_contractual_due_date<=loan.next_due_date:
            raise MissingTerms('paid-ahead excess needs an explicit advanced contractual due date')
        next_due=next_contractual_due_date
    elif next_contractual_due_date is not None:
        raise ValueError('due-date override is only for paid-ahead excess')
    interest_due=posting(loan.accrued_interest,loan.rounding_mode.value)
    fees=min(amount,loan.fees_outstanding)
    interest=min(amount-fees,interest_due)
    principal=min(amount-fees-interest,loan.principal_balance)
    return LoanPaymentResult(fees_paid=fees,interest_paid=interest,principal_paid=principal,
        unapplied=amount-fees-interest-principal,principal_remaining=loan.principal_balance-principal,
        interest_remaining=interest_due-interest,fees_remaining=loan.fees_outstanding-fees,next_due_date=next_due,
        interest_posting_adjustment=interest_due-loan.accrued_interest)
