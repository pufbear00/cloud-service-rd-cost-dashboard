"""Offline mode never guesses exchange rates or fetches historical rates."""


def get_monthly_rate(target_date, from_cur='USD', to_cur='CNY') -> float:
    if from_cur == to_cur:
        return 1.0
    raise ValueError('未配置演示汇率；空数据副本不从线上读取汇率。')
