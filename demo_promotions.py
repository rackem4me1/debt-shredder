"""Reproducible synthetic promo examples; no network, bank account, or LLM."""
import argparse
import calendar
import json
from datetime import date
from decimal import Decimal as D
from SCHEMA import (BalanceSegment, SegmentType, CompoundingMethod, DayCountConvention,
    DeferredInterestCalculationMethod, RevolvingAccount, AllocationRule, AllocationRuleType,
    GracePeriodState, BillingCycle, MinimumPaymentSnapshot, RoundingMode, assumed_default)
from engine.promotions import PromoTransition, PromoExitTerms
from engine.simulation import simulate_revolving


def scenario():
    segment=BalanceSegment(account_id='demo',segment_id='deferred',
        segment_type=SegmentType.PROMOTIONAL_DEFERRED_INTEREST,balance='100',apr=assumed_default(D(0)),
        compounding_method=assumed_default(CompoundingMethod.SIMPLE_DAILY),
        day_count_convention=assumed_default(DayCountConvention.ACTUAL_365),promo_expiration_date=date(2026,1,3),
        post_promo_apr=assumed_default(D('.1825')),post_promo_compounding_method=assumed_default(CompoundingMethod.SIMPLE_DAILY),
        deferred_interest_apr=assumed_default(D('.365')),
        deferred_interest_calculation_method=assumed_default(DeferredInterestCalculationMethod.AVERAGE_DAILY_BALANCE_SIMPLE),
        deferred_interest_to_date='5',projected_deferred_interest_at_expiration='5',deferred_interest_as_of_date=date(2025,12,31))
    account=RevolvingAccount(account_id='demo',issuer='Synthetic issuer',segments=(segment,),
        allocation_rule=AllocationRule(account_id='demo',minimum_payment_allocation_rule=assumed_default(AllocationRuleType.LOWEST_APR_FIRST),
            excess_payment_allocation_rule=assumed_default(AllocationRuleType.STATUTORY_DEFAULT)),
        statement_close_day=31,payment_due_day=20,current_grace_state=GracePeriodState.LOST_GRACE)
    cycles=[]
    for y,m in ((2025,11),(2025,12),(2026,1)):
        end=date(y,m,calendar.monthrange(y,m)[1])
        cycles.append(BillingCycle(account_id='demo',cycle_id=f'{y}-{m}',start_date=date(y,m,1),end_date=end,
            statement_date=end,due_date=date(y+(m==12),m%12+1,20)))
    minimum=MinimumPaymentSnapshot(account_id='demo',billing_cycle_id='2025-12',statement_minimum_original='0',statement_minimum_remaining='0')
    transition=PromoTransition(segment_id='deferred',terms=PromoExitTerms(cutoff=date(2026,1,3),rounding_mode=assumed_default(RoundingMode.HALF_UP)),
        post_exit_grace_eligible=assumed_default(False))
    return account,tuple(cycles),minimum,transition


def run():
    account,cycles,minimum,transition=scenario()
    outcomes={}
    for name,payments in (('unpaid',{}),('paid_on_cutoff',{date(2026,1,3):D('100')})):
        r=simulate_revolving(account,date(2026,1,1),date(2026,1,31),tuple(cycles),minimum,tuple(payments),
            lambda day,*args:payments[day],promo_transitions=(transition,))
        outcomes[name]={'ending_posted_balance':str(r.account.total_balance()),
            'exit':r.promo_exits[0].model_dump(mode='json'),
            'posted_events':[a.model_dump(mode='json') for a in r.audit if a.kind in ('promo_exit','interest_posting')],
            'payments':[p.model_dump(mode='json') for p in r.payments]}
    return {'description':'Synthetic inputs; estimated outputs; explicit end-of-day cutoff and no post-exit grace.',
        'unpaid_expected':'100 + 5.30 deferred assessment + 1.47 post-exit interest = 106.77',
        'outcomes':outcomes}


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output');args=parser.parse_args()
    serialized=json.dumps(run(),indent=2)+'\n'
    if args.output:
        from pathlib import Path
        Path(args.output).write_text(serialized)
    else:print(serialized)
