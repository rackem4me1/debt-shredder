"""Edit requested amounts without rebuilding contracts, dates or priorities."""
from decimal import Decimal
from zoneinfo import ZoneInfo
from dashboard.simple_view import page, tile
from dashboard.report import text, money, card_label, readable_time
from dashboard.strategies import payment_order, strategy_fingerprint
from dashboard.restore import review_signature
from engine.common import reconstruct, decimal_context

MAX_EDIT_REQUESTS = 100


def editable_payments(scenario):
    if not 1 <= len(scenario.requests) <= MAX_EDIT_REQUESTS:
        raise ValueError('Payment editing requires between 1 and 100 existing requests.')


@decimal_context
def change_payments(original, values):
    editable_payments(original)
    expected={'name'}|{f'amount_{i}' for i in range(len(original.requests))}
    if set(values)!=expected:raise ValueError('Every existing payment amount is required; additional fields are not accepted.')
    candidate=reconstruct(original,name=values['name'],requests=tuple(
        reconstruct(request,amount=values[f'amount_{i}']) for i,request in enumerate(original.requests)))
    candidate.project()
    return candidate


def payment_form(scenario, source, token, values=None, error=''):
    editable_payments(scenario)
    values = values if values is not None else {'name':scenario.name, **{f'amount_{i}':str(r.amount) for i,r in enumerate(scenario.requests)}}
    zones={d.account.account_id:ZoneInfo(d.credit_timezone) for d in scenario.debts}
    fields=[]
    for i,r in enumerate(scenario.requests):
        zone=zones[r.debt_account_id]
        fields.append('<div class="tile"><label for="amount-'+str(i)+'"><strong>'+text(card_label(scenario,r.debt_account_id))+'</strong><small>'+text(r.kind.value.title())+' portion · submit '+text(r.initiated_at.astimezone(zone).strftime('%b %d, %Y'))+'</small><span>Requested amount ($)</span></label><input id="amount-'+str(i)+'" name="amount_'+str(i)+'" type="number" min="0.01" step="0.01" value="'+text(values.get(f'amount_{i}',''))+'" required><small>Card credit date: '+text(r.credited_at.astimezone(zone).strftime('%b %d, %Y'))+' · '+text(zone.key)+'</small></div>')
    hidden={'token':token,'source':source,'fingerprint':strategy_fingerprint(scenario)}
    controls=''.join('<input type="hidden" name="'+k+'" value="'+text(v)+'">' for k,v in hidden.items())
    return page('Adjust payment amounts','<div class="hero"><span class="eyebrow">Step 1 of 2 · Try a change</span><h1>Adjust payment amounts</h1><p>Try different amounts, then see what changes before saving a copy.</p></div>'+('<div class="banner warning" role="alert">'+text(error)+'</div>' if error else '')+'<form method="post" action="/payment-preview">'+controls+'<section><label for="plan-name">Name for this version</label><input id="plan-name" name="name" maxlength="120" value="'+text(values.get('name',''))+'" required><p class="muted">Your existing plan stays available under its original name.</p></section><div class="cards">'+''.join(fields)+'</div><p>Minimum and extra portions are parts of your payments. Reducing a minimum portion can leave a due date unpaid. Each amount must be at least $0.01.</p><div class="actions"><button class="action" type="submit">Preview payment changes</button><a href="/plan/'+source+'">Cancel and return to original</a></div></form><details><summary>Dates, bills and payment order</summary><p>This step changes only the plan name and requested amounts. Your saved dates, card terms and cash activity are used for the new calculation.</p>'+payment_order(scenario)+'</details>')


@decimal_context
def payment_preview(candidate, original, source, token):
    payload=candidate.model_dump_json()
    hidden={'token':token,'payload':payload,'signature':review_signature(payload,token)}
    controls=''.join('<input type="hidden" name="'+k+'" value="'+text(v)+'">' for k,v in hidden.items())
    before=original.project();after=candidate.project()
    zones={d.credit_timezone for d in candidate.debts}
    zone=next(iter(zones)) if len(zones)==1 else 'UTC'
    def when(value):return text(readable_time(value.isoformat(),zone))
    accepted_before=sum((r.accepted for r in before.decisions),Decimal(0))
    accepted_after=sum((r.accepted for r in after.decisions),Decimal(0))
    requested=sum((r.amount for r in candidate.requests),Decimal(0))
    unmet=sum((r.unmet for r in after.decisions),Decimal(0))
    warnings=[]
    if after.missed_minimum_account_ids:
        warnings.append('Minimum-payment due dates are missed for '+', '.join(card_label(candidate,id_) for id_ in after.missed_minimum_account_ids)+'.')
    if unmet:warnings.append(money(unmet)+' of your requested payments cannot be applied.')
    if after.liquidity.status.value!='healthy':warnings.append('Cash falls short somewhere in the cash window. The ending balance alone does not show earlier shortages.')
    accepted_by_id={d.request_id:d for d in after.decisions}
    rows=[]
    for old,new in zip(original.requests,candidate.requests):
        decision=accepted_by_id[new.request_id]
        rows.append('<tr>'+''.join('<td>'+text(v)+'</td>' for v in (card_label(candidate,new.debt_account_id),new.kind.value.title(),money(old.amount),money(new.amount),money(decision.accepted),money(decision.unmet)))+'</tr>')
    old_cash={r.account_id:r for r in before.liquidity.points[-1].positions}
    floors={r.account_id:r.floor for r in candidate.openings}
    cash=''.join(tile(r.account_id,money(r.cleared),'Ending cash: '+money(old_cash[r.account_id].cleared)+' before → '+money(r.cleared)+' after. Floor setting '+money(floors[r.account_id])+', reserved '+money(r.reserved)+'. This is not a spending allowance.') for r in after.liquidity.points[-1].positions)
    debt_rows=[]
    for debt in after.debt_projections:
        unposted=sum((segment.accrued_unposted_interest for segment in debt.account.segments),Decimal(0))
        debt_rows.append('<li>'+text(card_label(candidate,debt.account.account_id))+': '+money(debt.account.total_balance())+' posted, plus '+money(unposted)+' unposted interest. Missed minimum dates: '+text(', '.join(map(str,debt.missed_due_dates)) or 'none in this window')+'.</li>')
    changed=any(a.amount!=b.amount for a,b in zip(original.requests,candidate.requests))
    return page('Review payment changes','<div class="hero"><span class="eyebrow">Step 2 of 2 · Review the result</span><h1>Review payment changes</h1><p>'+text(candidate.name)+' · Nothing saved yet.</p></div><div class="banner '+('warning' if warnings else '')+'"><strong>'+('This version needs a closer look.' if warnings else 'These payments fit the supplied forecast.')+'</strong><p>'+text(' '.join(warnings) if warnings else 'No missed minimums or cash shortages were found within the supplied dates.')+'</p></div><div class="cards">'+tile('Payments that fit',money(accepted_after),money(accepted_before)+' in the original → '+money(accepted_after)+' in this version.')+tile('Requested payments',money(requested),money(unmet)+' cannot be applied in this forecast.')+'</div>'+('<p>Payment amounts are unchanged. You can still save this as a separate version.</p>' if not changed else '')+'<section><h2>Your changes</h2><div class="scroll"><table><thead><tr><th>Card</th><th>Portion</th><th>Requested before</th><th>Requested after</th><th>Fits</th><th>Unfunded</th></tr></thead><tbody>'+''.join(rows)+'</tbody></table></div></section><h2>What happens to your cash</h2><p class="muted">After supplied activity through '+when(after.liquidity.end)+'. Each account is shown separately.</p><div class="cards">'+cash+'</div><section><h2>Debt at the end</h2><p>Through '+when(candidate.end)+'.</p><ul>'+''.join(debt_rows)+'</ul></section><form method="post" action="/payment-save">'+controls+'<div class="actions"><button class="action" type="submit">Save payment changes as a copy</button><a href="/plan/'+source+'">Keep the original</a></div></form><p>To edit these amounts again, use your browser’s Back button. Saving keeps your original and opens the new summary. No money moves.</p><details><summary>How payments are ordered</summary>'+payment_order(candidate)+'</details>')
