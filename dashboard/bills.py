"""Reviewable bill occurrences from a dated list, without inventing bank activity."""
from datetime import date
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Literal
from decimal import Decimal
from pydantic import Field,model_validator
from SCHEMA import StrictModel
from engine.common import Nonnegative,decimal_context,reconstruct
from dashboard.scenarios import _unique_object
from dashboard.simple_view import page,tile
from dashboard.report import text,money

FILENAME='bills_book.json'
ROUTES={'bills_box':'Bills Box','checking':'Checking','checking_from_bills_box':'Checking, funded from Bills Box',
        'savor':'Savor card charge','quicksilver':'Quicksilver card charge','none':'No funding source recorded'}
STATUSES={'estimate':'Use as an unverified estimate','include':'Include in my draft','covered':'Already reflected in my starting balances','exclude':'Leave out of this draft'}


class Bill(StrictModel):
    bill_id:str=Field(pattern=r'^[a-z0-9-]{1,60}$')
    name:str=Field(min_length=1,max_length=80)
    amount:Nonnegative
    due:date|None=None
    route:Literal['bills_box','checking','checking_from_bills_box','savor','quicksilver','none']
    status:Literal['estimate','include','covered','exclude']='estimate'
    note:str=Field(default='',max_length=1000)
    cash_kind:Literal['bill','debt_payment']='bill'

    @model_validator(mode='after')
    @decimal_context
    def valid(self):
        if not self.name.strip() or self.amount%Decimal('.01'):raise ValueError('Use a name and whole-cent amount.')
        if self.status=='include' and (self.due is None or self.route=='none'):
            raise ValueError('Included bills require an explicit date and funding source.')
        return self


class BillBook(StrictModel):
    version:Literal[1]=1
    source_date:date
    bills:tuple[Bill,...]=Field(max_length=40)

    @model_validator(mode='after')
    def ids(self):
        if len({b.bill_id for b in self.bills})!=len(self.bills):raise ValueError('Duplicate bill ID.')
        return self


def fingerprint(book):return sha256(book.model_dump_json().encode()).hexdigest()


def load(directory):
    raw=(Path(directory)/FILENAME).read_bytes()
    if len(raw)>131072:raise ValueError('Bill list too large.')
    data=json.loads(raw,object_pairs_hook=_unique_object)
    if not isinstance(data,dict) or type(data.get('version')) is not int:raise ValueError('Unsupported bill list.')
    return BillBook.model_validate(data)


def save(directory,book):
    directory=Path(directory);target=directory/FILENAME
    book=BillBook.model_validate_json(book.model_dump_json())
    if target.exists():
        old=load(directory);history=directory/'bills_history';history.mkdir(exist_ok=True)
        backup=history/(fingerprint(old)+'.json')
        if not backup.exists():
            with backup.open('x') as stream:stream.write(old.model_dump_json(indent=2))
    temp=None
    try:
        with tempfile.NamedTemporaryFile(mode='w',dir=directory,prefix='.bills-',delete=False) as stream:
            temp=Path(stream.name);stream.write(book.model_dump_json(indent=2));stream.flush();os.fsync(stream.fileno())
        os.replace(temp,target);temp=None
    finally:
        if temp is not None:temp.unlink(missing_ok=True)


def effective(book,snapshot):
    # Current statement minimum stays linked to the dated My Money source.
    return tuple(reconstruct(b,amount=snapshot.statement_minimum,due=snapshot.statement_due,status='estimate',cash_kind='debt_payment')
                 if b.bill_id=='quicksilver-minimum' else b for b in book.bills)


@decimal_context
def summary(book,snapshot):
    rows=effective(book,snapshot)
    active=[b for b in rows if b.status in ('estimate','include')]
    cash={key:sum((b.amount for b in active if b.due is not None and b.route==key),Decimal(0)) for key in ('checking','bills_box','checking_from_bills_box')}
    cards=sum((b.amount for b in active if b.due is not None and b.route in ('savor','quicksilver')),Decimal(0))
    return rows,cash,cards


@decimal_context
def render(book,snapshot):
    rows,cash,cards=summary(book,snapshot)
    items={'cash':[],'cards':[],'other':[]}
    for b in sorted(rows,key=lambda b:(b.due is None,b.due or date.max,b.name)):
        state={'estimate':'Unverified estimate','include':'Included in draft','covered':'Already in starting balances','exclude':'Left out of draft'}[b.status]
        due=b.due.strftime('%b %d, %Y') if b.due else 'Date needs checking'
        action='<a href="/my-money">Update statement amount in My Money</a>' if b.bill_id=='quicksilver-minimum' else '<a href="/bills/edit/'+b.bill_id+'">Review or change</a>'
        group='other' if b.due is None or b.status in ('covered','exclude') else 'cards' if b.route in ('savor','quicksilver') else 'cash'
        items[group].append('<li><div><strong>'+text(b.name)+'</strong><span>'+text(due)+' · '+text(ROUTES[b.route])+'</span><small>'+text(state)+'</small>'+('<small>'+text(b.note)+'</small>' if b.note else '')+action+'</div><strong class="number">'+money(b.amount)+'</strong></li>')
    before_payday=[b for b in rows if b.status in ('estimate','include') and b.route in ('checking','bills_box','checking_from_bills_box') and b.due is not None and snapshot.reported_on<=b.due<snapshot.expected_payday]
    before_box=sum((b.amount for b in before_payday if b.route in ('bills_box','checking_from_bills_box')),Decimal(0))
    before_checking=sum((b.amount for b in before_payday if b.route=='checking'),Decimal(0))
    payday_section='<section><h2>Before your expected payday</h2><p>From the reported balance date through the day before '+text(snapshot.expected_payday.strftime('%B %d'))+': '+money(before_box)+' in draft bills funded by Bills Box and '+money(before_checking)+' directly from checking.</p><p class="muted">Same-day payday bills are not in these totals because paycheck and autopay order is unverified. Estimated bills may already be reflected in your balances; these are not extra-payment limits.</p></section>'
    cash_list=''.join(items['cash'][:5]) or '<li>No dated cash bills in this draft.</li>'
    more_cash='<details><summary>More dated cash bills</summary><ul class="payment-list">'+''.join(items['cash'][5:])+'</ul></details>' if len(items['cash'])>5 else ''
    cards_list='<details><summary>Subscriptions charged to cards</summary><ul class="payment-list">'+(''.join(items['cards']) or '<li>No dated card charges in this draft.</li>')+'</ul></details>'
    other_list='<details><summary>Undated, covered or excluded items</summary><ul class="payment-list">'+(''.join(items['other']) or '<li>None.</li>')+'</ul></details>'
    return page('My Bills','<div class="hero"><span class="eyebrow">Connected to My Money</span><h1>Your bills, in one place.</h1><p>I’ve brought over the list you already shared. The dates below are draft occurrences from that old list, not proof that a payment is still due.</p><p class="muted">Source notes saved '+text(book.source_date.strftime('%B %d, %Y'))+'.</p></div><div class="banner warning"><strong>This is a bill draft, not an extra-payment budget.</strong><p>Amounts and payment status from the old list remain estimates until reviewed. Card charges are shown separately, so they are not also deducted from checking.</p></div><div class="cards">'+
        tile('Funded by Bills Box',money(cash['bills_box']+cash['checking_from_bills_box']),'Dated draft bills, including '+money(cash['checking_from_bills_box'])+' paid through checking. Transfers are not counted as another expense.')+
        tile('Funded by checking',money(cash['checking']),'Dated draft bills paid directly from checking. Excludes bills funded by Bills Box.')+
        tile('Charges to cards',money(cards),'Dated subscriptions charged to Savor or Quicksilver. These add card debt; they are not checking withdrawals.')+
        '</div><p class="muted">These totals cover the dated occurrences listed below, across their displayed dates. They are not a monthly budget. Undated, covered and excluded items are outside the totals. The Quicksilver statement minimum comes from My Money.</p>'+payday_section+'<section><h2>Next in the cash bill draft</h2><ul class="payment-list">'+cash_list+'</ul>'+more_cash+'</section>'+cards_list+other_list+'<section><h2>Paycheck and transfers</h2><p>My Money records an estimated '+money(snapshot.expected_paycheck)+' paycheck on '+text(snapshot.expected_payday.strftime('%B %d, %Y'))+'. Your existing notes describe paycheck transfers and everyday spending.</p><p>Those transfers and spending estimates are not deductions in the bill totals above. We have not calculated a running bank balance or an extra payment from this draft.</p><div class="actions"><a class="action" href="/cash-until-payday">See cash before payday</a><a href="/my-money">Back to My Money</a></div></section>')


def form(book,bill_id,token,values=None,error=''):
    bill=next((b for b in book.bills if b.bill_id==bill_id),None)
    if bill is None:raise KeyError('Bill not found.')
    if bill_id=='quicksilver-minimum':raise ValueError('Update the statement minimum in My Money.')
    values=values if values is not None else {'name':bill.name,'amount':str(bill.amount),'due':bill.due.isoformat() if bill.due else '', 'route':bill.route,'status':bill.status}
    def choices(key,options):return ''.join('<option value="'+k+'"'+(' selected' if values.get(key)==k else '')+'>'+text(label)+'</option>' for k,label in options.items())
    return page('Review bill','<div class="hero"><h1>Review '+text(bill.name)+'</h1><p>This edits one draft occurrence. It does not record a bank payment or change your account balances.</p></div>'+('<p class="banner warning" role="alert">'+text(error)+'</p>' if error else '')+'<form method="post" action="/bills/save"><input type="hidden" name="token" value="'+text(token)+'"><input type="hidden" name="fingerprint" value="'+fingerprint(book)+'"><input type="hidden" name="bill_id" value="'+text(bill_id)+'"><section><div class="grid"><label>Bill name<input required maxlength="80" name="name" value="'+text(values.get('name',''))+'"></label><label>Amount ($)<input required type="number" min="0" step="0.01" name="amount" value="'+text(values.get('amount',''))+'"></label><label>Date for this occurrence (leave blank if unknown)<input type="date" name="due" value="'+text(values.get('due',''))+'"></label><label>Paid from<select name="route">'+choices('route',ROUTES)+'</select></label><label>Use in this draft<select name="status">'+choices('status',STATUSES)+'</select></label></div><p class="muted">Use “already reflected” only when the starting balances already account for this occurrence. If money moved afterward, update My Money too. Changing this status does not mark a real transaction paid.</p><button class="action">Save bill change</button> <a href="/bills">Cancel</a></section></form>')


def change(book,bill_id,values):
    if set(values)!={'name','amount','due','route','status'}:raise ValueError('Use the bill review form.')
    original=next((b for b in book.bills if b.bill_id==bill_id),None)
    if original is None:raise KeyError('Bill not found.')
    if bill_id=='quicksilver-minimum':raise ValueError('Update the statement minimum in My Money.')
    updated=reconstruct(original,**(values|{'due':values['due'] or None}))
    return reconstruct(book,bills=tuple(updated if b.bill_id==bill_id else b for b in book.bills))
