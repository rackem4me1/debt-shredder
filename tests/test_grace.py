from datetime import date
from decimal import Decimal
import pytest
from SCHEMA import BillingCycle, GracePeriodState as G, assumed_default, ProvenanceSource as P, Sourced
from engine.grace import StatementCredit, GraceStatement, resolve_grace
from engine.common import MissingTerms


def statement(month, amount='100', paid='100', credit_day=20, **updates):
    end = (31, 28, 31)[month-1]
    cycle = BillingCycle(cycle_id=str(month), account_id='card', start_date=date(2027,month,1),
        end_date=date(2027,month,end), statement_date=date(2027,month,end), due_date=date(2027,month+1,20))
    data = dict(cycle=cycle, original_statement_balance=amount,
        credits=(StatementCredit(credit_id=str(month), credited_on=date(2027,month+1,credit_day), amount=paid),))
    return GraceStatement(**(data | updates))


def resolve(records, opening=G.LOST_GRACE, required=2, **kwargs):
    return resolve_grace('card', opening, assumed_default(required), records, date(2027,4,20), **kwargs)


def test_two_full_cycles_restore_default():
    result=resolve((statement(1),statement(2)))
    assert [x.resulting_state for x in result.decisions] == [G.LOST_GRACE,G.FULL_GRACE]
    assert result.consecutive_full_statements == 2
    assert result.label == 'estimate'


def test_contract_one_cycle_restoration():
    assert resolve((statement(1),),required=1).state == G.FULL_GRACE


def test_minimum_is_not_full_statement():
    r=resolve((statement(1,paid='25'),),opening=G.FULL_GRACE)
    assert r.state == G.LOST_GRACE
    assert r.decisions[0].remaining_at_due == Decimal('75')


def test_late_credit_does_not_retroactively_restore():
    assert resolve((statement(1,credit_day=21),),opening=G.FULL_GRACE).state == G.LOST_GRACE


def test_interrupted_streak_resets():
    r=resolve((statement(1),statement(2,paid='99.99'),statement(3)))
    assert r.state == G.LOST_GRACE
    assert r.consecutive_full_statements == 1


def test_full_grace_stays_full_after_one_full_statement():
    assert resolve((statement(1),),opening=G.FULL_GRACE).state == G.FULL_GRACE


def test_zero_statement_counts_as_satisfied():
    assert resolve((statement(1,amount='0',paid='0'),),required=1).state == G.FULL_GRACE


def test_pending_preserves_resolved_state_and_streak():
    r=resolve_grace('card',G.LOST_GRACE,assumed_default(2),(statement(1),statement(2)),date(2027,3,1))
    assert r.state == G.PENDING
    assert r.last_resolved_state == G.LOST_GRACE
    assert r.consecutive_full_statements == 1
    assert r.pending_cycle_ids == ('2',)


def test_credit_cannot_be_reused():
    a=statement(1)
    b=statement(2,credits=(StatementCredit(credit_id='1',credited_on=date(2027,3,20),amount='100'),))
    with pytest.raises(ValueError,match='reused'):resolve((a,b))


@pytest.mark.parametrize('records',[(statement(1),statement(3)),(statement(2),statement(1))])
def test_missing_or_reordered_cycles_stop_resolution(records):
    with pytest.raises(MissingTerms):resolve(records)


def test_pending_opening_requires_prior_resolved_state():
    with pytest.raises(MissingTerms):resolve((statement(1),),opening=G.PENDING)


def test_resume_streak():
    assert resolve((statement(2),),opening_consecutive_full=1).state == G.FULL_GRACE


def test_verified_label_requires_all_inputs():
    s=statement(1,balance_provenance=P.ACTUAL_STATEMENT,credits=(StatementCredit(
        credit_id='a',credited_on=date(2027,2,20),amount='100',provenance=P.ACTUAL_STATEMENT),))
    term=Sourced[int](value=2,provenance=P.CONTRACTUAL_DISCLOSURE,confirmed_date=date(2027,1,1))
    r=resolve_grace('card',G.FULL_GRACE,term,(s,),date(2027,2,20),opening_provenance=P.ACTUAL_STATEMENT)
    assert r.label == 'verified_projection'


def test_early_credit_and_subcent_amount_rejected():
    with pytest.raises(ValueError):statement(1,amount='100.001')
    with pytest.raises(ValueError):statement(1,credits=(StatementCredit(credit_id='a',credited_on=date(2027,1,1),amount='100'),))


def test_future_statement_rejected():
    with pytest.raises(ValueError,match='not closed'):
        resolve_grace('card',G.FULL_GRACE,assumed_default(2),(statement(1),),date(2027,1,15))


def test_wrong_account_and_duplicate_cycle_rejected():
    s=statement(1)
    with pytest.raises(ValueError,match='account mismatch'):
        resolve_grace('other',G.FULL_GRACE,assumed_default(2),(s,),date(2027,2,20))
    with pytest.raises(ValueError,match='duplicate statement cycle'):resolve((s,s))


def test_multiple_partial_credits_and_overpayment():
    s=statement(1,credits=tuple(StatementCredit(credit_id=str(i),credited_on=date(2027,2,day),amount=amount)
        for i,(day,amount) in enumerate(((1,'25'),(20,'80'),(21,'10')))))
    r=resolve((s,),required=1)
    assert r.decisions[0].credited_by_due == Decimal('105')
    assert r.decisions[0].remaining_at_due == 0
    assert r.state == G.FULL_GRACE


def test_resolution_is_immutable_and_json_roundtrips():
    s=statement(1)
    before=s.model_dump_json()
    r=resolve((s,))
    assert type(r).model_validate_json(r.model_dump_json()) == r
    assert s.model_dump_json() == before
    with pytest.raises(ValueError):r.state=G.FULL_GRACE
