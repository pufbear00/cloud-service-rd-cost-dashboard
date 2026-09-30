from lib.offline import require_online
from datetime import date
from typing import Iterable
import requests
from .base import Provider, UsageRecord

class OpenRouterProvider(Provider):
    slug = 'openrouter'
    label = 'API-OPENROUTER'
    supports_backfill = True

    def fetch_month_to_date(self, target: date) -> Iterable[UsageRecord]:
        require_online()
        if not self.config.get('api_key'):
            return
        from lib.currency import get_monthly_rate
        usd_to_cny = get_monthly_rate(target, 'USD', 'CNY')
        month_prefix = target.strftime('%Y-%m')
        target_iso = target.isoformat()
        r = requests.get('https://openrouter.ai/api/v1/activity', headers={'Authorization': f"Bearer {self.config['api_key']}"}, timeout=15)
        r.raise_for_status()
        agg: dict[str, dict] = {}
        for item in r.json().get('data', []):
            d = item.get('date', '')
            if not d.startswith(month_prefix) or d[:10] > target_iso:
                continue
            model = item.get('model', 'unknown')
            a = agg.setdefault(model, {'requests': 0, 'tokens': 0, 'cost_usd': 0.0})
            a['requests'] += int(item.get('requests', 0))
            a['tokens'] += int(item.get('prompt_tokens', 0)) + int(item.get('completion_tokens', 0))
            a['cost_usd'] += float(item.get('usage', 0))
        if not agg:
            agg = {'(本日无调用)': {'requests': 0, 'tokens': 0, 'cost_usd': 0.0}}
        for model, a in agg.items():
            yield UsageRecord(date=target, provider=self.label, product=model, usage_quantity=a['requests'], usage_unit='requests', cost_cny=round(a['cost_usd'] * usd_to_cny, 2), cost_original=a['cost_usd'], currency='USD', exchange_rate=usd_to_cny)

    def fetch_daily(self, target: date) -> Iterable[UsageRecord]:
        require_online()
        return self.fetch_month_to_date(target)
