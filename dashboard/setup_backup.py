"""Portable setup snapshots; restoring always creates a separate local copy."""
from typing import Literal
from uuid import uuid4
from pydantic import model_validator
from SCHEMA import StrictModel
from dashboard import payoff_setup as setup,setup_plan as plan
from dashboard.report import text
from dashboard.simple_view import page
from dashboard.restore import review_signature
from payoff_cli import _parse_json

MAX_BYTES=1024*1024


class Backup(StrictModel):
    format: Literal['debt-shredder-complete-setup']='debt-shredder-complete-setup'
    version: Literal[1]=1
    accounts: setup.Wizard
    planning: plan.Planning

    @model_validator(mode='after')
    def bounded(self):
        setup.parse(self.accounts.model_dump_json().encode())
        if len(self.planning.model_dump_json().encode())>512*1024:raise ValueError('Planning inputs too large')
        return self


def parse(raw):
    if len(raw)>MAX_BYTES:raise ValueError('Complete setup backup exceeds 1 MiB')
    data=_parse_json(raw)
    # Nested version markers must also be actual integers, never booleans.
    for key in ('accounts','planning'):
        child=data.get(key)
        if not isinstance(child,dict) or type(child.get('version')) is not int or child['version']!=1:
            raise ValueError('Unsupported setup version')
    return Backup.model_validate(data)


def capture(directory,identifier):
    return Backup(accounts=setup.load(directory,identifier),planning=plan.load(directory,identifier))


def restore(directory,backup):
    backup=parse(backup.model_dump_json().encode())
    identifier=uuid4().hex
    # Publish the inventory last: incomplete writes never appear as a saved setup.
    target=setup.path_for(directory,identifier);sidecar=plan.path(directory,identifier)
    if target.exists() or sidecar.exists():raise FileExistsError('New setup ID is already used')
    plan.save(directory,identifier,backup.planning,plan.Planning())
    try:setup.write(directory,identifier,backup.accounts)
    except BaseException:
        if not target.exists():sidecar.unlink(missing_ok=True)
        raise
    return identifier


def form(token,error=''):
    return page('Restore an account setup','<div class="hero"><h1>Bring back a complete setup.</h1><p>Choose a complete setup backup from this app. Review it first, then save a separate copy. Your current accounts and planning answers stay unchanged.</p></div>'+('<p class="banner warning" role="alert">'+text(error)+'</p>' if error else '')+'<form method="post" action="/setup/restore-preview"><input type="hidden" name="token" value="'+text(token)+'"><section><div id="file-choice" hidden><label for="backup-file">Complete setup backup (.json)</label><input id="backup-file" type="file" accept=".json,application/json" data-max-bytes="1048576"><p id="file-status" role="status" aria-live="polite"></p></div><details id="paste-backup" open><summary>Paste backup contents instead</summary><label for="backup-data">Backup contents</label><textarea id="backup-data" name="payload" rows="8" style="width:100%" required spellcheck="false"></textarea></details><p>Maximum 1 MiB. File contents go only to this local app when you choose Preview. Older account-only backups and calculated-run files are different formats.</p><button id="restore-preview">Preview setup backup</button></section></form><p><a href="/setup/drafts">Saved setups</a> · <a href="/">Home</a></p><script src="/restore.js" defer></script>')


def preview(backup,token):
    payload=backup.model_dump_json()
    fields={'token':token,'payload':payload,'signature':review_signature(payload,token)}
    hidden=''.join('<input type="hidden" name="'+k+'" value="'+text(v)+'">' for k,v in fields.items())
    w,p=backup.accounts,backup.planning
    accounts=''.join('<li>'+text(a.name)+' · '+text(a.kind.title())+' · '+('Balance unknown' if a.balance is None else 'Balance '+text(a.balance))+' · '+('Date unknown' if a.balance_date is None else text(a.balance_date))+'</li>' for a in w.accounts)
    flows=''.join('<li>'+text(f.name)+' · '+text({'yes':'Included','no':'Left out','review':'Needs review'}[f.include])+' · '+('Amount unknown' if f.amount is None else text(f.amount))+'</li>' for f in p.flows)
    return page('Review setup backup','<div class="hero"><h1>Review before restoring.</h1><p>Nothing has been saved yet. This is '+('a practice setup' if w.origin=='practice' else 'a personal setup')+'. Saving creates a separate copy with the same dated answers; it does not refresh balances, mark bills paid or restore bank transactions.</p></div><section><h2>Accounts</h2><ul>'+accounts+'</ul></section><section><h2>Planning answers</h2><p>Common balance date: '+text(p.settings.balance_date or 'Unknown')+'. Payment target: '+text(p.settings.target if p.settings.target is not None else 'Unknown')+'.</p><p>'+str(len(p.terms))+' saved repayment-term records. Income, bills and transfers:</p><ul>'+(flows or '<li>None entered.</li>')+'</ul><p>Incomplete answers remain incomplete. Review dates and terms in the restored copy before calculating.</p></section><details><summary>Review all saved fields</summary><pre style="white-space:pre-wrap;overflow-wrap:anywhere">'+text(backup.model_dump_json(indent=2))+'</pre></details><form method="post" action="/setup/restore-save">'+hidden+'<button>Save restored setup as a new copy</button></form><p><a href="/setup/restore">Choose another backup</a> · <a href="/setup/drafts">Cancel</a></p>')
