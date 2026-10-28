"""Read-only synthetic multi-card minimum forecasts, never personal advice."""
from decimal import Decimal
from datetime import timedelta
from dashboard.multimonth import example
from dashboard.forms import shell
from dashboard.report import text, money
from engine.common import reconstruct, decimal_context
from engine.minimum_forecast import MinimumTerms, PaymentSlot
from engine.portfolio_minimum_forecast import CardMinimumSchedule, forecast_portfolio_minimums
from engine.liquidity import CashPlan, CashKind


def practice_forecast(shortage=False):
    source = example()
    first = source.debts[0]
    second = reconstruct(first, account=reconstruct(first.account, account_id='practice-b',
        segments=tuple(reconstruct(s, account_id='practice-b') for s in first.account.segments),
        allocation_rule=reconstruct(first.account.allocation_rule, account_id='practice-b')),
        cycles=tuple(reconstruct(c, account_id='practice-b') for c in first.cycles),
        initial_minimum=reconstruct(first.initial_minimum, account_id='practice-b'))
    schedules = tuple(CardMinimumSchedule(debt=debt, priority=index,
        terms=MinimumTerms(floor='25', rate='.01'),
        slots=tuple(PaymentSlot(slot_id=f'card-{index}-{r.request_id}',
            **{k:getattr(r,k) for k in ('initiated_at','credited_at','debited_at','settled_at')})
            for r in source.requests)) for index, debt in enumerate((first,second)))
    opening = reconstruct(source.openings[0], cleared='200' if shortage else '400', reserved='20')
    at = source.start + timedelta(days=24)
    bill = CashPlan(plan_id='practice-bill', kind=CashKind.EXPENSE, amount='50',
        source_account_id=opening.account_id, initiated_at=at, credited_at=at, debited_at=at, settled_at=at)
    result = forecast_portfolio_minimums(schedules, opening, (bill,), source.start, source.end)
    return schedules, opening, result


@decimal_context
def render_example():
    sections=[]
    for shortage in (False,True):
        schedules, opening, result = practice_forecast(shortage)
        labels={s.debt.account.account_id:f'Practice card {i+1}' for i,s in enumerate(schedules)}
        requests={r.request_id:r for r in result.requests}
        paid=sum((d.accepted for d in result.decisions),Decimal(0))
        unmet=sum((d.unmet for d in result.decisions),Decimal(0))
        cash=result.liquidity.points[-1].positions[0]
        rows=''.join('<tr>'+''.join('<td>'+text(cell)+'</td>' for cell in (
            requests[d.request_id].credited_at.strftime('%b %d, %Y'),labels[d.debt_account_id],
            money(d.requested),money(d.accepted),money(d.unmet)))+'</tr>' for d in result.decisions)
        debt_rows=''.join('<tr>'+''.join('<td>'+text(cell)+'</td>' for cell in (
            labels[d.account.account_id],money(d.account.total_balance()),
            money(sum((s.accrued_unposted_interest for s in d.account.segments),Decimal(0))),
            ', '.join(day.isoformat() for day in d.missed_due_dates) or 'None in this window'))+'</tr>' for d in result.debts)
        alerts=('<p class="error">Some minimums cannot be funded. The amounts below are forecast shortfalls, not permission to skip payments. Card 1 receives cash first under the explicitly supplied priority.</p>'
                if unmet else '<p>Every generated minimum fits in this example. No missed minimum dates occur within the debt window.</p>')
        sections.append(f'''<section><h2>{'When cash is short' if shortage else 'When the minimums fit'}</h2>
<p>Starting checking: <strong>{money(opening.cleared)}</strong>. The same account also covers a $50 bill on January 25, a $100 cash floor and $20 reserved for another purpose. No income is assumed.</p>
<div class="grid"><div><h3>Payments applied</h3><strong>{money(paid)}</strong></div><div><h3>Ending checking</h3><strong>{money(cash.cleared)}</strong></div><div><h3>Unfunded requests</h3><strong>{money(unmet)}</strong></div></div>
{alerts}
<p>Ending checking includes the $100 floor and $20 reserve. It is not an extra-payment recommendation.</p>
<div class="scroll"><table><caption>Month-by-month minimum payments</caption><thead><tr><th>Credit date (UTC)</th><th>Card</th><th>Requested minimum</th><th>Applied</th><th>Unfunded request</th></tr></thead><tbody>{rows}</tbody></table></div>
<p>Unfunded requests are summed across payment attempts; they are not a separate debt balance or a measure of unique overdue debt.</p>
<div class="scroll"><table><caption>Debt on March 31</caption><thead><tr><th>Card</th><th>Posted balance</th><th>Unposted interest</th><th>Missed minimum dates</th></tr></thead><tbody>{debt_rows}</tbody></table></div>
<p class="note">Debt window: January 1–March 31, 2026. Cash checks extend through {text(result.liquidity.end.date())}. April minimums are outside the supplied payment schedule.</p></section>''')
    return shell('Multi-card forecast practice','''<h1>Two cards. One cash balance.</h1>
<p><strong>Synthetic practice data—not your accounts.</strong> See how future minimums change as interest posts, and how both cards compete for the same cash after a bill and reserves are protected.</p>
<p><a href="#assumptions">Example assumptions</a> · <a href="/multimonth-example">One-card forecast</a> · <a href="/">Saved scenarios</a></p>'''+''.join(sections)+'''
<section id="assumptions"><h2>What these examples assume</h2><p>Each card starts at $1,000 with a $25 unpaid minimum. Both use 36.5% APR, simple daily interest with a fixed 365-day divisor, no grace, purchases or fees. The minimum formula is the smaller of posted debt and the greater of $25 or 1% of statement balance plus billed interest. These terms are illustrative.</p>
<p>Statements close at month-end. Minimums are due on the following month’s 20th. Explicit payment slots occur on January 20, February 20 and March 20. Initiation, credit, debit and settlement coincide in UTC. Card 1 has priority when slots coincide; the software has not selected an optimal priority.</p>
<p>Only starting cash changes between these examples. The bill is reserved in the cash forecast before January’s payments. Cash remains in its physical account and is counted once. This is minimum-only planning, with no extra payments or full payoff date.</p>
<p>This view does not save or change any personal plan. Personal use still requires confirmed terms, real payment timing and a complete bill schedule. Overlapping payment lifecycles are not supported by this first coordinator.</p></section>''')
