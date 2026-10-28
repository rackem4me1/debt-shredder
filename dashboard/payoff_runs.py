"""Immutable payoff runs keep the original source and expanded calendar together."""
import json
import os
from pathlib import Path
import re
import tempfile
from uuid import uuid4
from pydantic import Field,model_validator
from SCHEMA import StrictModel
from engine.payoff_calendar import ExpandedPayoff,expand_payoff_template
from engine.payoff import compare_payoff
from dashboard.scenarios import Scenario,MAX_BYTES,_unique_object
from dashboard.simple_view import page
from dashboard.report import text
from dashboard import payoff_repeat,payoff_view
from dashboard.restore import review_signature


class PayoffRun(StrictModel):
    format: str=Field(default='debt-shredder-payoff-run',pattern='^debt-shredder-payoff-run$')
    version: int=Field(default=1,strict=True,ge=1,le=1)
    source_id: str=Field(pattern='^[0-9a-f]{32}$')
    source: Scenario
    expanded: ExpandedPayoff

    @model_validator(mode='after')
    def source_matches(self):
        template=self.expanded.template
        source_openings={o.account_id:o for o in self.source.openings}
        run_openings={o.account_id:o for o in (template.opening,)+template.additional_openings}
        if source_openings!=run_openings or self.source.start!=template.start or self.source.debts!=template.debts:
            raise ValueError('Saved run must retain the source opening balances, debt terms and starting date')
        return self


def parse(raw):
    if len(raw)>MAX_BYTES:raise ValueError('Payoff run exceeds 4 MiB')
    def reject(value):raise ValueError('Use decimal strings; nonfinite and floating-point JSON values are not accepted')
    try:data=json.loads(raw,object_pairs_hook=_unique_object,parse_float=reject,parse_constant=reject)
    except RecursionError as exc:raise ValueError('Payoff run nesting is too deep') from exc
    if not isinstance(data,dict) or type(data.get('version')) is not int or data.get('version')!=1 or data.get('format')!='debt-shredder-payoff-run':
        raise ValueError('Unsupported payoff run format or version')
    run=PayoffRun.model_validate(data)
    if expand_payoff_template(run.expanded.template)!=run.expanded:
        raise ValueError('Stored explicit dates do not match the saved recurrence assumptions')
    return run


def save(directory,run):
    raw=run.model_dump_json(indent=2).encode();run=parse(raw)
    compare_payoff(run.expanded.inputs)
    folder=Path(directory)/'payoff_runs';folder.mkdir(exist_ok=True)
    identifier=uuid4().hex;temporary=None
    try:
        with tempfile.NamedTemporaryFile(dir=folder,prefix='.payoff-',delete=False) as stream:
            temporary=Path(stream.name);stream.write(raw);stream.flush();os.fsync(stream.fileno())
        os.link(temporary,folder/(identifier+'.json'))
    finally:
        if temporary is not None:temporary.unlink(missing_ok=True)
    return identifier


def load(directory,identifier):
    if not re.fullmatch('[0-9a-f]{32}',identifier):raise ValueError('Invalid payoff run ID')
    with (Path(directory)/'payoff_runs'/(identifier+'.json')).open('rb') as stream:return parse(stream.read(MAX_BYTES+1))


def save_form(run,token):
    payload=run.model_dump_json()
    if len(payload.encode())>MAX_BYTES:raise ValueError('Payoff run is too large to save')
    fields={'token':token,'payload':payload,'signature':review_signature(payload,token)}
    return '<section><h2>Keep this payoff calculation</h2><p>Save the exact starting inputs, repeat assumptions and expanded dates together. Later edits to your original plan will not change this copy.</p><form method="post" action="/payoff-repeat-save/'+run.source_id+'">'+''.join('<input type="hidden" name="'+k+'" value="'+text(v)+'">' for k,v in fields.items())+'<button class="action">Save this payoff run</button></form></section>'


def render(run,identifier=None):
    comparison=compare_payoff(run.expanded.inputs)
    exports=''
    if identifier is not None:
        prefix='/payoff-run/'+identifier
        exports='<section><h2>Download this calculation</h2><p>These files contain the saved financial inputs. Keep them private.</p><div class="actions"><a class="action secondary" download="highest-interest-payments.csv" href="'+prefix+'/highest-interest.csv">Highest-interest schedule</a><a class="action secondary" download="smallest-balance-payments.csv" href="'+prefix+'/smallest-balance.csv">Smallest-balance schedule</a><a download="payoff-inputs.json" href="'+prefix+'/inputs.json">Exact calculation inputs</a><a download="payoff-template.json" href="'+prefix+'/template.json">Repeat assumptions</a></div></section>'
    return page('Saved payoff run','<div class="hero"><span class="sample">Saved estimate · '+('Sample accounts' if run.source.origin=='synthetic_demo' else 'Captured inputs')+'</span><h1>'+text(run.source.name)+'</h1><p>This saved payoff run retains its original inputs. It is not a current bank-balance update.</p></div>'+payoff_repeat.assumptions_section(run.expanded)+payoff_view.result_section(run.source,comparison)+exports+'<div class="actions"><a class="action secondary" href="/payoff-runs">Saved payoff runs</a><a href="/plan/'+run.source_id+'">Original saved plan</a><a href="/">Home</a></div>')


def library(directory):
    rows=[]
    for path in sorted((Path(directory)/'payoff_runs').glob('*.json'),key=lambda p:p.stat().st_mtime,reverse=True):
        if not re.fullmatch('[0-9a-f]{32}',path.stem):continue
        try:
            run=load(directory,path.stem)
            rows.append('<li><a href="/payoff-run/'+path.stem+'">'+text(run.source.name)+'</a><small>Saved opening '+text(run.source.start.date())+' · through '+text(run.expanded.template.end.date())+' · '+text(str(run.expanded.template.payment_target))+' target per date</small></li>')
        except (ValueError,OSError,ArithmeticError):rows.append('<li>A saved payoff run could not be opened. Its file has been kept.</li>')
    return page('Saved payoff runs','<div class="hero"><h1>Saved payoff runs</h1><p>Each run retains its starting balances, contract terms, cash schedules and repeated-calendar assumptions.</p></div><ul class="plan-list">'+(''.join(rows) or '<li>No payoff runs saved yet. Open a saved plan to calculate one.</li>')+'</ul><a href="/mixed-payoff-runs">Cards-and-loan runs</a> · <a href="/">Home</a>')
