from datetime import date
from decimal import Decimal as D,localcontext
import json
from urllib.parse import urlencode
import pytest
from dashboard import weekly_check as check
from test_dashboard_manual import web,call


def example():
    return check.WeeklyCheck(reported_on=date(2026,1,1),origin='synthetic_demo',
        fixed=(check.Allocation(name='Loan funding',weekly='100',status='intended'),check.Allocation(name='Food',weekly='90',status='estimated'),check.Allocation(name='Transport',weekly='30',status='estimated'),check.Allocation(name='Device savings',weekly='10',status='reported')),
        pay_cases=(check.PayCase(name='Typical',net='400'),check.PayCase(name='Lower',net='330'),check.PayCase(name='PTO',net='300')),
        bills_weekly='90',bills_monthly_budget='420',goal=check.Goal(name='Tournament fund',balance='80',target='200',weekly='30',opportunities=12),
        unresolved=('Withdrawal dates and pending items are not verified.',))


def test_weekly_check_counts_earmarks_once_preserves_fund_and_shows_shortfalls():
    value=example();before=value.model_dump_json();r=check.calculate(value)
    assert r['base']==230 and r['current_total']==r['tested_total']==350
    assert [row[3] for row in r['rows']]==[50,-20,-50]
    assert r['goal_rate']==10 and r['goal_end']==440
    assert r['bills_monthly_average']==390 and r['bills_monthly_gap']==30
    assert value.model_dump_json()==before and value.goal.balance==80


def test_alternatives_do_not_change_current_plan_or_count_fund_as_spending_cash():
    value=example();r=check.calculate(value,'pool=10&rent=5&bills=90')
    assert r['current_total']==350 and r['tested_total']==335
    assert [row[2] for row in r['rows']]==[50,-20,-50]
    assert [row[3] for row in r['rows']]==[65,-5,-35]
    assert r['goal_end']==200
    assert value.goal.weekly==30 and value.housing_weekly==0


@pytest.mark.parametrize('query',['pool=-1','rent=0.001','bills=NaN','pool=Infinity','pool=','extra=2','pool=1&pool=2','pool=1&rent=2&bills=3&extra=4','pool=1000000001','x'*2049])
def test_invalid_comparisons_fail_without_changes(query):
    value=example();before=value.model_dump_json()
    with pytest.raises(ValueError):check.calculate(value,query)
    assert value.model_dump_json()==before


def test_goal_rate_rounds_up_and_does_not_invent_needed_funding_after_goal_met():
    from engine.common import reconstruct
    value=example();value=reconstruct(value,goal=reconstruct(value.goal,target='200.01'))
    assert check.calculate(value)['goal_rate']==D('10.01')
    value=reconstruct(value,goal=reconstruct(value.goal,balance='250'))
    assert check.calculate(value)['goal_rate']==0


def test_decimal_and_input_protections_apply_to_reference():
    value=example();expected=check.calculate(value)
    with localcontext() as context:
        context.prec=3
        assert check.calculate(value)==expected
    for changes in ({'bills_weekly':1.1},{'bills_weekly':True},{'bills_weekly':'0.001'},{'bills_weekly':'NaN'}):
        with pytest.raises(ValueError):check.WeeklyCheck.model_validate(value.model_dump()|changes)
    for opportunities in (0,True,12.5):
        with pytest.raises(ValueError):check.Goal(name='Goal',balance='0',target='100',weekly='10',opportunities=opportunities)


def test_render_labels_limits_and_private_names_are_escaped():
    from engine.common import reconstruct
    value=example();value=reconstruct(value,goal=reconstruct(value.goal,name='<Pool & travel>'))
    html=check.render(value,'pool=10')
    assert '&lt;Pool &amp; travel&gt;' in html and '<Pool & travel>' not in html
    assert 'not a dated cash-flow forecast' in html and 'not verified spare cash' in html
    assert 'entire balance counts' in html and 'no withdrawals' in html
    assert 'not saved or activated' in html and 'not subtracted again' in html


def test_http_report_and_whatifs_are_read_only_and_home_only_links_when_present(web):
    before={str(f):f.read_bytes() for f in web[1].rglob('*') if f.is_file()}
    assert call(web,'GET','/weekly-check')[0]==404
    assert 'Open weekly system check' not in call(web,'GET','/')[2]
    p=web[1]/check.FILENAME;p.write_text(example().model_dump_json())
    before={str(f):f.read_bytes() for f in web[1].rglob('*') if f.is_file()}
    status,headers,html=call(web,'GET','/weekly-check?pool=10&rent=0&bills=90')
    assert status==200 and headers['Cache-Control']=='no-store'
    assert 'Tournament fund' in html and '$200.00' in html and 'Sample inputs' in html
    assert 'Open weekly system check' in call(web,'GET','/')[2]
    assert call(web,'GET','/weekly-check?pool=-1')[0]==422
    assert call(web,'GET','/weekly-check',headers={'Host':'other.test'})[0]==403
    assert call(web,'POST','/weekly-check','pool=20',{'Content-Type':'application/x-www-form-urlencoded'})[0]==404
    assert {str(f):f.read_bytes() for f in web[1].rglob('*') if f.is_file()}==before


def test_corrupt_private_reference_is_kept_and_rejected(web):
    p=web[1]/check.FILENAME
    for raw in (b'{"version":true}',b'{"version":1,"version":1}',b'x'*(check.MAX_BYTES+1)):
        p.write_bytes(raw)
        assert call(web,'GET','/weekly-check')[0]==422 and p.read_bytes()==raw
