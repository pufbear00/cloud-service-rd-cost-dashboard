from lib.offline import require_online
from datetime import date, datetime, timedelta
import requests
NO_PROXY = {'http': '', 'https': ''}
API = 'https://api.stripe.com/v1/balance_transactions'
INCOME_TYPES = {'charge', 'payment', 'refund', 'payment_refund', 'adjustment', 'payment_failure_refund'}

def fetch_day_transactions(api_key: str, target: date) -> list[dict]:
    require_online()
    start = int(datetime.combine(target, datetime.min.time()).timestamp())
    end = int(datetime.combine(target + timedelta(days=1), datetime.min.time()).timestamp())
    out = []
    starting_after = None
    while True:
        params = {'created[gte]': start, 'created[lt]': end, 'limit': 100}
        if starting_after:
            params['starting_after'] = starting_after
        r = requests.get(API, params=params, auth=(api_key, ''), proxies=NO_PROXY, timeout=30)
        r.raise_for_status()
        d = r.json()
        data = d.get('data', [])
        out.extend(data)
        if not d.get('has_more') or not data:
            break
        starting_after = data[-1]['id']
    return out
