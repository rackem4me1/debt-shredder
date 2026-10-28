from datetime import date,datetime,time,timezone
from decimal import Decimal as D
import pytest
from SCHEMA import GracePeriodState as G,assumed_default
from engine.simulation import DebtCreditEvent,simulate_revolving,resume_revolving,DebtCheckpoint
from engine.common import ZERO
from test_SCHEMA import _account,_segment
from test_search_simulation import cycles,minimum
from test_grace_simulation import terms as grace_terms


def event(id_,day=20,hour=12,sequence=0):
    return DebtCreditEvent(event_id=id_,credited_at=datetime(2026,1,day,hour,tzinfo=timezone.utc),sequence=sequence)


def account(state=G.LOST_GRACE):
    return _account(current_grace_state=state,segments=(_segment(balance='100',apr=assumed_default(D('3.65'))),))


def test_two_credits_same_day_apply_sequentially_before_daily_accrual():
    seen=[]
    def choose(view):seen.append(view);return D('30')
    r=simulate_revolving(account(),date(2026,1,1),date(2026,1,20),cycles(),minimum(),(),
        choose_decision=choose,credit_events=(event('one',hour=9),event('two',hour=16)))
    assert [p.amount for p in r.payments]==[D(30),D(30)]
    assert [v.segments[0].balance for v in seen]==[100,70]
    assert r.account.segments[0].accrued_unposted_interest==D('19.4')
    assert r.account.total_balance()==40
    assert [p.event_id for p in r.payments]==['one','two']


def test_same_day_full_payment_satisfies_grace_exactly_once():
    a=account(G.FULL_GRACE)
    r=simulate_revolving(a,date(2026,1,1),date(2026,1,31),cycles(),minimum(),(),
        choose_decision=lambda v:D(50),credit_events=(event('one',hour=9),event('two',hour=16)),grace_terms=grace_terms(a))
    assert r.account.current_grace_state==G.FULL_GRACE
    assert r.grace_decisions[0].credited_by_due==100 and r.account.total_balance()==0


def test_same_time_requires_explicit_sequence():
    with pytest.raises(ValueError,match='unambiguous'):
        simulate_revolving(account(),date(2026,1,1),date(2026,1,20),cycles(),minimum(),(),
            choose_decision=lambda v:ZERO,credit_events=(event('one'),event('two')))
    r=simulate_revolving(account(),date(2026,1,1),date(2026,1,20),cycles(),minimum(),(),
        choose_decision=lambda v:D(1),credit_events=(event('one'),event('two',sequence=1)))
    assert len(r.payments)==2


def test_credit_timezone_controls_due_date():
    # 01:00 UTC January 21 is January 20 in Chicago.
    a=account(G.FULL_GRACE)
    r=simulate_revolving(a,date(2026,1,1),date(2026,1,21),cycles(),minimum(),(),choose_decision=lambda v:D(100),
        credit_events=(DebtCreditEvent(event_id='late-utc',credited_at=datetime(2026,1,21,1,tzinfo=timezone.utc)),),
        credit_timezone='America/Chicago',grace_terms=grace_terms(a))
    assert r.payments[0].on==date(2026,1,20) and r.grace_decisions[0].paid_in_full


def test_resume_keeps_same_day_event_history_and_identity():
    events=(event('one',day=2),event('two',day=2,sequence=1),event('three',day=20))
    def run(end,ev):return simulate_revolving(account(),date(2026,1,1),end,cycles(),minimum(),(),
        choose_decision=lambda v:D(10),credit_events=ev)
    cp=DebtCheckpoint.model_validate_json(run(date(2026,1,3),events[:2]).checkpoint.model_dump_json())
    resumed=resume_revolving(cp,date(2026,1,31),(),choose_decision=lambda v:D(10),credit_events=events[2:])
    assert resumed==run(date(2026,1,31),events)
    with pytest.raises(ValueError,match='reused'):
        resume_revolving(cp,date(2026,1,31),(),choose_decision=lambda v:ZERO,credit_events=(event('one'),))


def test_zero_payment_event_is_still_recorded_for_duplicate_protection():
    r=simulate_revolving(account(),date(2026,1,1),date(2026,1,2),cycles(),minimum(),(),
        choose_decision=lambda v:ZERO,credit_events=(event('one',day=2),))
    assert not r.payments and r.checkpoint.credit_events
    with pytest.raises(ValueError,match='reused'):
        resume_revolving(r.checkpoint,date(2026,1,20),(),choose_decision=lambda v:ZERO,credit_events=(event('one'),))


def test_naive_timestamp_rejected():
    with pytest.raises(ValueError,match='timezone aware'):DebtCreditEvent(event_id='x',credited_at=datetime(2026,1,1))


def test_legacy_checkpoint_without_new_optional_fields_still_loads():
    r=simulate_revolving(account(),date(2026,1,1),date(2026,1,2),cycles(),minimum(),(date(2026,1,2),),lambda *args:D(1))
    raw=r.checkpoint.model_dump()
    raw.pop('credit_timezone');raw.pop('credit_events')
    for payment in raw['payments']:payment.pop('event_id');payment.pop('credited_at')
    assert DebtCheckpoint.model_validate(raw)==r.checkpoint


def test_checkpoint_rejects_reversed_same_day_credit_history():
    r=simulate_revolving(account(),date(2026,1,1),date(2026,1,20),cycles(),minimum(),(),
        choose_decision=lambda v:D(1),credit_events=(event('one',hour=9),event('two',hour=16)))
    raw=r.checkpoint.model_dump();raw['payments']=tuple(reversed(raw['payments']))
    with pytest.raises(ValueError,match='out of event order'):DebtCheckpoint.model_validate(raw)
