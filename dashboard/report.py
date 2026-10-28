"""Escaped local HTML view of the authoritative portfolio result."""
from html import escape
from decimal import Decimal
from datetime import datetime
from zoneinfo import ZoneInfo
from engine.common import decimal_context
from dashboard.scenarios import Scenario


def text(value):
    return escape(str(value), quote=True)


def money(value):
    # Display precision only; the underlying result remains an exact decimal string.
    return '$' + format(value, ',.2f')


def card_label(scenario, account_id):
    for index, debt in enumerate(scenario.debts):
        if debt.account.account_id == account_id:
            name = scenario.card_names[index] if scenario.card_names else ''
            return f'{name} ({account_id})' if name else account_id
    return account_id


def readable_time(value, zone='UTC'):
    moment = datetime.fromisoformat(value).astimezone(ZoneInfo(zone))
    return moment.strftime('%b %d, %Y at %I:%M %p %Z')


@decimal_context
def summary(scenario: Scenario):
    projection = scenario.project()
    floors = {row.account_id: row.floor for row in scenario.openings}
    final = projection.liquidity.points[-1]
    return {
        'name': scenario.name,
        'time_zone': scenario.debts[0].credit_timezone if len({d.credit_timezone for d in scenario.debts})==1 else 'UTC',
        'origin': scenario.origin,
        'debt_start': projection.debt_horizon_start.isoformat(),
        'debt_end': projection.debt_horizon_end.isoformat(),
        'cash_end': projection.liquidity.end.isoformat(),
        'cash_status': projection.liquidity.status.value,
        'cash': [{**row.model_dump(mode='json'), 'floor': str(floors[row.account_id])}
                 for row in final.positions],
        'debts': [{'account_id': debt.account.account_id,
                   'posted_balance': str(debt.account.total_balance()),
                   'unposted_interest': str(sum((segment.accrued_unposted_interest
                                                for segment in debt.account.segments), Decimal(0))),
                   'missed_due_dates': [day.isoformat() for day in debt.missed_due_dates]}
                  for debt in projection.debt_projections],
        'decisions': [row.model_dump(mode='json') for row in projection.decisions],
        'all_minimum_requests_funded': projection.all_minimum_requests_funded,
        'missed_minimum_account_ids': list(projection.missed_minimum_account_ids),
    }


@decimal_context
def render(scenario: Scenario) -> str:
    data = summary(scenario)
    def when(value):
        return text(readable_time(value, data['time_zone']))
    def amount(value):
        return text(money(Decimal(value)))
    cash_rows = ''.join('<tr>' + ''.join(f'<td>{cell}</td>' for cell in (
        text(row['account_id']), amount(row['cleared']), amount(row['floor']),
        amount(row['reserved']), amount(row['committed']), amount(row['held']), amount(row['above_floor']))) + '</tr>'
        for row in data['cash'])
    debt_rows = ''.join('<tr>' + ''.join(f'<td>{cell}</td>' for cell in (
        text(card_label(scenario,row['account_id'])), amount(row['posted_balance']), amount(row['unposted_interest']),
        text(', '.join(row['missed_due_dates']) or 'None in this window'))) + '</tr>' for row in data['debts'])
    reasons = {'fully_funded': 'Fully funded', 'cash_limit': 'Cash limit', 'opening_balance_limit': 'Opening balance limit'}
    request_dates = {row.request_id: row for row in scenario.requests}
    payment_rows = ''.join('<tr>' + ''.join(f'<td>{cell}</td>' for cell in (
        text(row['request_id']), text(card_label(scenario,row['debt_account_id'])), text(row['kind'].title()),
        when(request_dates[row['request_id']].initiated_at.isoformat()),
        when(request_dates[row['request_id']].credited_at.isoformat()),
        amount(row['requested']), amount(row['accepted']), amount(row['unmet']),
        text(reasons.get(row['reason'], row['reason'])))) + '</tr>' for row in data['decisions'])
    if not payment_rows:
        payment_rows = '<tr><td colspan="9">No payment requests supplied.</td></tr>'
    missed = ', '.join(card_label(scenario,id_) for id_ in data['missed_minimum_account_ids'])
    status = ('Missed minimum dates: ' + missed if missed else 'No missed minimum dates in the debt window.')
    request_status = ('No payment requests were supplied.' if not data['decisions'] else
        'Every requested payment dollar fits.' if all(Decimal(r['unmet'])==0 for r in data['decisions']) else
        'Some requested payment dollars do not fit; see the unfunded amounts below.')
    requested_total = sum((Decimal(r['requested']) for r in data['decisions']), Decimal(0))
    accepted_total = sum((Decimal(r['accepted']) for r in data['decisions']), Decimal(0))
    floor_total = sum((Decimal(r['floor']) for r in data['cash']), Decimal(0))
    reserve_total = sum((Decimal(r['reserved']) for r in data['cash']), Decimal(0))
    posted_total = sum((Decimal(r['posted_balance']) for r in data['debts']), Decimal(0))
    interest_total = sum((Decimal(r['unposted_interest']) for r in data['debts']), Decimal(0))
    attention = []
    if missed:
        attention.append('Minimum payments are missed in this forecast: ' + missed + '.')
    if requested_total > accepted_total:
        attention.append(money(requested_total - accepted_total) + ' of requested payments cannot be applied. See Payment requests for the reason.')
    if data['cash_status'] != 'healthy':
        attention.append('Cash needs attention somewhere in the cash window: ' + data['cash_status'].replace('_', ' ').lower() + '. Review the cash timeline; the ending balance alone does not show earlier shortages.')
    if not data['decisions']:
        attention.append('No payments are planned in this scenario.')
    attention_html = ('<ul>' + ''.join('<li>' + text(item) + '</li>' for item in attention) + '</ul>'
                      if attention else '<p>No missed minimums or cash alerts were found within the supplied forecast windows.</p>')
    overview = f'''<section aria-labelledby="overview-title"><h2 id="overview-title">Your plan at a glance</h2>
<p class="muted">A forecast of the entries you supplied. No money has moved.</p>
<div class="overview-grid">
<div class="metric"><h3>Planned payments applied</h3><strong>{amount(accepted_total)}</strong><p>Of {amount(requested_total)} requested in the debt window.</p></div>
<div class="metric"><h3>Cash protection settings</h3><strong>{amount(floor_total + reserve_total)}</strong><p>{amount(floor_total)} in account floors + {amount(reserve_total)} reserved at the cash-window end. Each stays attached to its account; this is not available spending money or proof that every floor is met.</p></div>
<div class="metric"><h3>Projected posted debt</h3><strong>{amount(posted_total)}</strong><p>Plus {amount(interest_total)} unposted interest at the debt-window end.</p></div>
</div>
<div class="notice"><h3>{'Needs your attention' if attention else 'Forecast checks'}</h3>{attention_html}</div>
<p class="muted">Debt forecast through {when(data['debt_end'])}. Cash checks through {when(data['cash_end'])}. Unentered bills and future minimum payments are not included automatically.</p>
<p><a href="#cash-details">Cash by account</a> · <a href="#payment-details">Payment details</a> · <a href="#debt-details">Debt details</a></p></section>'''
    explanation = ''
    if len(scenario.openings)==1 and len(data['debts'])==1:
        opening=scenario.openings[0]
        accepted=sum((Decimal(row['accepted']) for row in data['decisions']),Decimal(0))
        requested=sum((Decimal(row['requested']) for row in data['decisions']),Decimal(0))
        explanation=f'''<section><h2>What this means</h2>
<p>You requested <strong>{amount(requested)}</strong> in payments. This scenario applies <strong>{amount(accepted)}</strong>.</p>
<p>Your checking account starts with {amount(opening.cleared)}. You asked to protect {amount(opening.floor)} as a minimum balance and {amount(opening.reserved)} for other purposes.</p>
<p>After the supplied cash activity, checking has <strong>{amount(data['cash'][0]['cleared'])}</strong> left.</p>
<p>The card ends with <strong>{amount(data['debts'][0]['posted_balance'])}</strong> already posted, plus <strong>{amount(data['debts'][0]['unposted_interest'])}</strong> in interest that has built up but has not yet been added to a statement.</p>
<p>No money has moved. These results describe what would happen under the dates and assumptions you entered.</p></section>'''
    if len(scenario.openings)==1 and len(data['debts'])>1:
        totals=[]
        for debt in data['debts']:
            decisions=[r for r in data['decisions'] if r['debt_account_id']==debt['account_id']]
            requested=sum((Decimal(r['requested']) for r in decisions),Decimal(0))
            accepted=sum((Decimal(r['accepted']) for r in decisions),Decimal(0))
            totals.append('<li>'+text(card_label(scenario,debt['account_id']))+': requested '+amount(requested)+
                '; applied '+amount(accepted)+'.</li>')
        explanation='<section><h2>What this means</h2><p>These cards share one checking balance. Cash is counted once, with your floor and reserved money protected.</p><ul>'+''.join(totals)+'</ul><p>After supplied activity, checking has <strong>'+amount(data['cash'][0]['cleared'])+'</strong> left.</p><p>For multi-card form entries marked Minimum, the required-minimum portion is reserved before excess. The detailed rows below may split one proposed payment into minimum and excess portions; they are parts of that payment, not additional payments. Initiation time and the saved request priorities determine the order within each group. This forecast does not establish a full-payoff recommendation.</p><p>No money has moved.</p></section>'
    badge = 'Synthetic example' if scenario.origin == 'synthetic_demo' else 'Manually entered scenario'
    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{text(scenario.name)} · Debt Shredder</title>
<style>
:root{{font-family:system-ui,sans-serif;color:#172b41;background:#eef2f7;font-size:16px;line-height:1.5}}
*{{box-sizing:border-box}}body{{margin:0}}header{{background:#122b46;color:white;padding:1.4rem max(1rem,calc((100vw - 1160px)/2))}}
header strong{{font-size:1.3rem}}main{{max-width:1200px;margin:auto;padding:1.5rem 1.25rem 3rem}}
h1{{font-size:2rem;margin:.3rem 0}}h2{{font-size:1.25rem;margin:0 0 1rem}}p{{margin:.6rem 0}}
.badge{{display:inline-block;background:#d4e8fa;color:#173d65;border-radius:4px;padding:.2rem .6rem;font-size:.875rem}}
section{{background:white;border:1px solid #cbd5e1;border-radius:8px;padding:1.3rem;margin:1.25rem 0}}
.scroll{{overflow-x:auto}}table{{width:100%;border-collapse:collapse;font-variant-numeric:tabular-nums;font-size:.95rem}}
th,td{{text-align:left;padding:.8rem .6rem;border-bottom:1px solid #dae2ec;white-space:nowrap}}
th{{font-weight:600;color:#36506b}}.notice{{border-left:4px solid #b06605;padding-left:1rem}}.muted{{color:#48617a}}
.overview-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:1rem}}
.metric{{background:#f3f7fb;border-radius:8px;padding:1rem}}.metric h3,.notice h3{{font-size:1rem;margin:.2rem 0}}.metric strong{{font-size:1.8rem;font-variant-numeric:tabular-nums}}.metric p{{font-size:.9rem}}
@media(max-width:600px){{main{{padding:1rem .75rem}}section{{padding:1rem}}h1{{font-size:1.6rem}}}}
</style></head><body><header><strong>Debt Shredder</strong> · Local scenario</header><main>
<span class="badge">{badge} · Estimate</span><h1>{text(scenario.name)}</h1>
{overview}
{explanation}
<p class="muted">Debt window: {when(data['debt_start'])} through {when(data['debt_end'])}</p>
<p class="notice">{text(status)} {text(request_status)}</p>
<p class="muted">Dates shown in {text(data['time_zone'])}. Due-date results cover only the debt window.</p>
<section id="cash-details"><h2>Cash after planned activity</h2><p class="muted">Through {when(data['cash_end'])} · {text(data['cash_status'].replace('_',' '))}</p>
<div class="scroll"><table><thead><tr><th>Account</th><th>Cleared</th><th>Floor</th><th>Reserved</th><th>Committed</th><th>Held</th><th>Above floor</th></tr></thead><tbody>{cash_rows}</tbody></table></div></section>
<section id="payment-details"><h2>Payment requests</h2><p>Minimum requests reserve cash before extras. Each request uses its supplied initiation and credit dates.</p>
<div class="scroll"><table><thead><tr><th>Request</th><th>Debt</th><th>Kind</th><th>Initiated</th><th>Credited</th><th>Requested</th><th>Accepted</th><th>Unfunded</th><th>Result</th></tr></thead><tbody>{payment_rows}</tbody></table></div></section>
<section id="debt-details"><h2>Debt at the end of the debt window</h2><div class="scroll"><table><thead><tr><th>Account</th><th>Posted balance</th><th>Unposted interest</th><th>Missed due dates</th></tr></thead><tbody>{debt_rows}</tbody></table></div></section>
<p class="muted">This is a scenario, not an actual ledger or a payoff quote. Only supplied cash events and payment requests are included.
Future minimum requests are not generated automatically. The cash window may extend beyond the debt window.
Daily interest follows all credits on that day. No bank connection or payment execution is involved.</p>
</main></body></html>'''
