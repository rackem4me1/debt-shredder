from datetime import date,datetime,time
from zoneinfo import ZoneInfo
from pydantic import model_validator
from SCHEMA import StrictModel,Sourced,assumed_default
from engine.liquidity import add_business_days

class PaymentTiming(StrictModel):
    """Forecast lifecycle delays measured from initiation on a supplied calendar.

    The supported lifecycle follows frozen v2.4's credit-before-bank-debit order.
    Different contractual event ordering needs an explicit supported adapter.
    """
    credit_business_days:Sourced[int]
    debit_business_days:Sourced[int]
    settlement_business_days:Sourced[int]
    timezone_name:str
    initiation_time:time
    holidays:tuple[date,...]=()

    @model_validator(mode='after')
    def ordered(self):
        values=(self.credit_business_days.value,self.debit_business_days.value,self.settlement_business_days.value)
        if values[0]<0 or tuple(sorted(values))!=values:
            raise ValueError('payment delays must satisfy 0 <= credit <= debit <= settlement')
        ZoneInfo(self.timezone_name)
        if self.initiation_time.tzinfo is not None:raise ValueError('use a local clock time and the separate named timezone')
        return self

    def stamps(self,initiated_on:date)->tuple[datetime,datetime,datetime,datetime]:
        at=datetime.combine(initiated_on,self.initiation_time,ZoneInfo(self.timezone_name))
        return (at,add_business_days(at,self.credit_business_days.value,self.holidays),
                add_business_days(at,self.debit_business_days.value,self.holidays),
                add_business_days(at,self.settlement_business_days.value,self.holidays))


def assumed_same_day_timing()->PaymentTiming:
    return PaymentTiming(credit_business_days=assumed_default(0),debit_business_days=assumed_default(0),
        settlement_business_days=assumed_default(0),timezone_name='UTC',initiation_time=time(12))
