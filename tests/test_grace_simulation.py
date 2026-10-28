from datetime import date
from decimal import Decimal as D
import pytest
from SCHEMA import GracePeriodState as G, assumed_default
from engine.common import ZERO, MissingTerms
from engine.grace import GraceStatement, GraceReplayTerms, OpeningGraceAccrual
from engine.simulation import simulate_revolving
from test_SCHEMA import _account, _segment
from test_search_simulation import cycles, minimum


def account(state=G.FULL_GRACE, **kwargs):
    return _account(current_grace_state=state,segments=(_segment(balance='100',apr=assumed_default(D('3.65')),**kwargs),))


def terms(a, opening='0', streak=0):
    return GraceReplayTerms(statement=GraceStatement(cycle=cycles()[0],original_statement_balance='100'),
        last_resolved_state=a.current_grace_state,consecutive_full_statements=streak,
        opening_contingent=(OpeningGraceAccrual(segment_id=a.segments[0].segment_id,through=date(2025,12,31),amount=opening),))


def run(a,t,dates=(),amount='0',end=date(2026,1,31)):
    return simulate_revolving(a,date(2026,1,1),end,cycles(),minimum(),dates,lambda *args:D(amount),grace_terms=t)


def test_grace_loss_moves_contingent_once_then_accrues_and_posts():
    a=account();r=run(a,terms(a,opening='5'))
    assert r.account.current_grace_state==G.LOST_GRACE
    assert r.account.total_balance()==D('136') # opening 5 + 20 contingent days + 11 actual days
    assert r.contingent_grace_interest==0
    assert [(x.on,x.amount) for x in r.audit if x.kind=='grace_loss_unposted']==[(date(2026,1,20),D('25'))]
    assert sum((x.amount for x in r.audit if x.kind=='interest_posting'),ZERO)==36


def test_full_due_date_payment_cancels_contingent_not_residual_interest():
    a=account(accrued_unposted_interest=D('2'))
    r=run(a,terms(a,opening='5'),(date(2026,1,20),),'100')
    assert r.account.current_grace_state==G.FULL_GRACE
    assert r.account.total_balance()==2
    assert r.contingent_grace_interest==0
    assert not any(x.kind=='grace_loss_unposted' for x in r.audit)


def test_restoration_retains_trailing_interest():
    a=account(G.LOST_GRACE);r=run(a,terms(a,streak=1),(date(2026,1,20),),'100')
    assert r.account.current_grace_state==G.FULL_GRACE
    assert r.account.total_balance()==19


def test_one_full_statement_does_not_restore_two_cycle_contract():
    a=account(G.LOST_GRACE);r=run(a,terms(a),(date(2026,1,20),),'100')
    assert r.account.current_grace_state==G.LOST_GRACE
    assert r.account.total_balance()==19


def test_late_payment_does_not_retroactively_cancel_contingent():
    a=account();r=run(a,terms(a),(date(2026,1,21),),'100')
    assert r.account.current_grace_state==G.LOST_GRACE
    assert r.account.total_balance()==20


def test_minimum_payment_does_not_preserve_grace():
    a=account();r=run(a,terms(a),(date(2026,1,20),),'25')
    assert r.account.current_grace_state==G.LOST_GRACE
    assert r.account.total_balance()==D('103') # 75 + 19 + .75 + 11*.75


def test_multiple_due_dates_carry_new_statement_balance():
    a=account()
    r=run(a,terms(a),end=date(2026,2,20))
    assert len(r.grace_decisions)==2
    assert r.grace_decisions[0].remaining_at_due==100
    assert r.grace_decisions[1].remaining_at_due==131
    assert r.account.segments[0].accrued_unposted_interest==D('26.20')


def test_future_opening_credit_rejected_to_avoid_duplicate_simulation():
    from engine.grace import StatementCredit
    from engine.common import reconstruct
    a=account();t=terms(a)
    statement=reconstruct(t.statement,credits=(StatementCredit(credit_id='p',credited_on=date(2026,1,20),amount='100'),))
    with pytest.raises(ValueError,match='precede replay'):run(a,reconstruct(t,statement=statement))


def test_opening_contingent_requires_complete_segment_coverage():
    from engine.common import reconstruct
    a=account()
    with pytest.raises(MissingTerms,match='every eligible segment'):run(a,reconstruct(terms(a),opening_contingent=()))


def test_input_unchanged_and_audit_is_reproducible():
    a=account();t=terms(a,opening='5');before=(a.model_dump_json(),t.model_dump_json())
    assert run(a,t)==run(a,t)
    assert (a.model_dump_json(),t.model_dump_json())==before


def test_wrong_opening_exposure_date_is_rejected():
    from engine.common import reconstruct
    a=account();t=terms(a)
    t=reconstruct(t,opening_contingent=(reconstruct(t.opening_contingent[0],through=date(2026,1,1)),))
    with pytest.raises(ValueError,match='immediately before'):run(a,t)


def test_two_full_statements_restore_grace_during_continuous_replay():
    a=account(G.LOST_GRACE)
    payments={date(2026,1,20):D('100'),date(2026,2,20):D('19')}
    r=simulate_revolving(a,date(2026,1,1),date(2026,3,20),cycles(),minimum(),tuple(payments),
        lambda day,*args:payments[day],grace_terms=terms(a))
    assert [d.resulting_state for d in r.grace_decisions]==[G.LOST_GRACE,G.FULL_GRACE,G.LOST_GRACE]
    # January's 19 residual dollars accrue 19 days in February: 3.61.
    # Paying January's statement on February 20 does not erase that charge.
    assert [(x.on,x.amount) for x in r.audit if x.kind=='interest_posting'][:2]==[(date(2026,1,31),D('19')),(date(2026,2,28),D('3.61'))]
    assert r.grace_decisions[1].credited_by_due==19
    assert r.grace_decisions[2].credited_by_due==0
    assert r.grace_decisions[2].remaining_at_due==D('3.61')


def test_paying_residual_statement_preserves_restored_grace():
    a=account(G.LOST_GRACE)
    payments={date(2026,1,20):D('100'),date(2026,2,20):D('19'),date(2026,3,20):D('3.61')}
    r=simulate_revolving(a,date(2026,1,1),date(2026,3,31),cycles(),minimum(),tuple(payments),
        lambda day,*args:payments[day],grace_terms=terms(a))
    assert r.account.current_grace_state==G.FULL_GRACE
    assert r.account.total_balance()==0
    assert r.contingent_grace_interest==0
    assert r.grace_consecutive_full_statements==2
    assert [d.credited_by_due for d in r.grace_decisions]==[D('100'),D('19'),D('3.61')]


def test_payment_on_close_precedes_new_statement_and_is_not_reused():
    a=account(G.LOST_GRACE)
    r=run(a,terms(a),(date(2026,1,31),),'50',end=date(2026,2,20))
    assert r.grace_decisions[1].credited_by_due==0
    # 30*1 + .50 interest, plus the remaining 50 principal.
    assert r.grace_decisions[1].remaining_at_due==D('80.50')


def test_overlapping_due_windows_are_explicitly_unsupported():
    from engine.common import reconstruct
    c=list(cycles());c[0]=reconstruct(c[0],due_date=date(2026,1,31))
    a=account();t=reconstruct(terms(a),statement=GraceStatement(cycle=c[0],original_statement_balance='100'))
    with pytest.raises(MissingTerms,match='overlapping'):
        simulate_revolving(a,date(2026,1,1),date(2026,2,20),tuple(c),minimum(),(),lambda *args:ZERO,grace_terms=t)
