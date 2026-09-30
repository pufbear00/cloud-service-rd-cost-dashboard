from lib.offline import require_online
from datetime import date, datetime, timezone
from typing import Iterable
import requests
from .base import Provider, UsageRecord

class OpenAIProvider(Provider):
    slug = 'openai'
    label = 'API-OpenAI'
    supports_backfill = True

    def fetch_month_to_date(self, target: date) -> Iterable[UsageRecord]:
        require_online()
        keys: dict[str, str] = dict(self.config.get('admin_keys') or {})
        if self.config.get('admin_key'):
            keys.setdefault('default', self.config['admin_key'])
        if not keys:
            return
        month_start = target.replace(day=1)
        start_ts = int(datetime.combine(month_start, datetime.min.time(), tzinfo=timezone.utc).timestamp())
        end_ts = int(datetime.combine(target, datetime.max.time(), tzinfo=timezone.utc).timestamp())
        from lib.currency import get_monthly_rate
        usd_to_cny = get_monthly_rate(target, 'USD', 'CNY')
        for account_name, key in keys.items():
            try:
                r = requests.get('https://api.openai.com/v1/organization/costs', headers={'Authorization': f'Bearer {key}'}, params={'start_time': start_ts, 'end_time': end_ts, 'bucket_width': '1d', 'limit': 31}, timeout=15)
                r.raise_for_status()
            except Exception as e:
                print(f'  [openai/{account_name}] costs query failed: {e}')
                continue
            total_usd = 0.0
            currency = 'USD'
            for bucket in r.json().get('data', []):
                for result in bucket.get('results', []):
                    amount = result.get('amount', {})
                    total_usd += float(amount.get('value', 0))
                    currency = amount.get('currency', 'USD').upper()
            if total_usd > 0 or len(keys) > 1:
                yield UsageRecord(date=target, provider=self.label, product=account_name, usage_quantity=0, usage_unit='-', cost_cny=round(total_usd * usd_to_cny, 4), cost_original=round(total_usd, 4), currency=currency, exchange_rate=usd_to_cny)

    def fetch_daily(self, target: date) -> Iterable[UsageRecord]:
        require_online()
        return self.fetch_month_to_date(target)
