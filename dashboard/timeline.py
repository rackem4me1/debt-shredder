"""Explain engine ledger events without replaying or recomputing balances."""
from collections import defaultdict
from datetime import date
from zoneinfo import ZoneInfo
from decimal import Decimal
from dashboard.forms import shell
from dashboard.report import text, money, readable_time, card_label
from engine.liquidity import CashKind


def event_description(event, request_by_plan):
    if event.kind == CashKind.PAYMENT:
        request = request_by_plan[event.plan_id]
        label, detail = {
            'init': ('Payment submitted', 'Cash is committed in the source account; it has not left checking yet.'),
            'credit': ('Card receives payment', 'The accepted payment is applied to the card; this event alone does not debit checking.'),
            'debit': ('Money leaves checking', 'Cleared cash decreases and the matching cash commitment is released.'),
            'settle': ('Payment settles', 'The payment lifecycle finishes. This is not another withdrawal.'),
        }[event.stage]
        return dict(label=label, detail=detail, reference=request.request_id,
                    source=event.source_account_id, destination=request.debt_account_id,
                    amount=str(event.amount))
    if event.stage == 'atomic':
        label, detail = {
            CashKind.INCOME: ('Income arrives', 'Cleared money is added to the destination account.'),
            CashKind.EXPENSE: ('Expense paid', 'Cleared money leaves the source account.'),
            CashKind.RESERVE: ('Cash reserved', 'Money stays in the same account but becomes reserved for another purpose.'),
        }[event.kind]
    else:
        label, detail = {
            'init': ('Transfer submitted', 'Cash is committed in the source account.'),
            'debit': ('Transfer leaves source', 'Cash moves out of the source account and is in transit; it is not an expense.'),
            'credit': ('Transfer reaches destination', 'Cash reaches the destination but is held until settlement; it is not income.'),
            'settle': ('Transfer settles', 'The settlement hold is released.'),
        }[event.stage]
        if event.kind == CashKind.CONTRIBUTION and event.stage == 'settle':
            detail = 'The settlement hold becomes reserved cash in the destination account.'
    return dict(label=label,detail=detail,reference=event.plan_id,source=event.source_account_id,
                destination=event.destination_account_id,amount=str(event.amount))


def timeline_data(scenario):
    result = scenario.project()
    by_plan = {'portfolio:'+request.request_id: request for request in scenario.requests}
    events = defaultdict(list)
    for entry in result.liquidity.audit:
        events[entry.at].append(event_description(entry, by_plan))
    points = []
    floors = {row.account_id: str(row.floor) for row in scenario.openings}
    for index, point in enumerate(result.liquidity.points):
        # The opening point is BEFORE events at start, even if timestamps match.
        points.append(dict(at=point.at.isoformat(), opening=index==0,
            events=[] if index==0 else events[point.at],
            positions=[{**row.model_dump(mode='json'),'floor':floors[row.account_id]} for row in point.positions],
            in_transit=str(point.in_transit),status=point.status.value))
    checks = []
    for debt, projection in zip(scenario.debts, result.debt_projections):
        known = {state.cycle_id for state in projection.checkpoint.minimums}
        zone = ZoneInfo(debt.credit_timezone)
        start, end = result.debt_horizon_start.astimezone(zone).date(),result.debt_horizon_end.astimezone(zone).date()
        dates = sorted({cycle.due_date for cycle in debt.cycles if cycle.cycle_id in known and start<=cycle.due_date<=end})
        for day in dates:
            checks.append(dict(account_id=debt.account.account_id,on=day.isoformat(),zone=debt.credit_timezone,
                missed=day in projection.missed_due_dates))
    return dict(name=scenario.name,origin=scenario.origin,
        zone=scenario.debts[0].credit_timezone if len({d.credit_timezone for d in scenario.debts})==1 else 'UTC',
        points=points,due_checks=checks,
        unfunded=[row.model_dump(mode='json') for row in result.decisions if row.unmet],
        debt_end=result.debt_horizon_end.isoformat(),cash_end=result.liquidity.end.isoformat())


def render_timeline(scenario):
    data=timeline_data(scenario)
    def amount(value):return text(money(Decimal(value)))
    def when(value):return text(readable_time(value,data['zone']))
    blocks=[]
    for point in data['points']:
        heading='Opening cash — before activity' if point['opening'] else ('Planned activity' if point['events'] else 'End of supplied cash forecast')
        event_rows=''.join('<li><strong>'+text(event['label'])+' · '+amount(event['amount'])+'</strong> — '+
            text(event['reference'])+'<br>'+text(event['detail'])+'<br><small>From: '+text(event['source'] or 'Outside accounts')+
            ' · To: '+text(card_label(scenario,event['destination']) if event['destination'] else 'Outside accounts')+'</small></li>' for event in point['events'])
        rows=''.join('<tr><th scope="row">'+text(row['account_id'])+'</th>'+''.join('<td>'+amount(row[key])+'</td>' for key in
            ('cleared','committed','held','reserved','floor','above_floor'))+'</tr>' for row in point['positions'])
        blocks.append(f'''<section><h2>{heading}</h2><p>{when(point['at'])}</p>{'<ul>'+event_rows+'</ul>' if event_rows else ''}
<p>{'Opening balances' if point['opening'] else 'Cash after all events at this time'} · {text(point['status'].replace('_',' '))}</p>
<div class="scroll"><table><thead><tr><th>Account</th><th>Cleared cash</th><th>Committed</th><th>Held</th><th>Reserved</th><th>Minimum cash</th><th>Above protections</th></tr></thead><tbody>{rows}</tbody></table></div>
<p>Money between accounts: {amount(point['in_transit'])}</p></section>''')
    due_rows=''.join('<li>'+text(card_label(scenario,check['account_id']))+' · '+text(date.fromisoformat(check['on']).strftime('%b %d, %Y'))+' ('+text(check['zone'])+'): '+
                     ('Minimum missed' if check['missed'] else 'No missed minimum recorded')+'</li>' for check in data['due_checks'])
    unfunded=''.join('<li>'+text(row['request_id'])+': '+amount(row['unmet'])+' of the requested payment is not applied.</li>' for row in data['unfunded'])
    origin='Synthetic example' if data['origin']=='synthetic_demo' else 'Manual estimates'
    return shell('Payment timeline',f'''<h1>When the money moves</h1><p>{text(data['name'])} · {origin}</p>
<p><a href="/">Back to saved scenarios</a></p>
<p>These are the planned steps for your money. Submitting a payment, receiving card credit and debiting checking are different events. The same payment amount can appear at each stage; do not add those stages together.</p>
<p>Each balance is shown after the listed events. Events sharing a timestamp are grouped together; this does not predict the order a card company processes them. Daily interest follows that day’s card credits; this page does not assign interest to individual hours.</p>
{('<section><h2>Requested dollars that do not move</h2><ul>'+unfunded+'</ul></section>') if unfunded else ''}
<section><h2>Due-date checks</h2>{'<ul>'+due_rows+'</ul>' if due_rows else '<p>No known minimum due date falls inside this debt window.</p>'}
<p>These checks cover the debt forecast through {when(data['debt_end'])}. The cash forecast continues through {when(data['cash_end'])}; later minimums are not automatically supplied.</p></section>
{''.join(blocks)}<p>Committed cash is promised but not yet debited. Held cash awaits settlement. Reserved cash and the floor are separate protections. The amount above protections is a snapshot, not a recommendation for another payment: later obligations may need that cash. Money in one account is not automatically available from another. All amounts are estimates; no real money is moved.</p>''')
