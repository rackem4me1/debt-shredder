"""Explicit synthetic multi-statement example; no automatic future requests."""
import calendar
from datetime import date,datetime,timezone
from decimal import Decimal as D
from SCHEMA import BillingCycle,assumed_default
from engine.common import reconstruct,decimal_context
from engine.portfolio import PortfolioPaymentRequest,RequestKind
from demo_portfolio import scenario as base_scenario
from dashboard.forms import shell
from dashboard.report import text,money


def example(payment='100'):
    original=base_scenario();debt=original.debts[0];account=debt.account
    segment=reconstruct(account.segments[0],balance='1000',apr=assumed_default(D('.365')))
    account=reconstruct(account,segments=(segment,),minimum_payment_floor=assumed_default(D('25')),
                        minimum_payment_rate=assumed_default(D('.01')))
    cycles=[]
    for year,month in ((2025,12),(2026,1),(2026,2),(2026,3)):
        close=date(year,month,calendar.monthrange(year,month)[1])
        cycles.append(BillingCycle(account_id=account.account_id,cycle_id=f'{year}-{month}',
            start_date=date(year,month,1),end_date=close,statement_date=close,
            due_date=date(year+(month==12),month%12+1,20)))
    debt=reconstruct(debt,account=account,cycles=tuple(cycles),initial_minimum=reconstruct(
        debt.initial_minimum,statement_minimum_original='25',statement_minimum_remaining='25'))
    requests=[]
    for month in (1,2,3):
        at=datetime(2026,month,20,tzinfo=timezone.utc)
        requests.append(PortfolioPaymentRequest(request_id=f'month-{month}',debt_account_id=account.account_id,
            source_account_id='checking',amount=payment,kind=RequestKind.MINIMUM,priority=0,
            initiated_at=at,credited_at=at,debited_at=at,settled_at=at))
    return reconstruct(original,name='Three-statement practice forecast',debts=(debt,),requests=tuple(requests),
        openings=(reconstruct(original.openings[0],cleared='400',floor='100'),),
        end=datetime(2026,3,31,tzinfo=timezone.utc),card_names=('Practice card',))


@decimal_context
def statement_rows(scenario):
    """Replay accepted events to each supplied close; never re-budget a prefix."""
    from engine.simulation import simulate_revolving,DebtCreditEvent
    projection=scenario.project();debt,=scenario.debts
    accepted={r.request_id:r.accepted for r in projection.decisions}
    rows=[]
    for cycle in debt.cycles:
        if not scenario.start.date()<=cycle.end_date<=scenario.end.date():continue
        events=tuple(DebtCreditEvent(event_id=r.request_id,credited_at=r.credited_at,sequence=i)
                     for i,r in enumerate(scenario.requests) if r.credited_at.date()<=cycle.end_date and accepted[r.request_id])
        result=simulate_revolving(debt.account,scenario.start.date(),cycle.end_date,debt.cycles,debt.initial_minimum,(),
            choose_decision=lambda view:accepted[view.event_id],credit_events=events,credit_timezone=debt.credit_timezone)
        minimum=next(m.remaining for m in result.checkpoint.minimums if m.cycle_id==cycle.cycle_id)
        interest=sum((a.amount for a in result.audit if a.kind=='interest_posting' and a.on==cycle.end_date),D(0))
        paid=sum((p.amount for p in result.payments if cycle.start_date<=p.on<=cycle.end_date),D(0))
        rows.append(dict(close=cycle.end_date,due=cycle.due_date,interest=interest,paid=paid,balance=result.account.total_balance(),minimum=minimum))
    return tuple(rows),projection


def render_example():
    scenario=example()
    rows,projection=statement_rows(scenario)
    from engine.minimum_forecast import forecast_minimums,MinimumTerms,PaymentSlot
    slots=tuple(PaymentSlot(slot_id=r.request_id,**{k:getattr(r,k) for k in ('initiated_at','credited_at','debited_at','settled_at')}) for r in scenario.requests)
    minimums=forecast_minimums(scenario.debts[0],scenario.openings[0],scenario.cash_plans,slots,scenario.start,scenario.end,MinimumTerms(floor='25',rate='.01'))
    minimum_rows=''.join('<tr><td>'+text(slot.credited_at.date())+'</td><td>'+money(row.requested)+'</td><td>'+money(row.accepted)+'</td><td>'+money(row.unmet)+'</td></tr>' for slot,row in zip(slots,minimums.decisions))
    minimum_section='<section><h2>New: minimum-only forecast</h2><p>Using the same synthetic terms and supplied payment dates, the engine now generates each request from the unpaid minimum at that date. It checks available cash and preserves the floor. No extra payment is added.</p><div class="scroll"><table><thead><tr><th>Credit date</th><th>Generated request</th><th>Applied</th><th>Unfunded</th></tr></thead><tbody>'+minimum_rows+'</tbody></table></div><p>Ending card balance: '+money(minimums.debt.account.total_balance())+'. Ending checking: '+money(minimums.liquidity.points[-1].positions[0].cleared)+'.</p><p>This spends a different total than the fixed $100 payments above, so it is not a same-budget strategy comparison. This first version supports one ordinary card, explicit minimum terms and supplied payment dates. It does not choose dates, add other debts or calculate a full payoff plan.</p></section>' 
    table=''.join('<tr>'+''.join('<td>'+text(v)+'</td>' for v in [r['close'],money(r['paid']),money(r['interest']),money(r['balance']),money(r['minimum']),r['due']])+'</tr>' for r in rows)
    return shell('Three-statement practice forecast','<h1>Three-statement practice forecast</h1><p>Practice data only. This example follows a $1,000 card through three statement closes, with an explicitly supplied $100 payment on each month’s 20th.</p><section><h2>What changes each month</h2><div class="scroll"><table><thead><tr><th>Statement closes</th><th>Payment applied</th><th>Interest posted</th><th>Ending balance</th><th>New minimum</th><th>Minimum due</th></tr></thead><tbody>'+table+'</tbody></table></div></section><p>Ending checking cash: '+money(projection.liquidity.points[-1].positions[0].cleared)+'. The $100 cash floor remains protected.</p><section><h2>What this example assumes</h2><p>36.5% annual interest, simple daily accrual with a fixed 365-day divisor, no active grace, no purchases or fees. Each new minimum is the smaller of the balance and the greater of $25 or 1% of the statement balance plus that statement’s interest. These are synthetic assumptions, not your card terms.</p><p>Payment initiation, credit, debit and settlement coincide on the 20th in this example. Real timing must be supplied for a personal forecast. The April 20 minimum is shown but no April payment is supplied; the debt forecast ends March 31.</p><p>The fixed-payment example above does not generate future payments automatically, estimate a full payoff date or recommend a plan. Cash is checked through '+text(projection.liquidity.end.date())+', separately from the debt window.</p></section>'+minimum_section+'<p><a href="/">Back to saved scenarios</a></p>')
