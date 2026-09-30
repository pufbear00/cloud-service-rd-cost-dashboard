import socket
import unittest
from datetime import date

from lib.config import load, budgets_for, total_monthly_budget
from lib.offline import OfflineModeError
from local_report import summarize
from providers.base import UsageRecord
from providers.minimax import MinimaxProvider


class EmptyCopyTests(unittest.TestCase):
    def test_starts_empty(self):
        self.assertEqual(summarize([])['record_count'], 0)
        self.assertEqual(summarize([])['total_cny'], 0)
        self.assertEqual(load()['providers'], {})

    def test_local_summary_synthetic(self):
        self.assertEqual(summarize([{'provider': 'Demo', 'cost_cny': 12.5}, {'provider': 'Demo', 'cost_cny': -2.5}])['total_cny'], 10)

    def test_budget_schema(self):
        self.assertEqual(budgets_for({'budgets': {'Demo': 10}}, '2000-01'), {'Demo': 10})
        self.assertEqual(total_monthly_budget({'Demo': 10, 'total': 99, 'enabled': True}), 10)

    def test_record_schema(self):
        record = UsageRecord(date(2000, 1, 1), 'Demo', 'Synthetic', 0, '-', 0, 0, 'CNY')
        self.assertEqual(record.to_dict()['date'], '2000-01-01')

    def test_no_network(self):
        with self.assertRaises(OfflineModeError):
            socket.create_connection(('example.invalid', 443))

    def test_no_collector_or_keychain(self):
        with self.assertRaises(OfflineModeError):
            MinimaxProvider({})

    def test_direct_service_functions_are_guarded(self):
        # Static verification without installing/importing optional SDKs.
        import ast
        from pathlib import Path
        root = Path(__file__).resolve().parents[1] / 'lib'
        pure = {'merchant_name', '_record_to_row', '_build_post_content', 'parse_tradebill'}
        for name in ('airwallex.py', 'appstore.py', 'googleplay.py', 'stripe_client.py', 'wechatpay.py', 'feishu.py'):
            tree = ast.parse((root / name).read_text())
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef) and node.name not in pure:
                    self.assertEqual(ast.unparse(node.body[0]), 'require_online()')

    def test_collectors_cannot_read_old_cache(self):
        from providers.tencent import TencentProvider
        with self.assertRaises(OfflineModeError):
            TencentProvider._load_month_details(None, 2000, 1)


if __name__ == '__main__':
    unittest.main()
