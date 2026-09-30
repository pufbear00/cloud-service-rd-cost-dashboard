from lib.offline import require_online
import calendar
import csv
import json
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path
from typing import Iterable
import requests
from .base import Provider, UsageRecord
VERCEL_API_URL = 'https://api.vercel.com/v1/billing/charges'
NEON_API_URL = 'https://console.neon.tech/api/v2/projects'
NO_PROXY = {'http': '', 'https': ''}

class VercelProvider(Provider):
    slug = 'vercel'
    label = 'Vercel'
    supports_backfill = True

    def fetch_month_to_date(self, target: date) -> Iterable[UsageRecord]:
        require_online()
        yield from self._fetch_vercel_api(target)
        yield from self._emit_flat_marketplace(target)
        yield from self._fetch_neon_overage(target)

    def _fetch_vercel_api(self, target: date) -> Iterable[UsageRecord]:
        require_online()
        if not (self.config.get('access_token') and self.config.get('team_id')):
            return
        from lib.currency import get_monthly_rate
        usd_to_cny = get_monthly_rate(target, 'USD', 'CNY')
        month_start = target.replace(day=1)
        try:
            r = requests.get(VERCEL_API_URL, params={'teamId': self.config['team_id'], 'from': month_start.isoformat(), 'to': target.isoformat()}, headers={'Authorization': f"Bearer {self.config['access_token']}", 'Accept-Encoding': 'gzip'}, proxies=NO_PROXY, timeout=30)
            r.raise_for_status()
        except Exception as e:
            print(f'  [vercel] API failed: {e}')
            return
        by_service: dict[str, dict] = defaultdict(lambda: {'cost': 0.0, 'quantity': 0.0, 'unit': ''})
        for line in r.text.splitlines():
            if not line.strip():
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            service = rec.get('ServiceName', '?')
            by_service[service]['cost'] += float(rec.get('EffectiveCost', 0) or 0)
            by_service[service]['quantity'] += float(rec.get('ConsumedQuantity', 0) or 0)
            by_service[service]['unit'] = rec.get('ConsumedUnit', '-')
        for service, agg in by_service.items():
            if agg['cost'] < 0.01:
                continue
            yield UsageRecord(date=target, provider=self.label, product=service, usage_quantity=round(agg['quantity'], 2), usage_unit=agg['unit'] or '-', cost_cny=round(agg['cost'] * usd_to_cny, 2), cost_original=round(agg['cost'], 2), currency='USD', exchange_rate=usd_to_cny)

    def _emit_flat_marketplace(self, target: date) -> Iterable[UsageRecord]:
        require_online()
        from lib.currency import get_monthly_rate
        usd_to_cny = get_monthly_rate(target, 'USD', 'CNY')
        days_in_month = calendar.monthrange(target.year, target.month)[1]
        prorate = target.day / days_in_month
        for product, monthly in [('Prisma (固定月费)', self.config.get('prisma_monthly_usd', 0)), ('Redis (固定月费)', self.config.get('redis_monthly_usd', 0))]:
            if not monthly or monthly <= 0:
                continue
            mtd_usd = monthly * prorate
            yield UsageRecord(date=target, provider=self.label, product=product, usage_quantity=0, usage_unit='-', cost_cny=round(mtd_usd * usd_to_cny, 2), cost_original=round(mtd_usd, 4), currency='USD', exchange_rate=usd_to_cny)

    def _fetch_neon_overage(self, target: date) -> Iterable[UsageRecord]:
        require_online()
        from lib.currency import get_monthly_rate
        usd_to_cny = get_monthly_rate(target, 'USD', 'CNY')
        manual_dir = self.config.get('neon_manual_csv_dir')
        if manual_dir:
            csv_path = Path(manual_dir) / f"{target.strftime('%Y-%m')}.csv"
            if csv_path.exists():
                with csv_path.open(encoding='utf-8-sig') as f:
                    for row in csv.DictReader(f):
                        if row.get('date') == target.isoformat():
                            try:
                                usd = float(row['total_spent_usd'])
                            except (TypeError, ValueError, KeyError):
                                break
                            yield UsageRecord(date=target, provider=self.label, product='Neon 当月消耗', usage_quantity=0, usage_unit='-', cost_cny=round(usd * usd_to_cny, 2), cost_original=round(usd, 2), currency='USD', exchange_rate=usd_to_cny)
                            return
        today = date.today()
        if target.year != today.year or target.month != today.month:
            return
        if target >= today:
            return
        if not (self.config.get('neon_api_key') and self.config.get('neon_org_id')):
            return
        try:
            r = requests.get(NEON_API_URL, params={'org_id': self.config['neon_org_id'], 'limit': 100}, headers={'Authorization': f"Bearer {self.config['neon_api_key']}"}, proxies=NO_PROXY, timeout=20)
            r.raise_for_status()
            projects = r.json().get('projects', [])
        except Exception as e:
            print(f'  [vercel/neon] API failed: {e}')
            return
        total_cpu_sec = sum((p.get('cpu_used_sec', 0) for p in projects))
        total_storage_bytes = sum((p.get('synthetic_storage_size', 0) for p in projects))
        cu_hours = total_cpu_sec / 3600
        storage_gb = total_storage_bytes / 1024 ** 3
        included_cu = self.config.get('neon_included_cu_hours', 100)
        included_storage_gb = self.config.get('neon_included_storage_gb', 10)
        compute_rate = self.config.get('neon_compute_rate', 0.16)
        storage_rate = self.config.get('neon_storage_rate', 1.5)
        base_monthly = self.config.get('neon_base_monthly_usd', 19)
        days_in_month = calendar.monthrange(target.year, target.month)[1]
        prorate_today = today.day / days_in_month
        base_mtd_today = base_monthly * prorate_today
        compute_overage_today = max(0.0, cu_hours - included_cu) * compute_rate
        storage_overage_today = max(0.0, storage_gb - included_storage_gb) * storage_rate * prorate_today
        total_usd_today = base_mtd_today + compute_overage_today + storage_overage_today
        scale = target.day / today.day
        total_usd = total_usd_today * scale
        if total_usd < 0.01:
            return
        yield UsageRecord(date=target, provider=self.label, product='Neon 当月消耗(估算)', usage_quantity=round(cu_hours * scale, 2), usage_unit='CU-hour', cost_cny=round(total_usd * usd_to_cny, 2), cost_original=round(total_usd, 2), currency='USD', exchange_rate=usd_to_cny)

    def fetch_daily(self, target: date) -> Iterable[UsageRecord]:
        require_online()
        return self.fetch_month_to_date(target)
