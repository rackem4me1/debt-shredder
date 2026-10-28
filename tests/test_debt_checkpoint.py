from datetime import date
from decimal import Decimal as D
import pytest
from engine.common import ZERO
from engine.simulation import DebtCheckpoint,simulate_revolving,resume_revolving
from engine.promotions import PromoTransition
from SCHEMA import GracePeriodState as G,assumed_default
from test_SCHEMA import _account
from test_promotions import segment,terms
from test_promo_transitions import cycles
from test_search_simulation import minimum
from test_grace_simulation import account as grace_account,terms as grace_terms


def promo_run(end,payments):
    s=segment()
    t=PromoTransition(segment_id=s.segment_id,terms=terms(),post_exit_grace_eligible=assumed_default(False))
    return simulate_revolving(_account(segments=(s,),current_grace_state=G.LOST_GRACE),date(2026,1,1),end,
        cycles(),minimum(),tuple(d for d in payments if d<=end),lambda day,*args:payments[day],promo_transitions=(t,))


@pytest.mark.parametrize('cut',[date(2026,1,1),date(2026,1,2),date(2026,1,3),date(2026,1,4),date(2026,1,20),date(2026,1,31)])
def test_promo_restart_matches_continuous_including_cutoff_and_posting(cut):
    payments={date(2026,1,4):D('50'),date(2026,2,20):D('25')}
    full=promo_run(date(2026,2,28),payments)
    first=promo_run(cut,payments)
    cp=DebtCheckpoint.model_validate_json(first.checkpoint.model_dump_json())
    called=[]
    def choose(day,*args):called.append(day);return payments[day]
    tail=tuple(d for d in payments if d>cut)
    resumed=resume_revolving(cp,date(2026,2,28),tail,choose)
    assert resumed==full
    assert called==list(tail)
    assert len([a for a in resumed.audit if a.kind=='promo_exit'])==1


@pytest.mark.parametrize('cut',[date(2026,1,1),date(2026,1,19),date(2026,1,20),date(2026,1,31),date(2026,2,19),date(2026,2,20),date(2026,2,28)])
def test_grace_restart_preserves_statement_credits_shadow_and_restoration(cut):
    a=grace_account(G.LOST_GRACE);t=grace_terms(a)
    payments={date(2026,1,20):D('100'),date(2026,2,20):D('19'),date(2026,3,20):D('3.61')}
    def run(end):
        return simulate_revolving(a,date(2026,1,1),end,cycles(),minimum(),tuple(d for d in payments if d<=end),
            lambda day,*args:payments[day],grace_terms=t)
    cp=DebtCheckpoint.model_validate_json(run(cut).checkpoint.model_dump_json())
    resumed=resume_revolving(cp,date(2026,3,31),tuple(d for d in payments if d>cut),lambda day,*args:payments[day])
    assert resumed==run(date(2026,3,31))


def test_full_grace_shadow_survives_restart_until_loss():
    a=grace_account(G.FULL_GRACE);t=grace_terms(a,opening='5')
    def run(end):return simulate_revolving(a,date(2026,1,1),end,cycles(),minimum(),(),lambda *args:ZERO,grace_terms=t)
    first=run(date(2026,1,10))
    assert first.checkpoint.contingent==15
    assert resume_revolving(first.checkpoint,date(2026,1,31),(),lambda *args:ZERO)==run(date(2026,1,31))


def test_repeated_restart_does_not_reapply_history():
    payments={date(2026,1,4):D('50')}
    cp=promo_run(date(2026,1,2),payments).checkpoint
    for end in (date(2026,1,3),date(2026,1,4),date(2026,1,31),date(2026,2,28)):
        r=resume_revolving(cp,end,tuple(d for d in payments if cp.as_of<d<=end),lambda day,*args:payments[day])
        cp=DebtCheckpoint.model_validate_json(r.checkpoint.model_dump_json())
    assert r==promo_run(date(2026,2,28),payments)


def test_resume_rejects_old_payment_dates_before_callback():
    cp=promo_run(date(2026,1,4),{}).checkpoint
    def choose(*args):raise AssertionError('must not run')
    with pytest.raises(ValueError,match='strictly after'):
        resume_revolving(cp,date(2026,1,31),(date(2026,1,4),),choose)


def test_effective_decision_view_sees_reversion_and_previous_payments():
    s=segment();t=PromoTransition(segment_id=s.segment_id,terms=terms(),post_exit_grace_eligible=assumed_default(False))
    a=_account(segments=(s,),current_grace_state=G.LOST_GRACE)
    seen=[]
    def choose(view):seen.append(view);return D('1')
    first=simulate_revolving(a,date(2026,1,1),date(2026,1,3),cycles(),minimum(),(date(2026,1,2),),None,
        choose_decision=choose,promo_transitions=(t,))
    r=resume_revolving(first.checkpoint,date(2026,1,5),(date(2026,1,4),),choose_decision=choose)
    assert seen[0].segments[0].apr.value==0 and not seen[0].segments[0].promo_exited
    assert seen[1].segments[0].apr.value==D('.365') and seen[1].segments[0].promo_exited
    assert not seen[1].segments[0].grace_eligible
    assert seen[1].previous_payments==first.payments
    assert len(r.payments)==2
    with pytest.raises(ValueError):seen[1].segments[0].balance=D(0)


@pytest.mark.parametrize('field',['daily_histories','promo_exits','minimums'])
def test_checkpoint_rejects_missing_runtime_state(field):
    raw=promo_run(date(2026,1,4),{}).checkpoint.model_dump()
    raw[field]=[]
    with pytest.raises(ValueError):DebtCheckpoint.model_validate(raw)


@pytest.mark.parametrize('field,value',[('balance','101'),('accrued_unposted_interest','999')])
def test_checkpoint_rejects_balance_or_accrual_corruption(field,value):
    raw=promo_run(date(2026,1,4),{}).checkpoint.model_dump()
    raw['account']['segments'][0][field]=value
    with pytest.raises(ValueError,match='reconcile'):DebtCheckpoint.model_validate(raw)


def test_checkpoint_rejects_source_term_rewrite():
    raw=promo_run(date(2026,1,4),{}).checkpoint.model_dump()
    raw['account']['segments'][0]['post_promo_apr']['value']=D('.9')
    with pytest.raises(ValueError,match='terms changed'):DebtCheckpoint.model_validate(raw)


def test_checkpoint_rejects_unbilled_assessment_loss():
    raw=promo_run(date(2026,1,4),{}).checkpoint.model_dump()
    raw['assessed_since_close']='0'
    with pytest.raises(ValueError,match='assessment mismatch'):DebtCheckpoint.model_validate(raw)


def test_checkpoint_file_roundtrip_resume_and_no_clobber(tmp_path):
    from engine.checkpoint_io import save_debt_checkpoint,load_debt_checkpoint
    cp=promo_run(date(2026,1,3),{}).checkpoint
    path=tmp_path/'checkpoint.json'
    save_debt_checkpoint(cp,path)
    loaded=load_debt_checkpoint(path)
    assert loaded==cp
    assert resume_revolving(loaded,date(2026,1,31),(),lambda *args:ZERO)==promo_run(date(2026,1,31),{})
    old=path.read_bytes()
    with pytest.raises(FileExistsError):save_debt_checkpoint(cp,path)
    assert path.read_bytes()==old
    newer=promo_run(date(2026,1,4),{}).checkpoint
    save_debt_checkpoint(newer,path,overwrite=True)
    assert load_debt_checkpoint(path)==newer
    assert list(tmp_path.iterdir())==[path]


def test_checksum_catches_valid_json_edit(tmp_path):
    import json
    from engine.checkpoint_io import save_debt_checkpoint,load_debt_checkpoint
    path=tmp_path/'checkpoint.json';save_debt_checkpoint(promo_run(date(2026,1,3),{}).checkpoint,path)
    raw=json.loads(path.read_text());raw['payload']['assessed_since_close']='0';path.write_text(json.dumps(raw))
    with pytest.raises(ValueError,match='checksum'):load_debt_checkpoint(path)


def test_checkpoint_rejects_duplicate_json_keys_and_wrong_version(tmp_path):
    from engine.checkpoint_io import load_debt_checkpoint
    path=tmp_path/'bad.json';path.write_text('{"version":1,"version":2}')
    with pytest.raises(ValueError,match='duplicate JSON'):load_debt_checkpoint(path)
    path.write_text('{"format":"debt-shredder-debt-checkpoint","version":2,"sha256":"","payload":{}}')
    with pytest.raises(ValueError,match='format/version'):load_debt_checkpoint(path)


def test_fractional_opening_accrual_and_low_ambient_precision_resume():
    from decimal import localcontext
    from test_SCHEMA import _segment
    a=_account(current_grace_state=G.LOST_GRACE,segments=(_segment(balance='100',
        accrued_unposted_interest=D('0.1428571428571428571428571429')),))
    with localcontext() as ctx:
        ctx.prec=6
        partial=simulate_revolving(a,date(2026,1,1),date(2026,1,10),cycles(),minimum(),(),lambda *args:ZERO)
        loaded=DebtCheckpoint.model_validate_json(partial.checkpoint.model_dump_json())
        resumed=resume_revolving(loaded,date(2026,1,30),(),lambda *args:ZERO)
        full=simulate_revolving(a,date(2026,1,1),date(2026,1,30),cycles(),minimum(),(),lambda *args:ZERO)
    assert resumed==full


def test_effective_view_caps_minimum_to_remaining_balance():
    from test_SCHEMA import _segment
    seen=[]
    a=_account(current_grace_state=G.LOST_GRACE,segments=(_segment(balance='1'),))
    simulate_revolving(a,date(2026,1,1),date(2026,1,1),cycles(),minimum('25'),(date(2026,1,1),),None,
        choose_decision=lambda view:seen.append(view) or ZERO)
    assert seen[0].effective_minimum==1


def test_save_restart_demo_matches_full_replay(tmp_path):
    from demo_resume import run
    result=run(tmp_path)
    assert result['matches_uninterrupted'] and result['promo_assessment_count']==1
    assert result['ending_balance']=='56.07' # 105.30 - 50 + round(55.30 * .0005 * 28)
    assert result['decisions']==[{'date':'2026-01-04','effective_apr':'0.1825','promo_exited':True}]
