"""Resumable account inventory wizard; unknown terms remain unknown.

This collects facts for the existing engine. It never turns a partially described
account, promotional balance or loan into an ordinary-card payoff estimate.
"""
from datetime import date
from hashlib import sha256
import json,os,re,tempfile
from pathlib import Path
from typing import Literal
from uuid import uuid4
from pydantic import Field,model_validator
from SCHEMA import StrictModel
from engine.common import Money,Nonnegative,CENT,decimal_context,reconstruct
from dashboard.report import text,money
from dashboard.simple_view import page,tile
from payoff_cli import _parse_json


class Counts(StrictModel):
    checking: int=Field(ge=0,le=20,strict=True)
    savings: int=Field(ge=0,le=20,strict=True)
    cards: int=Field(ge=0,le=20,strict=True)
    loans: int=Field(ge=0,le=20,strict=True)

    @model_validator(mode='after')
    def bounded(self):
        if self.checking+self.savings>20:raise ValueError('This wizard supports up to 20 bank accounts')
        if self.checking+self.savings+self.cards+self.loans==0:raise ValueError('Add at least one account to start')
        return self


class Account(StrictModel):
    account_id: str=Field(pattern=r'^(checking|savings|card|loan)-[1-9][0-9]?$')
    kind: Literal['checking','savings','card','loan']
    name: str=Field(min_length=1,max_length=80)
    balance: Money|None=None
    balance_date: date|None=None
    floor: Nonnegative|None=None
    reserved: Nonnegative|None=None
    apr: Nonnegative|None=None
    apy: Nonnegative|None=None
    credit_limit: Nonnegative|None=None
    minimum: Nonnegative|None=None
    due_date: date|None=None
    payment_from: str|None=None
    autopay: Literal['unknown','yes','no']='unknown'
    promo: Literal['unknown','none','zero','deferred','other']='unknown'
    promo_balance: Nonnegative|None=None
    promo_apr: Nonnegative|None=None
    promo_end: date|None=None
    post_promo_apr: Nonnegative|None=None
    loan_type: Literal['unknown','simple','precomputed','other']='unknown'
    balance_type: Literal['unknown','principal','total']='unknown'
    note_rate: Nonnegative|None=None
    prepayment: Literal['unknown','principal','paid_ahead','rebate','other']='unknown'
    notes: str=Field(default='',max_length=2000)

    @model_validator(mode='after')
    @decimal_context
    def facts(self):
        if not self.name.strip():raise ValueError('Give this account a name')
        if not self.account_id.startswith(self.kind+'-'):raise ValueError('Account identity and type differ')
        if self.kind in ('card','loan') and self.balance is not None and self.balance<0:raise ValueError('Debt balances cannot be negative in this wizard')
        if any(v is not None and v%CENT for v in (self.balance,self.floor,self.reserved,self.credit_limit,self.minimum,self.promo_balance)):
            raise ValueError('Use whole-cent balances, payments and protected amounts')
        if self.promo=='none' and any(v is not None for v in (self.promo_balance,self.promo_apr,self.promo_end,self.post_promo_apr)):
            raise ValueError('Promotional details are present: choose a promotion type or clear those fields')
        if self.promo_balance is not None and self.balance is not None and self.promo_balance>self.balance:
            raise ValueError('Promotional balance exceeds the card balance')
        return self


class Wizard(StrictModel):
    format: Literal['debt-shredder-account-wizard']='debt-shredder-account-wizard'
    version: Literal[1]=1
    revision: int=Field(ge=0,strict=True)
    origin: Literal['personal','practice']='personal'
    counts: Counts
    accounts: tuple[Account,...]=Field(min_length=1,max_length=60)
    reviewed: tuple[str,...]=()
    next_step: int=Field(ge=0,strict=True)

    @model_validator(mode='after')
    def relationships(self):
        expected=tuple(f'{kind}-{i}' for kind,count in (('checking',self.counts.checking),('savings',self.counts.savings),('card',self.counts.cards),('loan',self.counts.loans)) for i in range(1,count+1))
        if tuple(a.account_id for a in self.accounts)!=expected:raise ValueError('Account list does not match the chosen counts')
        if len(set(self.reviewed))!=len(self.reviewed) or not set(self.reviewed)<=set(expected):raise ValueError('Invalid reviewed account IDs')
        bank_ids={a.account_id for a in self.accounts if a.kind in ('checking','savings')}
        if any(a.payment_from is not None and a.payment_from not in bank_ids for a in self.accounts):raise ValueError('Unknown payment bank account')
        if self.next_step>len(self.accounts):raise ValueError('Invalid next wizard step')
        return self


def path_for(directory,identifier):
    if not re.fullmatch('[0-9a-f]{32}',identifier):raise ValueError('Invalid setup ID')
    return Path(directory)/'account_wizards'/(identifier+'.json')


def parse(raw):
    if len(raw)>256*1024:raise ValueError('Account setup is too large')
    return Wizard.model_validate(_parse_json(raw))


def load(directory,identifier):
    with path_for(directory,identifier).open('rb') as stream:return parse(stream.read(256*1024+1))


def fingerprint(value):return sha256(value.model_dump_json().encode()).hexdigest()


def write(directory,identifier,value,previous=None):
    value=parse(value.model_dump_json().encode());path=path_for(directory,identifier);path.parent.mkdir(exist_ok=True)
    if previous is not None:
        old=load(directory,identifier)
        if fingerprint(old)!=fingerprint(previous):raise ValueError('Your setup changed in another tab. Reopen it before saving')
        history=path.parent/'history';history.mkdir(exist_ok=True)
        backup=history/(identifier+'-'+fingerprint(old)+'.json')
        if not backup.exists():
            with backup.open('x') as stream:stream.write(old.model_dump_json(indent=2))
    temporary=None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent,prefix='.setup-',delete=False) as stream:
            temporary=Path(stream.name);stream.write(value.model_dump_json(indent=2).encode());stream.flush();os.fsync(stream.fileno())
        if previous is None:os.link(temporary,path)
        else:os.replace(temporary,path);temporary=None
    finally:
        if temporary is not None:temporary.unlink(missing_ok=True)


def start(directory,counts,reuse=False,*,practice=False):
    accounts=tuple(Account(account_id=f'{kind}-{i}',kind=kind,name=f'{kind.title()} {i}') for kind,count in (('checking',counts.checking),('savings',counts.savings),('card',counts.cards),('loan',counts.loans)) for i in range(1,count+1))
    if reuse:
        from dashboard.my_money import load as money_load
        try:snapshot=money_load(directory)
        except FileNotFoundError:snapshot=None
        if snapshot:
            known={'checking-1':dict(name='Checking',balance=snapshot.checking,balance_date=snapshot.reported_on,floor=snapshot.checking_floor),
                'savings-1':dict(name='Bills Box',balance=snapshot.bills_box,balance_date=snapshot.reported_on),
                'card-1':dict(name='Previously reported card',balance=snapshot.card_balance,minimum=snapshot.statement_minimum,due_date=snapshot.statement_due,
                    notes='Historical card figure copied from My Money. Its balance date, current unpaid minimum and current balance still need review; it was not refreshed with later cash balances.')}
            accounts=tuple(reconstruct(a,**known.get(a.account_id,{})) for a in accounts)
    value=Wizard(revision=0,counts=counts,accounts=accounts,next_step=0,origin='practice' if practice else 'personal')
    identifier=uuid4().hex;write(directory,identifier,value)
    return identifier


BANK_FIELDS=('name','balance','balance_date','apy','floor','reserved','notes')
CARD_FIELDS=('name','balance','balance_date','apr','credit_limit','minimum','due_date','payment_from','autopay','promo','promo_balance','promo_apr','promo_end','post_promo_apr','notes')
LOAN_FIELDS=('name','balance','balance_date','balance_type','apr','note_rate','minimum','due_date','payment_from','autopay','loan_type','prepayment','notes')


def fields(account):return BANK_FIELDS if account.kind in ('checking','savings') else CARD_FIELDS if account.kind=='card' else LOAN_FIELDS


def change(value,step,values,intent):
    if not 0<=step<len(value.accounts):raise ValueError('Invalid setup step')
    original=value.accounts[step]
    if set(values)!=set(fields(original)):raise ValueError('Use the account questions shown')
    updated={k:(None if v=='' and k not in ('name','notes') else v) for k,v in values.items()}
    account=reconstruct(original,**updated)
    if intent not in ('next','previous','later'):raise ValueError('Choose a setup navigation button')
    destination=max(0,step-1) if intent=='previous' else min(len(value.accounts),step+1)
    accounts=list(value.accounts);accounts[step]=account
    return reconstruct(value,accounts=tuple(accounts),reviewed=tuple(dict.fromkeys(value.reviewed+(account.account_id,))),next_step=step if intent=='later' else destination)


def concerns(account):
    missing=[]
    if account.balance is None:missing.append('balance')
    if account.balance_date is None:missing.append('balance date')
    if account.kind in ('checking','savings'):
        if account.floor is None:missing.append('cash cushion')
        if account.reserved is None:missing.append('reserved amount')
    else:
        if account.apr is None:missing.append('APR')
        if account.minimum is None:missing.append('minimum payment')
        if account.due_date is None:missing.append('next due date')
        if account.payment_from is None:missing.append('payment account')
    if account.kind=='card':
        if account.credit_limit is None:missing.append('credit limit')
        if account.promo=='unknown':missing.append('whether there is a promotional rate')
        elif account.promo!='none':
            missing.append('how the promotional balance accrues interest before payoff planning')
            for key,label in (('promo_balance','promotion balance'),('promo_apr','promotion APR'),('promo_end','promotion end date'),('post_promo_apr','APR after promotion')):
                if getattr(account,key) is None:missing.append(label)
    if account.kind=='loan':
        if account.balance_type!='principal':missing.append('confirmed remaining principal')
        if account.note_rate is None:missing.append('contractual note rate')
        if account.loan_type=='unknown':missing.append('loan interest type')
        elif account.loan_type!='simple':missing.append('supported servicer schedule for this loan type')
        if account.prepayment=='unknown':missing.append('how extra payments are applied')
        elif account.prepayment!='principal':missing.append('supported prepayment schedule')
    return missing


def counts_form(token,values=None,error='',has_saved=False):
    values=values or {}
    controls=''.join('<label>'+label+'<input required type="number" min="0" max="20" step="1" name="'+kind+'" value="'+text(values.get(kind,''))+'"></label>' for kind,label in (
        ('checking','How many checking accounts?'),('savings','How many savings accounts?'),('cards','How many credit cards?'),('loans','How many loans?')))
    return page('Set up my accounts','<div class="hero"><span class="eyebrow">Account setup · Step 1</span><h1>Let’s get your accounts organized.</h1><p>First, tell us what you have. Then we’ll ask about one account at a time. You can leave unknown details blank and save your place whenever you need to.</p></div>'+('<p class="banner warning" role="alert">'+text(error)+'</p>' if error else '')+'<form method="post" action="/setup/start"><input type="hidden" name="token" value="'+text(token)+'"><section><h2>What accounts do you have?</h2><div class="grid">'+controls+'</div><p>Checking and savings together make up your bank-account count. Count credit cards and loans separately. You can add more accounts later.</p>'+('<label><input type="checkbox" name="reuse" value="yes" checked> Reuse matching figures already saved in My Money, keeping their original dates. They will still need review.</label>' if has_saved else '')+'<button type="submit">Start my account wizard</button></section></form><form method="post" action="/setup/practice"><input type="hidden" name="token" value="'+text(token)+'"><button type="submit" class="action secondary">Try the questions with sample accounts</button></form><p>Nothing here connects to a bank or moves money. This setup saves account details; it does not calculate a payoff plan from incomplete information.</p><p><a href="/setup/drafts">Resume a saved setup</a> · <a href="/">Home</a></p>')


def input_field(key,label,values,kind='number'):
    value=values.get(key,'');value='' if value is None else value
    number_step='any' if key in ('apr','apy','note_rate','promo_apr','post_promo_apr','minimum_rate','accrued') else '1' if key in ('credit_days','debit_days','settlement_days','close_day','due_day') else '0.01'
    attrs=' step="'+number_step+'"' if kind=='number' else ' maxlength="80"' if kind=='text' else ''
    if key not in ('balance',) and kind=='number':attrs+=' min="0"'
    if key=='name':attrs+=' required'
    return '<label>'+label+'<input name="'+key+'" type="'+kind+'" value="'+text(value)+'"'+attrs+'></label>'


def choice(key,label,options,values):
    return '<label>'+label+'<select name="'+key+'">'+''.join('<option value="'+text(k)+'"'+(' selected' if (values.get(key) or '')==k else '')+'>'+text(v)+'</option>' for k,v in options)+'</select></label>'


def account_form(wizard,identifier,step,token,values=None,error=''):
    a=wizard.accounts[step];values=a.model_dump(mode='json') if values is None else values
    bank=a.kind in ('checking','savings');card=a.kind=='card'
    basic=input_field('name','What do you call this account?',values,'text')+input_field('balance','Current balance ($)' if a.kind!='loan' else 'Balance shown by your lender ($)',values)+input_field('balance_date','What date is that balance from?',values,'date')
    content='<section><h2>'+('Your bank account' if bank else 'Your credit card' if card else 'Your loan')+'</h2><div class="grid">'+basic+'</div><p>Use a nickname rather than a full account number. Leave a number blank if you do not know it; enter 0 only if you know it is zero.</p></section>'
    if bank:
        content+='<section><h2>Does it earn interest?</h2>'+input_field('apy','Annual percentage yield (APY %), if known',values)+'</section>'
        content+='<section><h2>Money to keep protected</h2><div class="grid">'+input_field('floor','Cash cushion to keep in this account ($)',values)+input_field('reserved','Other money already reserved here ($)',values)+'</div><p>The reserved amount is separate from the cushion. Examples include money already set aside for rent or a specific goal. These figures stay attached to this account.</p></section>'
    else:
        banks=[('',"I’m not sure yet")]+[(b.account_id,b.name) for b in wizard.accounts if b.kind in ('checking','savings')]
        content+='<section><h2>Rate and payments</h2><div class="grid">'+input_field('apr','Regular purchase APR (%)' if card else 'Disclosed loan APR (%)',values)+(input_field('credit_limit','Credit limit ($)',values) if card else input_field('note_rate','Contractual note rate (%), if known',values))+input_field('minimum','Current unpaid minimum ($)' if card else 'Required installment payment ($)',values)+input_field('due_date','Next payment due date',values,'date')+choice('payment_from','Which bank account pays this debt?',banks,values)+choice('autopay','Is autopay turned on?',(('unknown',"I’m not sure"),('yes','Yes'),('no','No')),values)+'</div><p>Saving an autopay setting does not mark a payment paid or schedule a new payment.</p></section>'
        if card:
            content+='<section><h2>Any promotional rates?</h2>'+choice('promo','Does any part of this balance have a special rate?',(('unknown',"I’m not sure yet"),('none','No promotional rate'),('zero','Yes — introductory or balance-transfer 0%'),('deferred','Yes — deferred interest / no interest if paid in full'),('other','Yes — another promotional rate')),values)+'<p>“0% interest” and “no interest if paid in full” can work differently. Keep the offer wording if you are unsure.</p><details'+(' open' if values.get('promo') in ('zero','deferred','other') else '')+'><summary>Promotion details, if available</summary><div class="grid">'+''.join(input_field(k,label,values,kind) for k,label,kind in (
                ('promo_balance','Amount under the promotional offer ($)','number'),('promo_apr','Promotional APR (%)','number'),('promo_end','Promotion ends','date'),('post_promo_apr','APR after the promotion (%)','number')))+'</div><p>Leave unknown values blank. Add multiple offers, transfer fees or deferred-interest wording in your notes. This wizard will not treat a promotional balance as an ordinary-rate card.</p></details></section>'
        else:
            content+='<section><h2>How does this loan work?</h2><div class="grid">'+choice('balance_type','What does the balance above represent?',(('unknown',"I’m not sure"),('principal','Remaining principal only'),('total','Lender total / payoff amount')),values)+choice('loan_type','How is interest calculated?',(('unknown',"I’m not sure"),('simple','Simple interest on remaining principal'),('precomputed','Precomputed interest'),('other','Another method')),values)+choice('prepayment','What happens when you pay extra?',(('unknown',"I’m not sure"),('principal','Extra reduces principal; future payments still due'),('paid_ahead','It advances future payment due dates'),('rebate','Precomputed loan with an interest rebate'),('other','Another method')),values)+'</div><p>The note rate and disclosed APR can differ. We will not substitute one for the other or guess how your lender applies an extra payment.</p></section>'
    content+='<section><h2>Anything else we should keep?</h2><label>Notes, lender wording, or details to check later<textarea name="notes" maxlength="2000" rows="3" style="width:100%">'+text(values.get('notes',''))+'</textarea></label></section>'
    hidden=''.join('<input type="hidden" name="'+k+'" value="'+text(v)+'">' for k,v in {'token':token,'fingerprint':fingerprint(wizard)}.items())
    nav=('<button class="action secondary" name="intent" value="previous">Save and back</button>' if step else '')+'<button class="action" name="intent" value="next">'+('Save and review my accounts' if step==len(wizard.accounts)-1 else 'Save and next account')+'</button><button class="action secondary" name="intent" value="later">Save and finish later</button>'
    return page('Account setup: '+a.name,'<div class="hero"><span class="eyebrow">'+('Practice setup · ' if wizard.origin=='practice' else '')+'Account '+str(step+1)+' of '+str(len(wizard.accounts))+' · '+text(a.kind.title())+'</span><h1>'+text(a.name)+'</h1><p>Unknown is okay. Save what you know and come back for the rest.</p></div>'+('<p class="banner warning" role="alert">'+text(error)+'</p>' if error else '')+'<form method="post" action="/setup/'+identifier+'/account/'+str(step)+'">'+hidden+content+'<div class="actions">'+nav+'</div></form><p><a href="/setup/'+identifier+'">View saved setup summary</a> · <a href="/setup/drafts">Other saved setups</a></p>')


def summary(wizard,identifier,token):
    rows=[]
    for index,a in enumerate(wizard.accounts):
        missing=concerns(a)
        note='Still to review: '+', '.join(missing)+'.' if missing else 'Entered details saved.'
        if a.kind=='card' and a.balance is not None and a.credit_limit is not None and a.balance>a.credit_limit:note+=' Balance exceeds the entered credit limit.'
        if a.promo not in ('unknown','none') and a.kind=='card':note+=' Promotional terms are retained; no ordinary-rate payoff assumption is applied.'
        rows.append('<li><div><strong>'+text(a.name)+'</strong><span>'+text(a.kind.title())+' · '+(money(a.balance) if a.balance is not None else 'Balance unknown')+(' as of '+text(a.balance_date.strftime('%b %d, %Y')) if a.balance_date else ' · date not confirmed')+'</span><small>'+text(note)+'</small><small>'+('Reviewed in this setup' if a.account_id in wizard.reviewed else 'Not reviewed yet')+'</small></div><a href="/setup/'+identifier+'/account/'+str(index)+'">Review account</a></li>')
    next_step=min(wizard.next_step,len(wizard.accounts)-1)
    add=''.join('<button class="action secondary" name="kind" value="'+k+'">Add '+label+'</button>' for k,label in (('checking','checking'),('savings','savings'),('card','credit card'),('loan','loan')))
    return page('My account setup','<div class="hero"><span class="eyebrow">'+('Practice setup' if wizard.origin=='practice' else 'Your saved account setup')+'</span><h1>Your accounts, in one place.</h1><p>Saved locally on this Mac. You can update any account or continue where you stopped.</p></div><div class="cards">'+tile('Bank accounts',str(wizard.counts.checking+wizard.counts.savings),str(wizard.counts.checking)+' checking · '+str(wizard.counts.savings)+' savings')+tile('Credit cards',str(wizard.counts.cards),'Balances and promotional terms stay separate.')+tile('Loans',str(wizard.counts.loans),'Each lender’s payment rules are recorded.')+'</div><div class="actions"><a class="action" href="/setup/'+identifier+'/account/'+str(next_step)+'">Continue my setup</a><a class="action secondary" href="/setup/'+identifier+'/backup.json">Download accounts-only backup</a></div><ul class="payment-list">'+''.join(rows)+'</ul><section><h2>Build my payment plan</h2><p><a class="action" href="/setup/'+identifier+'/plan">Continue to income, bills and payoff</a></p><p>Next, review income, bills, statement dates and repayment terms before building your personal payoff plan. A saved account is not automatically ready for calculation. Promotional cards and unsupported loan terms stay flagged for review; this wizard does not move money or change your existing My Money figures.</p><form method="post" action="/setup/'+identifier+'/add"><input type="hidden" name="token" value="'+text(token)+'"><input type="hidden" name="fingerprint" value="'+text(fingerprint(wizard))+'"><div class="actions">'+add+'</div></form></section><p><a href="/setup/drafts">Saved account setups</a> · <a href="/">Home</a></p>')


def add_account(wizard,kind):
    field={'checking':'checking','savings':'savings','card':'cards','loan':'loans'}.get(kind)
    if field is None:raise ValueError('Unknown account type')
    count=getattr(wizard.counts,field)+1;counts=reconstruct(wizard.counts,**{field:count})
    new=Account(account_id=f'{kind}-{count}',kind=kind,name=f'{kind.title()} {count}')
    by={a.account_id:a for a in wizard.accounts};by[new.account_id]=new
    keys=tuple(f'{k}-{i}' for k,n in (('checking',counts.checking),('savings',counts.savings),('card',counts.cards),('loan',counts.loans)) for i in range(1,n+1))
    return reconstruct(wizard,counts=counts,accounts=tuple(by[k] for k in keys),next_step=keys.index(new.account_id))


def library(directory):
    rows=[]
    for path in sorted((Path(directory)/'account_wizards').glob('*.json'),key=lambda p:p.stat().st_mtime,reverse=True):
        if not re.fullmatch('[0-9a-f]{32}',path.stem):continue
        try:
            w=load(directory,path.stem)
            rows.append('<li><a href="/setup/'+path.stem+'">'+('Practice account setup' if w.origin=='practice' else 'Account setup')+' · '+str(len(w.accounts))+' accounts</a><small>'+str(len(w.reviewed))+' visited · saved revision '+str(w.revision)+'</small></li>')
        except (ValueError,OSError):rows.append('<li>A setup could not be opened. Its file has been kept.</li>')
    return page('Saved account setups','<div class="hero"><h1>Pick up where you left off.</h1><p>Each setup keeps your entered account details. Blank values stay unknown.</p></div><ul class="plan-list">'+(''.join(rows) or '<li>No account setups saved yet.</li>')+'</ul><div class="actions"><a class="action" href="/setup">Start a new account setup</a><a class="action secondary" href="/setup/restore">Restore a complete setup</a><a href="/">Home</a></div>')


def latest_personal(directory):
    """Resume an actual saved setup; practice records never displace it."""
    for path in sorted((Path(directory)/'account_wizards').glob('*.json'),key=lambda p:p.stat().st_mtime,reverse=True):
        if not re.fullmatch('[0-9a-f]{32}',path.stem):continue
        try:
            if load(directory,path.stem).origin=='personal':return path.stem
        except (ValueError,OSError):continue
    return None
