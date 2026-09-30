"""Credential/keychain integration is intentionally absent from this copy."""
from .base import Provider
from lib.offline import require_online


class MinimaxProvider(Provider):
    slug = 'minimax'
    label = 'API-minimax'
    supports_backfill = True
    resolve_credentials = require_online
    fetch_month_to_date = require_online
    fetch_daily = require_online
