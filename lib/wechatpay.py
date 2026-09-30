from lib.offline import require_online
import base64
import time
import uuid
from pathlib import Path
from urllib.parse import urlparse
import requests
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
API_BASE = 'https://api.mch.weixin.qq.com'
NO_PROXY = {'http': '', 'https': ''}

class WeChatPayClient:

    def __init__(self, mchid: str, private_key_path: str, cert_serial: str, wechatpay_pub_key_path: str, wechatpay_pub_key_id: str):
        require_online()
        self.mchid = mchid
        self.cert_serial = cert_serial
        self.pub_key_id = wechatpay_pub_key_id
        self._priv = serialization.load_pem_private_key(Path(private_key_path).read_bytes(), password=None)
        self._wx_pub = serialization.load_pem_public_key(Path(wechatpay_pub_key_path).read_bytes())

    def _auth_header(self, method: str, url_path: str, body: str='') -> str:
        require_online()
        ts = str(int(time.time()))
        nonce = uuid.uuid4().hex
        message = f'{method}\n{url_path}\n{ts}\n{nonce}\n{body}\n'
        sig = self._priv.sign(message.encode('utf-8'), padding.PKCS1v15(), hashes.SHA256())
        sig_b64 = base64.b64encode(sig).decode()
        return f'WECHATPAY2-SHA256-RSA2048 mchid="{self.mchid}",nonce_str="{nonce}",signature="{sig_b64}",timestamp="{ts}",serial_no="{self.cert_serial}"'

    def _verify_response(self, headers, body: str) -> bool:
        require_online()
        ts = headers.get('Wechatpay-Timestamp', '')
        nonce = headers.get('Wechatpay-Nonce', '')
        sig = headers.get('Wechatpay-Signature', '')
        if not (ts and nonce and sig):
            return False
        message = f'{ts}\n{nonce}\n{body}\n'
        try:
            self._wx_pub.verify(base64.b64decode(sig), message.encode('utf-8'), padding.PKCS1v15(), hashes.SHA256())
            return True
        except Exception:
            return False

    def get_tradebill(self, bill_date: str, bill_type: str='ALL') -> str:
        require_online()
        url_path = f'/v3/bill/tradebill?bill_date={bill_date}&bill_type={bill_type}'
        headers = {'Authorization': self._auth_header('GET', url_path), 'Accept': 'application/json', 'User-Agent': 'api-cost-monitor/1.0'}
        r = requests.get(API_BASE + url_path, headers=headers, proxies=NO_PROXY, timeout=30)
        if r.status_code != 200:
            if 'NO_STATEMENT_EXIST' in r.text or 'NO_BILL_EXIST' in r.text:
                return ''
            raise RuntimeError(f'tradebill {bill_date} 失败 HTTP {r.status_code}: {r.text[:300]}')
        if not self._verify_response(r.headers, r.text):
            raise RuntimeError(f'tradebill {bill_date} 响应验签失败')
        meta = r.json()
        download_url = meta['download_url']
        parsed = urlparse(download_url)
        dl_path = parsed.path + ('?' + parsed.query if parsed.query else '')
        dl_headers = {'Authorization': self._auth_header('GET', dl_path), 'Accept': 'application/json', 'User-Agent': 'api-cost-monitor/1.0'}
        dr = requests.get(download_url, headers=dl_headers, proxies=NO_PROXY, timeout=60)
        if dr.status_code != 200:
            raise RuntimeError(f'账单下载失败 HTTP {dr.status_code}: {dr.text[:300]}')
        return dr.text

def parse_tradebill(csv_text: str) -> list[dict]:
    csv_text = csv_text.lstrip('\ufeff')
    lines = [ln for ln in csv_text.splitlines() if ln.strip()]
    if not lines:
        return []
    header = [h.strip().lstrip('`').strip() for h in lines[0].split(',')]
    rows = []
    for ln in lines[1:]:
        if not ln.startswith('`'):
            break
        cells = [c.strip().lstrip('`').strip() for c in ln.split(',')]
        if len(cells) < len(header):
            continue
        rows.append(dict(zip(header, cells)))
    return rows
