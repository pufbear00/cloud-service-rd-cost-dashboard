from lib.offline import require_online
import csv
from datetime import date
from pathlib import Path
from typing import Iterable
from .base import Provider, UsageRecord

class DomainProvider(Provider):
    slug = 'domain'
    label = '域名费用'
    supports_backfill = False

    def fetch_month_to_date(self, target: date) -> Iterable[UsageRecord]:
        require_online()
        csv_path = Path(self.config['manual_csv_dir']) / f"{target.strftime('%Y-%m')}.csv"
        if not csv_path.exists():
            return
        with csv_path.open(encoding='utf-8-sig') as f:
            for row in csv.DictReader(f):
                yield UsageRecord(date=target, provider=self.label, product=row['product'], usage_quantity=0, usage_unit='-', cost_cny=float(row['cost_cny']), cost_original=float(row['cost_cny']), currency='CNY')

    def fetch_daily(self, target: date) -> Iterable[UsageRecord]:
        require_online()
        return self.fetch_month_to_date(target)
