"""Read-only review of supported manual-form scenarios, including practice copies."""
from html import escape
from datetime import date
from dashboard.forms import shell, GROUPS
from dashboard.guidance import HELP
from dashboard.manual import editable_inputs, MAX_CARDS
from dashboard.cash_review import cash_review


def render_inputs(scenario):
    values = editable_inputs(scenario)
    groups = []
    first_has_payment = any(r.debt_account_id==scenario.debts[0].account.account_id for r in scenario.requests)
    for heading, fields in GROUPS:
        rows = []
        for key, label, kind in fields:
            value = str(values[key])
            if kind=='date':value=date.fromisoformat(value).strftime('%b %d, %Y')
            if key in ('initiated','credited','debited','settled') and not first_has_payment:
                value = 'Not used — no payment requested'
            help_text = '<br><small class="note">'+escape(HELP[key])+'</small>' if key in HELP else ''
            rows.append('<tr><th scope="row">'+escape(label)+help_text+'</th><td>'+escape(value)+'</td></tr>')
        groups.append('<section><h2>'+escape(heading)+'</h2><div class="scroll"><table><tbody>'+''.join(rows)+'</tbody></table></div></section>')
    for i, debt in enumerate(scenario.debts[1:],2):
        rows=[]
        has_payment=any(r.debt_account_id==debt.account.account_id for r in scenario.requests)
        fields=[field for _,group in GROUPS[2:] for field in group]+[('day_count','Interest day count','text'),('payment_kind','Payment request type','text')]
        for key,label,kind_ in fields:
            if key=='card_name':label='Nickname (optional)'
            value=str(values[f'card_{i}_{key}'])
            if kind_=='date':value=date.fromisoformat(value).strftime('%b %d, %Y')
            if key in ('initiated','credited','debited','settled','payment_kind') and not has_payment:
                value='Not used — no payment requested'
            rows.append('<tr><th>'+escape(label)+'</th><td>'+escape(value)+'</td></tr>')
        groups.append(f'<section><h2>Card {i}: balances, terms and payment</h2><div class="scroll"><table><tbody>'+''.join(rows)+'</tbody></table></div></section>')
    groups.append(cash_review(scenario))
    day_count = {'actual_365_fixed':'Actual days / 365','actual_366':'Actual days / 366','actual_actual':'Actual days / days in year'}[values['day_count']]
    kind = values['payment_kind'].title() if first_has_payment else 'Not used — no payment requested'
    origin = 'Made-up practice data' if scenario.origin=='synthetic_demo' else 'Manually entered estimates'
    return shell('Inputs and assumptions',f'''<h1>Inputs behind {escape(scenario.name)}</h1><p>{origin}. This page only reads the saved scenario.</p>
<p><a href="/">Back to saved scenarios</a></p>{''.join(groups)}
<section><h2>Calculation assumptions</h2><ul><li>Simple daily interest; no active grace period or promotional terms.</li>
<li>Interest day count: {escape(day_count)}.</li><li>Payment request type: {escape(kind)}.</li>
<li>Events use midnight in {escape(values['timezone'])}. All creditor credits happen before daily interest.</li>
<li>The forecast ends before the next statement close. No future minimum formula or statement interest posting is applied.</li>
<li>Only listed cash occurrences are included. Repeating schedules expand only within the cash forecast; weekends and holidays are not adjusted. No new card purchases, fees or pending opening transactions. Same-day cash events are modeled together at midnight.</li>
<li>Floor and reserved cash are separate protections in the same physical account. Paying a bill does not release reserved cash.</li></ul>
<p>These are the assumptions this limited form can represent. They are not a claim that your issuer follows every one of them. Unknown real terms need to be checked before using a real-account scenario.</p></section>''')
