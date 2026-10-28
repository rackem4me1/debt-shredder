from datetime import date
from decimal import Decimal, ROUND_DOWN
from SCHEMA import (StrictModel, RevolvingAccount, MinimumPaymentSnapshot, AllocationRuleType,
                    BillingCycle, SegmentType, ProvenanceSource)
from engine.promotions import PromoExitResult
from engine.common import (ZERO, CENT, Nonnegative, Positive, Money, decimal_context,
                           decimal_input, MissingTerms, UnsupportedTerms, projection_label)


class DirectedAmount(StrictModel):
    segment_id: str
    amount: Positive

class AllocationLine(StrictModel):
    segment_id: str
    amount: Nonnegative
    phase: str

class PaymentAllocation(StrictModel):
    requested: Nonnegative
    applied: Nonnegative
    unapplied: Nonnegative
    minimum_remaining: Nonnegative
    lines: tuple[AllocationLine, ...]
    remaining_balances: tuple[DirectedAmount, ...]  # only positive balances
    label: str


@decimal_context
def projected_minimum(balance: Decimal, floor: Decimal, percentage: Decimal,
                      fees: Decimal = ZERO, billed_interest: Decimal = ZERO) -> Decimal:
    balance, floor, percentage, fees, billed_interest = map(decimal_input,
        (balance, floor, percentage, fees, billed_interest))
    if min(balance, floor, percentage, fees, billed_interest) < 0 or percentage > 1:
        raise ValueError('invalid projected minimum inputs')
    return min(balance, max(floor, fees + billed_interest + percentage * balance))


def expiring_priority(account: RevolvingAccount, cycles: tuple[BillingCycle, ...],
                      credited_on: date, *, exited_ids: frozenset[str] = frozenset()) -> tuple[str, ...]:
    """Use complete billing cycles, never an approximate 60-day window."""
    promos = [s for s in account.segments if s.segment_id not in exited_ids and s.promo_expiration_date and s.balance > 0
              and credited_on <= s.promo_expiration_date]
    if not promos or not account.allocation_rule.final_two_cycle_deferred_override_applies.value:
        return ()
    relevant = sorted((c for c in cycles if c.account_id == account.account_id), key=lambda c:c.start_date)
    if any(b.start_date.toordinal() != a.end_date.toordinal() + 1 for a,b in zip(relevant,relevant[1:])):
        raise MissingTerms('complete contiguous billing cycles are required for promo override')
    priorities = []
    for seg in promos:
        if not relevant or relevant[-1].end_date < seg.promo_expiration_date:
            raise MissingTerms('billing cycle schedule must cover the promotional expiration')
        before = [c for c in relevant if c.end_date < seg.promo_expiration_date]
        if len(before) < 2:
            raise MissingTerms('two complete pre-expiration billing cycles are required')
        if any(c.start_date <= credited_on <= c.end_date for c in before[-2:]):
            priorities.append(seg)
    return tuple(s.segment_id for s in sorted(priorities,key=lambda s:(s.promo_expiration_date,s.segment_id)))


@decimal_context
def allocate_payment(account: RevolvingAccount, amount: Decimal, minimum: MinimumPaymentSnapshot,
                     credited_on: date, cycles: tuple[BillingCycle, ...] = (),
                     directed: tuple[DirectedAmount, ...] = (), *,
                     promo_exits: tuple[PromoExitResult, ...] = ()) -> PaymentAllocation:
    """Allocate a posted payment; ledger movements and unposted accrual are separate.

    Equal APR ties use stable segment IDs, an ASSUMED_DEFAULT allocation detail.
    No financial result from the source models is mutated.
    """
    amount = decimal_input(amount)
    if amount < 0 or amount % CENT:
        raise ValueError('posted payment must be nonnegative whole cents')
    if any(request.amount % CENT for request in directed):
        raise ValueError('directed payment amounts must be exact whole cents')
    if minimum.account_id != account.account_id:
        raise ValueError('minimum belongs to another account')
    if not account.calculation_ready:
        raise MissingTerms('account allocation configuration is not ready')
    by_id = {s.segment_id:s for s in account.segments}
    balances = {s.segment_id:s.balance for s in account.segments}
    exits={e.segment_id:e for e in promo_exits}
    if len(exits)!=len(promo_exits) or any(e.account_id!=account.account_id or e.segment_id not in by_id for e in promo_exits):
        raise ValueError('promo exits must be unique and belong to this account')
    if any(credited_on<e.reversion_starts for e in promo_exits):
        raise ValueError('replacement allocation terms cannot apply before reversion')
    rates={k:exits[k].replacement_apr.value if k in exits else s.apr.value for k,s in by_id.items()}

    if any(b % CENT for b in balances.values()) or minimum.statement_minimum_remaining % CENT:
        raise ValueError('posted balances and minimums must be whole cents; unposted accrual is separate')
    total = sum(balances.values(),ZERO)
    remaining_min = min(minimum.statement_minimum_remaining,total)
    minimum_part = min(amount,remaining_min)
    excess = min(max(ZERO,amount-minimum_part),total-minimum_part)
    if directed and not account.allocation_rule.consumer_override_supported.value:
        raise MissingTerms('issuer does not support consumer-directed allocation')
    if len({r.segment_id for r in directed}) != len(directed) or any(r.segment_id not in by_id for r in directed):
        raise ValueError('directed segment references must be unique and belong to account')
    if sum((r.amount for r in directed),ZERO) > excess:
        raise ValueError('consumer requests exceed the excess portion')
    lines = []
    def apply(ids, budget, phase):
        for id_ in ids:
            take=min(balances[id_],budget)
            if take:
                balances[id_]-=take
                budget-=take
                lines.append(AllocationLine(segment_id=id_,amount=take,phase=phase))
            if budget == 0:break
        return budget
    def apply_rule(rule, config, budget, phase):
        if rule == AllocationRuleType.PRO_RATA:
            # Cent apportionment, largest fractional remainder first, stable ID ties.
            # Refuse fractional posted balances rather than distribute fractional cents.
            if budget % CENT or any(b % CENT for b in balances.values()):
                raise UnsupportedTerms('pro-rata posting requires cent-denominated balances')
            active={k:b for k,b in balances.items() if b>0}
            denom=sum(active.values(),ZERO)
            if not denom:return budget
            raw={k:budget*b/denom for k,b in active.items()}
            shares={k:v.quantize(CENT,rounding=ROUND_DOWN) for k,v in raw.items()}
            pennies=int((budget-sum(shares.values(),ZERO))/CENT)
            for k in sorted(active,key=lambda k:(-(raw[k]-shares[k]),k))[:pennies]:
                shares[k]+=CENT
            for k in sorted(shares):apply((k,),shares[k],phase)
            return ZERO
        if rule == AllocationRuleType.ISSUER_SPECIFIC_CONFIGURED:
            rank={kind:i for i,kind in enumerate(config.segment_priority_order)}
            ids=config.segment_id_priority_order or tuple(sorted(by_id,key=lambda k:(rank[by_id[k].segment_type],k)))
        elif rule == AllocationRuleType.LOWEST_APR_FIRST or (rule == AllocationRuleType.STATUTORY_DEFAULT and phase=='minimum'):
            ids=sorted(by_id,key=lambda k:(rates[k],k))
        elif rule == AllocationRuleType.STATUTORY_DEFAULT:
            ids=sorted(by_id,key=lambda k:(-rates[k],k))
        elif rule == AllocationRuleType.FEES_FINANCE_CHARGES_FIRST:
            ids=sorted(by_id,key=lambda k:(by_id[k].segment_type!=SegmentType.FEES_AND_PENALTIES,-rates[k],k))
        else:
            raise UnsupportedTerms('CONSUMER_DIRECTED must be expressed as explicit excess requests with a fallback rule')
        return apply(ids,budget,phase)
    rules=account.allocation_rule
    apply_rule(rules.minimum_payment_allocation_rule.value,rules.minimum_rule_configuration,minimum_part,'minimum')
    # Exclude exited segments before resolving promo windows; an early
    # disqualification must not retain a later scheduled expiration override.
    priority=expiring_priority(account,cycles,credited_on,exited_ids=frozenset(exits))
    excess=apply(priority,excess,'expiring_promo')
    for request in directed:
        budget=min(excess,request.amount)
        left=apply((request.segment_id,),budget,'consumer_directed')
        excess-=budget-left
    apply_rule(rules.excess_payment_allocation_rule.value,rules.excess_rule_configuration,excess,'excess')
    applied=sum((line.amount for line in lines),ZERO)
    sources=(rules.minimum_payment_allocation_rule.provenance,rules.excess_payment_allocation_rule.provenance,
             minimum.provenance,ProvenanceSource.ASSUMED_DEFAULT)  # tie-break policy is explicitly assumed
    return PaymentAllocation(requested=amount,applied=applied,unapplied=amount-applied,
        minimum_remaining=max(ZERO,remaining_min-minimum_part),lines=tuple(lines),
        remaining_balances=tuple(DirectedAmount(segment_id=k,amount=v) for k,v in sorted(balances.items()) if v>0),
        label=projection_label(sources))
