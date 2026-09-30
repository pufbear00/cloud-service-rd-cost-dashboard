from lib.offline import require_online
import csv
import io
import os
import warnings
import zipfile
warnings.filterwarnings('ignore', message='.*end user credentials.*')
_SA_JSON = 'config/gcp-sa.json'

def _download_report(bucket_name: str, object_name: str) -> bytes | None:
    require_online()
    from google.api_core import exceptions as gexc
    from google.cloud import storage
    from google.oauth2 import service_account

    def _try(creds, project):
        require_online()
        client = storage.Client(credentials=creds, project=project)
        blob = client.bucket(bucket_name).blob(object_name)
        if not blob.exists():
            return None
        return blob.download_as_bytes()
    sa = service_account.Credentials.from_service_account_file(_SA_JSON)
    try:
        return _try(sa, sa.project_id)
    except gexc.Forbidden:
        import google.auth
        print('  [googleplay] SA 403（权限被收），退回用户 ADC')
        adc, proj = google.auth.default()
        return _try(adc, proj or sa.project_id)

def fetch_sales_rows(bucket_name: str, year_month: str) -> list[dict]:
    require_online()
    data = _download_report(bucket_name, f'sales/salesreport_{year_month}.zip')
    if data is None:
        return []
    zf = zipfile.ZipFile(io.BytesIO(data))
    rows: list[dict] = []
    for name in zf.namelist():
        text = zf.read(name).decode('utf-8-sig')
        rows.extend(csv.DictReader(io.StringIO(text)))
    return rows
