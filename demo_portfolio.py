"""Synthetic shared-cash request coordination; no real account access."""
import argparse
import calendar
import json
from datetime import datetime,date,timedelta,timezone
from decimal import Decimal as D
from SCHEMA import (BalanceSegment,SegmentType,CompoundingMethod,DayCountConvention,RevolvingAccount,
    AllocationRule,AllocationRuleType,GracePeriodState,BillingCycle,MinimumPaymentSnapshot,assumed_default)
from engine.portfolio import PortfolioDebt,PortfolioPaymentRequest,RequestKind,coordinate_payments
from engine.liquidity import CashOpening


def scenario():
    start=datetime(2026,1,1,tzinfo=timezone.utc)
    debts=[]
    for id_ in ('card-a','card-b'):
        segment=BalanceSegment(account_id=id_,segment_id='purchase',segment_type=SegmentType.STANDARD_PURCHASE,
            balance='500',apr=assumed_default(D(0)),compounding_method=assumed_default(CompoundingMethod.SIMPLE_DAILY),
            day_count_convention=assumed_default(DayCountConvention.ACTUAL_365))
        account=RevolvingAccount(account_id=id_,issuer='Synthetic issuer',segments=(segment,),
            allocation_rule=AllocationRule(account_id=id_,minimum_payment_allocation_rule=assumed_default(AllocationRuleType.LOWEST_APR_FIRST),
                excess_payment_allocation_rule=assumed_default(AllocationRuleType.STATUTORY_DEFAULT)),
            statement_close_day=31,payment_due_day=20,current_grace_state=GracePeriodState.LOST_GRACE)
        cycles=[]
        for y,m in ((2025,12),(2026,1)):
            end=date(y,m,calendar.monthrange(y,m)[1])
            cycles.append(BillingCycle(account_id=id_,cycle_id=f'{y}-{m}',start_date=date(y,m,1),end_date=end,
                statement_date=end,due_date=date(y+(m==12),m%12+1,20)))
        debts.append(PortfolioDebt(account=account,cycles=tuple(cycles),initial_minimum=MinimumPaymentSnapshot(
            account_id=id_,billing_cycle_id='2025-12',statement_minimum_original='50',statement_minimum_remaining='50')))
    def request(id_,account,amount,day,kind,priority):
        at=start+timedelta(days=day-1)
        return PortfolioPaymentRequest(request_id=id_,debt_account_id=account,source_account_id='checking',amount=amount,
            kind=kind,priority=priority,initiated_at=at,credited_at=at+timedelta(days=1),
            debited_at=at+timedelta(days=2),settled_at=at+timedelta(days=3))
    requests=(request('extra-a','card-a','500',2,RequestKind.EXTRA,0),
        request('minimum-a','card-a','50',10,RequestKind.MINIMUM,0),request('minimum-b','card-b','50',10,RequestKind.MINIMUM,1))
    from dashboard.scenarios import Scenario
    return Scenario(name='Shared cash example',origin='synthetic_demo',debts=tuple(debts),
        openings=(CashOpening(account_id='checking',cleared='500',floor='100',primary=True),),
        cash_plans=(),requests=requests,start=start,end=datetime(2026,1,21,tzinfo=timezone.utc))


def run():
    result=scenario().project()
    return {'example':'Synthetic zero-rate accounts; explicit minimum requests before extras; supplied cash events only.',
        'decisions':[d.model_dump(mode='json') for d in result.decisions],
        'ending_checking':str(result.liquidity.points[-1].positions[0].cleared),
        'debt_balances':{d.account.account_id:str(d.account.total_balance()) for d in result.debt_projections},
        'missed_minimum_account_ids':result.missed_minimum_account_ids,
        'debt_horizon_end':result.debt_horizon_end.isoformat(),'cash_horizon_end':result.liquidity.end.isoformat()}


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output');args=parser.parse_args()
    encoded=json.dumps(run(),indent=2)+'\n'
    if args.output:
        from pathlib import Path
        Path(args.output).write_text(encoded)
    else:print(encoded)
