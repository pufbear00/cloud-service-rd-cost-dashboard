from lib.offline import require_online
import csv
import io
from datetime import date
from pathlib import Path
from typing import Iterable
import requests
from .base import Provider, UsageRecord

class CloudswayProvider(Provider):
    slug = 'cloudsway'
    label = 'API-Cloudsway'
    supports_backfill = True
    API_URL = 'https://console.cloudsway.net/api/as/bill/daily/export/csv'

    def fetch_month_to_date(self, target: date) -> Iterable[UsageRecord]:
        require_online()
        rows = self._try_api(target) or self._try_csv_fallback(target)
        for row in rows:
            product = row['productName']
            if product == 'Total':
                continue
            yield UsageRecord(date=target, provider=self.label, product=product, usage_quantity=0, usage_unit='-', cost_cny=float(row['unblendedCost(CNY)']), cost_original=float(row['unblendedCost']), currency=row['currencyCode'], exchange_rate=float(row.get('exchangeRate', 1) or 1))

    def _try_api(self, target: date) -> list[dict] | None:
        require_online()
        if not self.config.get('auth_token'):
            return None
        body = {'dayTimeStart': target.replace(day=1).isoformat(), 'dayTimeEnd': target.isoformat(), 'cloudAccountIds': [], 'region': '', 'queryLevel': 1, 'workspaceIds': self.config.get('workspace_ids', []), 'detailType': 'simple', 'detailLevel': 'product', 'formatType': 'csv'}
        try:
            r = requests.post(self.API_URL, headers={'auth-token': self.config['auth_token'], 'content-type': 'application/json', 'accept': 'application/json'}, json=body, timeout=20)
            r.raise_for_status()
        except Exception as e:
            print(f'  [cloudsway] API failed ({e}), fallback to CSV')
            return None
        text = r.content.decode('utf-8-sig')
        return list(csv.DictReader(io.StringIO(text)))

    def _try_csv_fallback(self, target: date) -> list[dict]:
        require_online()
        path = Path(self.config['manual_csv_dir']) / f'{target.isoformat()}.csv'
        if not path.exists():
            print(f'  [cloudsway] no fallback CSV at {path} (需精确到日)')
            return []
        with path.open(encoding='utf-8-sig') as f:
            return list(csv.DictReader(f))

    def fetch_daily(self, target: date) -> Iterable[UsageRecord]:
        require_online()
        return self.fetch_month_to_date(target)
