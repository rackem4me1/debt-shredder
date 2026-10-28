"""Immutable weekly comparison snapshots; no bank or source-reference mutations."""
import os,re,tempfile
import csv
from io import StringIO
from pathlib import Path
from typing import Literal
from uuid import uuid4
from hashlib import sha256
from urllib.parse import urlencode
from pydantic import Field,model_validator
from SCHEMA import StrictModel
from dashboard import weekly_check as check
from dashboard.report import text,money
from dashboard.simple_view import page
from dashboard.restore import review_signature
from payoff_cli import _parse_json
from payoff_exports import _cell
from engine.common import decimal_context

MAX_BYTES=96*1024


def canonical_query(value,query):
    r=check.calculate(value,query)
    pairs=[(key,format(r['choices'][key],'f')) for key in ('pool','rent','bills','back','spend')]+[('weeks',str(r['opportunities']))]
    if r['custom_pay'] is not None:pairs.append(('pay',format(r['custom_pay'],'f')))
    return urlencode(pairs)


def fingerprint(value):return sha256(value.model_dump_json().encode()).hexdigest()


class Snapshot(StrictModel):
    format: Literal['debt-shredder-weekly-comparison']='debt-shredder-weekly-comparison'
    version: Literal[1]=1
    report: check.WeeklyCheck
    query: str=Field(max_length=2048)

    @model_validator(mode='after')
    def valid(self):
        if self.query!=canonical_query(self.report,self.query):raise ValueError('Use canonical comparison inputs')
        if len(self.report.model_dump_json().encode())>check.MAX_BYTES:raise ValueError('Source report too large')
        return self


def prepare(value,query=''):return Snapshot(report=value,query=canonical_query(value,query))


def parse(raw):
    if len(raw)>MAX_BYTES:raise ValueError('Saved comparison too large')
    data=_parse_json(raw);report=data.get('report')
    if not isinstance(report,dict) or type(report.get('version')) is not int or report['version']!=1:raise ValueError('Invalid source report version')
    return Snapshot.model_validate(data)


def location(directory,identifier):
    if not re.fullmatch('[0-9a-f]{32}',identifier):raise ValueError('Invalid weekly comparison ID')
    return Path(directory)/'weekly_comparisons'/(identifier+'.json')


def load(directory,identifier):
    with location(directory,identifier).open('rb') as stream:return parse(stream.read(MAX_BYTES+1))


def save(directory,value):
    raw=value.model_dump_json(indent=2).encode();parse(raw)
    identifier=uuid4().hex;target=location(directory,identifier);target.parent.mkdir(exist_ok=True)
    temporary=None
    try:
        with tempfile.NamedTemporaryFile(dir=target.parent,prefix='.weekly-',delete=False) as stream:
            temporary=Path(stream.name);stream.write(raw);stream.flush();os.fsync(stream.fileno())
        os.link(temporary,target)
    finally:
        if temporary is not None:temporary.unlink(missing_ok=True)
    return identifier


def save_form(value,token):
    payload=value.model_dump_json();parse(payload.encode())
    fields={'token':token,'payload':payload,'signature':review_signature(payload,token)}
    hidden=''.join('<input type="hidden" name="'+key+'" value="'+text(v)+'">' for key,v in fields.items())
    return '<section><h2>Keep this comparison</h2><p>Save the reported inputs and this trial mix as a separate local snapshot. It does not activate a transfer or change the current report. Reopen it later or download its exact inputs.</p><form method="post" action="/weekly-check/save">'+hidden+'<button>Save this weekly comparison</button></form></section>'


def render(value,identifier):
    export='<section><h2>Keep the comparison files</h2><p>These downloads contain private reported financial information and trial assumptions, not a bank transaction history. Each CSV row is an alternative scenario, not another transfer.</p><p><a href="/weekly-checks/'+identifier+'/inputs.json" download="weekly-comparison.json">Download exact comparison inputs</a> · <a href="/weekly-checks/'+identifier+'/summary.csv" download="weekly-comparison.csv">Download comparison table</a></p></section>'
    return check.render(value.report,value.query,save_section=export,retained=True)


@decimal_context
def summary_csv(value):
    r=check.calculate(value.report,value.query);c=r['choices'];stream=StringIO(newline='');writer=csv.writer(stream)
    writer.writerow(('alternative_scenario','reported_on','net_pay','reported_weekly_allocations','tested_recurring_allocations','unassigned_before_support','transfer_back_once','unassigned_for_one_supported_week','fund_balance_before','fund_direct_spending_once','fund_balance_after_draws','fund_contribution_weekly','remaining_contributions_assumed','fund_goal','projected_fund_balance','goal_weekly_rate_after_draws','goal_shortfall'))
    for name,net,current,tested in r['rows']:
        writer.writerow((_cell(name),value.report.reported_on.isoformat(),str(net),str(r['current_total']),str(r['tested_total']),str(tested),str(c['back']),str(tested+c['back']),str(value.report.goal.balance),str(c['spend']),str(r['balance_after']),str(c['pool']),r['opportunities'],str(value.report.goal.target),str(r['goal_end']),str(r['goal_rate']),str(r['goal_shortfall'])))
    return stream.getvalue()


def library(directory):
    rows=[]
    for path in sorted((Path(directory)/'weekly_comparisons').glob('*.json'),key=lambda p:p.stat().st_mtime,reverse=True):
        if not re.fullmatch('[0-9a-f]{32}',path.stem):continue
        try:
            value=load(directory,path.stem);r=check.calculate(value.report,value.query);c=r['choices']
            label=('Sample' if value.report.origin=='synthetic_demo' else 'Reported')+' comparison · '+value.report.reported_on.strftime('%b %d, %Y')
            detail=value.report.goal.name+' '+money(c['pool'])+'/week · bill funding '+money(c['bills'])+'/week · housing savings '+money(c['rent'])+'/week · one-time support '+money(c['back'])+' · direct fund spending '+money(c['spend'])+' · '+str(r['opportunities'])+' contributions assumed'
            rows.append('<li><a href="/weekly-checks/'+path.stem+'">'+text(label)+'</a><small>'+text(detail)+'</small></li>')
        except (ValueError,OSError,ArithmeticError):rows.append('<li>A weekly comparison could not be opened. Its file has been kept.</li>')
    return page('Saved weekly comparisons','<div class="hero"><h1>Pick up a comparison later.</h1><p>Each snapshot keeps its original reported figures and assumptions. These are estimates, not records of transfers made.</p></div><ul class="plan-list">'+(''.join(rows) or '<li>No weekly comparisons saved yet.</li>')+'</ul><p><a href="/weekly-check">Current weekly system check</a> · <a href="/">Home</a></p>')
