"""Expand explicit repeating assumptions into auditable payoff inputs.

Templates remain estimates. Known cycles and one-off cash events are preserved;
no cash recurrence or bank holiday adjustment is inferred from an amount.
"""
import calendar
from datetime import date,datetime,time,timedelta,timezone
from typing import Literal
from zoneinfo import ZoneInfo
from pydantic import Field,model_validator
from SCHEMA import StrictModel,IncomeCadence,SemimonthlyShortMonthRule,ProvenanceSource,BillingCycle
from engine.common import Positive,Nonnegative,CENT,decimal_context,reconstruct
from engine.schedules import scheduled_dates
from engine.minimum_forecast import PaymentSlot
from engine.portfolio import PortfolioDebt
from engine.liquidity import CashOpening,CashPlan,CashKind
from engine.payoff import PayoffInputs,PaymentFunding,cash_horizon,validate_payoff_inputs


class RepeatingPaymentRule(StrictModel):
    first_date: date
    cadence: Literal['weekly','biweekly','monthly']
    timezone_name: str
    clock: time
    credit_days: int=Field(strict=True,ge=0,le=14)
    debit_days: int=Field(strict=True,ge=0,le=14)
    settlement_days: int=Field(strict=True,ge=0,le=14)
    short_month_rule: SemimonthlyShortMonthRule|None=None
    provenance: ProvenanceSource=ProvenanceSource.ASSUMED_DEFAULT

    @model_validator(mode='after')
    def valid(self):
        ZoneInfo(self.timezone_name)
        if self.clock.tzinfo is not None:raise ValueError('Use a local clock and named timezone')
        if not self.credit_days<=self.debit_days<=self.settlement_days:
            raise ValueError('Require credit delay <= debit delay <= settlement delay')
        if (self.cadence=='monthly')!=(self.short_month_rule is not None):
            raise ValueError('Only monthly payment recurrence requires an explicit short-month rule')
        return self


class MonthlyStatementRule(StrictModel):
    account_id: str
    close_day: int=Field(strict=True,ge=1,le=31)
    due_day: int=Field(strict=True,ge=1,le=31)
    due_month_offset: Literal[1]
    short_month_rule: SemimonthlyShortMonthRule
    provenance: ProvenanceSource=ProvenanceSource.ASSUMED_DEFAULT


class RecurringPayoffCash(StrictModel):
    schedule_id: str=Field(min_length=1,max_length=80)
    kind: Literal['income','expense']
    account_id: str|None=None
    amount: Positive
    first_date: date
    cadence: Literal['once','weekly','biweekly','monthly']
    clock: time
    until: date|None=None
    short_month_rule: SemimonthlyShortMonthRule|None=None
    provenance: ProvenanceSource=ProvenanceSource.USER_PROVIDED_ESTIMATE

    @model_validator(mode='after')
    @decimal_context
    def valid(self):
        if self.amount % CENT:raise ValueError('Cash schedules require whole cents')
        if self.clock.tzinfo is not None:raise ValueError('Cash clock must use the template timezone')
        if self.until is not None and (self.cadence=='once' or self.until<self.first_date):
            raise ValueError('A repeating stop date cannot precede its first date')
        if (self.cadence=='monthly')!=(self.short_month_rule is not None):
            raise ValueError('Monthly cash recurrence requires an explicit short-month rule')
        return self


class RecurringPayoffTransfer(StrictModel):
    schedule_id: str=Field(min_length=1,max_length=80)
    kind: Literal['transfer','contribution']='transfer'
    source_account_id: str
    destination_account_id: str
    amount: Positive
    first_date: date
    cadence: Literal['once','weekly','biweekly','monthly']
    clock: time
    debit_days: int=Field(strict=True,ge=0,le=14)
    credit_days: int=Field(strict=True,ge=0,le=14)
    settlement_days: int=Field(strict=True,ge=0,le=14)
    until: date|None=None
    short_month_rule: SemimonthlyShortMonthRule|None=None
    provenance: ProvenanceSource=ProvenanceSource.USER_PROVIDED_ESTIMATE

    @model_validator(mode='after')
    @decimal_context
    def valid(self):
        if self.amount%CENT:raise ValueError('Transfers require whole cents')
        if not self.source_account_id or not self.destination_account_id or self.source_account_id==self.destination_account_id:
            raise ValueError('Transfer recurrence needs two different physical accounts')
        if self.clock.tzinfo is not None:raise ValueError('Transfer clock must use the template timezone')
        if not self.debit_days<=self.credit_days<=self.settlement_days:raise ValueError('Require debit delay <= credit delay <= settlement delay')
        if self.until is not None and (self.cadence=='once' or self.until<self.first_date):raise ValueError('Invalid transfer stop date')
        if (self.cadence=='monthly')!=(self.short_month_rule is not None):raise ValueError('Monthly transfers require an explicit short-month rule')
        return self


class PayoffTemplate(StrictModel):
    format: Literal['debt-shredder-payoff-template']='debt-shredder-payoff-template'
    version: Literal[1]=1
    start: datetime
    end: datetime
    debts: tuple[PortfolioDebt,...]=Field(min_length=1,max_length=10)
    opening: CashOpening
    additional_openings: tuple[CashOpening,...]=Field(default=(),max_length=19)
    payment_sources: tuple[PaymentFunding,...]=Field(default=(),max_length=10)
    payment_target: Nonnegative
    payments: RepeatingPaymentRule
    statements: tuple[MonthlyStatementRule,...]=Field(min_length=1,max_length=10)
    cash_schedules: tuple[RecurringPayoffCash,...]=Field(default=(),max_length=40)
    transfer_schedules: tuple[RecurringPayoffTransfer,...]=Field(default=(),max_length=40)
    one_off_cash_plans: tuple[CashPlan,...]=Field(default=(),max_length=2000)


class ExpandedPayoff(StrictModel):
    template: PayoffTemplate
    inputs: PayoffInputs
    generated_cycle_ids: tuple[str,...]
    excluded_payment_dates: tuple[date,...]=()
    pending_transfer_ids: tuple[str,...]=()
    assumption_note: str='Generated dates and fixed future terms are estimates. Calendar-day delays; no inferred weekend or holiday adjustments. Only declared cash schedules repeat.'


def _local(day,clock,tz):
    at=datetime.combine(day,clock,tzinfo=tz)
    # Refuse ambiguous/nonexistent local times instead of choosing a DST fold.
    if at.astimezone(timezone.utc).astimezone(tz).replace(tzinfo=None)!=at.replace(tzinfo=None) or at.utcoffset()!=at.replace(fold=1).utcoffset():
        raise ValueError('Schedule contains an ambiguous or nonexistent local clock time')
    return at


def monthly_occurrence(year,month,day,rule):
    limit=calendar.monthrange(year,month)[1]
    if day<=limit:return date(year,month,day)
    if rule==SemimonthlyShortMonthRule.CLAMP_TO_LAST_DAY_OF_MONTH:return date(year,month,limit)
    return date(year+(month==12),month%12+1,1)


def _next_close(first,rule):
    candidate=monthly_occurrence(first.year,first.month,rule.close_day,rule.short_month_rule)
    if candidate<first:
        candidate=monthly_occurrence(first.year+(first.month==12),first.month%12+1,rule.close_day,rule.short_month_rule)
    return candidate


@decimal_context
def expand_payoff_template(template:PayoffTemplate)->ExpandedPayoff:
    if template.start.utcoffset() is None or template.end.utcoffset() is None or not 0<=(template.end-template.start).total_seconds()<=3660*86400:
        raise ValueError('Supply an aware ordered template of at most 3660 days')
    tz=ZoneInfo(template.payments.timezone_name)
    first=template.start.astimezone(tz).date();last=template.end.astimezone(tz).date()
    if template.payments.first_date<first:raise ValueError('First payment must be on or after the opening date')
    if any(d.credit_timezone!=template.payments.timezone_name for d in template.debts):
        raise ValueError('Repeating template requires all cards to share its named timezone')
    keys=[s.account_id for s in template.statements]
    ids=[d.account.account_id for d in template.debts]
    if len(set(keys))!=len(keys) or set(keys)!=set(ids):raise ValueError('Exactly one statement rule per debt account is required')
    schedule_ids=[s.schedule_id for s in template.cash_schedules+template.transfer_schedules]
    if len(set(schedule_ids))!=len(schedule_ids):raise ValueError('Duplicate cash or transfer schedule ID')
    slots=[];excluded=[];rule=template.payments
    events=scheduled_dates(IncomeCadence(rule.cadence),rule.first_date,first,last,
        day_of_month=rule.first_date.day,short_month_rule=rule.short_month_rule)
    for key,day in events:
        stamps=tuple(_local(day+timedelta(days=delay),rule.clock,tz) for delay in (0,rule.credit_days,rule.debit_days,rule.settlement_days))
        if stamps[-1]>template.end:
            excluded.append(day);continue
        slots.append(PaymentSlot(slot_id='repeat:'+key,**dict(zip(('initiated_at','credited_at','debited_at','settled_at'),stamps))))
    if not slots:raise ValueError('No complete payment lifecycle fits inside the chosen end date')
    if len(slots)>120:raise ValueError('Repeating schedule exceeds 120 payment rounds; shorten the horizon or use a slower cadence')
    debts=[];generated=[];rules={s.account_id:s for s in template.statements}
    for debt in template.debts:
        if not debt.cycles:raise ValueError('Keep at least the opening statement cycle')
        cycles=list(sorted(debt.cycles,key=lambda c:c.start_date));rule=rules[debt.account.account_id]
        existing={c.cycle_id for c in cycles}
        while cycles[-1].end_date<last:
            begin=cycles[-1].end_date+timedelta(days=1);close=_next_close(begin,rule)
            cycle_id='repeat:'+close.isoformat()
            if cycle_id in existing:raise ValueError('Generated cycle ID collides with a known cycle')
            due=monthly_occurrence(close.year+(close.month==12),close.month%12+1,rule.due_day,rule.short_month_rule)
            cycles.append(BillingCycle(account_id=debt.account.account_id,cycle_id=cycle_id,start_date=begin,
                end_date=close,statement_date=close,due_date=due))
            existing.add(cycle_id);generated.append(debt.account.account_id+'/'+cycle_id)
            if len(cycles)>250:raise ValueError('Too many statement cycles')
        debts.append(reconstruct(debt,cycles=tuple(cycles)))
    provisional=PayoffInputs(start=template.start,end=template.end,debts=tuple(debts),opening=template.opening,
        additional_openings=template.additional_openings,payment_sources=template.payment_sources,
        payment_target=template.payment_target,slots=tuple(slots),cash_plans=template.one_off_cash_plans)
    horizon=cash_horizon(provisional);last_cash=horizon.astimezone(tz).date();plans=list(template.one_off_cash_plans)
    for schedule in template.cash_schedules:
        if schedule.first_date<first:raise ValueError('Cash schedule first dates must not precede the opening balance date')
        cadence=IncomeCadence.IRREGULAR if schedule.cadence=='once' else IncomeCadence(schedule.cadence)
        events=scheduled_dates(cadence,schedule.first_date,first,min(last_cash,schedule.until or last_cash),
            day_of_month=schedule.first_date.day,short_month_rule=schedule.short_month_rule)
        for key,day in events:
            at=_local(day,schedule.clock,tz)
            if not template.start<=at<=horizon:continue
            plans.append(CashPlan(plan_id='repeat-cash:'+schedule.schedule_id+':'+key,kind=CashKind(schedule.kind),
                amount=schedule.amount,initiated_at=at,credited_at=at,debited_at=at,settled_at=at,
                source_account_id=(schedule.account_id or template.opening.account_id) if schedule.kind=='expense' else None,
                destination_account_id=(schedule.account_id or template.opening.account_id) if schedule.kind=='income' else None,
                provenance=schedule.provenance))
    for schedule in template.transfer_schedules:
        if schedule.first_date<first:raise ValueError('Transfer schedule must not precede the opening balance date')
        cadence=IncomeCadence.IRREGULAR if schedule.cadence=='once' else IncomeCadence(schedule.cadence)
        events=scheduled_dates(cadence,schedule.first_date,first,min(last_cash,schedule.until or last_cash),
            day_of_month=schedule.first_date.day,short_month_rule=schedule.short_month_rule)
        for key,day in events:
            stamps=tuple(_local(day+timedelta(days=delay),schedule.clock,tz) for delay in (0,schedule.debit_days,schedule.credit_days,schedule.settlement_days))
            if not template.start<=stamps[0]<=horizon:continue
            plans.append(CashPlan(plan_id='repeat-transfer:'+schedule.schedule_id+':'+key,kind=CashKind(schedule.kind),amount=schedule.amount,
                source_account_id=schedule.source_account_id,destination_account_id=schedule.destination_account_id,
                initiated_at=stamps[0],debited_at=stamps[1],credited_at=stamps[2],settled_at=stamps[3],provenance=schedule.provenance))
    inputs=reconstruct(provisional,cash_plans=tuple(plans));validate_payoff_inputs(inputs)
    return ExpandedPayoff(template=template,inputs=inputs,generated_cycle_ids=tuple(generated),excluded_payment_dates=tuple(excluded),pending_transfer_ids=tuple(p.plan_id for p in plans if p.kind in (CashKind.TRANSFER,CashKind.CONTRIBUTION) and p.initiated_at<=horizon<p.settled_at))
