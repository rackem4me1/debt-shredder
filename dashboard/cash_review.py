"""Plain-language schedule terms and every included cash occurrence."""
from html import escape
from zoneinfo import ZoneInfo
from dashboard.cash_inputs import CADENCE_LABELS, SHORT_MONTH_LABELS, cash_horizon
from engine.common import decimal_context


@decimal_context
def cash_review(scenario):
    tz = ZoneInfo(scenario.debts[0].credit_timezone)
    horizon = cash_horizon(scenario.start, scenario.end, scenario.requests)
    descriptions = []
    for event in scenario.manual_cash_schedules:
        text = f'{event.label}: {CADENCE_LABELS[event.cadence]}, ${event.amount:,.2f} each, starting {event.date:%b %d, %Y}'
        if event.cadence == 'monthly':
            text += f'; day {event.date.day}; {SHORT_MONTH_LABELS[event.short_month_rule.value].lower()}'
        if event.until:
            text += f'; stop after {event.until:%b %d, %Y} (only dates within this forecast are included)'
        elif event.cadence != 'once':
            text += '; repeat through this cash forecast'
        descriptions.append('<li>'+escape(text)+'</li>')
    rows = []
    for plan in sorted(scenario.cash_plans, key=lambda p:(p.initiated_at,p.plan_id)):
        rows.append('<tr><td>'+escape(plan.initiated_at.astimezone(tz).strftime('%b %d, %Y'))+
            '</td><td>'+('Income' if plan.kind.value=='income' else 'Bill / expense')+
            '</td><td>'+escape(plan.plan_id.split(': ',1)[-1])+'</td><td>$'+f'{plan.amount:,.2f}'+'</td></tr>')
    content = '<ul>'+''.join(descriptions)+'</ul>' if descriptions else ''
    content += ('<div class="scroll"><table><thead><tr><th>Cash date</th><th>Type</th><th>Description</th><th>Amount</th></tr></thead><tbody>'+''.join(rows)+'</tbody></table></div>') if rows else '<p>No income or bills entered.</p>'
    return '<section><h2>Upcoming income and bills</h2><p>'+str(len(rows))+' occurrences included through '+escape(horizon.astimezone(tz).strftime('%b %d, %Y at %I:%M %p %Z'))+'. Check these dates against when money will actually clear or leave checking. Weekends and holidays are not adjusted.</p>'+content+'</section>'
