"""Small forms for finishing an existing account setup's payoff inputs."""
from dashboard import setup_plan as plan
from dashboard.payoff_setup import input_field,choice
from dashboard.simple_view import page
from dashboard.report import text,money
from SCHEMA import DayCountConvention,RoundingMode,SemimonthlyShortMonthRule


def controls(w,p,token):
    return ''.join('<input type="hidden" name="'+k+'" value="'+text(v)+'">' for k,v in {'token':token,'fingerprint':plan.context(w,p)}.items())


def balances_form(w,p,identifier,token,values=None,error=''):
    sections=[]
    for a in plan.balance_accounts(w,p):
        loan_label='Remaining principal ($)' if a.balance_type=='principal' else 'Lender balance ($; balance type still needs review)'
        labels={'balance':'Balance ($)' if a.kind!='loan' else loan_label,'balance_date':'Balance reporting date','floor':'Cash cushion ($)','reserved':'Other reserved money ($)'}
        inputs=[]
        for k in plan.balance_fields(a):
            key=a.account_id+'__'+k
            v=(a.model_dump(mode='json')[k] if values is None else values.get(key,''))
            kind='date' if k=='balance_date' else 'number'
            extra=(' step="0.01"'+(' min="0"' if k!='balance' or a.kind in ('card','loan') else '')) if kind=='number' else ''
            inputs.append('<label>'+labels[k]+'<input name="'+key+'" type="'+kind+'" value="'+text('' if v is None else v)+'"'+extra+'></label>')
        index=next(i for i,item in enumerate(w.accounts) if item.account_id==a.account_id)
        links='<p><a href="/setup/'+identifier+'/account/'+str(index)+'">Review full account details</a>'
        if a.kind in ('card','loan'):links+=' · <a href="/setup/'+identifier+'/plan/terms/'+a.account_id+'">Review accrued interest and repayment terms</a>'
        sections.append('<section><h2>'+text(a.name)+'</h2><div class="grid">'+''.join(inputs)+'</div>'+links+'</p></section>')
    body='<p>Update only the figures you have checked. Blank means unknown; explicit 0 means a known zero. Rates, payment terms, account names and notes stay saved. For a loan, use the balance type recorded in its account details; do not substitute a lender payoff total for principal.</p><p>Each included balance must eventually match the common starting date. Saving here does not advance that date, mark a bill paid, or add a paycheck. Cash cushions and other reserves are separate amounts.</p><p>After a payment or new statement, also review unpaid minimums, due dates and accrued interest using the links below. Changing a balance does not adjust those figures or an existing promotional amount.</p>'
    if not p.settings.primary:body+='<p class="banner warning">Choose your everyday spending account in forecast settings to include its bank balance here. Unused bank accounts are left outside this form.</p>'
    body+='<form method="post" action="/setup/'+identifier+'/plan/balances">'+controls(w,p,token)+''.join(sections)+'<button>Save starting balances</button></form>'
    return wrapper('Update starting balances',body,identifier,error,practice=w.origin=='practice')


def wrapper(title,body,identifier,error='',practice=False):
    return page(title,'<div class="hero">'+('<span class="sample">Practice setup — sample inputs</span>' if practice else '')+'<h1>'+text(title)+'</h1><p>Continue from your saved accounts. Blank means unknown; zero means a known zero.</p></div>'+('<p class="banner warning" role="alert">'+text(error)+'</p>' if error else '')+body+'<p><a href="/setup/'+identifier+'/plan">Back to my plan review</a> · <a href="/setup/'+identifier+'">My accounts</a></p>')


def settings_form(w,p,identifier,token,values=None,error=''):
    v=p.settings.model_dump(mode='json') if values is None else values
    banks=[('', 'Choose an account')]+[(a.account_id,a.name) for a in w.accounts if a.kind in ('checking','savings')]
    fields=''.join(input_field(k,label,v,kind) for k,label,kind in (('balance_date','Common balance date (after that day’s included transactions)','date'),('end','Forecast through','date'),('timezone','Time zone, e.g. America/Chicago','text'),('target','Shared debt payment target per round ($)','number'),('first_payment','First payment initiation date','date'),('payment_time','Payment initiation time (local)','time')))
    fields+=choice('primary','Primary spending account',banks,v)+choice('cadence','How often to make a shared payment round?',(('', 'Choose frequency'),('weekly','Weekly'),('biweekly','Every two weeks'),('monthly','Monthly')),v)
    fields+=''.join(input_field(k,label,v) for k,label in (('credit_days','Creditor credit delay (calendar days)'),('debit_days','Bank debit delay (calendar days)'),('settlement_days','Payment settlement delay (calendar days)')))
    fields+=choice('short_month','When a monthly date does not exist', (('', 'Choose handling'),('clamp_to_last_day_of_month','Use that month’s last day'),('roll_to_next_month_first_day','Use the first day of the next month')),v)
    fields+=choice('pending','Any pending debits, holds or transfers crossing the starting date?',(('unknown','Not checked yet'),('none','No — opening balances are reconciled'),('present','Yes — needs reconciliation first')),v)
    fields+=choice('reviewed','Have you reviewed the assumptions below?',(('no','Not yet — save my progress'),('yes','Yes — use these inputs as an estimate')),v)
    body='<form method="post" action="/setup/'+identifier+'/plan/settings">'+controls(w,p,token)+'<section><div class="grid">'+fields+'</div><p>The forecast begins the morning AFTER the common balance date. Every included account balance must be reconciled to that date. Income and transfers already reflected in those balances must not be entered again.</p><p>Future rates and monthly statement/installment patterns remain fixed estimates. Calendar-day delays do not adjust for bank holidays. Only the income, living costs and transfers you include will repeat, through the cash-check horizon (including its 90-day tail). Review all forward costs; debt minimums are calculated separately and must not also be entered as bills. No new borrowing, promotional conversion, fees or rate changes are invented.</p><button>Save forecast settings</button></section></form>'
    return wrapper('Dates and payment budget',body,identifier,error,practice=w.origin=='practice')


def terms_form(w,p,identifier,account_id,token,values=None,error=''):
    a=next(a for a in w.accounts if a.account_id==account_id);t=plan.term_for(p,account_id)
    v=t.model_dump(mode='json') if values is None else values
    day=(('', 'Choose the contract’s day count'),)+tuple((x.value,y) for x,y in ((DayCountConvention.ACTUAL_365,'Actual days / 365'),(DayCountConvention.ACTUAL_366,'Actual days / 366'),(DayCountConvention.ACTUAL_ACTUAL,'Actual days / days in year')))
    rounding=(('', 'Choose the contract’s rounding'),)+tuple((x.value,x.name.replace('_',' ').title()) for x in RoundingMode)
    common=choice('day_count','Interest day count',day,v)+choice('rounding','Interest rounding',rounding,v)+input_field('accrued','Interest already accrued but not posted/paid ($)',v)
    if a.kind=='card':
        extra=choice('ordinary','Does this balance contain only ordinary purchases with no grace or promotional rate?',(('unknown','Not sure yet'),('yes','Yes'),('no','No — needs separate terms')),v)
        extra+=''.join(input_field(k,label,v,kind) for k,label,kind in (('previous_start','Previous statement period started','date'),('previous_close','Previous statement closed','date'),('next_close','Next statement closes','date'),('next_due','That next statement’s payment due date','date'),('close_day','Future monthly statement close day (1–31)','number'),('due_day','Future monthly due day (1–31, following month)','number'),('original_minimum','Original statement minimum ($)','number'),('minimum_floor','Future minimum dollar floor ($)','number'),('minimum_rate','Future minimum balance percentage (%)','number')))
        note='This entry path supports the smaller of the debt balance and the greater of the dollar floor or the balance percentage plus billed interest. Confirm this matches the card’s minimum formula. The unpaid minimum and current due date already come from your saved account. Unsupported formulas, mixed balance types and promotions need separate review.'
    else:
        extra=input_field('fees','Outstanding fees ($; explicit 0 if none)',v)+input_field('due_day','Monthly installment due day (1–31)',v)+choice('monthly','Are the required installments monthly?',(('unknown','Not sure yet'),('yes','Yes'),('no','No')),v)
        note='The saved account must identify remaining principal, a contractual note rate, simple interest and principal curtailment. Paid-ahead and precomputed loans cannot be converted here. Extra principal does not cancel future monthly installments.'
    body='<form method="post" action="/setup/'+identifier+'/plan/terms/'+account_id+'">'+controls(w,p,token)+'<section><div class="grid">'+common+extra+'</div><p>'+note+'</p><button>Save calculation terms</button></section></form>'
    return wrapper(a.name+': calculation details',body,identifier,error,practice=w.origin=='practice')


def flow_form(w,p,identifier,f,token,values=None,error=''):
    v=f.model_dump(mode='json') if values is None else values
    banks=[('', 'Choose a bank account')]+[(a.account_id,a.name) for a in w.accounts if a.kind in ('checking','savings')]
    fields=input_field('name','Description',v,'text')+input_field('amount','Amount ($)',v)+input_field('first_date','First date not already in starting balances',v,'date')
    fields+=choice('cadence','How often?',(('', 'Choose frequency'),('once','Once'),('weekly','Weekly'),('biweekly','Every two weeks'),('monthly','Monthly')),v)+input_field('clock','Time of day (local)',v,'time')+input_field('until','Last occurrence date, if it stops',v,'date')
    if f.kind!='income':fields+=choice('source','Paid/transferred from',banks,v)
    if f.kind!='expense':fields+=choice('destination','Received in',banks,v)
    if f.kind in ('transfer','contribution'):
        fields+=''.join(input_field(k,label,v) for k,label in (('debit_days','Debit delay (calendar days)'),('credit_days','Arrival delay (calendar days)'),('settlement_days','Spendable/settled delay (calendar days)')))
    fields+=choice('include','Use this event in the estimate?',(('review','Still reviewing'),('yes','Include it'),('no','Leave it out — not outstanding/in this plan')),v)
    fields+='<label>Notes<textarea name="notes" maxlength="2000" rows="3" style="width:100%">'+text(v.get('notes',''))+'</textarea></label>'
    label={'income':'Income','expense':'Living cost / bill','transfer':'Internal transfer','contribution':'Transfer into a reserved fund'}[f.kind]
    note='Enter living costs paid from bank accounts, not debt payments or new card charges. Set an old paid bill to “Leave it out” rather than deducting it again. Transfers are internal and never count as income or spending. A reserved-fund transfer protects the money in its destination account.'
    return wrapper(label+' details','<form method="post" action="/setup/'+identifier+'/plan/flow/'+f.flow_id+'">'+controls(w,p,token)+'<section><div class="grid">'+fields+'</div><p>'+note+'</p><button>Save this cash event</button></section></form>',identifier,error)


def balance_review(w,p,identifier):
    """Show dated source facts without refreshing them or treating unknown as zero."""
    participating=plan.participating_banks(w,p)
    included=[];outside=[]
    for index,a in enumerate(w.accounts):
        bank=a.kind in ('checking','savings')
        unused=bank and a.account_id not in participating
        status=('Outside this estimate' if unused else 'Balance needed' if a.balance is None
                else 'Date needed' if a.balance_date is None
                else 'Choose the common date first' if p.settings.balance_date is None
                else 'Update or reconcile date' if a.balance_date!=p.settings.balance_date
                else 'Known zero debt — no payments' if not bank and a.balance==0
                else 'Date matches the starting date')
        row='<tr><th scope="row">'+text(a.name)+'</th><td>'+(money(a.balance) if a.balance is not None else 'Unknown')+'</td><td>'+(text(a.balance_date.strftime('%b %d, %Y')) if a.balance_date else 'Unknown')+'</td><td>'+status+'</td><td><a href="/setup/'+identifier+'/account/'+str(index)+'">Edit '+text(a.name)+'</a></td></tr>'
        (outside if unused else included).append(row)
    def table(rows):
        return '<div style="overflow-x:auto"><table><caption>Saved balances and their reporting dates</caption><thead><tr><th scope="col">Account</th><th scope="col">Balance</th><th scope="col">Recorded for</th><th scope="col">Review</th><th scope="col">Update</th></tr></thead><tbody>'+''.join(rows)+'</tbody></table></div>'
    opening=p.settings.balance_date
    return '<section><h2>Starting balances</h2><p><a class="action secondary" href="/setup/'+identifier+'/plan/balances">Update balances together</a></p><p>'+('Common starting date: '+text(opening.strftime('%b %d, %Y'))+'.' if opening else 'Choose a common starting date in Dates and payment budget.')+' These are saved entries, not live bank balances. When your numbers change, update each included balance and its date, then review upcoming income and bills. Changing the forecast date does not refresh balances or mark bills paid.</p>'+table(included)+('<details><summary>Accounts outside this estimate</summary>'+table(outside)+'</details>' if outside else '')+'</section>'


def overview(w,p,identifier,token,error=''):
    reasons=plan.missing(w,p)
    def href(where):return '/setup/'+identifier if where=='accounts' else '/setup/'+identifier+'/'+where if where.startswith('account/') else '/setup/'+identifier+'/plan/'+where
    cash_warning='<p class="banner warning">No repeating living costs have been included. A longer payoff forecast may omit future bills unless you enter those dates or schedules.</p>' if not any(f.kind=='expense' and f.include=='yes' and f.cadence!='once' for f in p.flows) else ''
    checks=''.join('<li>'+text(label)+' <a href="'+href(where)+'">Review</a></li>' for label,where in reasons)
    debts=''.join('<li>'+text(a.name)+' <a href="/setup/'+identifier+'/plan/terms/'+a.account_id+'">Calculation details</a> · <a href="/setup/'+identifier+'/account/'+str(i)+'">Saved balance and rate</a></li>' for i,a in enumerate(w.accounts) if a.kind in ('card','loan'))
    kinds={'income':'Income','expense':'Living cost / bill','transfer':'Internal transfer','contribution':'Reserved-fund transfer'}
    statuses={'yes':'Included','no':'Left out','review':'Needs review'}
    banks={a.account_id:a.name for a in w.accounts if a.kind in ('checking','savings')}
    def flow_details(f):
        cadence={'once':'One time','weekly':'Weekly','biweekly':'Every two weeks','monthly':'Monthly'}
        schedule=(f.first_date.strftime('%b %d, %Y') if f.first_date else 'Date not set')+' · '+cadence.get(f.cadence,'Frequency not set')
        if f.until:schedule+=' · Stops '+f.until.strftime('%b %d, %Y')
        if f.kind=='income':route='Into '+banks.get(f.destination,'account not chosen')
        elif f.kind=='expense':route='From '+banks.get(f.source,'account not chosen')
        else:route=banks.get(f.source,'Source not chosen')+' → '+banks.get(f.destination,'destination not chosen')
        return '<small>'+text(schedule)+' · '+text(route)+'</small>'
    flows=''.join('<li><a href="/setup/'+identifier+'/plan/flow/'+f.flow_id+'">'+text(f.name)+'</a><small>'+text(kinds[f.kind])+' · '+(money(f.amount) if f.amount is not None else 'Amount unknown')+' · '+text(statuses[f.include])+'</small>'+flow_details(f)+'</li>' for f in p.flows)
    add='<form method="post" action="/setup/'+identifier+'/plan/add-flow">'+controls(w,p,token)+'<div class="actions">'+''.join('<button name="kind" value="'+k+'">Add '+label+'</button>' for k,label in (('income','income'),('expense','living cost / bill'),('transfer','internal transfer'),('contribution','reserved-fund transfer')))+'</div></form>'
    import_form='<form method="post" action="/setup/'+identifier+'/plan/import-cash">'+controls(w,p,token)+'<button class="action secondary">Bring in saved paycheck and bill amounts for review</button></form><p>This copies dated estimates for review only. It does not assume that a bill is unpaid or that a paycheck repeats. No debt payment is duplicated as a living cost.</p>'
    if w.origin=='practice':import_form='<p>Practice setups do not import personal paycheck or bill records.</p>'
    calculate='<form method="post" action="/setup/'+identifier+'/plan/preview">'+controls(w,p,token)+'<button>Calculate my payoff preview</button></form>' if not reasons else '<p>Finish the required checks above to calculate. Credit limits, bank APY and autopay settings do not block calculation.</p>'
    outside=[a.name for a in w.accounts if a.kind in ('checking','savings') and a.account_id not in plan.participating_banks(w,p)]
    outside_note=('<p>First, choose the bank account you use for everyday spending. Other accounts will be included when you assign them to a payment, income, bill or transfer.</p>' if not p.settings.primary else '<p>Money in these unused accounts will stay outside the payment plan: '+text(', '.join(outside))+'.</p>' if outside else '<p>Payments use the bank accounts you select. Money stays attached to each account.</p>')
    next_step=('<section><h2>Your next step</h2><p>'+text(reasons[0][0])+'</p><a class="action" href="'+href(reasons[0][1])+'">Continue this step</a><p>You can save partway through and return later.</p></section>' if reasons else '')
    body=next_step+outside_note+'<section><h2>1. Starting date and shared payment target</h2><a class="action" href="/setup/'+identifier+'/plan/settings">Review dates and budget</a></section>'+balance_review(w,p,identifier)+'<section><h2>2. Income, living costs and transfers</h2><ul class="plan-list">'+(flows or '<li>No cash events entered yet.</li>')+'</ul>'+add+import_form+cash_warning+'</section><section><h2>3. Repayment terms</h2><ul>'+debts+'</ul></section><section><h2>Ready to calculate?</h2>'+('<details><summary>'+'Review the remaining required information</summary><ul>'+checks+'</ul></details>' if reasons else '<p>The required fields are filled. The engine will validate the complete calendars, cash and contract relationships before showing a result.</p>')+calculate+'</section>'
    body+='<section><h2>Keep a complete backup</h2><p>Save your account entries, forecast settings, repayment terms, income, bills and transfers together. This contains private financial information. It does not include other setups, histories, calculated runs or real bank transactions.</p><p><a href="/setup/'+identifier+'/complete-backup.json" download="debt-shredder-complete-setup.json">Download complete setup backup</a> · <a href="/setup/restore">Restore as a separate copy</a></p></section>'
    return wrapper('Turn my accounts into a payment plan',body,identifier,error,practice=w.origin=='practice')
