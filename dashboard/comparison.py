"""Read-only scenario comparisons. No optimizer or recommendation logic."""
from decimal import Decimal
from dashboard.forms import shell
from dashboard.report import summary, text, money, readable_time
from dashboard.scenarios import Scenario
from engine.common import decimal_context


@decimal_context
def compare(left: Scenario, right: Scenario) -> dict:
    a, b = summary(left), summary(right)
    same_accounts = ({r['account_id'] for r in a['cash']} == {r['account_id'] for r in b['cash']}
                     and {r['account_id'] for r in a['debts']} == {r['account_id'] for r in b['debts']})
    same_windows = all(a[key] == b[key] for key in ('debt_start', 'debt_end', 'cash_end'))
    comparable = same_accounts and same_windows
    warnings = []
    if not same_accounts:
        warnings.append('The scenarios contain different accounts. Differences are hidden because the totals cover different accounts.')
    if not same_windows:
        warnings.append('The scenarios cover different time windows. Differences are hidden; the ending amounts are not measured over the same period.')
    if left.origin != right.origin:
        warnings.append('One scenario uses example data and the other uses manually entered data.')
    groups = [('Starting cash and protections', left.openings, right.openings),
              ('Card balances, terms and statement dates', left.debts, right.debts),
              ('Other planned cash activity', left.cash_plans, right.cash_plans),
              ('Income and bill schedule settings', left.manual_cash_schedules, right.manual_cash_schedules),
              ('Requested payments and timing', left.requests, right.requests),
              ('Forecast dates', (left.start, left.end), (right.start, right.end))]
    changes = [label for label, x, y in groups if x != y]
    def total(data, collection, field):
        return sum((Decimal(row[field]) for row in data[collection]), Decimal(0))
    definitions = [
        ('Payments requested', 'decisions', 'requested'),
        ('Payments applied', 'decisions', 'accepted'),
        ('Requested amount not funded', 'decisions', 'unmet'),
        ('Cash left in accounts', 'cash', 'cleared'),
        ('Protected minimum cash', 'cash', 'floor'),
        ('Reserved cash', 'cash', 'reserved'),
        ('Cash committed to pending activity', 'cash', 'committed'),
        ('Cash held until settlement', 'cash', 'held'),
        ('Posted card debt', 'debts', 'posted_balance'),
        ('Interest awaiting statement posting', 'debts', 'unposted_interest'),
    ]
    rows = []
    for label, collection, field in definitions:
        x, y = total(a, collection, field), total(b, collection, field)
        rows.append({'label': label, 'left': str(x), 'right': str(y),
                     'difference': str(y - x) if comparable else None})
    return {'left': a, 'right': b, 'rows': rows, 'comparable': comparable,
            'changes': changes, 'warnings': warnings}


@decimal_context
def render_comparison(left: Scenario, right: Scenario) -> str:
    data = compare(left, right)
    def currency(value):
        return text(money(Decimal(value)))
    def delta(value):
        if value is None:
            return 'Different scope'
        amount = Decimal(value)
        if amount == 0:
            return 'No change'
        if abs(amount)<Decimal('.01'):
            return 'Less than $0.01'+(' more' if amount>0 else ' less')
        return currency(abs(amount)) + (' more' if amount > 0 else ' less')
    rows = ''.join('<tr><th scope="row">'+text(row['label'])+'</th><td>'+currency(row['left'])+
                   '</td><td>'+currency(row['right'])+'</td><td>'+delta(row['difference'])+'</td></tr>'
                   for row in data['rows'])
    def status(record):
        missed = record['missed_minimum_account_ids']
        return ('Missed due dates: ' + ', '.join(missed)) if missed else 'No missed due dates in this window'
    rows += '<tr><th scope="row">Minimum payment due dates</th><td>'+text(status(data['left']))+'</td><td>'+text(status(data['right']))+'</td><td>Check each window</td></tr>'
    rows += '<tr><th scope="row">Cash condition</th><td>'+text(data['left']['cash_status'].replace('_',' '))+'</td><td>'+text(data['right']['cash_status'].replace('_',' '))+'</td><td>Across each cash window</td></tr>'
    warnings = ''.join('<p class="error">'+text(message)+'</p>' for message in data['warnings'])
    changes = ('<ul>'+''.join('<li>'+text(label)+'</li>' for label in data['changes'])+'</ul>'
               if data['changes'] else '<p>The financial inputs are identical. Only labels or source markings may differ.</p>')
    windows = ''.join(f'<section><h2>{text(record["name"])}</h2><p>{"Synthetic example" if record["origin"]=="synthetic_demo" else "Manual estimates"}</p><p>Debt: {text(readable_time(record["debt_start"],record["time_zone"]))} through {text(readable_time(record["debt_end"],record["time_zone"]))}</p><p>Cash through {text(readable_time(record["cash_end"],record["time_zone"]))}</p></section>' for record in (data['left'],data['right']))
    return shell('Compare scenarios',f'''<h1>Compare two what-ifs</h1><p><a href="/compare">Choose other scenarios</a> · <a href="/">Back to saved scenarios</a></p>
<p>Read the right-hand scenario as a change from the left. “More” and “less” describe amounts, not which plan you should choose.</p>{warnings}
<div class="scroll"><table><caption>Estimated results</caption><thead><tr><th scope="col">Measure</th><th scope="col">{text(left.name)}</th><th scope="col">{text(right.name)}</th><th scope="col">Right compared with left</th></tr></thead><tbody>{rows}</tbody></table></div>
<section><h2>What changed in the inputs?</h2>{changes}<p>When several inputs change, the result cannot be attributed to the payment amount alone.</p></section>
<div class="grid">{windows}</div><p>Cash means cleared money in the listed accounts; it excludes money in transit. Protected, reserved, committed and held amounts are not all available to spend. Interest shown here has not yet been added to a statement. Posted debt may already include earlier posted interest.</p>
<p>Only supplied activity is included. A longer cash window does not add future card minimums automatically. These estimates do not move money or identify a best plan.</p>''')


def selector(choices, selected_left='', selected_right='', message=''):
    def options(selected):
        return '<option value="">Choose a saved scenario…</option>'+''.join(
            f'<option value="{text(id_)}"'+(' selected' if selected==id_ else '')+f'>{text(name)} · {text(id_[:8])}</option>'
            for id_, name in choices)
    form = f'''<form method="get" action="/compare"><div class="grid"><label>Starting scenario<select required name="left">{options(selected_left)}</select></label><label>Compare with<select required name="right">{options(selected_right)}</select></label></div><button>Compare saved scenarios</button></form>''' if choices else '<p>Save a scenario first, then use “Adjust a copy” to create another version.</p>'
    return shell('Choose scenarios','<h1>Compare saved scenarios</h1><p>Pick two saved what-ifs. Nothing will be changed or saved by comparing them.</p>'+('<p role="alert" class="error">'+text(message)+'</p>' if message else '')+form+'<p><a href="/compare-example">Try a comparison with example data</a> · <a href="/">Back home</a></p>')
