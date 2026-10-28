"""Versioned inputs, distinct from ledger records and resume checkpoints."""
from datetime import datetime
from pathlib import Path
from typing import Literal, Annotated
import json
import os
import tempfile
from pydantic import Field, model_validator
from SCHEMA import StrictModel
from engine.portfolio import PortfolioDebt, PortfolioPaymentRequest, coordinate_payments
from engine.liquidity import CashOpening, CashPlan
from dashboard.cash_inputs import ManualCashEvent, CASH_ROWS, cash_horizon, expand_cash_events

MAX_BYTES = 4 * 1024 * 1024


class Scenario(StrictModel):
    format: Literal['debt-shredder-scenario'] = 'debt-shredder-scenario'
    version: Literal[1] = 1
    name: str = Field(min_length=1, max_length=120)
    origin: Literal['synthetic_demo', 'manual']
    start: datetime
    end: datetime
    debts: tuple[PortfolioDebt, ...] = Field(min_length=1, max_length=20)
    openings: tuple[CashOpening, ...] = Field(min_length=1, max_length=20)
    cash_plans: tuple[CashPlan, ...] = Field(max_length=500)
    requests: tuple[PortfolioPaymentRequest, ...] = Field(max_length=500)

    card_names: tuple[Annotated[str, Field(max_length=60)], ...] = Field(default=(), max_length=20)
    manual_cash_schedules: tuple[ManualCashEvent, ...] = Field(default=(), max_length=CASH_ROWS)

    @model_validator(mode='after')
    def validate_horizon(self):
        if self.start.utcoffset() is None or self.end.utcoffset() is None:
            raise ValueError('Scenario dates must include a time zone')
        if not 0 <= (self.end - self.start).total_seconds() <= 366 * 86400:
            raise ValueError('Scenario window must be ordered and no longer than 366 days')
        if not self.name.strip():
            raise ValueError('Scenario name cannot be blank')
        if self.card_names and len(self.card_names) != len(self.debts):
            raise ValueError('Card names must match the debt accounts in order')
        if self.manual_cash_schedules:
            if len({d.credit_timezone for d in self.debts}) != 1 or len(self.openings) != 1 or self.openings[0].account_id != 'checking':
                raise ValueError('Manual cash schedules require a shared time zone and the checking account')
            expected = expand_cash_events(self.manual_cash_schedules, self.start,
                cash_horizon(self.start, self.end, self.requests), self.debts[0].credit_timezone)
            if expected != self.cash_plans:
                raise ValueError('Saved schedule descriptions must match every expanded cash event')
        return self

    def project(self):
        return coordinate_payments(self.debts, self.openings, self.cash_plans,
                                   self.requests, self.start, self.end)


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate JSON key')
        result[key] = value
    return result


def parse_scenario(raw: bytes) -> Scenario:
    if len(raw) > MAX_BYTES:
        raise ValueError('Scenario file exceeds 4 MiB')
    data = json.loads(raw, object_pairs_hook=_unique_object)
    # Reject bool/float versions rather than allowing Literal coercion.
    if not isinstance(data, dict) or type(data.get('version')) is not int:
        raise ValueError('Scenario requires an integer version')
    scenario = Scenario.model_validate(data)
    scenario.project()  # Cross-record engine validation, including unsupported terms.
    return scenario


def load_scenario(path: str | Path) -> Scenario:
    with Path(path).open('rb') as stream:
        return parse_scenario(stream.read(MAX_BYTES + 1))


def save_scenario(scenario: Scenario, path: str | Path, *, overwrite=False) -> Path:
    raw = scenario.model_dump_json(indent=2).encode('utf-8') + b'\n'
    parse_scenario(raw)
    target = Path(path)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='wb', dir=target.parent,
                                         prefix='.' + target.name + '.', delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        if overwrite:
            os.replace(temporary, target)
        else:
            os.link(temporary, target)
            temporary.unlink()
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return target
