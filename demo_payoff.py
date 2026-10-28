"""Explicit synthetic terms and calendar for the headless payoff example."""
import calendar
from datetime import date,datetime,timezone
from decimal import Decimal
from SCHEMA import (BalanceSegment,SegmentType,CompoundingMethod,DayCountConvention,RevolvingAccount,
    AllocationRule,AllocationRuleType,GracePeriodState,BillingCycle,MinimumPaymentSnapshot,assumed_default)
from engine.portfolio import PortfolioDebt
from engine.liquidity import CashOpening,CashPlan,CashKind
from engine.minimum_forecast import PaymentSlot
from engine.payoff import PayoffInputs


def example():
    debts=[]
    for id_,balance,rate in (('high-rate','1000','.24'),('small-balance','500','.12')):
        segment=BalanceSegment(account_id=id_,segment_id='purchases',segment_type=SegmentType.STANDARD_PURCHASE,
            balance=balance,apr=assumed_default(Decimal(rate)),
            compounding_method=assumed_default(CompoundingMethod.SIMPLE_DAILY),
            day_count_convention=assumed_default(DayCountConvention.ACTUAL_365))
        account=RevolvingAccount(account_id=id_,issuer='Synthetic example',segments=(segment,),
            minimum_payment_floor=assumed_default(Decimal('25')),minimum_payment_rate=assumed_default(Decimal('.01')),
            allocation_rule=AllocationRule(account_id=id_,minimum_payment_allocation_rule=assumed_default(AllocationRuleType.LOWEST_APR_FIRST),
                excess_payment_allocation_rule=assumed_default(AllocationRuleType.STATUTORY_DEFAULT)),
            statement_close_day=31,payment_due_day=20,current_grace_state=GracePeriodState.LOST_GRACE)
        cycles=[]
        for year,month in ((2025,12),)+tuple((2026,m) for m in range(1,13)):
            close=date(year,month,calendar.monthrange(year,month)[1])
            cycles.append(BillingCycle(account_id=id_,cycle_id=f'{year}-{month:02}',start_date=date(year,month,1),
                end_date=close,statement_date=close,due_date=date(year+(month==12),month%12+1,20)))
        debts.append(PortfolioDebt(account=account,cycles=tuple(cycles),initial_minimum=MinimumPaymentSnapshot(
            account_id=id_,billing_cycle_id='2025-12',statement_minimum_original='25',statement_minimum_remaining='25')))
    slots=[];cash=[]
    for month in range(1,13):
        at=datetime(2026,month,20,tzinfo=timezone.utc)
        slots.append(PaymentSlot(slot_id=f'2026-{month:02}',initiated_at=at,credited_at=at,debited_at=at,settled_at=at))
    # Supply external cash events through the last initiation plus 90 days.
    for month in range(1,16):
        year=2026+(month-1)//12;calendar_month=(month-1)%12+1
        for kind,day,amount in ((CashKind.INCOME,1,'1200'),(CashKind.EXPENSE,2,'900')):
            when=datetime(year,calendar_month,day,tzinfo=timezone.utc)
            cash.append(CashPlan(plan_id=f'{kind.value}-{month}',kind=kind,amount=amount,
                source_account_id='checking' if kind==CashKind.EXPENSE else None,
                destination_account_id='checking' if kind==CashKind.INCOME else None,
                initiated_at=when,credited_at=when,debited_at=when,settled_at=when))
    return PayoffInputs(start=datetime(2026,1,1,tzinfo=timezone.utc),end=datetime(2026,12,31,tzinfo=timezone.utc),
        debts=tuple(debts),opening=CashOpening(account_id='checking',cleared='400',floor='100',reserved='50',primary=True),
        cash_plans=tuple(cash),slots=tuple(slots),payment_target='250')


def saved_example():
    """Same synthetic accounts in the existing app's saved-scenario format."""
    from dashboard.scenarios import Scenario
    from engine.portfolio import PortfolioPaymentRequest,RequestKind
    value=example();requests=[]
    for slot in value.slots:
        for index,debt in enumerate(value.debts):
            requests.append(PortfolioPaymentRequest(request_id=slot.slot_id+'-'+str(index),
                debt_account_id=debt.account.account_id,source_account_id=value.opening.account_id,
                amount='125',kind=RequestKind.EXTRA,priority=index,
                **{key:getattr(slot,key) for key in ('initiated_at','credited_at','debited_at','settled_at')}))
    return Scenario(name='Payoff practice: $1,500',origin='synthetic_demo',start=value.start,end=value.end,
        debts=value.debts,openings=(value.opening,),cash_plans=value.cash_plans,requests=tuple(requests),
        card_names=('24% sample card','12% sample card'))


def template_example():
    """Same payoff example from two known statements plus explicit repeat rules."""
    from datetime import time
    from engine.common import reconstruct
    from engine.payoff_calendar import (PayoffTemplate,RepeatingPaymentRule,MonthlyStatementRule,RecurringPayoffCash)
    from SCHEMA import SemimonthlyShortMonthRule
    value=example();short=SemimonthlyShortMonthRule.CLAMP_TO_LAST_DAY_OF_MONTH
    return PayoffTemplate(start=value.start,end=value.end,debts=tuple(reconstruct(d,cycles=d.cycles[:2]) for d in value.debts),
        opening=value.opening,payment_target=value.payment_target,
        payments=RepeatingPaymentRule(first_date=date(2026,1,20),cadence='monthly',timezone_name='UTC',clock=time(),
            credit_days=0,debit_days=0,settlement_days=0,short_month_rule=short),
        statements=tuple(MonthlyStatementRule(account_id=d.account.account_id,close_day=31,due_day=20,due_month_offset=1,short_month_rule=short) for d in value.debts),
        cash_schedules=(RecurringPayoffCash(schedule_id='paycheck',kind='income',amount='1200',first_date=date(2026,1,1),cadence='monthly',clock=time(),short_month_rule=short),
            RecurringPayoffCash(schedule_id='household-bills',kind='expense',amount='900',first_date=date(2026,1,2),cadence='monthly',clock=time(),short_month_rule=short)))


def saved_repeating_example():
    """App example with explicitly declared monthly income and bill recurrence."""
    from dashboard.cash_inputs import ManualCashEvent,expand_cash_events,cash_horizon
    from engine.common import reconstruct
    source=saved_example()
    events=(ManualCashEvent(kind='income',label='Sample monthly income',amount='1200',date=date(2026,1,1),
        cadence='monthly',short_month_rule='clamp_to_last_day_of_month'),
        ManualCashEvent(kind='expense',label='Sample monthly bills',amount='900',date=date(2026,1,2),
        cadence='monthly',short_month_rule='clamp_to_last_day_of_month'))
    return reconstruct(source,name='Payoff practice: recurring income and bills',manual_cash_schedules=events,
        cash_plans=expand_cash_events(events,source.start,cash_horizon(source.start,source.end,source.requests),'UTC'))


def loan_example():
    """Synthetic principal-curtailment installment loan; no real loan terms."""
    from SCHEMA import InstallmentLoan,LoanType,PrepaymentBehavior
    from engine.loan_payoff import LoanPayoffInputs
    value=example()
    loan=InstallmentLoan(loan_id='sample-loan',servicer='Sample servicer',loan_type=LoanType.SIMPLE_INTEREST,
        principal_balance='1000',contract_note_rate=assumed_default(Decimal('.12')),disclosed_apr=assumed_default(Decimal('.20')),
        day_count_convention=assumed_default(DayCountConvention.ACTUAL_365),contractual_payment_amount=assumed_default(Decimal('100')),
        payment_due_day=20,next_due_date=date(2026,1,20),prepayment_behavior=assumed_default(PrepaymentBehavior.PRINCIPAL_ONLY_CURTAILMENT))
    return LoanPayoffInputs(start=value.start,end=value.end,timezone_name='UTC',loan=loan,
        due_dates=tuple(date(2026,m,20) for m in range(1,13))+(date(2027,1,20),),
        opening=value.opening,cash_plans=value.cash_plans,slots=value.slots,payment_target='150')


def saved_multiaccount_example():
    """Explicit checking -> Bills Box transfers, with fixed debt funding routes."""
    from engine.common import reconstruct
    from engine.liquidity import CashKind,CashPlan,CashOpening
    source=saved_example();plans=list(source.cash_plans)
    savings=CashOpening(account_id='bills-box',cleared='250',floor='100',reserved='100')
    for month in range(1,16):
        year=2026+(month-1)//12;m=(month-1)%12+1
        sent=datetime(year,m,3,tzinfo=timezone.utc);arrived=datetime(year,m,5,tzinfo=timezone.utc);settled=datetime(year,m,6,tzinfo=timezone.utc)
        plans.append(CashPlan(plan_id=f'sample-bills-funding-{month}',kind=CashKind.TRANSFER,amount='200',
            source_account_id='checking',destination_account_id='bills-box',initiated_at=sent,debited_at=sent,credited_at=arrived,settled_at=settled))
    return reconstruct(source,name='Payoff practice: separate checking and Bills Box',openings=source.openings+(savings,),cash_plans=tuple(plans),
        requests=tuple(reconstruct(r,source_account_id='bills-box') if r.debt_account_id=='high-rate' else r for r in source.requests))


def mixed_example():
    """Two sample cards plus one sample loan under ONE $300 monthly target."""
    from engine.mixed_payoff import MixedPayoffInputs,PayoffLoan
    value=example();loan=loan_example()
    return MixedPayoffInputs(start=value.start,end=value.end,cards=value.debts,
        loans=(PayoffLoan(loan=loan.loan,timezone_name=loan.timezone_name,due_dates=loan.due_dates),),
        opening=value.opening,cash_plans=value.cash_plans,slots=value.slots,payment_target='300')
