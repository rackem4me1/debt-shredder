"""Coordinate explicit revolving-payment requests against one physical cash ledger.

This is a deterministic request allocator, not a portfolio optimizer or payoff
quote. Supplied minimum requests reserve cash before extras. Both groups follow
initiation time and explicit priority; exact ties are rejected. Spending is also
capped by each account's opening posted balance, less already accepted requests;
newly generated interest is reported by replay but is not new spending authority.
"""
from datetime import datetime,timezone,timedelta
from decimal import ROUND_DOWN
from enum import Enum
from zoneinfo import ZoneInfo
from pydantic import Field,model_validator
from SCHEMA import StrictModel,RevolvingAccount,BillingCycle,MinimumPaymentSnapshot,CashFlowStatus
from engine.common import ZERO,CENT,Nonnegative,Positive,decimal_context
from engine.grace import GraceReplayTerms
from engine.promotions import PromoTransition
from engine.simulation import DebtCreditEvent,DebtProjection,simulate_revolving
from engine.liquidity import CashOpening,CashPlan,CashKind,LiquidityProjection,project_liquidity


class PortfolioDebt(StrictModel):
    account:RevolvingAccount
    cycles:tuple[BillingCycle,...]
    initial_minimum:MinimumPaymentSnapshot
    grace_terms:GraceReplayTerms|None=None
    promo_transitions:tuple[PromoTransition,...]=()
    credit_timezone:str='UTC'


class RequestKind(str,Enum):
    MINIMUM='minimum'
    EXTRA='extra'


class PortfolioPaymentRequest(StrictModel):
    request_id:str=Field(min_length=1)
    debt_account_id:str
    source_account_id:str
    amount:Positive
    kind:RequestKind
    priority:int=Field(ge=0)
    initiated_at:datetime
    credited_at:datetime
    debited_at:datetime
    settled_at:datetime

    @model_validator(mode='after')
    def valid_lifecycle(self):
        if self.amount % CENT:raise ValueError('payment request must be whole cents')
        self.cash_plan(self.amount)
        return self

    def cash_plan(self,amount):
        return CashPlan(plan_id='portfolio:'+self.request_id,kind=CashKind.PAYMENT,amount=amount,
            source_account_id=self.source_account_id,initiated_at=self.initiated_at,credited_at=self.credited_at,
            debited_at=self.debited_at,settled_at=self.settled_at)


class PortfolioPaymentDecision(StrictModel):
    request_id:str
    debt_account_id:str
    kind:RequestKind
    requested:Positive
    accepted:Nonnegative
    unmet:Nonnegative
    reason:str


class PortfolioProjection(StrictModel):
    debt_horizon_start:datetime
    debt_horizon_end:datetime
    decisions:tuple[PortfolioPaymentDecision,...]
    payment_plans:tuple[CashPlan,...]
    debt_projections:tuple[DebtProjection,...]
    liquidity:LiquidityProjection
    all_requests_funded:bool
    all_minimum_requests_funded:bool
    missed_minimum_account_ids:tuple[str,...]
    label:str='estimate'


@decimal_context
def coordinate_payments(debts:tuple[PortfolioDebt,...],openings:tuple[CashOpening,...],
                        cash_plans:tuple[CashPlan,...],requests:tuple[PortfolioPaymentRequest,...],
                        start:datetime,end:datetime)->PortfolioProjection:
    """Reserve named minimums, then extras, and replay accepted credits per account.

    Caller supplies all external cash events through the returned cash horizon.
    No automatic transfers or new minimum requests are inferred. Unfunded
    requests and simulated missed due dates remain explicit in the result.
    """
    if start.utcoffset() is None or end.utcoffset() is None or end<start:
        raise ValueError('ordered timezone-aware portfolio horizon required')
    start=start.astimezone(timezone.utc);end=end.astimezone(timezone.utc)
    by_id={d.account.account_id:d for d in debts}
    if not debts or len(by_id)!=len(debts):raise ValueError('unique debt accounts required')
    cash_ids={o.account_id for o in openings}
    if len({r.request_id for r in requests})!=len(requests):raise ValueError('duplicate payment request ID')
    if any(p.plan_id.startswith('portfolio:') or p.kind==CashKind.PAYMENT for p in cash_plans):
        raise ValueError('portfolio debt payments must be supplied as requests, not duplicate cash plans')
    keys=[]
    for request in requests:
        if request.debt_account_id not in by_id or request.source_account_id not in cash_ids:
            raise ValueError('payment request references unknown account')
        if not start<=request.initiated_at<=request.credited_at<=end:
            raise ValueError('request initiation and credit must fall inside portfolio horizon')
        keys.append((request.initiated_at.astimezone(timezone.utc),request.priority))
    if len(keys)!=len(set(keys)):raise ValueError('simultaneous requests require distinct explicit priorities')
    ordered=sorted(requests,key=lambda r:(r.initiated_at.astimezone(timezone.utc),r.priority))
    sequence={r.request_id:i for i,r in enumerate(ordered)}
    horizon=max([end,start+timedelta(days=90)]+[r.initiated_at.astimezone(timezone.utc)+timedelta(days=90) for r in requests]
        +[r.settled_at.astimezone(timezone.utc) for r in requests])
    accepted=[];decisions={};used={id_:ZERO for id_ in by_id}
    for group in (RequestKind.MINIMUM,RequestKind.EXTRA):
        for request in (r for r in ordered if r.kind==group):
            projection=project_liquidity(openings,cash_plans+tuple(accepted),start,end_at=horizon)
            at=request.initiated_at.astimezone(timezone.utc)
            before=[p for p in projection.points if p.at<=at]
            window=(before[-1],)+tuple(p for p in projection.points if p.at>at)
            cash_capacity=max(ZERO,min(next(row.above_floor for row in p.positions if row.account_id==request.source_account_id) for p in window))
            if projection.status!=CashFlowStatus.HEALTHY:cash_capacity=ZERO
            balance_capacity=max(ZERO,by_id[request.debt_account_id].account.total_balance()-used[request.debt_account_id])
            amount=min(request.amount,cash_capacity,balance_capacity).quantize(CENT,rounding=ROUND_DOWN)
            reason='fully_funded' if amount==request.amount else ('cash_limit' if cash_capacity<=balance_capacity else 'opening_balance_limit')
            decisions[request.request_id]=PortfolioPaymentDecision(request_id=request.request_id,debt_account_id=request.debt_account_id,
                kind=request.kind,requested=request.amount,accepted=amount,unmet=request.amount-amount,reason=reason)
            if amount:
                accepted.append(request.cash_plan(amount));used[request.debt_account_id]+=amount
    debt_results=[]
    for debt in debts:
        tz=ZoneInfo(debt.credit_timezone)
        events=tuple(sorted((DebtCreditEvent(event_id=r.request_id,credited_at=r.credited_at,sequence=sequence[r.request_id])
            for r in ordered if r.debt_account_id==debt.account.account_id and decisions[r.request_id].accepted),key=lambda e:e.ordering_key()))
        result=simulate_revolving(debt.account,start.astimezone(tz).date(),end.astimezone(tz).date(),debt.cycles,debt.initial_minimum,(),
            choose_decision=lambda view:decisions[view.event_id].accepted,credit_events=events,credit_timezone=debt.credit_timezone,
            grace_terms=debt.grace_terms,promo_transitions=debt.promo_transitions)
        for payment in result.payments:
            if payment.amount!=decisions[payment.event_id].accepted:
                raise ArithmeticError('accepted cash commitment differs from creditor application')
        debt_results.append(result)
    final_cash=project_liquidity(openings,cash_plans+tuple(accepted),start,end_at=horizon)
    rows=tuple(decisions[r.request_id] for r in ordered)
    return PortfolioProjection(debt_horizon_start=start,debt_horizon_end=end,decisions=rows,payment_plans=tuple(accepted),debt_projections=tuple(debt_results),liquidity=final_cash,
        all_requests_funded=all(r.unmet==0 for r in rows),
        all_minimum_requests_funded=all(r.unmet==0 for r in rows if r.kind==RequestKind.MINIMUM),
        missed_minimum_account_ids=tuple(r.account.account_id for r in debt_results if r.missed_due_dates))
