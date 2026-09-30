from dataclasses import dataclass, asdict
from datetime import date
from typing import ClassVar, Iterable
from lib.offline import require_online

@dataclass
class UsageRecord:
    date: date
    provider: str
    product: str
    usage_quantity: float
    usage_unit: str
    cost_cny: float
    cost_original: float
    currency: str
    daily_amount: float = 0.0
    daily_amount_original: float = 0.0
    daily_pct_of_monthly: float = 0.0
    daily_budget: float = 0.0
    total_daily_budget: float = 0.0
    exchange_rate: float = 1.0

    def to_dict(self) -> dict:
        d = asdict(self)
        d['date'] = self.date.isoformat()
        return d

class Provider:
    slug: ClassVar[str]
    label: ClassVar[str]
    supports_backfill: ClassVar[bool]

    def __init_subclass__(cls, **kw):
        super().__init_subclass__(**kw)
        if 'supports_backfill' not in cls.__dict__:
            raise TypeError(f'{cls.__name__} 必须显式声明 supports_backfill = True/False。')

    def __init__(self, config: dict):
        require_online()
        self.config = config

    def fetch_daily(self, target_date: date) -> Iterable[UsageRecord]:
        raise NotImplementedError

    def fetch_month_to_date(self, month: date) -> Iterable[UsageRecord]:
        raise NotImplementedError
