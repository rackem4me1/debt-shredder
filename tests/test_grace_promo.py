from datetime import date, time
from decimal import Decimal as D
import pytest
from SCHEMA import GracePeriodState as G, SegmentType, CompoundingMethod, assumed_default
from engine.common import ZERO, MissingTerms, reconstruct
from engine.grace import GraceReplayTerms, GraceStatement, OpeningGraceAccrual
from engine.simulation import plan_promo, simulate_revolving
from engine.liquidity import CashOpening
from engine.timing import PaymentTiming
from test_SCHEMA import _account, _segment
from test_search_simulation import cycles, minimum


def inputs():
    a=_account(current_grace_state=G.FULL_GRACE,segments=(
        _segment(segment_id='purchase',balance='.02',apr=assumed_default(D('3.65'))),
        _segment(segment_id='promo',segment_type=SegmentType.PROMOTIONAL_TRUE_ZERO,balance='.02',apr=assumed_default(ZERO),
            promo_expiration_date=date(2026,4,15),post_promo_apr=assumed_default(D('.2')),
            post_promo_compounding_method=assumed_default(CompoundingMethod.SIMPLE_DAILY))))
    t=GraceReplayTerms(statement=GraceStatement(cycle=cycles()[0],original_statement_balance='.04'),
        last_resolved_state=G.FULL_GRACE,opening_contingent=tuple(OpeningGraceAccrual(segment_id=s.segment_id,
            through=date(2025,12,31),amount='0') for s in a.segments))
    return a,t


def plan(a,t,dates=(date(2026,1,20),date(2026,2,20)),cash='.04',**kwargs):
    return plan_promo(a,'promo',date(2026,1,1),date(2026,2,21),cycles(),minimum(),dates,
        (CashOpening(account_id='checking',cleared=cash,floor='0',primary=True),),(),grace_terms=t,**kwargs)


def test_search_replays_grace_for_every_candidate_and_returns_matching_replay():
    a,t=inputs();before=(a.model_dump_json(),t.model_dump_json())
    r=plan(a,t)
    assert r.search.feasible and r.search.candidate==D('.02')
    assert r.target_remaining==0
    assert [d.resulting_state for d in r.projection.grace_decisions]==[G.LOST_GRACE,G.LOST_GRACE]
    assert r.projection.grace_consecutive_full_statements==1
    assert r.projection.account.consecutive_statements_paid_in_full==1
    assert any(x.kind=='grace_loss_unposted' and x.amount>0 for x in r.projection.audit)
    direct=simulate_revolving(a,date(2026,1,1),date(2026,2,21),cycles(),minimum(),
        (date(2026,1,20),date(2026,2,20)),lambda *args:D('.02'),grace_terms=t)
    assert r.projection==direct
    assert before==(a.model_dump_json(),t.model_dump_json())


def test_full_payment_candidate_preserves_grace():
    a,t=inputs();r=plan(a,t,dates=(date(2026,1,20),))
    assert r.search.feasible and r.search.candidate==D('.04')
    assert all(d.resulting_state==G.FULL_GRACE for d in r.projection.grace_decisions)
    assert not any(x.kind=='grace_loss_unposted' for x in r.projection.audit)


def test_cash_shortage_is_infeasible_without_relaxing_grace_history():
    a,t=inputs();r=plan(a,t,cash='.03')
    assert not r.search.feasible
    assert sum((p.amount for p in r.projection.payments),ZERO)<=D('.03')
    assert r.target_remaining>0


def test_credit_date_not_initiation_resolves_grace():
    a,t=inputs()
    timing=PaymentTiming(credit_business_days=assumed_default(2),debit_business_days=assumed_default(3),
        settlement_business_days=assumed_default(4),timezone_name='UTC',initiation_time=time(12))
    r=plan(a,t,dates=(date(2026,1,19),),payment_timing=timing)
    assert r.projection.payments[0].on==date(2026,1,21)
    assert r.projection.grace_decisions[0].resulting_state==G.LOST_GRACE
    assert r.projection.grace_decisions[0].credited_by_due==0


def test_missing_history_still_fails_instead_of_assuming_full_grace():
    a,_=inputs()
    with pytest.raises(MissingTerms,match='original full statement'):
        plan(a,None)


def test_bad_history_propagates_through_search():
    a,t=inputs()
    with pytest.raises(MissingTerms,match='every eligible segment'):
        plan(a,reconstruct(t,opening_contingent=()))


def test_weekend_initiations_sharing_monday_credit_keep_separate_cash_commitments():
    a,t=inputs()
    timing=PaymentTiming(credit_business_days=assumed_default(1),debit_business_days=assumed_default(2),
        settlement_business_days=assumed_default(3),timezone_name='UTC',initiation_time=time(12))
    r=plan(a,t,dates=(date(2026,1,2),date(2026,1,3)),payment_timing=timing)
    assert r.search.feasible and r.search.candidate==D('.02')
    assert [p.on for p in r.projection.payments]==[date(2026,1,5)]*2
    assert len({p.event_id for p in r.projection.payments})==2
    assert sum((p.amount for p in r.projection.payments),ZERO)==D('.04')
    insufficient=plan(a,t,dates=(date(2026,1,2),date(2026,1,3)),payment_timing=timing,cash='.03')
    assert not insufficient.search.feasible
    assert sum((p.amount for p in insufficient.projection.payments),ZERO)<=D('.03')
