from lib.offline import require_online
import json
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Iterable
import requests
from .base import Provider, UsageRecord
NO_PROXY = {'http': '', 'https': ''}
_ROOT = Path(__file__).resolve().parent.parent
_STATE = _ROOT / 'output' / 'deepseek_balance.json'
_API = 'https://platform.deepseek.com/api/v0/usage/cost'

def _fetch_api_daily(token: str, cookie: str, year: int, month: int) -> dict[str, float] | None:
    require_online()
    headers = {'Authorization': f'Bearer {token}', 'accept': '*/*', 'cookie': cookie, 'user-agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36', 'referer': 'https://platform.deepseek.com/usage', 'x-app-version': '1.0.0'}
    try:
        r = requests.get(_API, params={'month': month, 'year': year}, headers=headers, proxies=NO_PROXY, timeout=25)
        r.raise_for_status()
        biz = r.json().get('data', {}).get('biz_data', [])
        if not biz:
            return {}
        daily = {}
        for day in biz[0].get('days', []):
            s = 0.0
            for m in day.get('data', []):
                for u in m.get('usage', []):
                    try:
                        s += float(u.get('amount', 0))
                    except (TypeError, ValueError):
                        continue
            daily[day.get('date', '')] = s
        return daily
    except Exception as e:
        print(f'  [deepseek] console API 失败（token/cookie 可能过期）: {e}')
        return None

def _load_snapshot() -> dict[str, float]:
    require_online()
    if not _STATE.exists():
        return {}
    try:
        return json.loads(_STATE.read_text())
    except Exception:
        return {}

def _save_snapshot(s: dict[str, float]) -> None:
    require_online()
    _STATE.parent.mkdir(parents=True, exist_ok=True)
    _STATE.write_text(json.dumps(s, indent=2, ensure_ascii=False))

def _record_balance(api_key: str) -> float | None:
    require_online()
    try:
        r = requests.get('https://api.deepseek.com/user/balance', headers={'Authorization': f'Bearer {api_key}', 'Accept': 'application/json'}, proxies=NO_PROXY, timeout=15)
        r.raise_for_status()
        for b in r.json().get('balance_infos', []):
            if b.get('currency') == 'CNY':
                return float(b.get('total_balance', 0))
    except Exception:
        pass
    return None

class DeepSeekProvider(Provider):
    slug = 'deepseek'
    label = 'API-DeepSeek'
    supports_backfill = True

    def fetch_month_to_date(self, target: date) -> Iterable[UsageRecord]:
        require_online()
        if self.config.get('api_key'):
            bal = _record_balance(self.config['api_key'])
            if bal is not None:
                snap = _load_snapshot()
                snap[target.isoformat()] = bal
                _save_snapshot(snap)
        api_daily = None
        if self.config.get('console_token') and self.config.get('console_cookie'):
            api_daily = _fetch_api_daily(self.config['console_token'], self.config['console_cookie'], target.year, target.month)
        from datetime import timedelta
        mtd = 0.0
        d = target.replace(day=1)
        snapshot = _load_snapshot()
        snap_days = sorted(snapshot.keys())
        while d <= target:
            di = d.isoformat()
            if api_daily is not None and di in api_daily:
                mtd += api_daily[di]
            elif di in snapshot:
                prev = max((s for s in snap_days if s < di), default=None)
                if prev:
                    drop = snapshot[prev] - snapshot[di]
                    if drop > 0:
                        mtd += drop
            d += timedelta(days=1)
        bal = snapshot.get(target.isoformat(), 0)
        yield UsageRecord(date=target, provider=self.label, product='API 调用', usage_quantity=round(bal, 2), usage_unit='CNY 余额', cost_cny=round(mtd, 2), cost_original=round(mtd, 2), currency='CNY', exchange_rate=1.0)

    def fetch_daily(self, target: date) -> Iterable[UsageRecord]:
        require_online()
        return self.fetch_month_to_date(target)
