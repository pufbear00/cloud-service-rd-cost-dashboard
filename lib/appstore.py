from lib.offline import require_online
import csv
import gzip
import io
import time
import jwt
import requests
NO_PROXY = {'http': '', 'https': ''}
API = 'https://api.appstoreconnect.apple.com/v1/salesReports'

def _token(key_id: str, private_key: str) -> str:
    require_online()
    now = int(time.time())
    return jwt.encode({'sub': 'user', 'aud': 'appstoreconnect-v1', 'iat': now, 'exp': now + 1200}, private_key, algorithm='ES256', headers={'kid': key_id, 'typ': 'JWT'})

def fetch_sales_day(key_id: str, private_key_path: str, vendor_number: str, report_date: str) -> list[dict]:
    require_online()
    with open(private_key_path) as f:
        priv = f.read()
    token = _token(key_id, priv)
    r = requests.get(API, params={'filter[frequency]': 'DAILY', 'filter[reportType]': 'SALES', 'filter[reportSubType]': 'SUMMARY', 'filter[reportDate]': report_date, 'filter[vendorNumber]': vendor_number}, headers={'Authorization': f'Bearer {token}'}, proxies=NO_PROXY, timeout=30)
    if r.status_code == 404:
        return []
    r.raise_for_status()
    text = gzip.decompress(r.content).decode('utf-8')
    return list(csv.DictReader(io.StringIO(text), delimiter='\t'))
