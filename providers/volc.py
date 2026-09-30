from lib.offline import require_online
from collections import defaultdict
from datetime import date, timedelta
from typing import Iterable
from .base import Provider, UsageRecord

class VolcProvider(Provider):
    slug = 'volc'
    label = 'API-火山引擎'
    supports_backfill = True

    def fetch_month_to_date(self, target: date) -> Iterable[UsageRecord]:
        require_online()
        import volcenginesdkcore
        import volcenginesdkbilling as vb
        cfg = volcenginesdkcore.Configuration()
        cfg.ak = self.config['access_key']
        cfg.sk = self.config['secret_key']
        cfg.region = 'cn-beijing'
        cfg.client_side_validation = True
        volcenginesdkcore.Configuration.set_default(cfg)
        client = vb.BILLINGApi()
        month_start = target.replace(day=1)
        bill_period = target.strftime('%Y-%m')
        by_product: dict[str, float] = defaultdict(float)
        d = month_start
        while d <= target:
            offset = 0
            while True:
                req = vb.ListBillDetailRequest(bill_period=bill_period, expense_date=d.isoformat(), group_period=1, group_term=1, limit=100, offset=offset, need_record_num=0)
                resp = client.list_bill_detail(req)
                items = resp.list or []
                for it in items:
                    name = it.product_zh or it.product
                    by_product[name] += float(it.payable_amount or 0)
                if len(items) < 100:
                    break
                offset += 100
            d += timedelta(days=1)
        for product, cost in by_product.items():
            if abs(cost) < 0.01:
                continue
            yield UsageRecord(date=target, provider=self.label, product=product, usage_quantity=0, usage_unit='-', cost_cny=round(cost, 2), cost_original=round(cost, 2), currency='CNY')

    def fetch_daily(self, target: date) -> Iterable[UsageRecord]:
        require_online()
        return self.fetch_month_to_date(target)
