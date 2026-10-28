"""Deterministic expansion of explicit schema income, bills and fund schedules."""
import calendar
from datetime import date,datetime,time,timedelta
from zoneinfo import ZoneInfo
from SCHEMA import IncomeCadence,SemimonthlyShortMonthRule,semimonthly_occurrences,FinancialSnapshot
from engine.common import MissingTerms
from engine.liquidity import CashKind,CashPlan,transfer_plan


def _months(first,last):
    y,m=first.year,first.month
    while (y,m)<=(last.year,last.month):
        yield y,m
        y,m=y+(m==12),m%12+1


def scheduled_dates(cadence,anchor,first,last,*,weekday=None,day_of_month=None,
                    semimonthly_days=None,short_month_rule=None):
    """Return (stable nominal-event key, effective date). Preserve coincident events.

    IRREGULAR represents only the one explicitly supplied anchor event. It never
    invents future paydays. Monthly recurrence needs an explicit short-month rule.
    """
    if last<first:raise ValueError('schedule range reversed')
    first=max(first,anchor)
    if last<first:return ()
    if cadence==IncomeCadence.IRREGULAR:return (('one',anchor),) if first<=anchor<=last else ()
    if cadence in (IncomeCadence.WEEKLY,IncomeCadence.BIWEEKLY):
        if weekday is not None and anchor.weekday()!=weekday:raise MissingTerms('weekly anchor disagrees with weekday')
        step=7 if cadence==IncomeCadence.WEEKLY else 14
        count=max(0,((first-anchor).days+step-1)//step)
        out=[]
        while anchor+timedelta(days=count*step)<=last:
            out.append((str(count),anchor+timedelta(days=count*step)));count+=1
        return tuple(out)
    if short_month_rule is None:raise MissingTerms('explicit short-month handling required')
    rule=SemimonthlyShortMonthRule(short_month_rule)
    prev=first.replace(day=1)-timedelta(days=1) if first>date(1,1,31) else first
    out=[]
    for y,m in _months(prev,last):
        if cadence==IncomeCadence.SEMIMONTHLY:
            if semimonthly_days is None:raise MissingTerms('two semimonthly days required')
            events=semimonthly_occurrences(y,m,semimonthly_days,rule)
        elif cadence==IncomeCadence.MONTHLY:
            if day_of_month is None or not 1<=day_of_month<=31:raise MissingTerms('monthly day required')
            limit=calendar.monthrange(y,m)[1]
            if day_of_month<=limit:events=(date(y,m,day_of_month),)
            elif rule==SemimonthlyShortMonthRule.CLAMP_TO_LAST_DAY_OF_MONTH:events=(date(y,m,limit),)
            else:events=(date(y+(m==12),m%12+1,1),)
        else:raise ValueError('unknown cadence')
        out.extend((f'{y}-{m}:{i}',day) for i,day in enumerate(events) if first<=day<=last)
    return tuple(sorted(out,key=lambda row:(row[1],row[0])))


def external_cash_schedule(snapshot:FinancialSnapshot,first:date,last:date,*,
                           timezone_name:str,income_time:time,obligation_time:time,
                           contribution_time:time,monthly_rule:SemimonthlyShortMonthRule,
                           holidays:tuple[date,...])->tuple[CashPlan,...]:
    """Explicit timing assumptions supplied by caller; generated events are estimates.

    This expands income, external bills and future fund contributions only. Debt
    payments are scheduled separately; never duplicate them as obligations here.
    """
    tz=ZoneInfo(timezone_name);plans=[]
    def atomic(id_,kind,amount,day,clock,account):
        instant=datetime.combine(day,clock,tz)
        return CashPlan(plan_id=id_,kind=kind,amount=amount,
            source_account_id=None if kind==CashKind.INCOME else account,
            destination_account_id=account if kind==CashKind.INCOME else None,
            initiated_at=instant,credited_at=instant,debited_at=instant,settled_at=instant)
    for inc in snapshot.income_sources:
        if not inc.amount:continue
        occurrences=scheduled_dates(inc.cadence,inc.anchor_date,first,last,weekday=inc.weekday,day_of_month=inc.day_of_month,
            semimonthly_days=inc.semimonthly_days,short_month_rule=inc.semimonthly_short_month_rule or monthly_rule)
        plans.extend(atomic(f'income:{inc.source_id}:{key}',CashKind.INCOME,inc.amount,day,income_time,inc.destination_account_id) for key,day in occurrences)
    for ob in snapshot.obligations:
        if ob.amount and first<=ob.due_date<=last:
            plans.append(atomic(f'obligation:{ob.obligation_id}',CashKind.EXPENSE,ob.amount,ob.due_date,obligation_time,ob.source_account_id))
    policies={(p.source_account_id,p.dest_account_id):p for p in snapshot.transfer_timing_policies}
    for fund in snapshot.sinking_funds:
        if fund.planned_contribution_suspended or not fund.planned_contribution_amount:continue
        anchor=fund.planned_contribution_next_date
        events=scheduled_dates(fund.planned_contribution_cadence,anchor,first,last,
            day_of_month=anchor.day,semimonthly_days=fund.planned_contribution_semimonthly_days,
            short_month_rule=fund.planned_contribution_semimonthly_short_month_rule or monthly_rule)
        for key,day in events:
            id_=f'contribution:{fund.allocation_id}:{key}'
            if fund.planned_contribution_source_account_id==fund.account_id:
                plans.append(atomic(id_,CashKind.RESERVE,fund.planned_contribution_amount,day,contribution_time,fund.account_id))
            else:
                policy=policies.get((fund.planned_contribution_source_account_id,fund.account_id))
                if policy is None:raise MissingTerms('scheduled fund transfer needs an explicit route timing policy')
                plans.append(transfer_plan(policy,id_,fund.planned_contribution_amount,datetime.combine(day,contribution_time,tz),holidays,contribution=True))
    return tuple(sorted(plans,key=lambda p:(p.initiated_at,p.plan_id)))
