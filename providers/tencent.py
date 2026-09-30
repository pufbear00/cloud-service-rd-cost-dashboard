from lib.offline import require_online
import json
import time
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Iterable
from .base import Provider, UsageRecord
_DETAIL_CACHE: dict[tuple[str, int, int, str], list[dict]] = {}
_LIMIT = 300

class TencentProvider(Provider):
    slug = 'tencent'
    label = '云-腾讯云'
    supports_backfill = True

    def fetch_month_to_date(self, target: date) -> Iterable[UsageRecord]:
        require_online()
        import calendar as _cal
        last_day = _cal.monthrange(target.year, target.month)[1]
        today = date.today()
        month_closed = (target.year, target.month) < (today.year, today.month)
        if target.day == last_day and month_closed:
            yield from self._fetch_billing_cycle(target.year, target.month, target)
            return
        details = self._load_month_details(target.year, target.month)
        target_iso = target.isoformat()
        agg: dict[str, float] = defaultdict(float)
        for d in details:
            pt = d.get('PayTime', '')
            if not pt or pt[:10] > target_iso:
                continue
            product = d.get('BusinessCodeName') or d.get('BusinessCode') or '未知'
            for c in d.get('ComponentSet', []) or []:
                try:
                    agg[product] += float(c.get('RealCost', 0))
                except (TypeError, ValueError):
                    continue
        for product, cost in agg.items():
            if abs(cost) < 0.005:
                continue
            yield UsageRecord(date=target, provider=self.label, product=product, usage_quantity=0, usage_unit='-', cost_cny=round(cost, 2), cost_original=round(cost, 2), currency='CNY')

    def fetch_daily(self, target: date) -> Iterable[UsageRecord]:
        require_online()
        return self.fetch_month_to_date(target)

    def _fetch_billing_cycle(self, year: int, month: int, target: date) -> Iterable[UsageRecord]:
        require_online()
        from tencentcloud.common import credential
        from tencentcloud.billing.v20180709 import billing_client, models
        cred = credential.Credential(self.config['secret_id'], self.config['secret_key'])
        client = billing_client.BillingClient(cred, '')
        ym = f'{year}-{month:02d}'
        req = models.DescribeBillSummaryByProductRequest()
        req.BeginTime = ym
        req.EndTime = ym
        resp = json.loads(client.DescribeBillSummaryByProduct(req).to_json_string())
        overview = resp.get('SummaryOverview') or []
        total = (resp.get('SummaryTotal') or {}).get('RealTotalCost')
        print(f'  [tencent] 账期 true-up {ym}: RealTotalCost={total} ({len(overview)} 产品)', flush=True)
        for x in overview:
            product = x.get('BusinessCodeName') or x.get('BusinessCode') or '未知'
            try:
                cost = float(x.get('RealTotalCost', 0) or 0)
            except (TypeError, ValueError):
                continue
            if abs(cost) < 0.005:
                continue
            yield UsageRecord(date=target, provider=self.label, product=product, usage_quantity=0, usage_unit='-', cost_cny=round(cost, 2), cost_original=round(cost, 2), currency='CNY')

    def _load_month_details(self, year: int, month: int) -> list[dict]:
        require_online()
        secret_id = self.config['secret_id']
        today_iso = date.today().isoformat()
        cache_key = (secret_id, year, month, today_iso)
        if cache_key in _DETAIL_CACHE:
            return _DETAIL_CACHE[cache_key]
        disk_cache = Path(__file__).resolve().parents[1] / 'output' / f'tencent_demo_{year}{month:02d}_{today_iso}.json'
        if disk_cache.exists():
            details = json.loads(disk_cache.read_text())
            print(f'  [tencent] DescribeBillDetail {year}-{month:02d}: {len(details)} 条 (磁盘缓存 {disk_cache.name})', flush=True)
            _DETAIL_CACHE[cache_key] = details
            return details
        details = self._call_describe_bill_detail(year, month)
        try:
            disk_cache.write_text(json.dumps(details, ensure_ascii=False))
        except Exception as e:
            print(f'  [tencent] ⚠️ 写缓存失败 {disk_cache}: {e}', flush=True)
        _DETAIL_CACHE[cache_key] = details
        return details

    def _call_describe_bill_detail(self, year: int, month: int) -> list[dict]:
        require_online()
        import calendar as cal
        from tencentcloud.common import credential
        from tencentcloud.billing.v20180709 import billing_client, models
        cred = credential.Credential(self.config['secret_id'], self.config['secret_key'])
        client = billing_client.BillingClient(cred, '')
        begin = date(year, month, 1).strftime('%Y-%m-%d 00:00:00')
        last = cal.monthrange(year, month)[1]
        end = date(year, month, last).strftime('%Y-%m-%d 23:59:59')
        all_details: list[dict] = []
        offset = 0
        t0 = time.time()
        print(f'  [tencent] DescribeBillDetail {year}-{month:02d} 开始拉…', flush=True)
        while True:
            req = models.DescribeBillDetailRequest()
            req.BeginTime = begin
            req.EndTime = end
            req.Limit = _LIMIT
            req.Offset = offset
            req.NeedRecordNum = 0
            req.PeriodType = 'byPayTime'
            resp = client.DescribeBillDetail(req)
            items = json.loads(resp.to_json_string()).get('DetailSet', []) or []
            all_details.extend(items)
            if offset % 3000 == 0:
                print(f'    offset={offset:>6} total={len(all_details):>6} 用时 {time.time() - t0:.0f}s', flush=True)
            if len(items) < _LIMIT:
                break
            offset += _LIMIT
        print(f'  [tencent] DescribeBillDetail {year}-{month:02d}: {len(all_details)} 条 / {time.time() - t0:.1f}s', flush=True)
        return all_details
