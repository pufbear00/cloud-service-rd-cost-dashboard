from lib.offline import require_online
import time
from datetime import date
from typing import Iterable
from lib import net
from .base import Provider, UsageRecord
TOKEN_URL = 'https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token'
QUERY_URL = 'https://management.azure.com/subscriptions/{sub}/providers/Microsoft.CostManagement/query?api-version=2023-11-01'

class AzureProvider(Provider):
    slug = 'azure'
    label = 'API-Azure'
    supports_backfill = True

    def fetch_month_to_date(self, target: date) -> Iterable[UsageRecord]:
        require_online()
        cfg = self.config
        for k in ('tenant_id', 'subscription_id', 'client_id', 'client_secret'):
            if not cfg.get(k):
                print(f'  [azure] 缺少配置 {k}')
                return
        try:
            tr = net.post(TOKEN_URL.format(tenant=cfg['tenant_id']), data={'grant_type': 'client_credentials', 'client_id': cfg['client_id'], 'client_secret': cfg['client_secret'], 'scope': 'https://management.azure.com/.default'}, timeout=30)
            tr.raise_for_status()
            token = tr.json()['access_token']
        except Exception as e:
            print(f'  [azure] 拿 token 失败: {e}')
            return
        body = {'type': 'ActualCost', 'timeframe': 'Custom', 'timePeriod': {'from': target.replace(day=1).isoformat(), 'to': target.isoformat()}, 'dataset': {'granularity': 'None', 'aggregation': {'totalCost': {'name': 'Cost', 'function': 'Sum'}}, 'grouping': [{'type': 'Dimension', 'name': 'ServiceName'}]}}
        props = None
        for attempt in range(4):
            try:
                qr = net.post(QUERY_URL.format(sub=cfg['subscription_id']), headers={'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}, json=body, timeout=60)
                if qr.status_code == 429:
                    wait = int(qr.headers.get('Retry-After', '60'))
                    print(f'  [azure] 429 限流，等 {wait}s 重试 (attempt {attempt + 1}/4)')
                    time.sleep(wait)
                    continue
                qr.raise_for_status()
                props = qr.json().get('properties', {})
                break
            except Exception as e:
                print(f'  [azure] cost query 失败 (attempt {attempt + 1}/4): {e}')
                if attempt == 3:
                    return
                time.sleep(30)
        if props is None:
            print('  [azure] cost query 全部重试失败')
            return
        cols = [c['name'] for c in props.get('columns', [])]
        try:
            ci = cols.index('Cost')
            si = cols.index('ServiceName')
            cur_i = cols.index('Currency')
        except ValueError:
            print(f'  [azure] 返回列异常: {cols}')
            return
        for row in props.get('rows', []):
            cost = float(row[ci] or 0)
            if cost < 0.01:
                continue
            currency = row[cur_i] or 'CNY'
            yield UsageRecord(date=target, provider=self.label, product=row[si] or '(未知服务)', usage_quantity=0, usage_unit='-', cost_cny=round(cost, 2), cost_original=round(cost, 2), currency=currency, exchange_rate=1.0)

    def fetch_daily(self, target: date) -> Iterable[UsageRecord]:
        require_online()
        return self.fetch_month_to_date(target)
