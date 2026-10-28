from datetime import date
from decimal import Decimal, localcontext
import pytest
from SCHEMA import *
from engine.common import *
from engine.interest import *
from engine.allocation import *
from engine.loans import *
from test_SCHEMA import _account,_segment,_loan as _simple_loan
D=Decimal

@pytest.mark.parametrize('mode,pos,neg',[(RoundingMode.HALF_UP,'1.01','-1.01'),(RoundingMode.HALF_EVEN,'1.00','-1.00'),(RoundingMode.TRUNCATE,'1.00','-1.00'),(RoundingMode.FLOOR,'1.00','-1.01'),(RoundingMode.CEILING,'1.01','-1.00')])
def test_posting(mode,pos,neg):
    assert posting(D('1.005'),mode)==D(pos)
    assert posting(D('-1.005'),mode)==D(neg)

@pytest.mark.parametrize('bad',[0.1,True,D('NaN'),D('Infinity')])
def test_unsafe_arithmetic(bad):
    with pytest.raises(ValueError):posting(bad,RoundingMode.HALF_UP)


def test_no_daily_rounding_and_ambient_independence():
    with localcontext() as ctx:
        ctx.prec=5
        result=accrue_constant(D(100),D('.1'),date(2026,1,1),date(2026,1,31),DayCountConvention.ACTUAL_365,CompoundingMethod.SIMPLE_DAILY)
    assert abs(result-D('0.8219178082191780821917808219'))<D('1e-26')
    assert result!=D('.03')*30
    assert posting(result,RoundingMode.HALF_UP)==D('.82')


def test_compounding_and_leap_year():
    assert accrue_constant(D(100),D('3.65'),date(2026,1,1),date(2026,1,3),DayCountConvention.ACTUAL_365,CompoundingMethod.DAILY_COMPOUNDING)==D('2.01')
    with localcontext(CONTEXT):expected=D(10)/366+D(10)/365
    assert accrue_constant(D(100),D('.1'),date(2024,12,31),date(2025,1,2),DayCountConvention.ACTUAL_ACTUAL,CompoundingMethod.SIMPLE_DAILY)==expected


def test_unknown_contract_terms_fail_closed():
    with pytest.raises(MissingTerms):accrue_constant(D(100),D('.1'),date(2026,1,1),date(2026,2,1),DayCountConvention.ACTUAL_365,CompoundingMethod.MONTHLY_COMPOUNDING)
    with pytest.raises(UnsupportedTerms):daily_rate(D('.1'),date(2026,1,1),DayCountConvention.THIRTY_360)


def test_deferred_and_contingent_grace_projection():
    history=tuple(DailyBalance(day=date(2026,1,d),balance='100') for d in range(1,4))
    verified=(ProvenanceSource.ACTUAL_STATEMENT,ProvenanceSource.CONTRACTUAL_DISCLOSURE)
    out=deferred_exposure(history,D('3.65'),DayCountConvention.ACTUAL_365,DeferredInterestCalculationMethod.AVERAGE_DAILY_BALANCE_SIMPLE,verified,opening=D(5))
    assert out.amount==8 and out.label=='verified_projection'
    assert deferred_exposure(history,D('3.65'),DayCountConvention.ACTUAL_365,DeferredInterestCalculationMethod.DAILY_COMPOUNDING,(ProvenanceSource.ASSUMED_DEFAULT,)).label=='estimate'
    assert contingent_grace_interest(history,D('3.65'),DayCountConvention.ACTUAL_365,verified).amount==3


def minimum(amount='25'):
    return MinimumPaymentSnapshot(account_id='a1',billing_cycle_id='c',statement_minimum_original=amount,statement_minimum_remaining=amount)


def test_minimum_then_excess_and_conservation():
    a=_account(segments=(_segment(segment_id='low',balance='100',apr=assumed_default(D('.1'))),_segment(segment_id='high',balance='200',apr=assumed_default(D('.3')))))
    out=allocate_payment(a,D(125),minimum(),date(2026,1,1))
    assert [(x.segment_id,x.amount,x.phase) for x in out.lines]==[('low',D(25),'minimum'),('high',D(100),'excess')]
    assert sum((r.amount for r in out.remaining_balances),ZERO)+out.applied==300
    assert a.total_balance()==300 and out.minimum_remaining==0


def test_cap_minimum_return_overpayment_and_projected_formula():
    out=allocate_payment(_account(segments=(_segment(balance='10'),)),D(100),minimum(),date(2026,1,1))
    assert (out.applied,out.unapplied,out.minimum_remaining)==(10,90,0)
    assert projected_minimum(D(10),D(25),D('.02'))==10
    assert projected_minimum(D(1000),D(25),D('.02'),D(5),D(10))==35


def test_partial_minimum_not_paid_twice():
    snap=MinimumPaymentSnapshot(account_id='a1',billing_cycle_id='c',statement_minimum_original='25',statement_minimum_remaining='5')
    out=allocate_payment(_account(),D(10),snap,date(2026,1,1))
    assert [(x.phase,x.amount) for x in out.lines]==[('minimum',D(5)),('excess',D(5))]


def promo_account():
    return _account(segments=(_segment(segment_id='promo',segment_type=SegmentType.PROMOTIONAL_TRUE_ZERO,balance='100',apr=assumed_default(D(0)),promo_expiration_date=date(2026,4,15),post_promo_apr=assumed_default(D('.2')),post_promo_compounding_method=assumed_default(CompoundingMethod.SIMPLE_DAILY)),_segment(segment_id='high',balance='200',apr=assumed_default(D('.3')))))


def cycles():
    import calendar
    return tuple(BillingCycle(cycle_id=str(m),account_id='a1',start_date=date(2026,m,1),end_date=date(2026,m,calendar.monthrange(2026,m)[1]),statement_date=date(2026,m,calendar.monthrange(2026,m)[1]),due_date=date(2026,m+1,20)) for m in range(1,5))


def test_complete_cycles_not_sixty_days():
    a=promo_account()
    assert expiring_priority(a,cycles(),date(2026,2,1))==('promo',)
    assert expiring_priority(a,cycles(),date(2026,1,31))==()
    out=allocate_payment(a,D(50),minimum('0'),date(2026,2,1),cycles())
    assert out.lines[0].segment_id=='promo' and out.lines[0].phase=='expiring_promo'
    with pytest.raises(MissingTerms):allocate_payment(a,D(10),minimum(),date(2026,2,1))


def test_pro_rata_residual_cents():
    a=_account(segments=tuple(_segment(segment_id=k,balance='1') for k in ('a','b','c')),allocation_rule=AllocationRule(account_id='a1',minimum_payment_allocation_rule=assumed_default(AllocationRuleType.PRO_RATA),excess_payment_allocation_rule=assumed_default(AllocationRuleType.STATUTORY_DEFAULT)))
    out=allocate_payment(a,D(1),minimum('1'),date(2026,1,1))
    assert tuple(x.amount for x in out.lines)==(D('.34'),D('.33'),D('.33'))


def test_unresolved_rule_is_not_calculated():
    a=_account(allocation_rule=AllocationRule(account_id='a1',minimum_payment_allocation_rule=assumed_default(AllocationRuleType.ISSUER_SPECIFIC_CONFIGURED),minimum_rule_configuration=IssuerAllocationConfiguration(segment_priority_order=(SegmentType.STANDARD_PURCHASE,)),excess_payment_allocation_rule=assumed_default(AllocationRuleType.STATUTORY_DEFAULT)))
    with pytest.raises(MissingTerms):allocate_payment(a,D(10),minimum(),date(2026,1,1))


def test_note_rate_not_disclosed_apr():
    loan=_simple_loan(principal_balance=D(3650),contract_note_rate=assumed_default(D('.1')),disclosed_apr=assumed_default(D('.8')))
    assert accrue_loan(loan,date(2026,1,1),date(2026,1,2))==1


def test_loan_waterfall_and_paid_ahead_still_accrues():
    loan=_simple_loan(principal_balance=D(1000),fees_outstanding=D(10),accrued_interest=D(20))
    out=pay_loan(loan,D(100))
    assert (out.fees_paid,out.interest_paid,out.principal_paid)==(10,20,70)
    ahead=reconstruct(loan,prepayment_behavior=assumed_default(PrepaymentBehavior.PAID_AHEAD),contractual_payment_amount=assumed_default(D(50)))
    with pytest.raises(MissingTerms):pay_loan(ahead,D(100))
    assert pay_loan(ahead,D(100),next_contractual_due_date=date(2027,1,1)).next_due_date==date(2027,1,1)
    assert accrue_loan(ahead,date(2026,1,1),date(2026,1,2))>ahead.accrued_interest


def test_supported_consumer_override_only_uses_excess():
    rule=AllocationRule(account_id='a1',minimum_payment_allocation_rule=assumed_default(AllocationRuleType.LOWEST_APR_FIRST),
        excess_payment_allocation_rule=assumed_default(AllocationRuleType.STATUTORY_DEFAULT),consumer_override_supported=assumed_default(True))
    a=_account(segments=(_segment(segment_id='low',balance='100',apr=assumed_default(D('.1'))),_segment(segment_id='high',balance='100',apr=assumed_default(D('.3')))),allocation_rule=rule)
    result=allocate_payment(a,D(50),minimum('25'),date(2026,1,1),directed=(DirectedAmount(segment_id='low',amount='25'),))
    assert [(r.segment_id,r.phase,r.amount) for r in result.lines]==[('low','minimum',D(25)),('low','consumer_directed',D(25))]
    with pytest.raises(ValueError,match='excess'):allocate_payment(a,D(50),minimum('25'),date(2026,1,1),directed=(DirectedAmount(segment_id='low',amount='26'),))


def test_custom_same_type_order_drives_actual_allocation():
    rule=AllocationRule(account_id='a1',minimum_payment_allocation_rule=assumed_default(AllocationRuleType.ISSUER_SPECIFIC_CONFIGURED),
        minimum_rule_configuration=IssuerAllocationConfiguration(segment_priority_order=(SegmentType.STANDARD_PURCHASE,),segment_id_priority_order=('b','a'),is_resolved=True),
        excess_payment_allocation_rule=assumed_default(AllocationRuleType.STATUTORY_DEFAULT))
    a=_account(segments=(_segment(segment_id='a',balance='100'),_segment(segment_id='b',balance='100')),allocation_rule=rule)
    r=allocate_payment(a,D(25),minimum(),date(2026,1,1))
    assert r.lines[0].segment_id=='b'


def test_posted_balance_boundary_does_not_round_silently():
    with pytest.raises(ValueError,match='whole cents'):
        allocate_payment(_account(segments=(_segment(balance='1.005'),)),D(1),minimum(),date(2026,1,1))


def test_deferred_projection_requires_complete_daily_history():
    with pytest.raises(ValueError,match='consecutive'):
        deferred_exposure((DailyBalance(day=date(2026,1,1),balance='100'),DailyBalance(day=date(2026,1,3),balance='100')),
            D('.1'),DayCountConvention.ACTUAL_365,DeferredInterestCalculationMethod.AVERAGE_DAILY_BALANCE_SIMPLE,())
