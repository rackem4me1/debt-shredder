"""Read-only weekly allocation comparisons; not a dated liquidity forecast."""
from datetime import date
from decimal import ROUND_CEILING
from pathlib import Path
from typing import Literal
from urllib.parse import parse_qs
from pydantic import Field,model_validator
from SCHEMA import StrictModel
from engine.common import Nonnegative,CENT,ZERO,decimal_context,decimal_input
from payoff_cli import _parse_json
from dashboard.report import text,money
from dashboard.simple_view import page,tile

FILENAME='weekly_system_check.json'
MAX_BYTES=65536


class Allocation(StrictModel):
    name: str=Field(min_length=1,max_length=100)
    weekly: Nonnegative=Field(le=1000000000)
    status: Literal['reported','estimated','intended']


class PayCase(StrictModel):
    name: str=Field(min_length=1,max_length=100)
    net: Nonnegative=Field(le=1000000000)


class Goal(StrictModel):
    name: str=Field(min_length=1,max_length=100)
    balance: Nonnegative=Field(le=1000000000)
    target: Nonnegative=Field(le=1000000000)
    weekly: Nonnegative=Field(le=1000000000)
    opportunities: int=Field(strict=True,ge=1,le=520)


class WeeklyCheck(StrictModel):
    format: Literal['debt-shredder-weekly-check']='debt-shredder-weekly-check'
    version: Literal[1]=1
    reported_on: date
    origin: Literal['reported','synthetic_demo']='reported'
    fixed: tuple[Allocation,...]=Field(max_length=30)
    pay_cases: tuple[PayCase,...]=Field(min_length=1,max_length=10)
    bills_weekly: Nonnegative=Field(le=1000000000)
    bills_monthly_budget: Nonnegative=Field(le=1000000000)
    goal: Goal
    housing_weekly: Nonnegative=Field(default=ZERO,le=1000000000)
    unresolved: tuple[str,...]=Field(default=(),max_length=30)

    @model_validator(mode='after')
    @decimal_context
    def valid(self):
        amounts=[self.bills_weekly,self.bills_monthly_budget,self.housing_weekly,self.goal.balance,self.goal.target,self.goal.weekly]
        amounts.extend(a.weekly for a in self.fixed);amounts.extend(p.net for p in self.pay_cases)
        if any(v%CENT for v in amounts):raise ValueError('Use whole cents')
        for collection in (self.fixed,self.pay_cases):
            names=[a.name for a in collection]
            if len(set(names))!=len(names) or any(not name.strip() for name in names):raise ValueError('Use distinct nonblank names')
        if not self.goal.name.strip() or any(not v.strip() or len(v)>1000 for v in self.unresolved):raise ValueError('Use nonblank bounded labels')
        return self


def load(directory):
    with (Path(directory)/FILENAME).open('rb') as stream:raw=stream.read(MAX_BYTES+1)
    if len(raw)>MAX_BYTES:raise ValueError('Weekly report too large')
    return WeeklyCheck.model_validate(_parse_json(raw))


@decimal_context
def calculate(value,query=''):
    if len(query)>2048:raise ValueError('Comparison query too long')
    params=parse_qs(query,keep_blank_values=True,strict_parsing=True,max_num_fields=7)
    if set(params)-{'pool','rent','bills','back','spend','weeks','pay'} or any(len(v)!=1 for v in params.values()):raise ValueError('Use the weekly comparison form')
    raw_pay=params.pop('pay',[''])[0]
    custom_pay=decimal_input(raw_pay) if raw_pay!='' else None
    if custom_pay is not None and (custom_pay<0 or custom_pay>1000000000 or custom_pay%CENT):raise ValueError('Use a nonnegative whole-cent take-home paycheck')
    pay_cases=value.pay_cases+((PayCase(name='Trial paycheck (illustration)',net=custom_pay),) if custom_pay is not None else ())
    raw_weeks=params.pop('weeks',[str(value.goal.opportunities)])[0]
    if not raw_weeks.isascii() or not raw_weeks.isdigit() or not 1<=int(raw_weeks)<=520:raise ValueError('Use 1–520 remaining weekly contributions')
    opportunities=int(raw_weeks)
    defaults={'pool':value.goal.weekly,'rent':value.housing_weekly,'bills':value.bills_weekly,'back':ZERO,'spend':ZERO}
    choices={k:decimal_input(params[k][0]) if k in params else v for k,v in defaults.items()}
    if any(v<0 or v>1000000000 or v%CENT for v in choices.values()):raise ValueError('Use nonnegative whole-cent weekly amounts')
    base=sum((a.weekly for a in value.fixed),ZERO)
    current_total=base+value.goal.weekly+value.bills_weekly+value.housing_weekly
    tested_total=base+choices['pool']+choices['rent']+choices['bills']
    drawn=choices['back']+choices['spend']
    if drawn>value.goal.balance:raise ValueError('One-time transfers and spending exceed the reported fund balance')
    balance_after=value.goal.balance-drawn
    remaining=max(ZERO,value.goal.target-balance_after)
    goal_rate=(remaining/opportunities).quantize(CENT,rounding=ROUND_CEILING)
    return {'choices':choices,'base':base,'current_total':current_total,'tested_total':tested_total,
        'rows':tuple((p.name,p.net,p.net-current_total,p.net-tested_total) for p in pay_cases),
        'custom_pay':custom_pay,
        'goal_rate':goal_rate,'goal_end':balance_after+choices['pool']*opportunities,
        'goal_shortfall':max(ZERO,value.goal.target-balance_after-choices['pool']*opportunities),
        'opportunities':opportunities,'balance_after':balance_after,
        'supported_rows':tuple((p.name,p.net-tested_total,p.net-tested_total+choices['back']) for p in pay_cases),
        'bills_monthly_average':choices['bills']*52/12,
        'bills_monthly_gap':value.bills_monthly_budget-choices['bills']*52/12}


@decimal_context
def render(value,query='',*,save_section='',retained=False):
    r=calculate(value,query);choices=r['choices']
    rows=''.join('<tr>'+''.join('<td>'+text(v)+'</td>' for v in (name,money(net),money(current),money(tested)))+'</tr>' for name,net,current,tested in r['rows'])
    fixed=''.join('<li>'+text(a.name)+': '+money(a.weekly)+' / week · '+text(a.status)+'</li>' for a in value.fixed)
    def field(key,label,amount,*,whole=False,required=True):
        return '<label>'+text(label)+'<input type="number" step="'+('1' if whole else '0.01')+'" min="'+('1' if whole else '0')+'" max="'+('520' if whole else '1000000000')+'"'+(' required' if required else '')+' name="'+key+'" value="'+text('' if amount is None else amount)+'"></label>'
    controls=''.join(field(k,label,choices[k]) for k,label in (('pool',value.goal.name+' automatic contribution / week ($)'),('rent','Optional housing savings / week ($)'),('bills','Bills account funding / week ($)')))
    controls+=field('pay','Try a specific take-home paycheck ($), optional',r['custom_pay'],required=False)
    one_time=field('back','One-time transfer back to checking ($)',choices['back'])+field('spend','One-time spending directly from this fund ($)',choices['spend'])+field('weeks','Remaining weekly contributions to test',r['opportunities'],whole=True)
    warning=('<p class="banner warning">At least one pay scenario is short on these weekly allocations alone. One-time support is shown separately below; it does not fix recurring weekly funding. This is not a predicted overdraft.</p>' if any(row[3]<0 for row in r['rows']) else '<p class="banner">These listed weekly allocations fit the tested pay amounts. Unlisted spending, pending items and account timing can still change the outcome. This is not a safe-extra amount.</p>')
    goal_note=('The goal is covered by these assumed contributions.' if not r['goal_shortfall'] else '<strong>These assumed contributions do not reach the target. Goal shortfall: '+money(r['goal_shortfall'])+'.</strong>')
    bills_note=('Average funding is below the listed bill budget by '+money(r['bills_monthly_gap'])+' per month.' if r['bills_monthly_gap']>0 else 'Average funding meets or exceeds the listed bill budget. Dated withdrawal coverage is still unverified.')
    unknowns='<ul>'+''.join('<li>'+text(v)+'</li>' for v in value.unresolved)+'</ul>' if value.unresolved else '<p>Confirm pending items, protected cash, statement payments and withdrawal dates before using this as a dated cash plan.</p>'
    support=''
    if choices['back']:
        support_rows=''.join('<tr>'+''.join('<td>'+text(v)+'</td>' for v in (name,money(before),money(choices['back']),money(after)))+'</tr>' for name,before,after in r['supported_rows'])
        support='<section><h2>One tight week: transfer-back illustration</h2><p>The same '+money(choices['back'])+' transfer is tested against each alternative pay scenario for ONE chosen week. It is not new income and is not repeated in later weeks. It reduces the fund balance once and supports checking once, only if accessible money settles before it is needed.</p><div style="overflow-x:auto"><table><thead><tr><th>Alternative pay scenario</th><th>Before support</th><th>One-time support</th><th>After support for this week</th></tr></thead><tbody>'+support_rows+'</tbody></table></div><p>A positive result here does not certify account liquidity or remove future low-pay gaps.</p></section>'
    header='<div class="hero"><span class="sample">'+('Sample inputs' if value.origin=='synthetic_demo' else 'Reported planning inputs')+' · '+text(value.reported_on.strftime('%b %d, %Y'))+(' · Saved comparison' if retained else '')+'</span><h1>Does my weekly setup hold up?</h1><p>Keep the reported automatic contributions and test a transfer back during a tight week, or compare a different funding mix. No bank, payroll or saved budget setting changes here.</p></div>'
    form='<section><h2>Try a different funding mix</h2><form method="get" action="/weekly-check"><div class="grid">'+controls+'</div><details'+(' open' if choices['back'] or choices['spend'] or r['opportunities']!=value.goal.opportunities else '')+'><summary>Test a withdrawal and recheck the goal</summary><div class="grid">'+one_time+'</div><p>Use a transfer back when money supports checking. Use direct spending for a tournament, trip or other fund expense. Do not enter the same withdrawal in both fields. The combined amount cannot exceed the reported fund balance; future automatic deposits are not available today.</p></details><button>Compare this weekly mix</button> <a href="/weekly-check">Reset trial to reported plan</a></form><p>Values entered here are illustrations only. They are not saved or activated at a bank. Both comparison columns use the same historical pay scenarios. An optional trial paycheck is a what-if take-home amount, not a received deposit; no gross-to-net pay conversion is assumed.</p></section>'
    if retained:
        form='<p class="banner">This is a retained comparison with its original inputs and contribution count. It does not refresh as time passes. <a href="/weekly-check">Open the current weekly report</a> to test a new mix.</p>'
    weekly='<section><h2>What each pay scenario leaves unassigned each week</h2>'+warning+'<div style="overflow-x:auto"><table><thead><tr><th>Scenario</th><th>Take-home pay</th><th>Reported plan</th><th>Tested recurring mix</th></tr></thead><tbody>'+rows+'</tbody></table></div><p>Historical pay is not a guaranteed future minimum. Negative means these allocations alone exceed that pay amount. Positive figures are before any unlisted expenses and balance protections. One-time transfers or fund spending are not added to this recurring table.</p></section>'
    goal='<section><h2>'+text(value.goal.name)+': deadline first, surplus over time</h2><p>Reported fund balance: '+money(value.goal.balance)+'. Target: '+money(value.goal.target)+'. Trial transfer back: '+money(choices['back'])+'. Trial direct spending: '+money(choices['spend'])+'. Balance after those one-time withdrawals: '+money(r['balance_after'])+'.</p><p>Assuming the entire balance counts toward this target and '+str(r['opportunities'])+' more weekly contributions arrive, the goal-only rate after these withdrawals is '+money(r['goal_rate'])+'/week. The tested automatic contribution stays '+money(choices['pool'])+'/week.</p><p>The tested contribution would produce '+money(r['goal_end'])+' in the fund. '+goal_note+' This covers the stated target only, not all future activities or trips. The projection assumes no withdrawals beyond the two trial amounts, and the fund balance is not treated as recurring income.</p><p>The remaining contribution count is a planning assumption, not a verified payment calendar. Earlier spending or fewer deposits changes the required rate. Recheck the goal after any withdrawal.</p></section>'
    bills='<section><h2>Bill funding check</h2><p>Listed monthly bill budget: '+money(value.bills_monthly_budget)+'. The tested weekly funding averages '+money(r['bills_monthly_average'])+'/month over52 paychecks. '+bills_note+'</p><p>Weekly bill-account and loan funding is counted once. Monthly bills and loan payments paid from that funding are not subtracted again here. Internal transfers remain internal allocations, not additional household spending.</p></section>'
    body=header+'<p class="banner warning">A weekly budget screen, not a dated cash-flow forecast. Existing bank balances are not included in the recurring amounts below. An unassigned amount is not verified spare cash.</p><div class="cards">'+tile('Current listed allocations',money(r['current_total'])+'/week','Current means the reported funding plan, including intended and estimated items.')+tile('Tested recurring allocations',money(r['tested_total'])+'/week','One-time withdrawals stay separate from these recurring amounts.')+'</div>'+form+weekly+support+goal+bills+'<details><summary>Other weekly amounts included</summary><ul>'+fixed+'</ul></details><section><h2>Still needs review</h2>'+unknowns+'<p>Your earlier My Money entries and saved forecasts retain their original facts. This report does not refresh them or certify pending transactions as settled.</p></section>'+save_section+'<p><a href="/weekly-checks">Saved weekly comparisons</a> · <a href="/">Home</a> · <a href="/my-money">Earlier My Money snapshot</a></p>'
    return page('Weekly system check',body)


def render_error(value,query,error):
    """Keep validly encoded trial fields for correction without showing false results."""
    defaults={'pool':value.goal.weekly,'rent':value.housing_weekly,'bills':value.bills_weekly,'back':ZERO,'spend':ZERO,'weeks':value.goal.opportunities,'pay':''}
    try:
        if len(query)>2048:raise ValueError('Comparison query too long')
        params=parse_qs(query,keep_blank_values=True,strict_parsing=True,max_num_fields=7)
        if set(params)-set(defaults) or any(len(v)!=1 for v in params.values()):raise ValueError('Use the comparison form')
        defaults.update({key:rows[0] for key,rows in params.items()})
    except ValueError:
        error='Use one value per field in the comparison form. The reported defaults are shown below.'
    labels={'pool':value.goal.name+' automatic contribution / week ($)','rent':'Optional housing savings / week ($)','bills':'Bills account funding / week ($)','back':'One-time transfer back to checking ($)','spend':'One-time spending directly from this fund ($)','weeks':'Remaining weekly contributions to test','pay':'Trial take-home paycheck ($), optional'}
    fields=''
    for key,label in labels.items():
        whole=key=='weeks'
        fields+='<label>'+text(label)+'<input type="number" step="'+('1' if whole else '0.01')+'" min="'+('1' if whole else '0')+'" max="'+('520' if whole else '1000000000')+'"'+(' required' if key!='pay' else '')+' name="'+key+'" value="'+text(defaults[key])+'"></label>'
    return page('Correct the weekly trial','<div class="hero"><h1>Review these trial amounts.</h1><p>The report and bank settings are unchanged. No comparison was calculated or saved from these invalid entries.</p></div><p class="banner warning" role="alert">'+text(error)+'</p><p>The reported fund balance is '+money(value.goal.balance)+'. Combined one-time support and direct spending cannot exceed that balance; future deposits are not available today.</p><form method="get" action="/weekly-check"><section><div class="grid">'+fields+'</div><button>Recheck this trial</button></section></form><p><a href="/weekly-check">Reset trial to reported plan</a> · <a href="/weekly-checks">Saved comparisons</a></p>')
