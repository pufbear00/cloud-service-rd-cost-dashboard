from lib.offline import require_online
from collections import defaultdict
from datetime import date, timedelta
from typing import Iterable
from .base import Provider, UsageRecord
_daily_cache: dict[tuple[str, str, str], list] = {}

class AliyunProvider(Provider):
    slug = 'aliyun'
    label = 'API-阿里云'
    supports_backfill = True

    def fetch_month_to_date(self, target: date) -> Iterable[UsageRecord]:
        require_online()
        from alibabacloud_bssopenapi20171214.client import Client
        from alibabacloud_bssopenapi20171214 import models
        from alibabacloud_tea_openapi.models import Config as TeaConfig
        ak = self.config['access_key_id']
        sk = self.config['access_key_secret']
        client = Client(TeaConfig(access_key_id=ak, access_key_secret=sk, endpoint='business.aliyuncs.com'))
        billing_cycle = target.strftime('%Y-%m')
        by_product: dict[str, float] = defaultdict(float)
        d = target.replace(day=1)
        while d <= target:
            day_str = d.isoformat()
            key = (ak, billing_cycle, day_str)
            if key in _daily_cache:
                items = _daily_cache[key]
            else:
                try:
                    req = models.QueryInstanceBillRequest(billing_cycle=billing_cycle, billing_date=day_str, granularity='DAILY')
                    resp = client.query_instance_bill(req)
                    items = resp.body.data.items.item or []
                    _daily_cache[key] = items
                except Exception as e:
                    print(f'  [aliyun] {day_str} failed: {e}')
                    items = []
                    _daily_cache[key] = items
            for it in items:
                name = it.product_name or it.product_code or '?'
                by_product[name] += float(it.pretax_amount or 0)
            d += timedelta(days=1)
        for product, cny in by_product.items():
            if abs(cny) < 0.01:
                continue
            yield UsageRecord(date=target, provider=self.label, product=product, usage_quantity=0, usage_unit='-', cost_cny=round(cny, 4), cost_original=round(cny, 4), currency='CNY')

    def fetch_daily(self, target: date) -> Iterable[UsageRecord]:
        require_online()
        return self.fetch_month_to_date(target)
