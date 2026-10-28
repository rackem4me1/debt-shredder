"""Immutable local combined payoff inputs, validated on review/save/reopen."""
import os
from pathlib import Path
import re
import tempfile
from uuid import uuid4
from typing import Literal
from pydantic import Field,field_validator
from SCHEMA import StrictModel
from engine.mixed_payoff import MixedPayoffInputs,compare_mixed_payoff
from payoff_cli import _parse_json,parse_mixed_input
from dashboard.restore import review_signature
from dashboard.report import text
from dashboard.simple_view import page
from dashboard.mixed_payoff_view import render_saved

MAX_BYTES=4*1024*1024


class AccountLabel(StrictModel):
    account_id: str=Field(min_length=1,max_length=100)
    name: str=Field(min_length=1,max_length=100)


class MixedPayoffRun(StrictModel):
    format: Literal['debt-shredder-mixed-payoff-run']='debt-shredder-mixed-payoff-run'
    version: Literal[1]=1
    name: str=Field(min_length=1,max_length=120)
    origin: Literal['synthetic_demo','supplied_estimate']
    inputs: MixedPayoffInputs
    account_labels: tuple[AccountLabel,...]=Field(default=(),max_length=60)
    wizard_id: str|None=Field(default=None,pattern=r'^[0-9a-f]{32}$')

    @field_validator('account_labels')
    @classmethod
    def unique_labels(cls,value):
        if len({v.account_id for v in value})!=len(value):raise ValueError('Duplicate account label')
        return value

    @field_validator('name')
    @classmethod
    def named(cls,value):
        if not value.strip():raise ValueError('Give the calculation a name')
        return value


def parse(raw):return MixedPayoffRun.model_validate(_parse_json(raw))


def load(directory,identifier):
    if not re.fullmatch('[0-9a-f]{32}',identifier):raise ValueError('Invalid combined run ID')
    with (Path(directory)/'mixed_payoff_runs'/(identifier+'.json')).open('rb') as stream:return parse(stream.read(MAX_BYTES+1))


def save(directory,run):
    raw=run.model_dump_json(indent=2).encode();run=parse(raw)
    compare_mixed_payoff(run.inputs)
    folder=Path(directory)/'mixed_payoff_runs';folder.mkdir(exist_ok=True)
    identifier=uuid4().hex;temporary=None
    try:
        with tempfile.NamedTemporaryFile(dir=folder,prefix='.mixed-',delete=False) as stream:
            temporary=Path(stream.name);stream.write(raw);stream.flush();os.fsync(stream.fileno())
        os.link(temporary,folder/(identifier+'.json'))
    finally:
        if temporary is not None:temporary.unlink(missing_ok=True)
    return identifier


def save_form(run,token):
    payload=run.model_dump_json()
    if len(payload.encode())>MAX_BYTES:raise ValueError('Combined payoff run exceeds 4 MiB')
    values={'token':token,'payload':payload,'signature':review_signature(payload,token)}
    return '<section><h2>Save this combined payoff run</h2><p>Keep the exact starting inputs and dates as a separate local calculation. No account balances or bills will be changed.</p><form method="post" action="/mixed-payoff/save">'+''.join('<input type="hidden" name="'+k+'" value="'+text(v)+'">' for k,v in values.items())+'<button type="submit">Save combined payoff run</button></form></section>'


def import_form(token,name='',inputs='',error=''):
    return page('Review combined payoff inputs','<div class="hero"><h1>Review a prepared payoff input file.</h1><p>This advanced path accepts exact inputs exported by the combined payoff tool. Paste the file contents below to calculate a preview before saving. It does not fill in unknown loan terms or change your current balances.</p></div>'+('<p class="banner warning" role="alert">'+text(error)+'</p>' if error else '')+'<form method="post" action="/mixed-payoff/import-preview"><input type="hidden" name="token" value="'+text(token)+'"><label>Name this calculation <input required name="name" maxlength="120" value="'+text(name)+'"></label><label>Combined payoff input JSON <textarea required name="inputs" rows="12" maxlength="4194304">'+text(inputs)+'</textarea></label><button type="submit">Calculate and review</button></form><p>Money and rates must use exact decimal strings. Only supported card and loan contracts are accepted. Keep private financial files on this Mac.</p><p><a href="/mixed-payoff-runs">Saved combined runs</a> · <a href="/">Home</a></p>')


def review(name,raw):
    run=MixedPayoffRun(name=name,origin='supplied_estimate',inputs=parse_mixed_input(raw))
    compare_mixed_payoff(run.inputs)
    return run


def library(directory):
    rows=[]
    for path in sorted((Path(directory)/'mixed_payoff_runs').glob('*.json'),key=lambda p:p.stat().st_mtime,reverse=True):
        if not re.fullmatch('[0-9a-f]{32}',path.stem):continue
        try:
            run=load(directory,path.stem)
            rows.append('<li><a href="/mixed-payoff-run/'+path.stem+'">'+text(run.name)+'</a><small>'+('Sample accounts' if run.origin=='synthetic_demo' else 'Supplied-input estimate')+' · opening '+text(run.inputs.start.date())+' · target '+text(run.inputs.payment_target)+' per round</small></li>')
        except (ValueError,OSError,ArithmeticError):rows.append('<li>A combined run could not be opened. Its file has been kept.</li>')
    return page('Saved combined payoff runs','<div class="hero"><h1>Saved cards-and-loan payoff runs</h1><p>Each calculation retains one shared target, its original financial inputs and dated cash events. These are estimates, not records of completed payments.</p></div><ul class="plan-list">'+(''.join(rows) or '<li>No combined payoff runs saved yet.</li>')+'</ul><div class="actions"><a class="action" href="/mixed-payoff-example">Try the combined sample</a><a class="action secondary" href="/mixed-payoff/import">Review a prepared input file</a><a href="/payoff-runs">Card payoff runs</a><a href="/">Home</a></div>')
