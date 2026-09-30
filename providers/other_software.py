from lib.offline import require_online
from collections import defaultdict
from datetime import date
from typing import Iterable
from lib import airwallex
from .base import Provider, UsageRecord
SOFTWARE_KEYWORDS = []
EXCLUDE_MERCHANTS = []

class OtherSoftwareProvider(Provider):
    slug = 'other_software'
    label = '软件-其他'
    supports_backfill = True

    def fetch_month_to_date(self, target: date) -> Iterable[UsageRecord]:
        require_online()
        if not (self.config.get('client_id') and self.config.get('api_key')):
            return
        from lib.currency import get_monthly_rate
        from providers.other import API_KEYWORDS
        from providers.employee_software import AI_KEYWORDS
        usd_to_cny = get_monthly_rate(target, 'USD', 'CNY')
        keywords = [k.lower() for k in self.config.get('software_keywords', SOFTWARE_KEYWORDS)]
        excludes = [e.lower() for e in self.config.get('exclude_merchants', EXCLUDE_MERCHANTS)]
        other_provider_keywords = [k.lower() for k in API_KEYWORDS + AI_KEYWORDS]
        all_tx = airwallex.fetch_all_transactions(self.config['client_id'], self.config['api_key'], target)
        month_prefix = target.strftime('%Y-%m')
        target_iso = target.isoformat()
        by_merchant: dict[str, dict] = defaultdict(lambda: {'usd': 0.0, 'count': 0})
        for t in all_tx:
            if t.get('status') != 'APPROVED' or t.get('transaction_type') not in ('CLEARING', 'REFUND'):
                continue
            d = t.get('transaction_date', '')
            if not d.startswith(month_prefix) or d[:10] > target_iso:
                continue
            m_lower = airwallex.merchant_name(t).lower()
            if any((ex in m_lower for ex in excludes)):
                continue
            if m_lower.startswith('vercel mkt'):
                continue
            if any((kw in m_lower for kw in other_provider_keywords)):
                continue
            merchant = airwallex.merchant_name(t)
            if not any((kw in m_lower for kw in keywords)):
                merchant = f'[未分类] {merchant}'
            amount = -float(t.get('billing_amount', 0))
            by_merchant[merchant]['usd'] += amount
            by_merchant[merchant]['count'] += 1
        for merchant, agg in sorted(by_merchant.items()):
            yield UsageRecord(date=target, provider=self.label, product=merchant, usage_quantity=agg['count'], usage_unit='笔', cost_cny=round(agg['usd'] * usd_to_cny, 2), cost_original=round(agg['usd'], 2), currency='USD', exchange_rate=usd_to_cny)

    def fetch_daily(self, target: date) -> Iterable[UsageRecord]:
        require_online()
        return self.fetch_month_to_date(target)
