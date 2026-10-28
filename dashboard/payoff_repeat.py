"""Explicit recurring payoff assumptions; adapts the existing saved inputs."""
from datetime import date,datetime,time,timedelta
from zoneinfo import ZoneInfo
from SCHEMA import SemimonthlyShortMonthRule,ProvenanceSource
from engine.payoff_calendar import (PayoffTemplate,RepeatingPaymentRule,MonthlyStatementRule,
    RecurringPayoffCash,expand_payoff_template,monthly_occurrence)
from engine.payoff import compare_payoff
from dashboard.strategies import strategy_fingerprint
from dashboard.report import text
from dashboard import payoff_view

FIELDS={'payment_target','end','cadence','first_payment','credit_days','debit_days','settlement_days','short_month_rule','scope'}


def template_from_scenario(source,values):
    if set(values)!=FIELDS or values['scope']!='assumed_calendar':
        raise ValueError('Complete the repeating calendar and confirm that future dates and terms are estimates.')
    if len({d.credit_timezone for d in source.debts})!=1:
        raise ValueError('Repeating payoff currently needs one shared card timezone.')
    funding=payoff_view.inputs_from_scenario(source,values['payment_target'])
    zone=source.debts[0].credit_timezone;tz=ZoneInfo(zone)
    end=datetime.combine(date.fromisoformat(values['end']),time(),tzinfo=tz)
    if end<source.end:raise ValueError('The new end date must be on or after the saved forecast end.')
    delays={}
    for key in ('credit_days','debit_days','settlement_days'):
        if not values[key].isdigit():raise ValueError('Use whole calendar-day delays from 0 to 14.')
        delays[key]=int(values[key])
    short=SemimonthlyShortMonthRule(values['short_month_rule'])
    for debt in source.debts:
        latest=max(debt.cycles,key=lambda cycle:cycle.end_date)
        close=latest.end_date
        if latest.statement_date!=close:
            raise ValueError('The saved statement has a delay after cycle close. This repeating form does not infer that delay.')
        previous=close.replace(day=1)-timedelta(days=1)
        close_dates={monthly_occurrence(d.year,d.month,debt.account.statement_close_day,short) for d in (close,previous)}
        expected_due=monthly_occurrence(close.year+(close.month==12),close.month%12+1,debt.account.payment_due_day,short)
        if close not in close_dates or latest.due_date!=expected_due:
            raise ValueError('Saved statement dates do not match the proposed repeating pattern. Review the close/due terms before extending this plan.')
    rule=RepeatingPaymentRule(first_date=date.fromisoformat(values['first_payment']),cadence=values['cadence'],
        timezone_name=zone,clock=time(12),short_month_rule=short if values['cadence']=='monthly' else None,**delays)
    statements=tuple(MonthlyStatementRule(account_id=d.account.account_id,close_day=d.account.statement_close_day,
        due_day=d.account.payment_due_day,due_month_offset=1,short_month_rule=short) for d in source.debts)
    schedules=tuple(RecurringPayoffCash(schedule_id='saved-cash-'+str(i),kind=e.kind,amount=e.amount,
        first_date=e.date,cadence=e.cadence,clock=time(),until=e.until,short_month_rule=e.short_month_rule,
        provenance=ProvenanceSource.USER_PROVIDED_ESTIMATE) for i,e in enumerate(source.manual_cash_schedules))
    return PayoffTemplate(start=source.start,end=end,debts=source.debts,opening=funding.opening,
        additional_openings=funding.additional_openings,payment_sources=funding.payment_sources,
        payment_target=values['payment_target'],payments=rule,statements=statements,cash_schedules=schedules,
        one_off_cash_plans=() if schedules else source.cash_plans)


def form_section(source,identifier,token,values=None,error=''):
    if len({d.credit_timezone for d in source.debts})!=1:return ''
    values=values or {}
    defaults={'payment_target':'','end':str(source.end.date()),'cadence':'','first_payment':'',
        'credit_days':'0','debit_days':'0','settlement_days':'0','short_month_rule':''}
    values=defaults|values
    def field(key,label,kind='text',extra=''):
        return '<label>'+text(label)+'<input required name="'+key+'" type="'+kind+'" '+extra+'value="'+text(values.get(key,''))+'"></label>'
    def select(key,label,options):
        return '<label>'+label+'<select required name="'+key+'"><option value="">Choose…</option>'+''.join('<option value="'+key_value+'"'+(' selected' if values.get(key)==key_value else '')+'>'+text(name)+'</option>' for key_value,name in options)+'</select></label>'
    hidden=''.join('<input type="hidden" name="'+k+'" value="'+text(v)+'">' for k,v in {'token':token,'fingerprint':strategy_fingerprint(source)}.items())
    cash_note=('Saved repeating income/bill rules will expand through the cash horizon, with their existing stop dates.' if source.manual_cash_schedules else 'This plan has no saved repeating income/bill rules. Only its dated cash events will be included; no future paychecks or bills are invented.')
    rules='; '.join(d.account.account_id+': statement day '+str(d.account.statement_close_day)+', due day '+str(d.account.payment_due_day)+' of the following month' for d in source.debts)
    return '<details'+(' open' if error else '')+'><summary>Repeat a longer payoff calendar</summary><section><h2>Build future dates from explicit assumptions</h2><p>Starts from the saved balances on '+text(source.start.date())+', not today’s bank balances. Future statement dates use '+text(rules)+'. Rates and minimum formulas stay as supplied.</p><p>'+text(cash_note)+'</p>'+('<p class="banner warning" role="alert">'+text(error)+'</p>' if error else '')+'<form method="post" action="/payoff-repeat/'+identifier+'">'+hidden+'<div class="grid">'+field('payment_target','Total target per payment date ($)','number','min="0" step="0.01" ')+field('end','Repeat through','date')+field('first_payment','First payment initiation','date')+select('cadence','Payment frequency',(('weekly','Weekly'),('biweekly','Every two weeks'),('monthly','Monthly')))+select('short_month_rule','If a monthly date does not exist',(('clamp_to_last_day_of_month','Use the last day of the month'),('roll_to_next_month_first_day','Use the first day of the next month')))+''.join(field(k,label,'number','min="0" max="14" step="1" ') for k,label in (('credit_days','Card credit delay (calendar days)'),('debit_days','Bank debit delay (calendar days)'),('settlement_days','Settlement delay (calendar days)')))+'</div><p>Payments start at noon in '+text(source.debts[0].credit_timezone)+'. Zero means the same day. Delays count calendar days; weekends and bank holidays are not adjusted. Only lifecycles that settle by the end date are included. Maximum 120 payment rounds.</p><label><input required type="checkbox" name="scope" value="assumed_calendar"'+(' checked' if values.get('scope')=='assumed_calendar' else '')+'> Treat generated dates and unchanged future terms as planning assumptions. Only declared cash schedules repeat; I will review the included cash events.</label><button class="action">Calculate the repeating plan</button></form></section></details>'


def assumptions_section(expanded):
    template=expanded.template
    missing='<p class="banner warning">No repeating income/bill rules were supplied. This result uses only the saved dated cash events. It does not establish that future living costs are covered.</p>' if not template.cash_schedules else ''
    transfer_note=('<p>Only the declared transfer schedules repeat. Internal transfers do not count as income or spending. Destination money remains unavailable until settlement.</p>'+('<p>Transfers still pending at the cash horizon: '+text(', '.join(expanded.pending_transfer_ids))+'. The cash ledger retains their commitments, holds or transit.</p>' if expanded.pending_transfer_ids else '')) if template.transfer_schedules else ''
    excluded='<p>Payment initiations excluded because settlement is after the end date: '+text(', '.join(map(str,expanded.excluded_payment_dates)))+'.</p>' if expanded.excluded_payment_dates else ''
    cash=''.join('<tr><td>'+text(p.plan_id)+'</td><td>'+text(p.kind.value)+'</td><td>'+text(p.credited_at.isoformat())+'</td><td>'+text(str(p.amount))+'</td></tr>' for p in expanded.inputs.cash_plans)
    cycles=''.join('<li>'+text(d.account.account_id)+': '+text(', '.join(str(c.end_date)+' → due '+str(c.due_date) for c in d.cycles))+'</li>' for d in expanded.inputs.debts)
    return '<section><h2>Repeated-calendar assumptions</h2><p>Debt forecast: '+text(template.start.date())+' through '+text(template.end.date())+'. '+str(len(expanded.inputs.slots))+' payment rounds; '+str(len(expanded.generated_cycle_ids))+' generated statement cycles.</p><p>'+text(expanded.assumption_note)+'</p>'+transfer_note+missing+excluded+'<details><summary>Review every included cash event and statement date</summary><ul>'+cycles+'</ul><div class="scroll"><table><thead><tr><th>Cash event</th><th>Kind</th><th>When</th><th>Amount</th></tr></thead><tbody>'+cash+'</tbody></table></div></details></section>'


def calculate(source,values):
    expanded=expand_payoff_template(template_from_scenario(source,values))
    comparison=compare_payoff(expanded.inputs)
    return expanded,assumptions_section(expanded)+payoff_view.result_section(source,comparison)
