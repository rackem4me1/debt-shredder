from decimal import Context, Decimal, localcontext, ROUND_DOWN
from functools import wraps
from typing import Annotated
from pydantic import BeforeValidator, Field
from SCHEMA import RoundingMode, ProvenanceSource

ZERO = Decimal('0')
CENT = Decimal('0.01')
CONTEXT = Context(prec=28)

class MissingTerms(ValueError):
    """Calculation needs explicit contract or schedule inputs."""

class UnsupportedTerms(ValueError):
    """A term is representable but not implemented by this engine release."""


def decimal_input(value):
    if isinstance(value, (float, bool)):
        raise ValueError('financial inputs must be Decimal, integer, or decimal string')
    try:
        result = Decimal(value)
    except (TypeError, ValueError, ArithmeticError) as exc:
        raise ValueError('invalid decimal input') from exc
    if not result.is_finite():
        raise ValueError('financial inputs must be finite')
    return result

Money = Annotated[Decimal, BeforeValidator(decimal_input)]
Nonnegative = Annotated[Money, Field(ge=0)]
Positive = Annotated[Money, Field(gt=0)]


def decimal_context(fn):
    @wraps(fn)
    def scoped(*args, **kwargs):
        with localcontext(CONTEXT):
            return fn(*args, **kwargs)
    return scoped


@decimal_context
def posting(amount: Decimal, mode: RoundingMode) -> Decimal:
    """Use only at a contractual posting event, never during accrual."""
    amount = decimal_input(amount)
    mode = RoundingMode(mode)
    return amount.quantize(CENT, rounding=ROUND_DOWN if mode == RoundingMode.TRUNCATE else mode.value)


def projection_label(sources: tuple[ProvenanceSource, ...]) -> str:
    verified = {ProvenanceSource.ACTUAL_STATEMENT, ProvenanceSource.CONTRACTUAL_DISCLOSURE}
    return 'verified_projection' if sources and all(s in verified for s in sources) else 'estimate'


def reconstruct(record, **updates):
    """Validate a complete replacement; never bypass immutable-model validators."""
    return type(record).model_validate({**record.model_dump(), **updates})
