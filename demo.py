"""Synthetic examples only. Run: python demo.py [--output results.json]."""
import argparse
import json
from datetime import datetime,date,timedelta,timezone
from decimal import Decimal
from SCHEMA import *
from engine.common import ZERO
from engine.interest import accrue_constant
from engine.allocation import allocate_payment
from engine.liquidity import *
from engine.search import bounded_payment_search
D=Decimal
T=datetime(2026,1,2,12,tzinfo=timezone.utc)


def event(id_,kind,amount,day):
    when=T+timedelta(days=day)
    return CashPlan(plan_id=id_,kind=kind,amount=amount,
        source_account_id='checking' if kind!=CashKind.INCOME else None,
        destination_account_id='checking' if kind==CashKind.INCOME else None,
        initiated_at=when,credited_at=when,debited_at=when,settled_at=when)


def run():
    openings=(CashOpening(account_id='checking',cleared='1000',floor='100',primary=True),
              CashOpening(account_id='savings',cleared='1500',reserved='1200',floor='0'))
    transfer=CashPlan(plan_id='savings-transfer',kind=CashKind.TRANSFER,amount='300',
        source_account_id='savings',destination_account_id='checking',initiated_at=T+timedelta(days=1),
        debited_at=T+timedelta(days=1),credited_at=T+timedelta(days=2),settled_at=T+timedelta(days=3))
    plans=(transfer,event('bill-1',CashKind.EXPENSE,'350',5),event('paycheck',CashKind.INCOME,'800',14),event('bill-2',CashKind.EXPENSE,'1000',30))
    cash=project_liquidity(openings,plans,T)
    def seg(id_,amount,apr):
        return BalanceSegment(segment_id=id_,account_id='card',segment_type=SegmentType.STANDARD_PURCHASE,
            balance=amount,apr=assumed_default(D(apr)),compounding_method=assumed_default(CompoundingMethod.SIMPLE_DAILY),day_count_convention=assumed_default(DayCountConvention.ACTUAL_365))
    account=RevolvingAccount(account_id='card',issuer='Synthetic issuer',segments=(seg('lower','100','.10'),seg('higher','200','.30')),
        allocation_rule=AllocationRule(account_id='card',minimum_payment_allocation_rule=assumed_default(AllocationRuleType.LOWEST_APR_FIRST),
            excess_payment_allocation_rule=assumed_default(AllocationRuleType.STATUTORY_DEFAULT)),statement_close_day=31,payment_due_day=20)
    minimum=MinimumPaymentSnapshot(account_id='card',billing_cycle_id='example',statement_minimum_original='25',statement_minimum_remaining='25')
    allocated=allocate_payment(account,D('125'),minimum,date(2026,1,10))
    # This simple fixed-budget family is provably monotone, so bisection applies.
    # The integrated plan_promo replay uses the general safe fallback instead.
    search=bounded_payment_search(lambda p:max(ZERO,D(160)-min(p,D(50))-min(p,D(150))),D(150),monotone_contract=True)
    interest=accrue_constant(D(1000),D('.12'),date(2026,1,1),date(2026,2,1),DayCountConvention.ACTUAL_365,CompoundingMethod.SIMPLE_DAILY)
    return {'example':'Synthetic data; not a recommendation for a real account',
        'liquidity':cash.model_dump(mode='json'),'payment_allocation':allocated.model_dump(mode='json'),
        'candidate_search':search.model_dump(mode='json'),'unposted_interest':str(interest)}

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output');args=parser.parse_args()
    result=run();serialized=json.dumps(result,indent=2)
    if args.output:
        from pathlib import Path
        Path(args.output).write_text(serialized+'\n')
    else:print(serialized)
