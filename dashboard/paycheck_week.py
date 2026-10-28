"""One expected paycheck and seven-day follow-through, with explicit draft timing."""
from datetime import date,datetime,time,timedelta
from decimal import Decimal
from pathlib import Path
from typing import Literal
from uuid import uuid4
import os
import tempfile
from pydantic import Field,model_validator
from SCHEMA import StrictModel,ProvenanceSource
from engine.common import Money,Nonnegative,decimal_context
from engine.liquidity import CashOpening,CashPlan,CashKind,project_liquidity
from dashboard import payday_cash,bills,my_money
from dashboard.simple_view import page,tile
from dashboard.report import text,money

FILENAME='paycheck_settings.json'


class PaycheckSettings(StrictModel):
    version:Literal[1]=1
    bills_box_transfer:Nonnegative
    kc_transfer:Nonnegative
    kc_opening:Money|None=None
    kc_as_of:date|None=None
    bills_box_delay:int=Field(default=0,strict=True,ge=0,le=14)
    kc_delay:int=Field(default=0,strict=True,ge=0,le=14)
    food:Nonnegative
    fuel:Nonnegative

    @model_validator(mode='after')
    @decimal_context
    def cents(self):
        for name in ('bills_box_transfer','kc_transfer','kc_opening','food','fuel'):
            value=getattr(self,name)
            if value is not None and value%Decimal('.01'):raise ValueError('Use whole-cent money amounts.')
        if (self.kc_opening is None)!=(self.kc_as_of is None):
            raise ValueError('Supply both KC opening balance and its date, or leave both unknown.')
        return self


class WeekInputs(StrictModel):
    version:Literal[1]=1
    base:payday_cash.DraftInputs
    settings:PaycheckSettings


def load_settings(directory):return payday_cash._read(Path(directory)/FILENAME,PaycheckSettings)

def load_inputs(directory):return WeekInputs(base=payday_cash.load_inputs(directory),settings=load_settings(directory))


def save_settings(directory,settings):
    directory=Path(directory);target=directory/FILENAME
    settings=PaycheckSettings.model_validate_json(settings.model_dump_json())
    if target.exists():
        old=load_settings(directory);folder=directory/'paycheck_settings_history';folder.mkdir(exist_ok=True)
        prior=folder/(payday_cash.digest(old)+'.json')
        if not prior.exists():
            with prior.open('x') as stream:stream.write(old.model_dump_json(indent=2))
    temporary=None
    try:
        with tempfile.NamedTemporaryFile(mode='w',dir=directory,prefix='.week-',delete=False) as stream:
            temporary=Path(stream.name);stream.write(settings.model_dump_json(indent=2));stream.flush();os.fsync(stream.fileno())
        os.replace(temporary,target);temporary=None
    finally:
        if temporary is not None:temporary.unlink(missing_ok=True)


@decimal_context
def calculate(inputs,*,bills_first=False):
    base=inputs.base;settings=inputs.settings;snapshot=base.snapshot;tz=payday_cash.ZoneInfo(payday_cash.ZONE)
    if my_money.needs_next_payday(snapshot):
        raise ValueError('Paycheck already received. Confirm the next payday before making a new forecast.')
    if settings.kc_opening is not None and settings.kc_as_of!=snapshot.reported_on:
        raise ValueError('KC balance must have the same reported date as the My Money starting balances. Update its date/balance or leave both blank.')
    days=(snapshot.expected_payday-snapshot.reported_on).days
    if not 1<=days<=60:raise ValueError('Expected payday must be 1 to 60 days after reported balances.')
    start=datetime.combine(snapshot.reported_on,time(),tzinfo=tz)
    end=datetime.combine(snapshot.expected_payday+timedelta(days=7),time(),tzinfo=tz)-timedelta(microseconds=1)
    def at(day,hour):return datetime.combine(day,time(hour),tzinfo=tz)
    openings=[CashOpening(account_id='checking',cleared=snapshot.checking,floor=snapshot.checking_floor,
        reserved=base.budget.food+base.budget.fuel,primary=True,provenance=ProvenanceSource.USER_PROVIDED_ESTIMATE),
        CashOpening(account_id='bills_box',cleared=snapshot.bills_box,floor='0',eligible=False,
        provenance=ProvenanceSource.USER_PROVIDED_ESTIMATE)]
    if settings.kc_opening is not None:
        openings.append(CashOpening(account_id='kc_open',cleared=settings.kc_opening,floor='0',eligible=False,
            provenance=ProvenanceSource.USER_PROVIDED_ESTIMATE))
    plans=[];labels={};included=[];unresolved=[];outside=[];card_charges=[]
    def atomic(id_,label,kind,amount,when,account):
        if not amount:return
        labels[id_]=label
        plans.append(CashPlan(plan_id=id_,kind=kind,amount=amount,initiated_at=when,credited_at=when,
            debited_at=when,settled_at=when,source_account_id=account if kind!=CashKind.INCOME else None,
            destination_account_id=account if kind==CashKind.INCOME else None,
            provenance=ProvenanceSource.USER_PROVIDED_ESTIMATE))
    def transfer(id_,label,amount,account,delay):
        if not amount:return
        labels[id_]=label
        sent=at(snapshot.expected_payday,10)
        arrived=at(snapshot.expected_payday+timedelta(days=delay),10)
        plans.append(CashPlan(plan_id=id_,kind=CashKind.TRANSFER,amount=amount,source_account_id='checking',
            destination_account_id=account,initiated_at=sent,debited_at=sent,credited_at=arrived,settled_at=arrived,
            provenance=ProvenanceSource.ASSUMED_DEFAULT))
    atomic('expected-pay','Expected paycheck',CashKind.INCOME,snapshot.expected_paycheck,at(snapshot.expected_payday,9),'checking')
    transfer('fund-bills','Transfer to Bills Box',settings.bills_box_transfer,'bills_box',settings.bills_box_delay)
    if settings.kc_opening is None:
        atomic('hold-kc','Set aside for KC transfer (not moved)',CashKind.RESERVE,settings.kc_transfer,at(snapshot.expected_payday,10),'checking')
    else:transfer('fund-kc','Transfer to KC Open',settings.kc_transfer,'kc_open',settings.kc_delay)
    atomic('week-cushion','Protect next-week food and fuel',CashKind.RESERVE,settings.food+settings.fuel,at(snapshot.expected_payday,10),'checking')
    for bill in sorted(bills.effective(base.book,snapshot),key=lambda b:(b.due is None,b.due or snapshot.expected_payday,b.name)):
        if bill.status in ('covered','exclude'):continue
        if bill.due is None:
            unresolved.append((bill,'No due date; not deducted.'));continue
        if bill.due<=snapshot.reported_on:
            unresolved.append((bill,'On or before the opening balance date; payment status/order unresolved.'));continue
        if bill.due> end.astimezone(tz).date():outside.append(bill);continue
        if bill.route in ('savor','quicksilver'):
            card_charges.append(bill);continue
        if bill.route not in ('checking','bills_box'):
            unresolved.append((bill,'Checking payment funded by a transfer, or funding source missing; timing unresolved.'));continue
        included.append(bill)
        hour=7 if bills_first and bill.due==snapshot.expected_payday else 11
        atomic('bill:'+bill.bill_id,bill.name,CashKind.PAYMENT if bill.cash_kind=='debt_payment' else CashKind.EXPENSE,
               bill.amount,at(bill.due,hour),bill.route)
    result=project_liquidity(tuple(openings),tuple(plans),start,end_at=end)
    return result,tuple(included),tuple(unresolved),tuple(card_charges),tuple(outside),labels


def save_draft(directory,inputs):
    inputs=WeekInputs.model_validate_json(inputs.model_dump_json());calculate(inputs);calculate(inputs,bills_first=True)
    folder=Path(directory)/'paycheck_drafts';folder.mkdir(exist_ok=True);id_=uuid4().hex;temporary=None
    try:
        with tempfile.NamedTemporaryFile(mode='w',dir=folder,prefix='.draft-',delete=False) as stream:
            temporary=Path(stream.name);stream.write(inputs.model_dump_json(indent=2));stream.flush();os.fsync(stream.fileno())
        os.link(temporary,folder/(id_+'.json'))
    finally:
        if temporary is not None:temporary.unlink(missing_ok=True)
    return id_


def load_draft(directory,id_):return payday_cash._read(Path(directory)/'paycheck_drafts'/(id_+'.json'),WeekInputs)


FIELDS=(('bills_box_transfer','Transfer to Bills Box ($)','number'),('kc_transfer','KC transfer amount ($)','number'),
 ('kc_opening','KC balance on the reported balance date ($), optional','number'),
 ('kc_as_of','Date of that KC balance, optional','date'),
 ('bills_box_delay','Bills Box arrival delay (calendar days)','number'),('kc_delay','KC arrival delay (calendar days)','number'),
 ('food','Food cushion for the following week ($)','number'),('fuel','Fuel cushion for the following week ($)','number'))


def change(settings,values):
    if set(values)!={key for key,_,_ in FIELDS}:raise ValueError('Use the listed paycheck settings.')
    data=values|{'kc_opening':values['kc_opening'] or None,'kc_as_of':values['kc_as_of'] or None}
    for name in ('bills_box_delay','kc_delay'):
        if not values[name].isdigit():raise ValueError('Use whole calendar-day delays.')
        data[name]=int(values[name])
    return PaycheckSettings(**data)


def form(settings,token,values=None,error=''):
    values=settings.model_dump(mode='json') if values is None else values
    fields=''.join('<div><label for="week-'+key+'">'+text(label)+'</label><input id="week-'+key+'" name="'+key+'" type="'+kind+'" '+('' if key in ('kc_opening','kc_as_of') else 'required ')+('step="1" min="0" max="14" ' if key.endswith('delay') else '' if key=='kc_as_of' else 'step="0.01" ')+ 'value="'+text(values.get(key,'') if values.get(key) is not None else '')+'"></div>' for key,label,kind in FIELDS)
    return page('Paycheck assumptions','<div class="hero"><h1>Paycheck and transfer estimates</h1><p>Your expected paycheck and date come from My Money. These settings cover that one paycheck and the following seven days.</p></div>'+('<p class="banner warning" role="alert">'+text(error)+'</p>' if error else '')+'<form method="post" action="/paycheck-week/settings-save"><input type="hidden" name="token" value="'+text(token)+'"><input type="hidden" name="fingerprint" value="'+payday_cash.digest(settings)+'"><section><div class="grid">'+fields+'</div><p>Leave KC’s opening balance and date blank if unknown. When supplied, its date must match the reported starting date in My Money. When both are blank, the transfer amount stays protected in checking and no KC balance is invented. Supplying both enables internal-transfer modeling.</p><p>Delays are scenario assumptions in calendar days, not verified bank settlement terms. Zero means same-day arrival. This view also tests payday bills leaving before the deposit.</p><button class="action">Save estimates</button> <a href="/paycheck-week">Cancel</a></section></form>')


@decimal_context
def render(inputs,token=None,*,saved=False):
    if my_money.needs_next_payday(inputs.base.snapshot):return my_money.render_received(inputs.base.snapshot)
    normal=calculate(inputs);stress=calculate(inputs,bills_first=True)
    result,included,unresolved,charges,outside,labels=normal
    snapshot=inputs.base.snapshot;settings=inputs.settings;tz=payday_cash.ZoneInfo(payday_cash.ZONE)
    positions={p.account_id:p for p in result.points[-1].positions}
    uncertain=unresolved or settings.kc_opening is None or any(b.status=='estimate' for b in included)
    warning=result.status.value!='healthy' or stress[0].status.value!='healthy'
    daily={}
    for point in result.points:
        day=point.at.astimezone(tz).date()
        if not point.trigger_ids:continue
        row=daily.setdefault(day,{'labels':[],'positions':None,'transit':Decimal(0)})
        row['positions']={p.account_id:p for p in point.positions};row['transit']=point.in_transit
        for trigger in point.trigger_ids:
            name=labels.get(trigger,trigger)
            stages={a.stage for a in result.audit if a.at==point.at and a.plan_id==trigger}
            if trigger in ('fund-bills','fund-kc'):
                name+=' · completed' if 'settle' in stages else ' · sent, awaiting arrival'
            if name not in row['labels']:row['labels'].append(name)
    rows=''.join('<tr>'+''.join('<td>'+text(v)+'</td>' for v in (day.strftime('%b %d'),'; '.join(row['labels']),money(row['positions']['checking'].cleared),money(row['positions']['bills_box'].cleared),money(row['transit'])))+'</tr>' for day,row in sorted(daily.items()))
    controls='<p class="sample">Saved week draft · captured inputs, not live balances</p>' if saved else ''
    if token is not None:
        controls+='<form method="post" action="/paycheck-week/save"><input type="hidden" name="token" value="'+text(token)+'"><input type="hidden" name="fingerprint" value="'+payday_cash.digest(inputs)+'"><button class="action">Save this week draft</button></form>'
    kc=('<p>KC’s opening balance is unknown. '+money(settings.kc_transfer)+' is held in checking for that transfer, not shown as already moved.</p>' if settings.kc_opening is None else '<p>Modeled KC Open ending balance: '+money(positions['kc_open'].cleared)+'. It is not available for checking payments.</p>')
    pre=inputs.base.budget.food+inputs.base.budget.fuel;post=settings.food+settings.fuel
    status=lambda r:'No modeled cash shortage' if r.status.value=='healthy' else 'Cash protection or balance shortage'
    navigation='<a class="action secondary" href="/paycheck-week">Open current week picture</a>' if saved else '<a class="action secondary" href="/paycheck-week/settings">Adjust paycheck estimates</a>'
    return page('Payday and the following week','<div class="hero"><span class="eyebrow">One paycheck · following week</span><h1>Will the week stay covered?</h1><p>Uses balances reported '+text(snapshot.reported_on.strftime('%B %d, %Y'))+' and your expected '+money(snapshot.expected_paycheck)+' paycheck on '+text(snapshot.expected_payday.strftime('%B %d'))+'. Runs through '+text(result.end.astimezone(tz).strftime('%B %d, %Y'))+'.</p></div>'+controls+'<div class="banner '+('warning' if warning or uncertain else '')+'"><strong>'+('The timing test found a shortage.' if warning else 'The included events fit; this is still an estimate.')+'</strong><p>Old bill amounts/status, deposit timing and transfer arrival remain assumptions. Unknown items below prevent a complete coverage claim. No extra debt payment is recommended here.</p></div><div class="cards">'+tile('Checking before everyday spending',money(positions['checking'].cleared),'Includes reserved cushions and any pending KC hold. It is not a spending allowance.')+tile('Bills Box after modeled activity',money(positions['bills_box'].cleared),'Only completed transfers have arrived. This money remains for bills.')+tile('Protected in checking',money(positions['checking'].reserved+snapshot.checking_floor),money(snapshot.checking_floor)+' floor plus '+money(positions['checking'].reserved)+' held for spending or pending transfers.')+'</div><section><h2>How your paycheck is used</h2><ul><li>'+money(settings.bills_box_transfer)+' transfer to Bills Box; arrival delay '+str(settings.bills_box_delay)+' calendar day(s).</li><li>'+money(settings.kc_transfer)+' for KC Open.</li><li>'+money(post)+' protected for food and fuel after payday, in addition to the '+money(pre)+' pre-payday cushion.</li></ul>'+kc+'<p class="muted">Cushions are held as unspent money. No food or fuel spending is subtracted as an actual transaction, and the earlier cushion is not assumed spent or released. Only one paycheck is included; the next one is outside this window.</p></section><section><h2>Day-by-day cash picture</h2><p>Dates group modeled activity; the table shows each day’s final balances. Earlier shortages within the day are checked separately below. Starting checking '+money(snapshot.checking)+'; Bills Box '+money(snapshot.bills_box)+'.</p><div class="scroll"><table><thead><tr><th>Date</th><th>What is modeled</th><th>Checking</th><th>Bills Box</th><th>In transit</th></tr></thead><tbody>'+rows+'</tbody></table></div></section><section><h2>What if a payday bill leaves first?</h2><div class="cards">'+tile('Deposit before payday bills',status(result),'Assumed order: paycheck, transfers/cushions, then bills.')+tile('Payday bills before the deposit',status(stress[0]),'Same amounts, but payday bills leave before the expected deposit. A later deposit cannot erase an earlier shortage.')+'</div><p class="muted">These are two illustrative orderings, not verified bank times. Transfers start after the paycheck in both. Other same-day arrival/bill ordering, weekends and bank holidays are not verified.</p></section><details open><summary>Items still needing review</summary><ul>'+(''.join('<li>'+text(b.name)+': '+text(reason)+'</li>' for b,reason in unresolved) or '<li>No unresolved dates/routes from the bill list in this window.</li>')+'</ul>'+kc+'<p>Included cash bills: '+text(', '.join(b.name for b in included) or 'none')+'. They are treated as unpaid draft outflows. Saved balances are not updated automatically.</p></details><details><summary>Card charges and later bills</summary><ul>'+''.join('<li>'+text(b.name)+' · '+money(b.amount)+' · charged to a card; not deducted from checking and not added to a debt forecast here.</li>' for b in charges)+''.join('<li>'+text(b.name)+' · '+text(b.due)+' · outside this window.</li>' for b in outside)+'</ul><p>Excluded/already-reflected bills are omitted. Unlisted spending and missing obligations are not inferred.</p></details><div class="actions">'+navigation+'<a href="/paycheck-week/saved">Saved week drafts</a><a href="/my-money">My Money</a><a href="/bills">Bills</a><a href="/cash-until-payday">Before payday only</a></div><p class="muted">Scenario timing is represented in America/Chicago with an assumed morning deposit, later transfer and bill phases. Savings has no additional modeled floor and cannot fund extra checking payments. Internal transfers remain internal movements, never income or expense. Debt interest and bank transactions are not performed by this view.</p>')


def library(directory):
    import re
    rows=[]
    for path in sorted((Path(directory)/'paycheck_drafts').glob('*.json'),key=lambda p:p.stat().st_mtime,reverse=True):
        if not re.fullmatch(r'[0-9a-f]{32}',path.stem):continue
        try:
            inputs=load_draft(directory,path.stem)
            rows.append('<li><a href="/week-draft/'+path.stem+'">Payday '+text(inputs.base.snapshot.expected_payday)+' and following week</a><small>Balances reported '+text(inputs.base.snapshot.reported_on)+' · captured estimates</small></li>')
        except (ValueError,OSError,ArithmeticError):rows.append('<li>A saved week draft could not be opened. Its file was kept.</li>')
    return page('Saved week drafts','<div class="hero"><h1>Saved week drafts</h1><p>Each draft keeps the balances, bills, spending cushions and timing assumptions it used.</p></div><ul class="plan-list">'+(''.join(rows) or '<li>No week drafts saved yet.</li>')+'</ul><a class="action" href="/paycheck-week">Current week picture</a>')
