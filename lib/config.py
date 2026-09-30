"""No original configuration, dotenv, credentials or OS account lookup."""


def load() -> dict:
    return {'offline': True, 'providers': {}, 'budgets': {}, 'budgets_by_month': {}}


def budgets_for(cfg: dict, month: str) -> dict:
    return (cfg.get('budgets_by_month') or {}).get(month, cfg.get('budgets', {}))


def total_monthly_budget(budgets: dict) -> float:
    return sum(v for k, v in budgets.items()
               if k != 'total' and isinstance(v, (int, float)) and not isinstance(v, bool))
