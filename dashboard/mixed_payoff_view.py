"""Plain-language views over the shared card/loan payoff engine."""
import re
from zoneinfo import ZoneInfo
from engine.common import reconstruct,ZERO,decimal_context
from engine.mixed_payoff import compare_mixed_payoff
from dashboard.simple_view import page,tile
from dashboard.report import text,money

NAMES={'high-rate':'24% sample card','small-balance':'12% sample card','sample-loan':'12% sample loan'}
STRATEGIES={'highest_interest_first':'Highest interest first','smallest_balance_first':'Smallest balance first'}


def sample(query):
    from demo_payoff import mixed_example
    if set(query)-{'target'} or len(query.get('target',[]))>1:raise ValueError('Supply one payment target only')
    target=query.get('target',['300'])[0]
    if not re.fullmatch(r'\d{1,7}(?:\.\d{1,2})?',target):raise ValueError('Use a nonnegative payment amount with at most two decimal places')
    return reconstruct(mixed_example(),payment_target=target)


@decimal_context
def results_section(value,comparison,sample_numbers=False,account_labels=None):
    labels={c.account.account_id:c.account.issuer for c in value.cards}|{l.loan.loan_id:l.loan.servicer for l in value.loans}
    labels.update(account_labels or {})
    def name(key):return NAMES.get(key,labels.get(key,key)) if sample_numbers else labels.get(key,key)
    zones={c.account.account_id:ZoneInfo(c.credit_timezone) for c in value.cards}|{l.loan.loan_id:ZoneInfo(l.timezone_name) for l in value.loans}
    summary='';schedules=''
    for result in comparison.results:
        cash_ok=result.liquidity.status.value=='healthy'
        summary+='<tr>'+''.join('<td>'+text(v)+'</td>' for v in (STRATEGIES[result.strategy],str(result.payoff_date) if result.payoff_date else 'Not reached',
            money(result.total_paid),money(result.interest_total),money(result.remaining_unposted_interest),
            'Met' if result.all_minimums_met else 'Missed minimum','Protected' if cash_ok else 'Shortfall'))+'</tr>'
        rows=''.join('<tr>'+''.join('<td>'+text(v)+'</td>' for v in (p.initiated_at.astimezone(zones[p.account_id]).strftime('%b %d, %Y'),p.credited_at.astimezone(zones[p.account_id]).strftime('%b %d, %Y'),name(p.account_id),labels.get(p.source_account_id,p.source_account_id),
            money(p.minimum_paid),money(p.extra_paid),money(p.total_paid)))+'</tr>' for p in result.payments if p.total_paid or p.minimum_required)
        first_slot=value.slots[0].slot_id
        first_rows=''
        for p in result.payments:
            if p.slot_id!=first_slot or not (p.total_paid or p.minimum_required):continue
            zone=zones[p.account_id]
            first_rows+='<tr>'+''.join('<td>'+text(v)+'</td>' for v in (
                name(p.account_id),labels.get(p.source_account_id,p.source_account_id),
                p.initiated_at.astimezone(zone).strftime('%b %d, %Y at %I:%M %p %Z'),money(p.total_paid),money(p.minimum_required-p.minimum_paid)))+'</tr>'
        first_round=('<h3>First payment round to review</h3><p>These are estimated actions for this strategy. Nothing is scheduled with a bank. Confirm current balances, bills and lender timing before acting.</p><div class="scroll"><table><thead><tr><th>Debt</th><th>Paid from</th><th>Start payment</th><th>Planned amount</th><th>Unfunded requested minimum</th></tr></thead><tbody>'+first_rows+'</tbody></table></div><p>An unfunded requested minimum shows a shortage at this round; the due-date check for the full forecast includes later rounds too.</p>' if first_rows else '<h3>First payment round to review</h3><p>No payment is applied or minimum requested in the first supplied round. Review the dated schedule for later rounds.</p>')
        loan_rows=''.join('<tr>'+''.join('<td>'+text(v)+'</td>' for v in (p.credited_at.astimezone(zones[loan.account_id]).strftime('%b %d, %Y'),name(loan.account_id),money(p.fees_paid),money(p.interest_paid),money(p.principal_paid),money(p.principal_remaining)))+'</tr>' for loan in result.loans for p in loan.projection.payments if p.total_paid)
        cash_rows=''.join('<tr>'+''.join('<td>'+text(v)+'</td>' for v in (labels.get(p.account_id,p.account_id),money(p.cleared),money(p.reserved),money(p.above_floor)))+'</tr>' for p in result.liquidity.points[-1].positions)
        missed=[c.account.account_id+': '+', '.join(map(str,c.missed_due_dates)) for c in result.cards if c.missed_due_dates]
        missed += [l.account_id+': '+', '.join(map(str,l.projection.missed_due_dates)) for l in result.loans if l.projection.missed_due_dates]
        alerts='<p class="banner warning">Missed minimum due dates: '+text('; '.join(missed))+'.</p>' if missed else ''
        if not cash_ok:alerts+='<p class="banner warning">Supplied cash events breach protection. Review the funding inputs before relying on this plan.</p>'
        residual=result.remaining_posted+result.remaining_unposted_interest
        schedules+='<section><h2>'+text(STRATEGIES[result.strategy])+'</h2><p>'+('All supplied debts reached zero.' if result.status=='paid_off' else 'Debt remains at the end of the supplied calendar: '+money(residual)+'. No payoff date is claimed.')+'</p>'+alerts+first_round+'<details><summary>See dated payments</summary><div class="scroll"><table><thead><tr><th>Start payment</th><th>Credited</th><th>Debt</th><th>Paid from</th><th>Minimum portion</th><th>Extra portion</th><th>Total</th></tr></thead><tbody>'+rows+'</tbody></table></div><p>All debts share ONE '+money(value.payment_target)+' target per round, limited by cash available in the named account. Start payment is the initiation date; credited is when the lender applies it. Dates and first-round clocks use each debt’s supplied credit timezone; exact bank-debit and settlement timestamps remain in the downloads.</p></details><details><summary>See loan interest and principal</summary><div class="scroll"><table><thead><tr><th>Credited</th><th>Loan</th><th>Fees</th><th>Interest</th><th>Principal</th><th>Principal left</th></tr></thead><tbody>'+loan_rows+'</tbody></table></div></details><details><summary>See ending cash by account</summary><p>Cash checked through '+text(result.liquidity.end.isoformat())+'.</p><div class="scroll"><table><thead><tr><th>Account</th><th>Cleared cash</th><th>Reserved</th><th>Above floor</th></tr></thead><tbody>'+cash_rows+'</tbody></table></div></details><p>Posted card interest: '+money(result.card_posted_interest)+'. Loan interest paid: '+money(result.loan_interest_paid)+'. Unpaid interest at the end: '+money(result.remaining_unposted_interest)+'. Loan fees paid: '+money(result.loan_fees_paid)+'.</p></section>'
    return '<section><h2>Compare the results</h2><div class="scroll"><table><thead><tr><th>Strategy</th><th>All debt cleared</th><th>Total paid</th><th>Posted/paid interest</th><th>Unpaid interest</th><th>Minimum due dates</th><th>Cash</th></tr></thead><tbody>'+summary+'</tbody></table></div><p>'+text(comparison.comparison_note)+'</p><p>First cover each unpaid minimum. Only then direct extra money toward the highest rate or the smallest current balance. Equal-priority minimums use account ID order when money is short.</p></section>'+schedules


def limits_section():
    return '<details><summary>Dates, assumptions and limits</summary><p>Only supplied dates, income, bills and contract terms are included. Future living costs are covered only to the extent they were entered. Card payoff dates include trailing interest, so they may be later than the last payment. Loan principal, interest and fees must all reach zero. No future fees, purchases or rate changes are inferred.</p><p>Loans require a contractual note rate, daily simple interest, principal curtailment and explicit due dates. Disclosed APR does not replace the note rate. Paid-ahead and precomputed loans are unsupported. Cards require ordinary purchases with lost grace and no promotions. These are estimates, not bank actions or payoff quotes.</p></details>'


def downloads(prefix,query=''):
    return '<section><h2>Keep the calculation files</h2><p>Exact inputs may contain private financial details.</p><div class="actions">'+''.join('<a class="action secondary" href="'+prefix+'/'+file+query+'">'+label+'</a>' for file,label in (
        ('inputs.json','Download exact inputs'),('highest-interest.csv','Download highest-interest schedule'),('smallest-balance.csv','Download smallest-balance schedule')))+'</div></section>'


def render(value,save_section=''):
    comparison=compare_mixed_payoff(value)
    return page('Cards and loan together','<div class="hero"><span class="sample">Sample numbers · One shared budget</span><h1>Cards and a loan. One payoff plan.</h1><p>Two cards owing $1,500 together and a $1,000 simple-interest loan. Both strategies use the same money, minimum due dates and cash protections.</p></div><div class="cards">'+tile('Starting debt','$2,500.00','24% and 12% cards; a loan with a 12% note rate.')+tile('One monthly target',money(value.payment_target),'Shared across all three debts. It is not a separate amount for each.')+tile('Keep protected','$150.00','$100 cash floor plus $50 reserved in checking.')+'</div><section><h2>Try a payment target</h2><form action="/mixed-payoff-example" method="get"><label>Monthly amount shared by all debts <input name="target" type="number" min="0" max="9999999" step="0.01" value="'+text(value.payment_target)+'" required></label><button type="submit">Compare payoff plans</button></form><p>Sample income is $1,200 per month and bills are $900. A larger target may be reduced to keep bill money protected.</p></section>'+results_section(value,comparison,True)+save_section+limits_section()+'<p>The sample loan has a 12% note rate and 20% disclosed APR, daily /365 accrual and monthly installments on the 20th. Your actual Avant terms are not assumed.</p>'+downloads('/mixed-payoff-example','?target='+str(value.payment_target))+'<p><a href="/mixed-payoff-runs">Saved combined runs</a> · <a href="/">Home</a></p>')


@decimal_context
def render_saved(run,identifier=None,save_section=''):
    value=run.inputs;comparison=compare_mixed_payoff(value)
    debt=sum((c.account.total_balance() for c in value.cards),ZERO)+sum((l.loan.principal_balance+l.loan.fees_outstanding for l in value.loans),ZERO)
    source_link=('<a href="/setup/'+run.wizard_id+'/plan">Review my plan inputs</a>' if run.wizard_id else '<a href="/mixed-payoff/import">Review another input file</a>')
    return page(run.name,'<div class="hero"><span class="sample">'+('Sample accounts' if run.origin=='synthetic_demo' else 'Supplied-input estimate')+' · '+('Saved calculation' if identifier else 'Review before saving')+'</span><h1>'+text(run.name)+'</h1><p>Captured opening '+text(value.start.strftime('%b %d, %Y'))+'; debt forecast through '+text(value.end.strftime('%b %d, %Y'))+'. This is a retained estimate, not a current bank-balance update.</p></div><div class="cards">'+tile('Opening posted debt',money(debt),'Card balances plus loan principal and outstanding fees; accrued interest is additional.')+tile('Shared target per round',money(value.payment_target),'One target across every supplied debt.')+'</div>'+results_section(value,comparison,run.origin=='synthetic_demo',{v.account_id:v.name for v in run.account_labels})+save_section+limits_section()+(downloads('/mixed-payoff-run/'+identifier) if identifier else '')+'<p><a href="/mixed-payoff-runs">Saved combined runs</a> · '+source_link+' · <a href="/">Home</a></p>')
