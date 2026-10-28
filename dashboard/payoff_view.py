"""Read-only payoff preview inside an existing saved-plan page."""
from zoneinfo import ZoneInfo
from engine.common import CENT, decimal_context
from engine.payoff import PayoffInputs, PaymentFunding, compare_payoff, validate_payoff_inputs
from engine.minimum_forecast import PaymentSlot
from dashboard.report import text, money, card_label
from dashboard.strategies import strategy_fingerprint
from dashboard.simple_view import tile


@decimal_context
def inputs_from_scenario(scenario,target):
    primary=[o for o in scenario.openings if o.primary]
    if len(primary)!=1:raise ValueError('Keep exactly one primary cash account')
    opening=primary[0];routes={}
    if not scenario.requests:
        raise ValueError('This plan has no supplied payment dates. Add explicit payment dates before calculating payoff.')
    timelines={}
    for request in scenario.requests:
        previous_source=routes.setdefault(request.debt_account_id,request.source_account_id)
        if previous_source!=request.source_account_id:
            raise ValueError('A debt uses different funding accounts across payment dates. This preview requires one explicit funding route per debt.')
        timeline=tuple(getattr(request,key) for key in ('initiated_at','credited_at','debited_at','settled_at'))
        previous=timelines.setdefault(request.initiated_at,timeline)
        if previous!=timeline:
            raise ValueError('Cards with the same initiation date have different payment timelines. A shared payoff round needs one explicit timeline; nothing has been merged.')
    ordered=tuple(timelines[k] for k in sorted(timelines))
    if len(scenario.openings)>1 and any(d.account.account_id not in routes for d in scenario.debts):
        raise ValueError('A debt has no saved funding route. Choose its account before calculating a multi-account payoff.')
    slots=tuple(PaymentSlot(slot_id='round-'+str(i+1),**dict(zip(
        ('initiated_at','credited_at','debited_at','settled_at'),timeline))) for i,timeline in enumerate(ordered))
    value=PayoffInputs(start=scenario.start,end=scenario.end,debts=scenario.debts,opening=opening,
        additional_openings=tuple(o for o in scenario.openings if o.account_id!=opening.account_id),
        payment_sources=tuple(PaymentFunding(debt_account_id=d.account.account_id,cash_account_id=routes.get(d.account.account_id,opening.account_id)) for d in scenario.debts),
        cash_plans=scenario.cash_plans,slots=slots,payment_target=target)
    validate_payoff_inputs(value)
    return value


def form_section(scenario,source,token,*,value='',error=''):
    try:inputs=inputs_from_scenario(scenario,'0')
    except (ValueError,ArithmeticError) as exc:
        return '<section id="payoff"><h2>Payoff projection</h2><p>'+text(str(exc))+'</p><p>Your saved plan has not changed. No payoff date has been guessed.</p></section>'
    controls=''.join('<input type="hidden" name="'+key+'" value="'+text(v)+'">' for key,v in
        {'token':token,'fingerprint':strategy_fingerprint(scenario)}.items())
    return '<section id="payoff"><h2>Calculate a payoff schedule</h2><p>Compare highest-interest-first and smallest-balance-first using one shared payment target per supplied date. Minimums come first; bills, cash reserves and saved account terms stay in the calculation.</p>'+('<p class="banner warning" role="alert">'+text(error)+'</p>' if error else '')+\
        '<p>This preview replaces the old requested amounts and account priorities with the two strategies. It uses '+str(len(inputs.slots))+' existing payment date(s), through '+text(scenario.end.date())+'. It does not repeat dates, extend statements or add income. A short date range may end before payoff.</p>'+\
        '<form method="post" action="/payoff-preview/'+source+'">'+controls+'<label for="payoff-target">Total payment target for each date, across all cards ($)</label><input required id="payoff-target" name="payment_target" type="number" min="0" step="0.01" value="'+text(value)+'"><p class="muted">Use an amount you want to test. This is not an extra-payment recommendation; available cash may reduce it.</p><button class="action">Calculate both payoff plans</button></form></section>'


@decimal_context
def result_section(scenario,result):
    names={'highest_interest_first':'Highest interest first','smallest_balance_first':'Smallest balance first'}
    comparison=[];details=[]
    for plan in result.results:
        complete=plan.status=='paid_off'
        date=plan.payoff_date.strftime('%B %d, %Y') if complete else 'Not reached within supplied dates'
        minimum='All modeled minimums met' if plan.all_minimums_met else 'Minimum payment missed or underfunded'
        cash='Protected cash stays covered' if plan.liquidity.status.value=='healthy' else 'Cash shortage exists'
        comparison.append('<tr><th scope="row">'+names[plan.strategy]+'</th><td>'+text(date)+'</td><td>'+money(plan.total_paid)+'</td><td>'+money(plan.posted_interest)+'</td><td>'+text(minimum)+'; '+text(cash)+'</td></tr>')
        rows=[];timing=[]
        zones={d.account.account_id:ZoneInfo(d.credit_timezone) for d in scenario.debts}
        for payment in plan.payments:
            if not payment.total_paid and not payment.minimum_required:continue
            rows.append('<tr>'+''.join('<td>'+text(v)+'</td>' for v in (
                payment.credited_at.astimezone(zones[payment.account_id]).strftime('%b %d, %Y'),
                card_label(scenario,payment.account_id),payment.source_account_id or '',money(payment.minimum_required),
                money(payment.minimum_paid),money(payment.extra_paid),money(payment.total_paid)))+'</tr>')
            timing.append('<tr>'+''.join('<td>'+text(v)+'</td>' for v in (
                card_label(scenario,payment.account_id),payment.initiated_at.isoformat(),payment.credited_at.isoformat(),
                payment.debited_at.isoformat(),payment.settled_at.isoformat()))+'</tr>')
        missed=''.join('<li>'+text(card_label(scenario,debt.account.account_id))+': '+text(', '.join(d.isoformat() for d in debt.missed_due_dates))+'</li>' for debt in plan.debts if debt.missed_due_dates)
        accrued_label='Less than $0.01' if 0<plan.remaining_unposted_interest<CENT else money(plan.remaining_unposted_interest)
        cash_rows=''.join('<tr><td>'+text(p.account_id)+'</td><td>'+money(p.cleared)+'</td><td>'+money(p.reserved)+'</td></tr>' for p in plan.liquidity.points[-1].positions)
        transfers=''.join('<li>'+text(p.source_account_id)+' → '+text(p.destination_account_id)+': '+money(p.amount)+'; sent '+text(p.debited_at.isoformat())+'; available '+text(p.settled_at.isoformat())+'</li>' for p in plan.transfers)
        details.append('<details><summary>'+names[plan.strategy]+' — dated payment schedule</summary><p>'+minimum+'. '+cash+'. Credit dates use each card’s saved time zone.</p><div class="cards">'+tile('Debt still posted',money(plan.remaining_posted),'At the end of the supplied debt dates.')+tile('Interest not yet posted',accrued_label,'Any remaining amount here is still owed.')+'</div>'+('<ul>'+missed+'</ul>' if missed else '')+\
            '<div class="scroll"><table><thead><tr><th>Credited</th><th>Account</th><th>Paid from</th><th>Minimum required</th><th>Minimum paid</th><th>Extra</th><th>Total</th></tr></thead><tbody>'+(''.join(rows) or '<tr><td colspan="7">No positive payments or minimums in the supplied dates.</td></tr>')+'</tbody></table></div><details><summary>Exact payment timing</summary><div class="scroll"><table><thead><tr><th>Account</th><th>Initiate</th><th>Credited</th><th>Debited</th><th>Settled</th></tr></thead><tbody>'+''.join(timing)+'</tbody></table></div></details><h3>Separate cash balances</h3><p>At '+text(plan.liquidity.end.isoformat())+'. Protected money stays in its physical account; these balances are not spending allowances.</p><table><thead><tr><th>Account</th><th>Balance</th><th>Reserved</th></tr></thead><tbody>'+cash_rows+'</tbody></table>'+('<h3>Declared internal transfers</h3><ul>'+transfers+'</ul><p>These are movements of existing cash, not income or expenses. No transfer has been initiated by this app.</p>' if transfers else '')+'</details>')
    winner=names[result.lowest_interest_strategy]+' has the lowest posted interest among these two completed plans.' if result.lowest_interest_strategy else 'No winning plan is claimed. Review unfinished balances, minimums and cash coverage below.'
    return '<section id="payoff-result"><h2>Payoff calculation</h2><p><strong>'+text(winner)+'</strong></p><p>This is a new estimate from the saved opening date, not an update to today’s balances. No money moved and your saved plan is unchanged.</p><div class="scroll"><table><thead><tr><th>Strategy</th><th>Debt-free date</th><th>Total paid</th><th>Interest posted</th><th>Checks</th></tr></thead><tbody>'+''.join(comparison)+'</tbody></table></div><p class="muted">'+text(result.comparison_note)+' A later statement may be needed to clear trailing interest or round its last fraction of a cent to zero. Interest posted is not final total interest for an unfinished plan.</p>'+''.join(details)+'</section>'


def calculate_section(scenario,target):
    return result_section(scenario,compare_payoff(inputs_from_scenario(scenario,target)))
