"""Bounded comparisons and explicit save review using the existing engine."""
from decimal import Decimal
from datetime import timezone
from hashlib import sha256
from dashboard.manual import ManualScenario, editable_inputs, CARD_FIELDS
from dashboard.cash_inputs import cash_horizon
from dashboard.forms import shell
from dashboard.report import text, money, card_label, readable_time
from dashboard.guidance import practice_inputs
from engine.common import decimal_context, reconstruct
from engine.portfolio import RequestKind

ZERO = Decimal(0)


@decimal_context
def strategy_variants(scenario):
    """Generate alternatives only when budget and payment timing can stay comparable.

    No balances, contract terms, cash events or dates are changed. The adapter's
    deterministic split feeds the existing coordinator; only extra priorities vary.
    """
    values = editable_inputs(scenario)
    if not 2 <= len(scenario.debts) <= 3:
        raise ValueError('Add two or three cards to compare payment priorities.')
    dates = set()
    for debt in scenario.debts:
        requests = [r for r in scenario.requests if r.debt_account_id == debt.account.account_id]
        if not requests:
            raise ValueError('Each card needs a positive proposed payment with explicit dates before comparing priorities.')
        dates.update((r.initiated_at, r.credited_at, r.debited_at, r.settled_at) for r in requests)
    if len(dates) != 1:
        raise ValueError('For this comparison, all cards must use the same initiation, credit, bank debit and settlement dates. Adjust a copy to compare a common payment date.')
    budget = sum((r.amount for r in scenario.requests), ZERO)
    minimums = {d.account.account_id:d.initial_minimum.statement_minimum_remaining for d in scenario.debts}
    balances = {d.account.account_id:d.account.total_balance() for d in scenario.debts}
    if budget < sum(minimums.values(), ZERO):
        raise ValueError('The total requested budget is below the combined remaining minimums. Review the shortfall in your current result before comparing extra-payment priorities.')
    if budget > sum(balances.values(), ZERO):
        raise ValueError('The total requested budget exceeds the opening posted debt. Reduce it to compare the same budget without inventing payments toward future interest.')
    accounts = [d.account.account_id for d in scenario.debts]
    rates = {d.account.account_id:d.account.segments[0].apr.value for d in scenario.debts}
    ranks = [
        ('Highest interest first', sorted(accounts, key=lambda id_:(-rates[id_], accounts.index(id_)))),
        ('Smallest balance first', sorted(accounts, key=lambda id_:(balances[id_], accounts.index(id_)))),
    ]
    variants = [('Your entered plan', scenario)]
    for label, order in ranks:
        allocated = dict(minimums)
        remaining = budget - sum(allocated.values(), ZERO)
        for id_ in order:
            extra = min(remaining, balances[id_] - allocated[id_])
            allocated[id_] += extra
            remaining -= extra
        if remaining:
            raise ArithmeticError('Strategy failed to allocate the explicit budget')
        inputs = dict(values)
        for index, id_ in enumerate(accounts):
            prefix = '' if index == 0 else f'card_{index+1}_'
            inputs[prefix+'payment_amount'] = str(allocated[id_])
            inputs[prefix+'payment_kind'] = 'minimum'
        candidate = ManualScenario.model_validate(inputs).scenario()
        requests = tuple(reconstruct(r, priority=order.index(r.debt_account_id)*2+1)
            if r.kind == RequestKind.EXTRA else r for r in candidate.requests)
        candidate = reconstruct(candidate, name=(scenario.name[:85]+' — '+label)[:120],
                                origin=scenario.origin, requests=requests)
        if sum((r.amount for r in candidate.requests), ZERO) != budget:
            raise ArithmeticError('Strategy budget changed')
        if (candidate.debts, candidate.openings, candidate.cash_plans, candidate.start, candidate.end,
            cash_horizon(candidate.start,candidate.end,candidate.requests)) != (
            scenario.debts,scenario.openings,scenario.cash_plans,scenario.start,scenario.end,
            cash_horizon(scenario.start,scenario.end,scenario.requests)):
            raise ArithmeticError('Strategy changed the comparison scope')
        variants.append((label, candidate))
    return tuple(variants)


@decimal_context
def strategy_results(scenario):
    results = []
    for label, candidate in strategy_variants(scenario):
        projection = candidate.project()
        paid = {d.account.account_id:sum((r.accepted for r in projection.decisions
                if r.debt_account_id==d.account.account_id), ZERO) for d in candidate.debts}
        requested = {d.account.account_id:sum((r.amount for r in candidate.requests
                     if r.debt_account_id==d.account.account_id), ZERO) for d in candidate.debts}
        results.append(dict(label=label, scenario=candidate, requested=requested, paid=paid,
            total_requested=sum(requested.values(),ZERO), total_paid=sum(paid.values(),ZERO),
            cash=projection.liquidity.points[-1].positions[0].cleared,
            interest=sum((s.accrued_unposted_interest for d in projection.debt_projections
                          for s in d.account.segments), ZERO),
            posted=sum((d.account.total_balance() for d in projection.debt_projections),ZERO),
            missed=projection.missed_minimum_account_ids, cash_status=projection.liquidity.status.value,
            cash_end=projection.liquidity.end))
    return tuple(results)


@decimal_context
def render_strategies(scenario, back_url='/', source=None):
    intro = f'<h1>Compare payment priorities</h1><p>{text(scenario.name)} · '+('Practice data' if scenario.origin=='synthetic_demo' else 'Manual estimates')+'</p>'
    navigation = f'<p><a href="{text(back_url)}">Back to saved result</a> · <a href="/">Home</a></p>'
    if back_url == '/':navigation = '<p><a href="/">Home</a></p>'
    try:
        results = strategy_results(scenario)
    except ValueError as exc:
        return shell('Payment priorities',intro+navigation+'<section><h2>This scenario needs a change first</h2><p>'+text(exc)+'</p><p>Your saved scenario is unchanged. Use Adjust a copy on its result page, or <a href="/strategies-example">try the two-card example</a>.</p></section>')
    actions = ''
    if source is not None:
        actions = '<section><h2>Keep an alternative</h2><p>Review its exact payment order before saving a separate scenario.</p>' + ''.join(
            '<p><a href="/strategy-review/'+text(source)+'/'+key+'">Review '+text(label)+'</a></p>'
            for key,label in STRATEGY_CHOICES.items()) + '</section>'
    base = results[0]
    def currency(value):return text(money(value))
    def difference(value):
        delta=value-base['interest']
        if not delta:return 'Same as entered plan'
        return ('Less than $0.01' if abs(delta)<Decimal('.01') else currency(abs(delta)))+(' more' if delta>0 else ' less')
    headers=''.join('<th scope="col">'+text(row['label'])+'</th>' for row in results)
    rows=[]
    for title,key in [('Total requested budget','total_requested'),('Payments applied','total_paid'),
                      ('Cash left after supplied activity','cash'),('Posted debt at window end','posted'),
                      ('Interest awaiting statement posting','interest')]:
        rows.append('<tr><th scope="row">'+title+'</th>'+''.join('<td>'+currency(row[key])+'</td>' for row in results)+'</tr>')
    rows.append('<tr><th scope="row">Interest change in this window</th>'+''.join('<td>'+difference(row['interest'])+'</td>' for row in results)+'</tr>')
    rows.append('<tr><th scope="row">Missed minimum dates</th>'+''.join('<td>'+text(', '.join(card_label(scenario,id_) for id_ in row['missed']) or 'None in this window')+'</td>' for row in results)+'</tr>')
    rows.append('<tr><th scope="row">Cash condition across forecast</th>'+''.join('<td>'+text(row['cash_status'].replace('_',' '))+'</td>' for row in results)+'</tr>')
    allocations=[]
    for debt in scenario.debts:
        id_=debt.account.account_id
        allocations.append('<tr><th scope="row">'+text(card_label(scenario,id_))+'</th>'+''.join('<td>'+currency(row['paid'][id_])+' applied<br><small>'+currency(row['requested'][id_])+' requested</small></td>' for row in results)+'</tr>')
    zone=scenario.debts[0].credit_timezone
    explanation='''<section><h2>How this comparison works</h2><p>Both generated alternatives request each remaining minimum first, then direct the remaining requested budget toward the highest opening APR or the smallest opening posted balance. Ties use card order. Your entered plan is shown unchanged.</p><p>All options share the same total requested budget, payment dates, card terms, income, bills and cash protections. The engine may apply less than requested to protect cash. Read applied amounts and missed due dates as well as interest. Displayed amounts and differences are rounded independently from the unrounded estimates.</p><p>This compares one set of payments over the dates shown, not an entire debt payoff. Future statement minimums, new purchases, fees and unsupplied activity are not generated. Lower interest here does not establish a globally best plan. Nothing is saved or sent to a bank.</p></section>'''
    return shell('Payment priorities',intro+navigation+
        comparison_takeaways(results,scenario)+'<p>Debt window: '+text(readable_time(scenario.start.isoformat(),zone))+' through '+text(readable_time(scenario.end.isoformat(),zone))+'. Cash through '+text(readable_time(base['cash_end'].isoformat(),zone))+'.</p>'+
        '<div class="scroll"><table><caption>Same requested budget, different priorities</caption><thead><tr><th>Measure</th>'+headers+'</tr></thead><tbody>'+''.join(rows)+'</tbody></table></div>'+
        '<section><h2>Payments by card</h2><div class="scroll"><table><thead><tr><th>Card</th>'+headers+'</tr></thead><tbody>'+''.join(allocations)+'</tbody></table></div></section>'+explanation+actions)


def strategy_example():
    values = practice_inputs() | {'scope':'confirmed','name':'Two-card priority example','card_name':'Higher rate'}
    card = {key:values[key] for key in CARD_FIELDS if key in values}
    card.update(card_name='Smaller balance',balance='100',apr_percent='12',payment_amount='200')
    values['additional_cards'] = (card,)
    return reconstruct(ManualScenario.model_validate(values).scenario(),origin='synthetic_demo')


STRATEGY_CHOICES = {'highest-interest':'Highest interest first', 'smallest-balance':'Smallest balance first'}


def selected_strategy(scenario, choice):
    if choice not in STRATEGY_CHOICES:
        raise ValueError('Choose one of the displayed payment priorities.')
    return dict(strategy_variants(scenario))[STRATEGY_CHOICES[choice]]


def strategy_fingerprint(scenario):
    """Bind saving to the exact reviewed candidate, including priority semantics."""
    return sha256(scenario.model_dump_json().encode('utf-8')).hexdigest()


def payment_order(scenario):
    rows = []
    for request in sorted(scenario.requests, key=lambda r:(r.kind != RequestKind.MINIMUM, r.initiated_at.astimezone(timezone.utc), r.priority)):
        rows.append('<tr><td>'+text(card_label(scenario,request.debt_account_id))+'</td><td>'+text(request.kind.value)+
                    '</td><td>'+text(money(request.amount))+'</td><td>'+text(readable_time(request.initiated_at.isoformat(),scenario.debts[0].credit_timezone))+'</td></tr>')
    return '<section><h2>Payment request order</h2><p>Minimum requests reserve cash before extra requests. Within each group, initiation time comes first, then the saved priority. Amounts below are requests; actual payments may be reduced to protect cash.</p><div class="scroll"><table><thead><tr><th>Card</th><th>Portion</th><th>Requested</th><th>Initiation</th></tr></thead><tbody>'+''.join(rows)+'</tbody></table></div></section>'


def render_strategy_review(original, source, choice, token):
    from dashboard.report import render
    candidate = selected_strategy(original, choice)
    back = '/strategies-example' if source == 'example' else '/strategies/'+source
    fields = {'token':token, 'source':source, 'choice':choice, 'fingerprint':strategy_fingerprint(candidate)}
    hidden = ''.join('<input type="hidden" name="'+text(key)+'" value="'+text(value)+'">' for key,value in fields.items())
    intro = '<section><h1>Review before saving</h1><p>'+text(STRATEGY_CHOICES[choice])+'. Saving keeps these exact requests and their priority order as a new local scenario. Your original stays unchanged; no payment is sent.</p><p>This option may not be editable in the simple form, which uses card order for extra payments. Its saved result, timeline and request order remain available.</p><p><a href="'+back+'">Back to comparison</a></p>'+payment_order(candidate)+'<form method="post" action="/save-strategy">'+hidden+'<button type="submit">Save as a separate scenario</button></form></section>'
    return render(candidate).replace('<h1>', '<h2>', 1).replace('</h1>', '</h2>', 1).replace('<main>', '<main>'+intro, 1)


@decimal_context
def comparison_takeaways(results, scenario):
    """Describe observed results without promoting a winner or inventing a payoff."""
    items = []
    for row in results:
        shortfall = row['total_requested'] - row['total_paid']
        message = text(row['label'])+': '+text(money(row['total_paid']))+' applied of '+text(money(row['total_requested']))+' requested.'
        if shortfall:
            message += ' '+text(money(shortfall))+' of the requested payments is not funded in this forecast.'
        if row['missed']:
            message += ' Minimum due dates are missed for '+text(', '.join(card_label(scenario,id_) for id_ in row['missed']))+'.'
        else:
            message += ' No minimum due dates are missed within the debt window.'
        items.append('<li>'+message+'</li>')
    same = all(row['paid']==results[0]['paid'] for row in results[1:])
    explanation = ('All three options apply the same amount to each card in this window. Changing priorities does not change these projected payments.'
        if same else 'The options send different amounts to individual cards. The table below shows how that changes interest during this window.')
    if any(row['missed'] for row in results):
        explanation += ' Review missed minimums before using an interest difference to choose a plan.'
    return '<section><h2>What to notice</h2><ul>'+''.join(items)+'</ul><p>'+explanation+'</p></section>'
