import hashlib
import hmac
import json
import time
from urllib.parse import urlencode

import pytest
from fastapi import HTTPException
import accounts


def telegram_payload(token="test:token", user_id=1234, age=0):
    payload = {"auth_date": str(int(time.time()) - age),
               "user": json.dumps({"id": user_id, "first_name": "Test"})}
    check = "\n".join(f"{k}={v}" for k, v in sorted(payload.items()))
    key = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    payload["hash"] = hmac.new(key, check.encode(), hashlib.sha256).hexdigest()
    return urlencode(payload)


def test_valid_telegram_signature(monkeypatch):
    monkeypatch.setattr(accounts, "BOT_TOKEN", "test:token")
    assert accounts.verify_telegram_init_data(telegram_payload())["id"] == 1234


def test_reject_tampered_data(monkeypatch):
    monkeypatch.setattr(accounts, "BOT_TOKEN", "test:token")
    raw = telegram_payload().replace("1234", "9999")
    with pytest.raises(HTTPException) as error:
        accounts.verify_telegram_init_data(raw)
    assert error.value.status_code == 401


def test_reject_expired_signature(monkeypatch):
    monkeypatch.setattr(accounts, "BOT_TOKEN", "test:token")
    with pytest.raises(HTTPException) as error:
        accounts.verify_telegram_init_data(telegram_payload(age=7200))
    assert error.value.status_code == 401


def test_missing_db_does_not_create_local_fallback(monkeypatch):
    monkeypatch.setattr(accounts, "_Session", None)
    with pytest.raises(HTTPException) as error:
        next(accounts.session())
    assert error.value.status_code == 503
