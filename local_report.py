"""Explicit local JSON reporting; starts with zero business records."""
import argparse
import json
import math
from collections import defaultdict
from pathlib import Path

from lib.config import load, total_monthly_budget


def summarize(records):
    totals = defaultdict(float)
    for item in records:
        amount = float(item['cost_cny'])
        if not math.isfinite(amount):
            raise ValueError('金额必须为有限数字')
        totals[str(item['provider'])] += amount
    return {
        'mode': 'offline',
        'record_count': len(records),
        'total_cny': round(sum(totals.values()), 2),
        'by_provider': {k: round(v, 2) for k, v in sorted(totals.items())},
        'configured_budget': total_monthly_budget(load()['budgets']),
    }


def main():
    parser = argparse.ArgumentParser(description='本地空数据费用汇总；不访问云服务。')
    parser.add_argument('--input', type=Path, help='可选：明确指定自行制作的虚构 JSON 记录；不扫描其他文件')
    args = parser.parse_args()
    records = json.loads(args.input.read_text(encoding='utf-8')) if args.input else []
    if not isinstance(records, list):
        raise ValueError('输入必须为记录数组')
    print(json.dumps(summarize(records), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
