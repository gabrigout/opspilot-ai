from functools import lru_cache

from app.core.config import get_settings
from app.rules.engine import RuleConfig


@lru_cache
def get_rule_config() -> RuleConfig:
    return RuleConfig.from_overrides(get_settings().rules_overrides)
