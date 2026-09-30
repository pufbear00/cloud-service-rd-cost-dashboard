from lib.offline import require_online
import time
from datetime import date, timedelta
from typing import Optional
from lib import net
AUTH_URL = 'https://api.airwallex.com/api/v1/authentication/login'
TX_URL = 'https://api.airwallex.com/api/v1/issuing/transactions'
_token_cache: dict[str, tuple[str, float]] = {}
_tx_cache: dict[tuple, tuple[list, float]] = {}
_TX_CACHE_TTL = 300

def get_token(client_id: str, api_key: str) -> Optional[str]:
    require_online()
    now = time.time()
    cached = _token_cache.get(client_id)
    if cached and cached[1] > now + 60:
        return cached[0]
    try:
        r = net.post(AUTH_URL, headers={'x-client-id': client_id, 'x-api-key': api_key}, timeout=20)
        r.raise_for_status()
        token = r.json()['token']
        _token_cache[client_id] = (token, now + 25 * 60)
        return token
    except Exception as e:
        print(f'  [airwallex] auth failed: {e}')
        return None

def fetch_all_transactions(client_id: str, api_key: str, target: Optional[date]=None) -> list[dict]:
    require_online()
    month = target.strftime('%Y-%m') if target else None
    now = time.time()
    cached = _tx_cache.get((client_id, month))
    if cached and now - cached[1] < _TX_CACHE_TTL:
        return cached[0]
    token = get_token(client_id, api_key)
    if not token:
        return []
    headers = {'Authorization': f'Bearer {token}'}
    window = {}
    if target:
        first = target.replace(day=1)
        next_first = (first + timedelta(days=32)).replace(day=1)
        window = {'from_created_at': f'{first.isoformat()}T00:00:00+08:00', 'to_created_at': f'{next_first.isoformat()}T00:00:00+08:00'}
    all_tx: list[dict] = []
    page_after = None
    for _ in range(50):
        params = {'page_size': 200, **window}
        if page_after:
            params['page_after'] = page_after
        r = net.get(TX_URL, params=params, headers=headers, timeout=30)
        r.raise_for_status()
        data = r.json()
        all_tx.extend(data.get('items', []))
        page_after = data.get('page_after')
        if not data.get('has_more'):
            break
    _tx_cache[client_id, month] = (all_tx, now)
    return all_tx

def merchant_name(tx: dict) -> str:
    info = tx.get('merchant', {}).get('additional_merchant_info', {})
    return info.get('merchant_full_name') or tx.get('merchant', {}).get('name', 'UNKNOWN')
