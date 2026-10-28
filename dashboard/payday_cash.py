"""Bounded cash-only draft before payday; no income or extra-debt recommendation."""
from datetime import datetime,time,timedelta
from decimal import Decimal
from hashlib import sha256
import json
import os
from pathlib import Path
import tempfile
from typing import Literal
from uuid import uuid4
from zoneinfo import ZoneInfo
from pydantic import model_validator
from SCHEMA import StrictModel,ProvenanceSource
from engine.common import Nonnegative,decimal_context
from engine.liquidity import CashOpening,CashPlan,CashKind,project_liquidity
from dashboard import bills,my_money
from dashboard.scenarios import _unique_object
from dashboard.simple_view import page,tile
from dashboard.report import text,money

FILENAME='payday_budget.json'
ZONE='America/Chicago'


class EverydayBudget(StrictModel):
    version:Literal[1]=1
    food:Nonnegative
    fuel:Nonnegative

    @model_validator(mode='after')
    @decimal_context
    def cents(self):
        if self.food%Decimal('.01') or self.fuel%Decimal('.01'):raise ValueError('Use whole-cent spending cushions.')
        return self


class DraftInputs(StrictModel):
    version:Literal[1]=1
    snapshot:my_money.MoneySnapshot
    book:bills.BillBook
    budget:EverydayBudget


def digest(model):return sha256(model.model_dump_json().encode()).hexdigest()


def _read(path,model):
    with Path(path).open('rb') as stream:raw=stream.read(262145)
    if len(raw)>262144:raise ValueError('Cash draft file too large.')
    data=json.loads(raw,object_pairs_hook=_unique_object)
    if not isinstance(data,dict) or type(data.get('version')) is not int:raise ValueError('Unsupported cash draft version.')
    return model.model_validate(data)


def load_budget(directory):return _read(Path(directory)/FILENAME,EverydayBudget)


def save_budget(directory,budget):
    directory=Path(directory);budget=EverydayBudget.model_validate_json(budget.model_dump_json());target=directory/FILENAME
    if target.exists():
        old=load_budget(directory);history=directory/'payday_budget_history';history.mkdir(exist_ok=True)
        prior=history/(digest(old)+'.json')
        if not prior.exists():
            with prior.open('x') as stream:stream.write(old.model_dump_json(indent=2))
    temp=None
    try:
        with tempfile.NamedTemporaryFile(mode='w',dir=directory,prefix='.payday-',delete=False) as stream:
            temp=Path(stream.name);stream.write(budget.model_dump_json(indent=2));stream.flush();os.fsync(stream.fileno())
        os.replace(temp,target);temp=None
    finally:
        if temp is not None:temp.unlink(missing_ok=True)


def load_inputs(directory):
    return DraftInputs(snapshot=my_money.load(directory),book=bills.load(directory),budget=load_budget(directory))


@decimal_context
def calculate(inputs):
    snapshot=inputs.snapshot;tz=ZoneInfo(ZONE)
    if my_money.needs_next_payday(snapshot):
        raise ValueError('Paycheck already received. Confirm the next payday before making a new forecast.')
    days=(snapshot.expected_payday-snapshot.reported_on).days
    if not 1<=days<=60:raise ValueError('Update the reported balance date and expected payday: payday must be 1 to 60 days after the balances.')
    start=datetime.combine(snapshot.reported_on,time(),tzinfo=tz)
    end=datetime.combine(snapshot.expected_payday,time(),tzinfo=tz)-timedelta(microseconds=1)
    cushion=inputs.budget.food+inputs.budget.fuel
    openings=(CashOpening(account_id='checking',cleared=snapshot.checking,floor=snapshot.checking_floor,
        reserved=cushion,primary=True,provenance=ProvenanceSource.USER_PROVIDED_ESTIMATE),
        CashOpening(account_id='bills_box',cleared=snapshot.bills_box,floor='0',eligible=False,
        provenance=ProvenanceSource.USER_PROVIDED_ESTIMATE))
    plans=[];included=[];unresolved=[];outside=[]
    for bill in sorted(bills.effective(inputs.book,snapshot),key=lambda b:(b.due is None,b.due or snapshot.expected_payday,b.name)):
        if bill.status in ('covered','exclude'):continue
        if bill.due is None:
            unresolved.append((bill,'No due date; not deducted.'));continue
        if bill.due<snapshot.reported_on:
            unresolved.append((bill,'Before the reported balance date; unpaid status needs checking.'));continue
        if bill.due==snapshot.reported_on:
            unresolved.append((bill,'Same date as starting balances; payment order is unknown.'));continue
        if bill.due>=snapshot.expected_payday:
            outside.append(bill);continue
        if bill.route in ('savor','quicksilver'):
            unresolved.append((bill,'Charge to a card; no checking deduction or debt projection here.'));continue
        if bill.route not in ('checking','bills_box'):
            unresolved.append((bill,'Funding transfer timing or payment account needs checking.'));continue
        included.append(bill)
        if not bill.amount:continue
        at=datetime.combine(bill.due,time(),tzinfo=tz)
        kind=CashKind.PAYMENT if bill.cash_kind=='debt_payment' else CashKind.EXPENSE
        plans.append(CashPlan(plan_id='bill:'+bill.bill_id,kind=kind,amount=bill.amount,
            source_account_id=bill.route,initiated_at=at,credited_at=at,debited_at=at,settled_at=at,
            provenance=ProvenanceSource.USER_PROVIDED_ESTIMATE))
    result=project_liquidity(openings,tuple(plans),start,end_at=end)
    return result,tuple(included),tuple(unresolved),tuple(outside)


def save_draft(directory,inputs):
    inputs=DraftInputs.model_validate_json(inputs.model_dump_json());calculate(inputs)
    folder=Path(directory)/'payday_drafts';folder.mkdir(exist_ok=True);id_=uuid4().hex
    # Serialize completely before exposing the new path, and never overwrite a draft.
    raw=inputs.model_dump_json(indent=2);temp=None
    try:
        with tempfile.NamedTemporaryFile(mode='w',dir=folder,prefix='.draft-',delete=False) as stream:
            temp=Path(stream.name);stream.write(raw);stream.flush();os.fsync(stream.fileno())
        os.link(temp,folder/(id_+'.json'))
    finally:
        if temp is not None:temp.unlink(missing_ok=True)
    return id_


def load_draft(directory,id_):return _read(Path(directory)/'payday_drafts'/(id_+'.json'),DraftInputs)


def budget_form(budget,token,values=None,error=''):
    values=values if values is not None else {'food':str(budget.food),'fuel':str(budget.fuel)}
    return page('Everyday spending cushion','<div class="hero"><h1>Keep room for everyday spending.</h1><p>Set aside a cushion in checking for the period before payday. This is protected money, not a prediction that it has already been spent.</p></div>'+('<p class="banner warning" role="alert">'+text(error)+'</p>' if error else '')+'<form method="post" action="/cash-until-payday/budget-save"><input type="hidden" name="token" value="'+text(token)+'"><input type="hidden" name="fingerprint" value="'+digest(budget)+'"><section><div class="grid"><label>Food cushion ($)<input required type="number" min="0" step="0.01" name="food" value="'+text(values.get('food',''))+'"></label><label>Fuel cushion ($)<input required type="number" min="0" step="0.01" name="fuel" value="'+text(values.get('fuel',''))+'"></label></div><p class="muted">These cushions are in addition to the checking floor. They are held in full from the starting balance date, regardless of how many days remain. Update balances after real spending; this does not update them automatically.</p><button class="action">Save cushions</button> <a href="/cash-until-payday">Cancel</a></section></form>')


@decimal_context
def render(inputs,token=None,*,saved=False):
    if my_money.needs_next_payday(inputs.snapshot):return my_money.render_received(inputs.snapshot)
    result,included,unresolved,outside=calculate(inputs);snapshot=inputs.snapshot
    positions={p.account_id:p for p in result.points[-1].positions}
    tz=ZoneInfo(ZONE);before=snapshot.expected_payday-timedelta(days=1)
    rows=[]
    for point in result.points:
        if not point.trigger_ids:continue
        positions_at={p.account_id:p for p in point.positions}
        labels=[]
        for event in point.trigger_ids:
            # Cash events expose stage suffixes; match exact known bill IDs below.
            for b in included:
                if event==('bill:'+b.bill_id) or event.startswith('bill:'+b.bill_id+':'):
                    if b.name not in labels:labels.append(b.name)
        rows.append('<tr>'+''.join('<td>'+text(v)+'</td>' for v in (point.at.astimezone(tz).strftime('%b %d'),', '.join(labels) or 'Bill activity',money(positions_at['checking'].cleared),money(positions_at['bills_box'].cleared)))+'</tr>')
    issues=''.join('<li>'+text(b.name)+': '+text(reason)+'</li>' for b,reason in unresolved)
    bill_rows=''.join('<li><div><strong>'+text(b.name)+'</strong><span>'+text(b.due.strftime('%b %d'))+' · '+text(bills.ROUTES[b.route])+' · '+('unverified estimate' if b.status=='estimate' else 'included in draft')+'</span></div><strong class="number">'+money(b.amount)+'</strong></li>' for b in included)
    warning=result.status.value!='healthy'
    controls=('<p class="sample">Saved draft · uses the figures captured when saved</p><p>Later updates to your balances, bills or cushions do not change this saved picture.</p>' if saved else '')
    if token is not None:
        controls+='<form method="post" action="/cash-until-payday/save"><input type="hidden" name="token" value="'+text(token)+'"><input type="hidden" name="fingerprint" value="'+digest(inputs)+'"><button class="action">Save this cash draft</button></form>'
    navigation=('<a class="action secondary" href="/cash-until-payday">Open current cash picture</a>' if saved else '<a class="action" href="/paycheck-week">See payday and the following week</a><a class="action secondary" href="/cash-until-payday/budget">Adjust spending cushions</a>')
    return page('Before payday','<div class="hero"><span class="eyebrow">Your cash picture</span><h1>What needs covering before payday?</h1><p>From your reported balances on '+text(snapshot.reported_on.strftime('%B %d, %Y'))+' through '+text(before.strftime('%B %d, %Y'))+'. Your expected '+money(snapshot.expected_paycheck)+' paycheck on '+text(snapshot.expected_payday.strftime('%B %d'))+' is outside this view.</p></div>'+controls+'<div class="banner '+('warning' if warning or unresolved else '')+'"><strong>'+('The modeled bills or protections exceed available cash.' if warning else 'Included bills fit; some items still need checking.' if unresolved else 'The modeled bills fit these dated balances.')+'</strong><p>This is a conditional draft: estimated bills are treated as unpaid and included on their draft dates. Unknown items remain listed below. No extra-payment recommendation is calculated.</p></div><div class="cards">'+tile('Checking after modeled bills',money(positions['checking'].cleared),'Cash remaining before everyday spending. Includes the protections below; not an available-to-spend amount.')+tile('Bills Box after modeled bills',money(positions['bills_box'].cleared),'Stays in Bills Box for bills. No transfer to checking or extra debt payment is assumed.')+tile('Protected in checking',money(snapshot.checking_floor+inputs.budget.food+inputs.budget.fuel),money(snapshot.checking_floor)+' floor + '+money(inputs.budget.food)+' food + '+money(inputs.budget.fuel)+' fuel. These are settings, not proof they are fully funded.')+'</div><p class="muted">Spending cushions are one total for this entire '+str((snapshot.expected_payday-snapshot.reported_on).days)+'-day period, not weekly repeats or recorded spending.</p><section><h2>Bills in this cash draft</h2><ul class="payment-list">'+(bill_rows or '<li>No dated cash bills inside this period.</li>')+'</ul><p class="muted">Bills Box is used only for its own bills; it is not treated as money for extra card payments. Card and loan payments here show bank outflows only; card balances and interest are not projected in this view.</p></section><section><h2>How the two balances change</h2><p>Starting checking '+money(snapshot.checking)+'; starting Bills Box '+money(snapshot.bills_box)+'. Dates are modeled together at midnight in America/Chicago; bank timing is not verified.</p><div class="scroll"><table><thead><tr><th>Date</th><th>Modeled bills</th><th>Checking cash</th><th>Bills Box cash</th></tr></thead><tbody>'+(''.join(rows) or '<tr><td colspan="4">No modeled bill activity.</td></tr>')+'</tbody></table></div><p>Whole-period cash check: '+text(result.status.value.replace('_',' '))+'. '+('A floor/reserve or cash shortage occurs in this draft.' if warning else 'This only checks the supplied draft events and protection settings.')+'</p></section><details'+(' open' if unresolved else '')+'><summary>Not resolved in this draft ('+str(len(unresolved))+')</summary><ul>'+(issues or '<li>No unresolved items from this bill list.</li>')+'</ul><p>Excluded or already-reflected bills are not deducted. Missing obligations, pending transactions and unlisted spending are not automatically inferred.</p></details><details><summary>Payday and later ('+str(len(outside))+')</summary><p>Paycheck funding, automatic transfers and payday bills are outside this view. Their ordering must be resolved for a forecast that includes payday.</p><ul>'+''.join('<li>'+text(b.name)+' · '+text(b.due)+' · '+money(b.amount)+'</li>' for b in outside)+'</ul></details><div class="actions">'+navigation+'<a href="/cash-until-payday/saved">Saved cash drafts</a><a href="/bills">Review bills</a><a href="/my-money">My Money</a></div><p class="muted">This view does not update bank balances, schedule payments or move money.</p>')


def library(directory):
    rows=[];folder=Path(directory)/'payday_drafts'
    for path in sorted(folder.glob('*.json'),key=lambda p:p.stat().st_mtime,reverse=True):
        import re
        if not re.fullmatch(r'[0-9a-f]{32}',path.stem):continue
        try:
            inputs=load_draft(directory,path.stem)
            rows.append('<li><a href="/cash-draft/'+path.stem+'">Before payday '+text(inputs.snapshot.expected_payday)+'</a><small>Balances reported '+text(inputs.snapshot.reported_on)+' · saved inputs, not live balances</small></li>')
        except (ValueError,OSError,ArithmeticError):rows.append('<li>A saved draft could not be opened. Its file was kept.</li>')
    return page('Saved cash drafts','<div class="hero"><h1>Saved cash drafts</h1><p>Each draft keeps the balances, bills and cushions used when you saved it. Later edits do not change it.</p></div><ul class="plan-list">'+(''.join(rows) or '<li>No cash drafts saved yet.</li>')+'</ul><a class="action" href="/cash-until-payday">Open the current cash picture</a>')
