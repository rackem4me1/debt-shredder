"""Dated, user-reported starting picture; separate from hypothetical scenarios."""
from datetime import date
from decimal import Decimal
from hashlib import sha256
import json
import os
from pathlib import Path
import tempfile
from typing import Literal
from pydantic import Field, model_validator
from SCHEMA import StrictModel
from engine.common import Money, Nonnegative, decimal_context, reconstruct
from dashboard.scenarios import _unique_object
from dashboard.simple_view import page, tile
from dashboard.report import text, money

FILENAME='money_snapshot.json'


class ReceivedPaycheck(StrictModel):
    received_on: date
    amount: Nonnegative
    replaces_expected_payday: date
    automatic_transfers_completed: Literal[True]
    rent_balance: Money
    kc_balance: Money
    iphone_balance: Money

    @model_validator(mode='after')
    @decimal_context
    def cents(self):
        for name in ('amount','rent_balance','kc_balance','iphone_balance'):
            if getattr(self,name)%Decimal('.01'):raise ValueError('Use whole-cent money amounts.')
        return self


class MoneySnapshot(StrictModel):
    version: Literal[1]=1
    reported_on: date
    checking: Money
    checking_floor: Nonnegative
    bills_box: Money
    card_balance: Nonnegative
    statement_minimum: Nonnegative
    statement_due: date
    expected_paycheck: Nonnegative
    expected_payday: date
    paycheck_estimate_pending: bool=False
    received_paycheck: ReceivedPaycheck|None=None
    notes: str=Field(default='',max_length=12000)

    @model_validator(mode='after')
    @decimal_context
    def cents(self):
        for name in ('checking','checking_floor','bills_box','card_balance','statement_minimum','expected_paycheck'):
            if getattr(self,name)%Decimal('.01'):raise ValueError('Money amounts must use whole cents.')
        if self.received_paycheck is not None and self.received_paycheck.received_on>self.reported_on:
            raise ValueError('Received paycheck cannot be later than the reported balance date.')
        return self


def fingerprint(snapshot):
    return sha256(snapshot.model_dump_json().encode()).hexdigest()


def load(directory):
    raw=(Path(directory)/FILENAME).read_bytes()
    if len(raw)>65536:raise ValueError('Money snapshot is too large.')
    data=json.loads(raw,object_pairs_hook=_unique_object)
    if not isinstance(data,dict) or type(data.get('version')) is not int:raise ValueError('Unsupported money snapshot.')
    return MoneySnapshot.model_validate(data)


def save(directory,snapshot):
    """Atomically replace after preserving the previous input record by content hash."""
    directory=Path(directory)
    target=directory/FILENAME
    snapshot=MoneySnapshot.model_validate_json(snapshot.model_dump_json())
    if target.exists():
        old=load(directory)
        history=directory/'money_history';history.mkdir(exist_ok=True)
        backup=history/(fingerprint(old)+'.json')
        if not backup.exists():
            with backup.open('x') as stream:stream.write(old.model_dump_json(indent=2))
    temporary=None
    try:
        with tempfile.NamedTemporaryFile(mode='w',dir=directory,prefix='.money-',delete=False) as stream:
            temporary=Path(stream.name);stream.write(snapshot.model_dump_json(indent=2));stream.flush();os.fsync(stream.fileno())
        os.replace(temporary,target);temporary=None
    finally:
        if temporary is not None:temporary.unlink(missing_ok=True)


FIELDS=(('reported_on','These balance figures are from','date'),('checking','Checking balance ($)','number'),
        ('checking_floor','Checking cushion to protect ($)','number'),('bills_box','Bills Box savings ($)','number'),
        ('card_balance','Quicksilver 1 balance ($)','number'),('statement_minimum','Statement minimum ($)','number'),
        ('statement_due','Statement due date','date'),('expected_paycheck','Expected paycheck ($)','number'),
        ('expected_payday','Expected payday','date'))


def change(original,values):
    if set(values)!={k for k,_,_ in FIELDS}:raise ValueError('Use the listed money fields.')
    return reconstruct(original,**values)


def needs_next_payday(snapshot):
    receipt=snapshot.received_paycheck
    return receipt is not None and (snapshot.paycheck_estimate_pending or snapshot.expected_payday<=receipt.replaces_expected_payday)


def render_received(snapshot):
    receipt=snapshot.received_paycheck
    next_note=('Next payday is '+text(snapshot.expected_payday.strftime('%B %d, %Y'))+', but a conservative take-home amount is still needed. The last received check is not being used as the forecast estimate.' if snapshot.paycheck_estimate_pending else 'The next paycheck date and amount are not confirmed.')
    return page('Paycheck received','<div class="hero"><h1>Your paycheck is recorded.</h1><p>'+money(receipt.amount)+' received '+text(receipt.received_on.strftime('%B %d, %Y'))+'. These balances already include the paycheck and completed automatic transfers; they will not be added again.</p></div><div class="cards">'+
        tile('Checking',money(snapshot.checking),money(snapshot.checking_floor)+' stays protected.')+
        tile('Bills Box',money(snapshot.bills_box),'Separate money for bills.')+
        tile('Rent',money(receipt.rent_balance),'Kept separate; not available for extra debt payments.')+
        tile('KC Open Fund',money(receipt.kc_balance),'Kept separate from checking.')+
        tile('iPhone',money(receipt.iphone_balance),'Kept separate from checking.')+
        '</div><section><h2>What still needs checking</h2><p>Individual autopay withdrawals are unconfirmed. No bills have been marked paid. Earlier bills may still be outstanding; we have not deducted them again or assumed they cleared.</p><p>'+next_note+' Payday forecasts are paused until the missing information is supplied. No extra-payment recommendation is available.</p><p>Quicksilver’s last supplied balance remains '+money(snapshot.card_balance)+' from the earlier report; it was not refreshed with these cash balances.</p></section><a class="action" href="/bills">Review bills</a> <a href="/">Back home</a>')


@decimal_context
def render(snapshot,*,has_bills=False):
    if needs_next_payday(snapshot):return render_received(snapshot)
    bill_link='<a class="action" href="/paycheck-week">See payday and the following week</a><a class="action secondary" href="/cash-until-payday">See cash before payday</a><a class="action secondary" href="/bills">See my bills</a>' if has_bills else ''
    bill_note='Your bills are now in a dated draft calendar. Review them there; uncertain payment status and transfer timing still prevent an extra-payment recommendation.' if has_bills else 'Your bills list is recorded below. It still needs to be connected to the forecast with current payment status and timing.'
    shown=snapshot.reported_on.strftime('%B %d, %Y')
    return page('My Money','<div class="hero"><span class="eyebrow">Your starting picture</span><h1>My Money</h1><p>These are the numbers you shared, dated '+text(shown)+'. They stay here so you don’t have to keep entering them.</p></div><div class="cards">'+
        tile('Checking',money(snapshot.checking),'You asked to keep '+money(snapshot.checking_floor)+' protected here.')+
        tile('Bills Box',money(snapshot.bills_box),'Your separate savings account for bills. It is not added to checking’s payment budget.')+
        tile('Quicksilver 1',money(snapshot.card_balance),'Reported card balance. This is not a live bank update.')+'</div><section><h2>Coming up</h2><ul class="payment-list"><li><div><strong>Expected paycheck</strong><span>'+text(snapshot.expected_payday.strftime('%A, %B %d, %Y'))+' · approximate amount</span></div><strong class="number">'+money(snapshot.expected_paycheck)+'</strong></li><li><div><strong>Quicksilver statement minimum</strong><span>Due '+text(snapshot.statement_due.strftime('%B %d, %Y'))+' · autopay is on; payment status not verified</span></div><strong class="number">'+money(snapshot.statement_minimum)+'</strong></li></ul></section><div class="banner warning"><strong>Extra-payment amount: not calculated yet</strong><p>'+bill_note+' The balances above are not a recommendation to pay extra.</p></div><section><h2>What happens next</h2><p>Use the bill calendar to see the amounts and funding accounts already recorded. You can review this screen now; there is nothing else you need to enter for this step.</p><div class="actions">'+bill_link+'<a class="action secondary" href="/my-money/edit">Update these numbers</a><a class="action secondary" href="/#saved-plans">Open my what-if plans</a></div><p class="muted">Updating this picture does not change existing what-if plans. Those plans retain their original inputs.</p></section><details><summary>Notes and bills already shared</summary><p style="white-space:pre-wrap">'+text(snapshot.notes or 'No additional notes saved.')+'</p></details><p><a href="/">Back home</a></p>')


def form(snapshot,token,values=None,error=''):
    values=snapshot.model_dump(mode='json') if values is None else values
    controls='<input type="hidden" name="token" value="'+text(token)+'"><input type="hidden" name="fingerprint" value="'+fingerprint(snapshot)+'">'
    fields=''.join('<div><label for="money-'+k+'">'+text(label)+'</label><input id="money-'+k+'" name="'+k+'" type="'+kind+'" '+('step="0.01" ' if kind=='number' else '')+'required value="'+text(values.get(k,''))+'"></div>' for k,label,kind in FIELDS)
    return page('Update My Money','<div class="hero"><h1>Update my numbers</h1><p>Change the figures that need updating. Keep the original reporting date if the balances are still from that day.</p></div>'+('<p class="banner warning" role="alert">'+text(error)+'</p>' if error else '')+'<form method="post" action="/my-money/save">'+controls+'<section><div class="grid">'+fields+'</div><p class="muted">The paycheck is an estimate. The statement minimum is not marked paid by this form. Previous figures are kept locally in history.</p><button class="action" type="submit">Save my numbers</button> <a href="/my-money">Cancel</a></section></form>')
