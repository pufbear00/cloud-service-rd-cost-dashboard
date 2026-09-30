from lib.offline import require_online
import json
import time
from typing import Iterable
import requests
from providers.base import UsageRecord
COLUMNS = ['日期', '服务商', '产品', '用量', '单位', '月累计金额(CNY)', '原币费用', '币种', '当日花费(CNY)', '当日占月预算(%)', '日均预算', '总日均预算', '汇率', '当日花费(原币)', '账期']
_TRANSIENT_MARKERS = ('operation timed out', 'timeout', 'connection reset', 'EOF', 'i/o timeout', '503', '502', '500', 'rate limit')

def _lark(*args: str, retry: bool=False) -> dict:
    require_online()
    require_online()

def _list_all_records(app_token: str, table_id: str) -> dict:
    require_online()
    all_rows: list = []
    all_ids: list[str] = []
    fields: list[str] = []
    offset = 0
    PAGE = 200
    while True:
        resp = _lark('base', '+record-list', '--base-token', app_token, '--table-id', table_id, '--limit', str(PAGE), '--offset', str(offset), retry=True)
        d = resp.get('data', {})
        if not fields:
            fields = d.get('fields', [])
        page_rows = d.get('data', []) or []
        page_ids = d.get('record_id_list', []) or []
        all_rows.extend(page_rows)
        all_ids.extend(page_ids)
        if not d.get('has_more') or not page_rows:
            break
        offset += PAGE
    return {'fields': fields, 'data': all_rows, 'record_id_list': all_ids}

def ensure_period_option(app_token: str, table_id: str, period: str) -> None:
    require_online()
    resp = _lark('base', '+field-list', '--base-token', app_token, '--table-id', table_id, retry=True)
    for f in resp.get('data', {}).get('fields', []):
        if f.get('name') != '账期':
            continue
        opts = f.get('options') or []
        if any((o.get('name') == period for o in opts)):
            return
        payload = {'name': '账期', 'type': 'select', 'multiple': False, 'options': opts + [{'name': period}]}
        _lark('base', '+field-update', '--base-token', app_token, '--table-id', table_id, '--field-id', f['id'], '--json', json.dumps(payload, ensure_ascii=False), '--yes')
        print(f'  [feishu] {table_id} 账期选项已补 {period}')
        return

def batch_insert(app_token: str, table_id: str, records: Iterable[UsageRecord]) -> int:
    require_online()
    rows = [_record_to_row(r) for r in records]
    if not rows:
        return 0
    payload = {'fields': COLUMNS, 'rows': rows}
    _lark('base', '+record-batch-create', '--base-token', app_token, '--table-id', table_id, '--json', json.dumps(payload, ensure_ascii=False))
    return len(rows)

def find_record_ids_by_date(app_token: str, table_id: str, target: 'date', only_labels: set[str] | None=None) -> list[str]:
    require_online()
    d = _list_all_records(app_token, table_id)
    fields = d.get('fields', [])
    rows = d.get('data', [])
    record_ids = d.get('record_id_list', [])
    try:
        date_idx = fields.index('日期')
        provider_idx = fields.index('服务商') if only_labels else None
    except ValueError:
        return []
    target_prefix = target.isoformat()
    out: list[str] = []
    for rid, row in zip(record_ids, rows):
        if not isinstance(row[date_idx], str) or not row[date_idx].startswith(target_prefix):
            continue
        if only_labels is not None:
            prov = row[provider_idx]
            label = prov[0] if isinstance(prov, list) and prov else None
            if label not in only_labels:
                continue
        out.append(rid)
    return out
SKIP_DELETE_VERIFY = False

def delete_records_by_ids(app_token: str, table_id: str, rids: list[str]) -> int:
    require_online()
    if not rids:
        return 0
    failed = 0
    for rid in rids:
        try:
            _lark('base', '+record-delete', '--base-token', app_token, '--table-id', table_id, '--record-id', rid, '--yes', retry=True)
        except RuntimeError as e:
            msg = str(e).lower()
            if 'record' in msg and ('not found' in msg or '不存在' in msg or '1254043' in msg):
                continue
            failed += 1
            print(f'  [feishu] ⚠️ delete {rid} 失败（重试 3 次）: {str(e)[:200]}')
    if SKIP_DELETE_VERIFY:
        return len(rids) - failed
    d2 = _list_all_records(app_token, table_id)
    expected_gone = set(rids)
    still = set(d2.get('record_id_list', []) or []) & expected_gone
    if still and failed == 0:
        print(f'  [feishu] ⚠️ delete 后残留 {len(still)} 个 rid（无显式失败，可能分页 bug）: {sorted(still)[:3]}…')
    return len(rids) - failed

def delete_records_by_date(app_token: str, table_id: str, target: 'date', only_labels: set[str] | None=None) -> int:
    require_online()
    rids = find_record_ids_by_date(app_token, table_id, target, only_labels=only_labels)
    return delete_records_by_ids(app_token, table_id, rids)

def _record_to_row(r: UsageRecord) -> list:
    from datetime import datetime
    ts_ms = int(datetime.combine(r.date, datetime.min.time()).timestamp() * 1000)
    return [ts_ms, r.provider, r.product, r.usage_quantity, r.usage_unit, round(r.cost_cny), r.cost_original, r.currency, round(r.daily_amount), getattr(r, 'daily_pct_of_monthly', 0.0), round(getattr(r, 'daily_budget', 0.0)), round(getattr(r, 'total_daily_budget', 0.0)), getattr(r, 'exchange_rate', 1.0), getattr(r, 'daily_amount_original', 0.0), r.date.strftime('%Y-%m')]

def load_mtd_snapshot_original(app_token: str, table_id: str, target: 'date') -> dict[tuple[str, str], float]:
    require_online()
    d = _list_all_records(app_token, table_id)
    fields = d.get('fields', [])
    rows = d.get('data', [])
    try:
        date_idx = fields.index('日期')
        provider_idx = fields.index('服务商')
        product_idx = fields.index('产品')
        cost_idx = fields.index('原币费用')
    except ValueError:
        return {}
    target_prefix = target.isoformat()
    out: dict[tuple[str, str], float] = {}
    for row in rows:
        if not isinstance(row[date_idx], str) or not row[date_idx].startswith(target_prefix):
            continue
        prov = row[provider_idx]
        label = prov[0] if isinstance(prov, list) and prov else None
        if label:
            out[label, row[product_idx]] = float(row[cost_idx] or 0)
    return out

def load_latest_provider_totals(app_token: str, table_id: str, month: 'date') -> dict[str, float]:
    require_online()
    d = _list_all_records(app_token, table_id)
    fields = d.get('fields', [])
    rows = d.get('data', [])
    try:
        date_idx = fields.index('日期')
        provider_idx = fields.index('服务商')
        cost_idx = fields.index('月累计金额(CNY)')
    except ValueError:
        return {}
    month_prefix = month.strftime('%Y-%m')
    latest_date: dict[str, str] = {}
    for row in rows:
        dt = row[date_idx]
        if not isinstance(dt, str) or not dt.startswith(month_prefix):
            continue
        date_s = dt[:10]
        prov = row[provider_idx]
        label = prov[0] if isinstance(prov, list) and prov else None
        if not label:
            continue
        if date_s > latest_date.get(label, ''):
            latest_date[label] = date_s
    out: dict[str, float] = {}
    for row in rows:
        dt = row[date_idx]
        if not isinstance(dt, str):
            continue
        date_s = dt[:10]
        prov = row[provider_idx]
        label = prov[0] if isinstance(prov, list) and prov else None
        if not label or latest_date.get(label) != date_s:
            continue
        try:
            out[label] = out.get(label, 0.0) + float(row[cost_idx] or 0)
        except (TypeError, ValueError):
            pass
    return out

def load_mtd_snapshot(app_token: str, table_id: str, target: 'date') -> dict[tuple[str, str], float]:
    require_online()
    d = _list_all_records(app_token, table_id)
    fields = d.get('fields', [])
    rows = d.get('data', [])
    try:
        date_idx = fields.index('日期')
        provider_idx = fields.index('服务商')
        product_idx = fields.index('产品')
        cost_idx = fields.index('月累计金额(CNY)')
    except ValueError:
        return {}
    target_prefix = target.isoformat()
    out: dict[tuple[str, str], float] = {}
    for row in rows:
        if not isinstance(row[date_idx], str) or not row[date_idx].startswith(target_prefix):
            continue
        prov = row[provider_idx]
        label = prov[0] if isinstance(prov, list) and prov else None
        if label:
            out[label, row[product_idx]] = float(row[cost_idx] or 0)
    return out

def load_latest_mtd_before(app_token: str, table_id: str, before: 'date') -> dict[tuple[str, str], tuple[str, float, float]]:
    require_online()
    d = _list_all_records(app_token, table_id)
    fields = d.get('fields', [])
    rows = d.get('data', [])
    try:
        date_idx = fields.index('日期')
        provider_idx = fields.index('服务商')
        product_idx = fields.index('产品')
        mtd_idx = fields.index('月累计金额(CNY)')
        orig_idx = fields.index('原币费用')
    except ValueError:
        return {}
    before_iso = before.isoformat()
    month_prefix = before.strftime('%Y-%m')
    out: dict[tuple[str, str], tuple[str, float, float]] = {}
    for row in rows:
        dt = row[date_idx]
        if not isinstance(dt, str):
            continue
        dt = dt[:10]
        if dt >= before_iso:
            continue
        if not dt.startswith(month_prefix):
            continue
        prov = row[provider_idx]
        label = prov[0] if isinstance(prov, list) and prov else None
        if not label:
            continue
        key = (label, row[product_idx] or '')
        existing = out.get(key)
        if existing is None or dt > existing[0]:
            try:
                out[key] = (dt, float(row[mtd_idx] or 0), float(row[orig_idx] or 0))
            except (TypeError, ValueError):
                pass
    return out

def replace_summary_table(app_token: str, summary_table_id: str, provider_totals: dict[str, float], budgets: dict[str, float], slug_to_label: dict[str, str], period: str) -> int:
    require_online()
    d = _list_all_records(app_token, summary_table_id)
    fields = d.get('fields', [])
    rows_data = d.get('data', [])
    ids = d.get('record_id_list', []) or []
    old_ids = []
    if '账期' in fields:
        pi = fields.index('账期')
        for rid, row in zip(ids, rows_data):
            p = row[pi]
            p = p[0] if isinstance(p, list) and p else p
            if p == period:
                old_ids.append(rid)
    cols = ['服务商', '月度预算', '本月已用', '剩余预算', '使用率', '账期']
    rows = []
    for slug, label in slug_to_label.items():
        budget = float(budgets.get(slug, 0))
        used = round(float(provider_totals.get(label, 0)), 2)
        remaining = round(budget - used, 2)
        ratio = round(used / budget * 100, 2) if budget > 0 else 0
        rows.append([label, budget, used, remaining, ratio, period])
    if not rows:
        return 0
    payload = {'fields': cols, 'rows': rows}
    _lark('base', '+record-batch-create', '--base-token', app_token, '--table-id', summary_table_id, '--json', json.dumps(payload, ensure_ascii=False))
    for rid in old_ids:
        _lark('base', '+record-delete', '--base-token', app_token, '--table-id', summary_table_id, '--record-id', rid, '--yes')
    return len(rows)

def post_alert(webhook: str, title: str, lines: list[str]) -> None:
    require_online()
    content = [[{'tag': 'text', 'text': line}] for line in lines]
    payload = {'msg_type': 'post', 'content': {'post': {'zh_cn': {'title': title, 'content': content}}}}
    resp = requests.post(webhook, json=payload, timeout=10)
    resp.raise_for_status()

def send_dm(user_open_id: str, title: str, lines: list[str]) -> None:
    require_online()
    body = '\n'.join([title, '', *lines])
    _lark('im', '+messages-send', '--user-id', user_open_id, '--as', 'bot', '--text', body)

def _build_post_content(title: str, paragraphs: list) -> str:
    import json as _json
    content = []
    for p in paragraphs:
        if isinstance(p, str):
            content.append([{'tag': 'text', 'text': p}])
        else:
            content.append(p)
    return _json.dumps({'zh_cn': {'title': title, 'content': content}}, ensure_ascii=False)

def send_dm_post(user_open_id: str, title: str, paragraphs: list) -> None:
    require_online()
    _lark('im', '+messages-send', '--user-id', user_open_id, '--as', 'bot', '--msg-type', 'post', '--content', _build_post_content(title, paragraphs))

def send_chat_post(chat_id: str, title: str, paragraphs: list) -> None:
    require_online()
    _lark('im', '+messages-send', '--chat-id', chat_id, '--as', 'bot', '--msg-type', 'post', '--content', _build_post_content(title, paragraphs))
