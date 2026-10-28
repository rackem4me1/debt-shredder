from decimal import Decimal, ROUND_FLOOR
from typing import Callable
from itertools import chain
from SCHEMA import StrictModel
from engine.common import ZERO,CENT,Nonnegative,decimal_context,decimal_input

class SearchBudgetExceeded(RuntimeError):
    """No guessed result is returned when evaluation budget is exhausted."""

class SearchResult(StrictModel):
    candidate:Nonnegative
    feasible:bool
    remaining:Nonnegative
    method:str
    evaluations:int
    minimum_certified:bool

@decimal_context
def bounded_payment_search(evaluate:Callable[[Decimal],Decimal],high:Decimal,*,
                           monotone_contract:bool=False,max_evaluations:int=100000)->SearchResult:
    """Scalar dollar search; evaluator simulates event-level liquidity clipping.

    Declared monotone contract paths use cent-bounded bisection after probes.
    General paths use the frozen $1 grid then exact cent verification, because
    sampling cannot certify that a nonmonotone feasible island does not exist.
    Budget exhaustion raises instead of falsely claiming infeasibility.
    """
    high=decimal_input(high)
    if high<0 or max_evaluations<1:raise ValueError('nonnegative bound and positive budget required')
    upper=int((high/CENT).to_integral_value(rounding=ROUND_FLOOR));cache={}
    def value(i):
        if i not in cache:
            if len(cache)>=max_evaluations:raise SearchBudgetExceeded('evaluation budget exhausted; no certified result')
            r=decimal_input(evaluate(Decimal(i)*CENT))
            if r<0:raise ValueError('residual must be nonnegative')
            cache[i]=r
        return cache[i]
    def finish(i,ok,method):
        residual=value(i)
        return SearchResult(candidate=Decimal(i)*CENT,feasible=ok,remaining=residual,
            method=method,evaluations=len(cache),minimum_certified=True)
    if value(0)==0:return finish(0,True,'already_satisfied')
    samples=sorted({0,upper//4,upper//2,upper*3//4,upper})
    vals=[value(i) for i in samples]
    if monotone_contract and all(b<=a for a,b in zip(vals,vals[1:])):
        if value(upper)>0:return finish(upper,False,'bounded_bisection')
        low=0;top=upper
        while top-low>1:
            mid=(low+top)//2
            if value(mid)==0:top=mid
            else:low=mid
        observed=sorted(cache)
        if all(value(b)<=value(a) for a,b in zip(observed,observed[1:])):
            return finish(top,True,'bounded_bisection')
    grid=chain(range(0,upper+1,100),(upper,) if upper%100 else ())
    limit=upper
    for i in grid:
        if value(i)==0:limit=i;break
    # Interpolation between a positive residual and a zero endpoint identifies
    # that endpoint only; verify every earlier cent instead of claiming it minimal.
    for i in range(1,limit+1):
        if value(i)==0:return finish(i,True,'bounded_grid_cent_verification')
    return finish(upper,False,'bounded_grid_cent_verification')
