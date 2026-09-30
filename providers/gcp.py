from lib.offline import require_online
from datetime import date
from typing import Iterable
from .base import Provider, UsageRecord

class GCPProvider(Provider):
    slug = 'gcp'
    label = 'API-GCP'
    supports_backfill = True

    def fetch_month_to_date(self, target: date) -> Iterable[UsageRecord]:
        require_online()
        if self.config.get('bigquery_dataset'):
            yield from self._fetch_bigquery(target)
        else:
            yield from self._fetch_billing_api(target)

    def fetch_daily(self, target: date) -> Iterable[UsageRecord]:
        require_online()
        return self.fetch_month_to_date(target)

    def _fetch_bigquery(self, target: date) -> Iterable[UsageRecord]:
        require_online()
        from google.cloud import bigquery
        from google.oauth2 import service_account
        from lib.currency import get_monthly_rate
        creds = service_account.Credentials.from_service_account_file(self.config['service_account_json'])
        client = bigquery.Client(credentials=creds, project=creds.project_id)
        dataset = self.config['bigquery_dataset']
        month_start = target.replace(day=1).isoformat()
        usd_to_cny = get_monthly_rate(target, 'USD', 'CNY')
        sql = f"\n        SELECT service.description AS product,\n               SUM(cost) AS cost_usd,\n               currency\n        FROM `{dataset}.gcp_billing_export_v1_*`\n        WHERE DATE(usage_start_time) >= '{month_start}'\n          AND DATE(usage_start_time) <= '{target.isoformat()}'\n        GROUP BY product, currency\n        "
        for row in client.query(sql).result():
            cost_usd = float(row.cost_usd or 0)
            yield UsageRecord(date=target, provider=self.label, product=row.product, usage_quantity=0, usage_unit='-', cost_cny=round(cost_usd * usd_to_cny, 2), cost_original=cost_usd, currency=row.currency or 'USD', exchange_rate=usd_to_cny)

    def _fetch_billing_api(self, target: date) -> Iterable[UsageRecord]:
        require_online()
        raise NotImplementedError('GCP 请开启 BigQuery billing export，并在 config 填 bigquery_dataset。见 https://cloud.google.com/billing/docs/how-to/export-data-bigquery')
