"""Read-only three-slot personal forecast from explicit schedules and saved terms."""
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo
from SCHEMA import BillingCycle, ProvenanceSource, SegmentType, CompoundingMethod, GracePeriodState
from engine.common import reconstruct, decimal_context
from engine.minimum_forecast import MinimumTerms, PaymentSlot
from engine.portfolio_minimum_forecast import CardMinimumSchedule, forecast_portfolio_minimums
from dashboard.cash_inputs import cash_horizon, expand_cash_events
from dashboard.forms import shell
from dashboard.report import text, money, card_label
from dashboard.strategies import strategy_fingerprint
from dashboard.forecast_terms import terms_table


def eligibility(scenario):
    if not 1<=len(scenario.debts)<=3 or len(scenario.openings)!=1 or len({d.credit_timezone for d in scenario.debts})!=1:
        raise ValueError('This form supports one cash account and one to three cards sharing a time zone.')
    for debt in scenario.debts:
        if (len(debt.account.segments)!=1 or debt.account.segments[0].segment_type!=SegmentType.STANDARD_PURCHASE
                or debt.account.segments[0].compounding_method.value!=CompoundingMethod.SIMPLE_DAILY
                or debt.account.current_grace_state!=GracePeriodState.LOST_GRACE or debt.grace_terms or debt.promo_transitions):
            raise ValueError('This forecast form supports ordinary simple-daily cards without active grace or promotions.')
        if any(t.provenance==ProvenanceSource.ASSUMED_DEFAULT for t in (debt.account.minimum_payment_floor,debt.account.minimum_payment_rate,debt.account.rounding_mode)):
            raise ValueError('Review future minimum terms and save a copy first. The minimum floor, percentage and rounding must be entered explicitly, even when they are estimates.')


def form(scenario,source,token,values=None,error=''):
    eligibility(scenario)
    values=values or {}
    def field(key,label,kind='date'):
        return '<label>'+text(label)+'<input required type="'+kind+'" name="'+key+'" value="'+text(values.get(key,''))+'"></label>'
    cards=[]
    for i,debt in enumerate(scenario.debts):
        cycles=''.join('<li>'+text(f'{c.start_date} through {c.end_date}; statement {c.statement_date}; due {c.due_date}')+'</li>' for c in debt.cycles)
        sections='<h3>Already saved statement cycles</h3><ul>'+cycles+'</ul>'
        for j in range(2):
            sections+=f'<h3>Additional statement cycle {j+1}</h3><div class="grid">'+''.join(field(f'c_{i}_{j}_{key}',label) for key,label in (('start','Cycle starts'),('end','Cycle ends'),('statement','Statement date'),('due','Minimum due date')))+'</div>'
        for j in range(3):
            sections+=f'<h3>Payment opportunity {j+1}</h3><div class="grid">'+''.join(field(f'p_{i}_{j}_{key}',label) for key,label in (('initiated','Initiate'),('credited','Creditor credits'),('debited','Bank debits'),('settled','Settles')))+'</div>'
        cards.append('<fieldset><legend>'+text(card_label(scenario,debt.account.account_id))+'</legend>'+field(f'priority_{i}','Priority (0 goes first)','number')+sections+'</fieldset>')
    hidden=''.join('<input type="hidden" name="'+k+'" value="'+text(v)+'">' for k,v in {'token':token,'source':source,'fingerprint':strategy_fingerprint(scenario)}.items())
    return shell('Plan future minimums','<h1>Plan future minimum payments</h1>'+('<p class="error">'+text(error)+'</p>' if error else '')+
        '<p>Uses the saved opening balances on '+text(scenario.start)+'. This is a new what-if forecast from that date, not a current bank balance update.</p>'+terms_table(scenario)+
        '<p>Supply two additional statement cycles and three payment opportunities per card. Existing payment requests—including extras—are replaced for this preview by generated minimum-only requests. Nothing is saved or paid.</p>'+
        '<p>Dates use midnight in '+text(scenario.debts[0].credit_timezone)+'. Initiation must precede credit, then debit, then settlement; equal dates are allowed. Each payment must settle before the next card’s payment begins. This limited timing model may not fit your autopay schedule.</p>'+
        '<form method="post" action="/personal-forecast-preview">'+hidden+field('end','Last debt forecast date')+''.join(cards)+
        '<p>Saved recurring income and bills will expand through the new cash-check horizon (at least 90 days after the last payment initiation). Their stop dates remain in effect. One-time entries stay one-time. No new bills or income are inferred.</p>'+
        '<label><input required type="checkbox" name="ack" value="understood"> I understand this uses only the supplied cash schedule and replaces existing payment requests in this preview.</label><button>Calculate minimum-only preview</button></form><p><a href="/scenario/'+text(source)+'">Back to original plan</a></p>')


@decimal_context
def calculate(scenario,values):
    eligibility(scenario)
    expected={'end','ack'}|{f'priority_{i}' for i in range(len(scenario.debts))}|{f'c_{i}_{j}_{key}' for i in range(len(scenario.debts)) for j in range(2) for key in ('start','end','statement','due')}|{f'p_{i}_{j}_{key}' for i in range(len(scenario.debts)) for j in range(3) for key in ('initiated','credited','debited','settled')}
    if set(values)!=expected or values['ack']!='understood':raise ValueError('Complete all schedule fields and acknowledge the preview scope.')
    tz=ZoneInfo(scenario.debts[0].credit_timezone)
    def at(value):return datetime.combine(date.fromisoformat(value),time(),tzinfo=tz)
    end=at(values['end'])
    if not scenario.end<=end or (end-scenario.start).total_seconds()>366*86400:
        raise ValueError('Choose an end at or after the saved forecast end, within 366 days of its start.')
    schedules=[];all_slots=[]
    for i,debt in enumerate(scenario.debts):
        cycles=list(debt.cycles)
        for j in range(2):
            row={key:date.fromisoformat(values[f'c_{i}_{j}_{key}']) for key in ('start','end','statement','due')}
            latest=max(c.end_date for c in cycles)
            if row['start']!=latest+timedelta(days=1):raise ValueError('Additional cycles must follow saved cycles without a gap or overlap.')
            id_=f'forecast-{i}-{j}'
            if any(c.cycle_id==id_ for c in cycles):raise ValueError('Forecast cycle ID already exists in this plan.')
            cycles.append(BillingCycle(account_id=debt.account.account_id,cycle_id=id_,start_date=row['start'],end_date=row['end'],statement_date=row['statement'],due_date=row['due']))
        if max(c.end_date for c in cycles)<end.date():raise ValueError('Statement cycles must cover the full debt forecast.')
        slots=tuple(PaymentSlot(slot_id=f'forecast-{i}-{j}',**{key+'_at':at(values[f'p_{i}_{j}_{key}']) for key in ('initiated','credited','debited','settled')}) for j in range(3))
        priority=int(values[f'priority_{i}'])
        schedules.append(CardMinimumSchedule(debt=reconstruct(debt,cycles=tuple(cycles)),terms=MinimumTerms(floor=debt.account.minimum_payment_floor.value,rate=debt.account.minimum_payment_rate.value),slots=slots,priority=priority))
        all_slots.extend(slots)
    horizon=cash_horizon(scenario.start,end,all_slots)
    plans=expand_cash_events(scenario.manual_cash_schedules,scenario.start,horizon,scenario.debts[0].credit_timezone) if scenario.manual_cash_schedules else scenario.cash_plans
    if len(plans)>500:raise ValueError('Expanded cash schedule exceeds 500 events. Use a shorter forecast.')
    result=forecast_portfolio_minimums(tuple(schedules),scenario.openings[0],plans,scenario.start,end)
    return result,plans,end


@decimal_context
def preview(scenario,source,values):
    result,plans,end=calculate(scenario,values)
    requests={r.request_id:r for r in result.requests}
    rows=''.join('<tr>'+''.join('<td>'+text(v)+'</td>' for v in (card_label(scenario,d.debt_account_id),requests[d.request_id].initiated_at.date(),requests[d.request_id].credited_at.date(),requests[d.request_id].debited_at.date(),requests[d.request_id].settled_at.date(),money(d.requested),money(d.accepted),money(d.unmet)))+'</tr>' for d in result.decisions)
    debts=''.join('<li>'+text(card_label(scenario,d.account.account_id))+': posted '+money(d.account.total_balance())+', unposted interest '+money(sum((s.accrued_unposted_interest for s in d.account.segments),Decimal(0)))+'; missed minimum dates: '+text(', '.join(map(str,d.missed_due_dates)) or 'none in this window')+'</li>' for d in result.debts)
    cash=result.liquidity.points[-1].positions[0]
    cashrows=''.join('<tr>'+''.join('<td>'+text(v)+'</td>' for v in (p.plan_id,p.kind.value,p.initiated_at.isoformat(),money(p.amount)))+'</tr>' for p in plans)
    rows = rows or '<tr><td colspan="8">No minimum payment was due at the supplied opportunities.</td></tr>'
    cashrows = cashrows or '<tr><td colspan="4">No income or bills were supplied.</td></tr>'
    warnings=any(d.unmet for d in result.decisions) or any(d.missed_due_dates for d in result.debts) or result.liquidity.status.value!='healthy'
    return shell('Personal minimum forecast','<h1>Minimum-only forecast: '+text(scenario.name)+'</h1><p>'+('Synthetic saved example.' if scenario.origin=='synthetic_demo' else 'Based on your saved inputs; estimates remain estimates.')+' No money has moved. This preview is not saved.</p>'+
        '<p class="'+('error' if warnings else 'note')+'">'+('Needs attention: review shortfalls, missed dates and cash status below.' if warnings else 'No missed minimums or cash shortages were found within the supplied windows.')+'</p>'+
        '<p>Debt ends '+text(end.date())+'; cash checks end '+text(result.liquidity.end.date())+'. Ending checking: '+money(cash.cleared)+'. Floor: '+money(scenario.openings[0].floor)+'. Reserved: '+money(cash.reserved)+'. Whole-window cash status: '+text(result.liquidity.status.value.replace('_',' '))+'. Ending cash is not a safe-to-spend recommendation.</p>'+
        '<section><h2>Generated minimum payments</h2><p>Dates use midnight in '+text(scenario.debts[0].credit_timezone)+'.</p><div class="scroll"><table><thead><tr><th>Card</th><th>Initiated</th><th>Credited</th><th>Debited</th><th>Settled</th><th>Requested</th><th>Applied</th><th>Unfunded</th></tr></thead><tbody>'+rows+'</tbody></table></div><p>Zero-minimum opportunities produce no request. Unfunded amounts may repeat unpaid obligations; do not add them to your debt.</p></section><section><h2>Debt at the end</h2><ul>'+debts+'</ul></section><section><h2>Cash events included</h2><p>Check these entries through the cash horizon. Missing bills are not protected automatically.</p><div class="scroll"><table><thead><tr><th>Entry</th><th>Kind</th><th>Initiation</th><th>Amount</th></tr></thead><tbody>'+cashrows+'</tbody></table></div></section><section><h2>Terms used</h2>'+terms_table(scenario)+'</section><p>No extra payments, full payoff date, or optimized priority. Original requests were replaced for this preview only. To change dates, use your browser’s Back button.</p><p><a href="/scenario/'+text(source)+'">Return to original plan</a></p>')
