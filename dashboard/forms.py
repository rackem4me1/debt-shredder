"""Plain HTML forms for the deliberately bounded local workflow."""
from html import escape
from dashboard.guidance import HELP
from dashboard.cash_inputs import CASH_ROWS, CADENCE_LABELS, SHORT_MONTH_LABELS
from dashboard.manual import MAX_CARDS

GROUPS = (
    ('Scenario', (('name','Scenario name','text'),('start','First forecast day','date'),('end','Last forecast day','date'),('timezone','Time zone (for example America/Chicago)','text'))),
    ('Checking account', (('cash','Cleared cash ($)','number'),('floor','Minimum cash to protect ($)','number'),('reserved','Reserved cash, in addition to floor ($)','number'))),
    ('Card 1 balance', (('card_name','Card 1 nickname (optional)','text'),('balance','Opening posted balance ($)','number'),('unposted_interest','Opening unposted interest ($)','number'),('apr_percent','Annual interest rate (%)','number'))),
    ('Card 1 statement dates and minimum', (('previous_start','Previous billing cycle started','date'),('previous_close','Previous statement closed','date'),('minimum_due','Current minimum due date','date'),('next_close','Next statement closes','date'),('next_due','Next statement due date','date'),('minimum_original','Original statement minimum ($)','number'),('minimum_remaining','Minimum still unpaid ($)','number'))),
    ('Card 1 planned payment', (('payment_amount','Requested payment ($); enter 0 for no payment','number'),('initiated','Initiation date','date'),('credited','Creditor credit date','date'),('debited','Bank debit date','date'),('settled','Settlement date','date'))),
)


def shell(title, content):
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{escape(title)} · Debt Shredder</title><style>
:root{{font-family:system-ui,sans-serif;font-size:16px;line-height:1.5;color:#172b41;background:#eef2f7}}*{{box-sizing:border-box}}body{{margin:0}}header{{padding:1.25rem;background:#122b46;color:white}}header a{{color:white}}main{{max-width:1050px;padding:1.5rem;margin:auto}}h1{{font-size:1.9rem}}fieldset,section{{min-width:0;background:white;border:1px solid #bdccdc;border-radius:8px;padding:1.25rem;margin:1.5rem 0}}legend{{font-weight:650}}.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(240px,100%),1fr));gap:1rem}}label{{display:block}}small{{display:block;font-size:.875rem;margin-top:.4rem}}input,select,button{{font:inherit;padding:.65rem;width:100%;border:1px solid #849bb2;border-radius:4px}}input[type=checkbox]{{width:auto}}button{{background:#154d80;color:white;cursor:pointer;margin:1rem 0;width:auto}}a{{color:#154d80}}.error{{border-left:4px solid #b52d20;background:#fff1ed;padding:1rem}}.note{{color:#405a73}}li{{margin:.5rem 0}}.scroll{{overflow-x:auto;background:white;border:1px solid #bdccdc;border-radius:8px}}table{{border-collapse:collapse;width:100%;font-variant-numeric:tabular-nums}}th,td{{padding:.85rem;text-align:left;border-bottom:1px solid #bdccdc;min-width:140px}}caption{{text-align:left;font-weight:650;padding:1rem}}[hidden]{{display:none!important}}#setup-progress{{display:flex;flex-wrap:wrap;gap:.5rem;margin:1.5rem 0}}#setup-progress span{{padding:.4rem .7rem;border-radius:20px;background:#dde5ef}}#setup-progress [aria-current]{{background:#154d80;color:white}}#setup-heading:focus{{outline:none}}:focus-visible{{outline:3px solid #c47700;outline-offset:3px}}
</style></head><body><header><a href="/">Debt Shredder</a> · Local scenarios</header><main>{content}</main></body></html>'''


def manual_form(token, values=None, errors=(), *, sample=False):
    values = values or {}
    def input_(key,label,kind,required=True):
        value = escape(str(values.get(key,'')), quote=True)
        attrs = ' min="0" step="any"' if kind == 'number' else ''
        help_text = f'<small id="help-{key}" class="note">{escape(HELP[key])}</small>' if key in HELP else ''
        described = f' aria-describedby="help-{key}"' if key in HELP else ''
        return f'<label for="field-{key}">{escape(label)}</label><input id="field-{key}" {"required" if required else ""} name="{key}" type="{kind}" value="{value}"{attrs}{described}>{help_text}'
    groups = ''.join(f'<fieldset data-setup-step="{(0,0,1,1,3)[index]}"><legend>{escape(title)}</legend><div class="grid">'+
                     ''.join('<div>'+input_(*field,required=field[0]!='card_name')+'</div>' for field in fields)+'</div></fieldset>' for index,(title,fields) in enumerate(GROUPS))
    def select(key,label,options,required=True):
        choices='<option value="">Choose…</option>'+''.join(f'<option value="{v}"'+(' selected' if values.get(key)==v else '')+f'>{escape(t)}</option>' for v,t in options)
        return f'<label>{label}<select {"required" if required else ""} name="{key}">{choices}</select></label>'
    day_choice=select('day_count','Interest day count',(('actual_365_fixed','Actual days / 365'),('actual_366','Actual days / 366'),('actual_actual','Actual days / days in year')))
    choices=select('payment_kind','Payment request type',(('minimum','Minimum'),('extra','Extra')))
    extra_card_html = []
    for i in range(2, MAX_CARDS+1):
        prefix = f'card_{i}_'
        for step, selected_groups, title in [(1,GROUPS[2:4],f'Card {i} (optional)'),(3,GROUPS[4:],f'Card {i} payment')]:
            content = ''.join('<div>'+input_(prefix+key,f'Card {i}: '+('Nickname (optional)' if key=='card_name' else label),kind,False)+'</div>'
                for _, fields in selected_groups for key,label,kind in fields)
            if step==1:
                content += '<div>'+select(prefix+'day_count',f'Card {i}: Interest day count',
                    (('actual_365_fixed','Actual days / 365'),('actual_366','Actual days / 366'),('actual_actual','Actual days / days in year')),False)+'</div>'
            else:
                content += '<div>'+select(prefix+'payment_kind',f'Card {i}: Payment request type',
                    (('minimum','Minimum plus any excess'),('extra','Extra')),False)+'</div>'
            opened = ' open' if any(str(value) for key,value in values.items() if key.startswith(prefix)) else ''
            extra_card_html.append(f'<fieldset data-setup-step="{step}"><details{opened}><summary>{title}</summary><p>Complete this card’s balance, statement and payment fields to include it. Leave all its fields blank to omit it. Enter a payment of 0 if you do not plan to pay this card.</p><div class="grid">'+content+'</div></details></fieldset>')
    extra_cards = ''.join(extra_card_html)
    cash_rows = []
    for i in range(CASH_ROWS):
        prefix = f'cash_{i}_'
        options = '<option value="">Unused row</option>' + ''.join(
            f'<option value="{kind}"' + (' selected' if values.get(prefix+'kind') == kind else '') + f'>{label}</option>'
            for kind, label in [('income', 'Income'), ('expense', 'Bill / expense')])
        row = f'<div><label>Income or bill {i+1}<select name="{prefix}kind">{options}</select></label></div>'
        row += '<div>'+input_(prefix+'label', f'Row {i+1} description', 'text', False)+'</div>'
        row += '<div>'+input_(prefix+'amount', f'Row {i+1} amount ($)', 'number', False)+'</div>'
        row += '<div>'+input_(prefix+'date', f'Row {i+1} cash date', 'date', False)+'</div>'
        for field, label, options in [
            ('cadence', f'Row {i+1} repeats', CADENCE_LABELS),
            ('short_month_rule', f'Row {i+1} short-month handling', {'':'Only for monthly entries'} | SHORT_MONTH_LABELS)]:
            selected = values.get(prefix+field, 'once' if field == 'cadence' else '')
            options_html = ''.join(f'<option value="{key}"'+(' selected' if selected == key else '')+f'>{escape(text)}</option>' for key,text in options.items())
            row += f'<div><label>{label}<select name="{prefix}{field}">{options_html}</select></label></div>'
        row += '<div>'+input_(prefix+'until', f'Row {i+1} stop date (optional, inclusive)', 'date', False)+'</div>'
        cash_rows.append('<details'+(' open' if any(values.get(prefix+f) for f in ('kind','label','amount','date','until','short_month_rule')) or values.get(prefix+'cadence','once') not in ('','once') else '')+f'><summary>Income or bill {i+1}'+(' — '+escape(str(values.get(prefix+'label',''))) if values.get(prefix+'label') else ' (optional)')+'</summary><div class="grid">'+row+'</div></details><hr>')
    cash_html = '<fieldset data-setup-step="2"><legend>Upcoming income and bills (optional)</legend><p>Add up to six income or bill schedules. For income, use the date funds are cleared and available. For bills, use the bank withdrawal date. Choose once, weekly, every two weeks or monthly. The cash date is the first occurrence; monthly entries repeat on that day number and require a choice for shorter months. Leave the stop date blank to repeat through this cash forecast. Weekends and holidays do not move dates. Leave unused rows blank with repeats set to Once.</p><p>Include known activity through the cash forecast: at least 90 days from the first day, or 90 days after payment initiation when a payment is requested, extended through settlement if later. Dates beyond that forecast are rejected. Same-day entries are modeled together at midnight; use a later income date if funds will not be available for that day’s payment.</p><p>Do not enter the planned card payment again as a bill. Opening cleared cash is before first-day entries. Reserved cash stays protected even after a bill is paid; this form does not release earmarked savings.</p>' + ''.join(cash_rows) + '</fieldset>'
    error_html='<div role="alert" class="error"><strong>Please correct these inputs:</strong><ul>'+''.join(f'<li>{escape(str(e))}</li>' for e in errors)+'</ul></div>' if errors else ''
    action = '/preview-example' if sample else '/preview'
    practice = '<section><h2>Practice mode — made-up numbers</h2><p>These January 2026 dates are intentional. Change a value to explore, but do not use this example as your real account information. Anything saved here stays labeled as an example.</p></section>' if sample else '<p><a href="/practice">Practice with prefilled example numbers first</a></p>'
    return shell('Practice scenario' if sample else 'New scenario',f'''<h1>Try a payment scenario</h1><p class="note">A scenario is a saved “what if.” Start with your balances, propose a payment, and see what changes. You can adjust a copy later.</p><p>One checking account shared by up to three ordinary cards, with one proposed payment per card. The first card below is Card 1; additional cards are optional. Enter estimates explicitly; nothing is sent to a bank.</p>
<p class="note">This form models simple daily interest with no active grace period. The shared window must begin after every card’s previous statement close and finish before every card’s next close. Only the income and bills you enter are included. No new card purchases, fees or future minimum payments are generated. Use the shared-cash example to explore multiple accounts.</p>
{practice}{error_html}
<nav id="setup-progress" aria-label="Setup progress" hidden></nav>
<h2 id="setup-heading" tabindex="-1" hidden></h2><p id="setup-hint" class="note" hidden></p>
<form id="scenario-setup" method="post" action="{action}"><input type="hidden" name="token" value="{escape(token,quote=True)}">{groups}{extra_cards}{cash_html}
<fieldset data-setup-step="1"><legend>Card 1 interest terms</legend>{day_choice}<p class="note">The day-count rule controls daily interest; check your account terms rather than guessing.</p></fieldset>
<fieldset data-setup-step="3"><legend>Review the assumptions</legend><div class="grid">{choices}</div><p class="note">The day-count rule controls the daily interest divisor; check the account terms rather than guessing. With multiple cards, “Minimum” reserves the requested portion of each statement minimum before any excess. Extra requests follow. Within each group, earlier initiation dates come first; ties use Card 1, then Card 2, then Card 3. This is a processing order, not an optimized payoff recommendation. Requested amounts below a minimum can still leave it unpaid.</p><p>Dates use midnight in the supplied time zone. All creditor credits happen before daily interest. This form supports credit on or before bank debit, followed by settlement. Opening unposted interest is through the day before the forecast starts.</p>
<label><input required type="checkbox" name="scope" value="confirmed" {'checked' if values.get('scope')=='confirmed' else ''}> I want this limited scenario: simple daily interest, no grace, no promotions, only the cash activity entered here, and no pending opening transactions. These inputs are estimates.</label></fieldset>
<div id="setup-navigation" hidden><button type="button" id="setup-back">Back</button> <button type="button" id="setup-next">Continue</button> <button type="button" id="setup-all">Show all fields</button></div>
<button id="setup-preview" type="submit">Preview dates and payment</button><p>Preview first, then save a separate local scenario. Existing scenarios are never overwritten.</p></form><script src="/setup.js" defer></script>''')


def validation_messages(errors):
    labels = {key: label for _,fields in GROUPS for key,label,_ in fields}
    base_labels = dict(labels)
    base_labels.update(day_count='Interest day count',payment_kind='Payment request type')
    for i in range(2,MAX_CARDS+1):
        labels.update({f'card_{i}_{key}':f'Card {i}: {label}' for key,label in base_labels.items()})
    labels.update(additional_cards='Additional card',day_count='Interest day count',payment_kind='Payment request type',scope='Scenario acknowledgment',cash_events='Upcoming income and bills')
    messages=[]
    for error in errors:
        location=error['loc']
        label=labels.get(location[0], 'Input') if location else ''
        message=error['msg'].removeprefix('Value error, ')
        messages.append((label+': ' if label else '')+message)
    return messages
