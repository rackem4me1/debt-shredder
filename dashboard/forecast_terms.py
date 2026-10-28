"""Explicit future minimum terms; save reviewed copies through signed restore path."""
from datetime import date
from decimal import Decimal
from SCHEMA import Sourced, ProvenanceSource, RoundingMode
from dashboard.forms import shell
from dashboard.report import text, money, card_label
from dashboard.strategies import strategy_fingerprint
from dashboard.restore import review_signature
from engine.common import reconstruct, decimal_context


def terms_table(scenario):
    rows=[]
    for debt in scenario.debts:
        account=debt.account
        for label,term,value in (
            ('Minimum dollar floor',account.minimum_payment_floor,money(account.minimum_payment_floor.value)),
            ('Statement balance percentage',account.minimum_payment_rate,str(account.minimum_payment_rate.value*100)+'%'),
            ('Rounding',account.rounding_mode,account.rounding_mode.value.name.replace('_',' ').title())):
            rows.append('<tr>'+''.join('<td>'+text(v)+'</td>' for v in (card_label(scenario,account.account_id),label,value,term.provenance.value.replace('_',' '),term.confirmed_date or 'Not supplied'))+'</tr>')
    return '<div class="scroll"><table><thead><tr><th>Card</th><th>Term</th><th>Value</th><th>Source</th><th>Confirmed date</th></tr></thead><tbody>'+''.join(rows)+'</tbody></table></div>'


@decimal_context
def terms_form(scenario,source,token):
    fields={'token':token,'source':source,'fingerprint':strategy_fingerprint(scenario)}
    hidden=''.join('<input type="hidden" name="'+text(k)+'" value="'+text(v)+'">' for k,v in fields.items())
    cards=[]
    for i,debt in enumerate(scenario.debts):
        account=debt.account
        # Source/rounding/value blanks force explicit entry, not silent acceptance of defaults.
        cards.append('<fieldset><legend>'+text(card_label(scenario,account.account_id))+'</legend><div class="grid">'+
            f'<label>Minimum dollar floor ($)<input name="floor_{i}" type="number" min="0" step="0.01" required></label>'+
            f'<label>Statement balance percentage (%)<input name="rate_{i}" type="number" min="0" max="100" step="any" required></label>'+
            f'<label>Rounding<select name="rounding_{i}" required><option value="">Choose…</option>'+''.join('<option value="'+v.value+'">'+text(v.name.replace('_',' ').title())+'</option>' for v in RoundingMode)+'</select></label>'+
            f'<label>Source for these three terms<select name="provenance_{i}" required><option value="">Choose…</option><option value="user_provided_estimate">My estimate</option><option value="user_confirmed">I checked these terms</option></select></label>'+
            f'<label>Date checked (required if checked)<input name="date_{i}" type="date"></label></div></fieldset>')
    return shell('Review future minimum terms','<h1>Future minimum-payment terms</h1><p>Today’s statement minimum and the formula for future statements are different inputs. Review the saved values below; assumed defaults are not verified issuer terms.</p>'+terms_table(scenario)+
        '<p>This step updates only the three terms shown for each card. It does not extend the forecast, verify other card terms, or add payment dates.</p>'+
        '<form method="post" action="/forecast-terms-preview">'+hidden+'<label>Name for the new copy<input name="name" maxlength="120" required value="'+text(scenario.name)+'"></label>'+''.join(cards)+
        '<p>The supported future-minimum formula is the smaller of posted balance and the greater of the dollar floor or the percentage of posted balance plus billed interest and fees. The selected rounding mode applies to both posted interest and projected minimums. An issuer using a different formula needs additional support.</p>'+
        '<label><input type="checkbox" name="formula" value="understood" required> I understand which formula these values will be used with.</label><button type="submit">Review term changes</button></form><p><a href="/scenario/'+text(source)+'">Back to saved plan</a></p>')


@decimal_context
def change_terms(original,values):
    expected={'name','formula'}|{f'{field}_{i}' for i in range(len(original.debts)) for field in ('floor','rate','rounding','provenance','date')}
    if any(not isinstance(v,str) for v in values.values()):
        raise ValueError('Form values must be text')
    if set(values)!=expected or values['formula']!='understood' or not values['name'].strip():
        raise ValueError('Complete every card and acknowledge the formula')
    debts=[]
    for i,debt in enumerate(original.debts):
        floor=Decimal(values[f'floor_{i}']);rate=Decimal(values[f'rate_{i}'])
        if not floor.is_finite() or not rate.is_finite() or floor<0 or floor%Decimal('.01') or not 0<=rate<=100:
            raise ValueError('Use a nonnegative whole-cent floor and a percentage from 0 to 100')
        provenance=ProvenanceSource(values[f'provenance_{i}'])
        if provenance not in (ProvenanceSource.USER_CONFIRMED,ProvenanceSource.USER_PROVIDED_ESTIMATE):
            raise ValueError('Choose estimate or checked terms')
        confirmed=date.fromisoformat(values[f'date_{i}']) if values[f'date_{i}'] else None
        if provenance==ProvenanceSource.USER_PROVIDED_ESTIMATE and confirmed:
            raise ValueError('Leave date checked blank for estimated terms')
        def sourced(value):
            return Sourced[type(value)](value=value,provenance=provenance,confirmed_date=confirmed)
        account=reconstruct(debt.account,minimum_payment_floor=sourced(floor),minimum_payment_rate=sourced(rate/100),rounding_mode=sourced(RoundingMode(values[f'rounding_{i}'])))
        debts.append(reconstruct(debt,account=account))
    candidate=reconstruct(original,name=values['name'].strip(),debts=tuple(debts))
    candidate.project()
    return candidate


@decimal_context
def terms_preview(original,candidate,token):
    payload=candidate.model_dump_json()
    hidden=''.join('<input type="hidden" name="'+text(k)+'" value="'+text(v)+'">' for k,v in
        {'token':token,'payload':payload,'signature':review_signature(payload,token)}.items())
    return shell('Review term changes','<h1>Review future minimum terms</h1><p>Nothing has been saved. Saving creates a separate copy named '+text(candidate.name)+'. Your original stays unchanged.</p><section><h2>Previously saved</h2>'+terms_table(original)+'</section><section><h2>New terms</h2>'+terms_table(candidate)+'</section><p>Payment requests, cash entries, balances and forecast dates stay as entered. These terms can affect projected minimums and posted interest at statement closes inside the existing window. This step does not generate future payments or a longer forecast.</p><form method="post" action="/restore-save">'+hidden+'<button type="submit">Save copy with these terms</button></form><p><a href="/">Cancel and return home</a></p>')
