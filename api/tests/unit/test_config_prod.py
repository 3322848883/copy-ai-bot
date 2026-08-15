# 生产配置 fail-fast 单元测试（Task 4）
# 覆盖：prod 缺密钥/默认值 → 拒绝实例化；补齐必填 → 正常
from __future__ import annotations

import pytest

from api.core.config import Settings


def _prod_env(monkeypatch, **overrides) -> None:
    base = {
        "APP_ENV": "prod",
        "DEBUG": "false",
        "JWT_SECRET": "x" * 40,
        "VAULT_KEY_HEX": "ab" * 32,
        "DATABASE_URL": "postgresql+asyncpg://app:pass@db.internal:5432/signal_saas",
        "REDIS_URL": "redis://redis:6379/0",
        "SMTP_HOST": "smtp.example.com",
        "SMTP_PORT": "587",
        "SMTP_USER": "svc",
        "SMTP_PASSWORD": "pw",
        "CORS_ORIGINS": "https://app.example.com",
        "ENABLED_EXCHANGES": "gate",
    }
    for k, v in {**base, **overrides}.items():
        monkeypatch.setenv(k, v)


class TestProdRejectsDefaults:
    def test_default_jwt_secret_rejected(self, monkeypatch):
        _prod_env(monkeypatch, JWT_SECRET="change-me-in-prod")
        with pytest.raises(ValueError, match="JWT_SECRET"):
            Settings(_env_file=None)

    def test_short_jwt_secret_rejected(self, monkeypatch):
        _prod_env(monkeypatch, JWT_SECRET="short")
        with pytest.raises(ValueError, match="JWT_SECRET"):
            Settings(_env_file=None)

    def test_zero_vault_key_rejected(self, monkeypatch):
        _prod_env(monkeypatch, VAULT_KEY_HEX="0" * 64)
        with pytest.raises(ValueError, match="VAULT_KEY_HEX"):
            Settings(_env_file=None)

    def test_bad_vault_key_length_rejected(self, monkeypatch):
        _prod_env(monkeypatch, VAULT_KEY_HEX="ab" * 30)
        with pytest.raises(ValueError, match="VAULT_KEY_HEX"):
            Settings(_env_file=None)

    def test_local_smtp_rejected(self, monkeypatch):
        _prod_env(monkeypatch, SMTP_HOST="mailhog")
        with pytest.raises(ValueError, match="SMTP_HOST"):
            Settings(_env_file=None)

    def test_wildcard_cors_rejected(self, monkeypatch):
        _prod_env(monkeypatch, CORS_ORIGINS="*")
        with pytest.raises(ValueError, match="CORS_ORIGINS"):
            Settings(_env_file=None)

    def test_local_db_rejected(self, monkeypatch):
        _prod_env(monkeypatch, DATABASE_URL="postgresql+asyncpg://signal:signal@localhost:5432/signal_saas")
        with pytest.raises(ValueError, match="DATABASE_URL"):
            Settings(_env_file=None)

    def test_empty_enabled_exchanges_rejected(self, monkeypatch):
        _prod_env(monkeypatch, ENABLED_EXCHANGES="")
        with pytest.raises(ValueError, match="ENABLED_EXCHANGES"):
            Settings(_env_file=None)


class TestProdAcceptsValid:
    def test_full_valid_config(self, monkeypatch):
        _prod_env(monkeypatch)
        s = Settings(_env_file=None)
        assert s.app_env == "prod"
        assert s.enabled_exchange_list() == ["gate"]

    def test_dev_skips_validation(self, monkeypatch):
        _prod_env(monkeypatch, APP_ENV="dev", JWT_SECRET="change-me-in-prod")
        s = Settings(_env_file=None)
        assert s.app_env == "dev"  # dev 允许默认密钥
