import math
from datetime import datetime

import pytest

from tests.conftest import load_mock

SESSIONS = load_mock("sessions.json")
TRANSACTIONS = load_mock("transactions.json")
RATES = load_mock("rates.json")
DEVICES = load_mock("devices.json")

SESSIONS_BY_ID = {s["session_id"]: s for s in SESSIONS}
RATES_BY_GARAGE = {r["garage_id"]: r for r in RATES}

# Deliberate billing error kept in the data to test overcharge detection (daily max not applied).
KNOWN_OVERCHARGES = {"TXN-9014"}


def expected_charge(session: dict, end_time: str) -> float:
    rate = RATES_BY_GARAGE[session["garage_id"]]
    start = datetime.fromisoformat(session["entry_time"])
    event = rate["event"]
    if event and datetime.fromisoformat(event["start"]) <= start <= datetime.fromisoformat(event["end"]):
        return event["flat_rate"]
    hours = math.ceil((datetime.fromisoformat(end_time) - start).total_seconds() / 3600)
    hourly = rate["standard_hourly_rate"]
    if session["validation"] and rate["validated_hourly_rate"] is not None and hours <= rate["validation_window_hours"]:
        hourly = rate["validated_hourly_rate"]
    return min(hours * hourly, rate["daily_max"])


@pytest.mark.parametrize(
    "records, key",
    [(SESSIONS, "session_id"), (TRANSACTIONS, "transaction_id"), (RATES, "garage_id"), (DEVICES, "garage_id")],
    ids=["sessions", "transactions", "rates", "devices"],
)
def test_ids_are_unique(records, key):
    ids = [r[key] for r in records]
    assert len(ids) == len(set(ids))


def test_session_transaction_links_are_consistent():
    transaction_ids = {t["transaction_id"] for t in TRANSACTIONS}
    for session in SESSIONS:
        assert set(session["transaction_ids"]) <= transaction_ids, session["session_id"]
    for transaction in TRANSACTIONS:
        session = SESSIONS_BY_ID[transaction["session_id"]]
        assert transaction["transaction_id"] in session["transaction_ids"]


def test_every_session_garage_has_rates_and_devices():
    device_garages = {d["garage_id"] for d in DEVICES}
    for session in SESSIONS:
        assert session["garage_id"] in RATES_BY_GARAGE
        assert session["garage_id"] in device_garages


@pytest.mark.parametrize("session", SESSIONS, ids=lambda s: s["session_id"])
def test_session_status_matches_exit_time(session):
    if session["status"] == "closed":
        assert session["exit_time"] is not None
    else:
        assert session["status"] == "active"
        assert session["exit_time"] is None


@pytest.mark.parametrize("transaction", TRANSACTIONS, ids=lambda t: t["transaction_id"])
def test_transaction_fields_are_valid(transaction):
    assert transaction["status"] in {"successful", "failed", "pending"}
    assert transaction["gateway_status"] in {"successful", "failed", "pending", "not_found"}
    assert transaction["settled"] == (transaction["gateway_status"] == "successful")
    if transaction["gateway_status"] == "not_found":
        assert transaction["gateway_reference"] is None


@pytest.mark.parametrize("transaction", TRANSACTIONS, ids=lambda t: t["transaction_id"])
def test_transaction_amount_matches_billing_rules(transaction):
    session = SESSIONS_BY_ID[transaction["session_id"]]
    expected = expected_charge(session, session["exit_time"] or transaction["created_at"])
    if transaction["transaction_id"] in KNOWN_OVERCHARGES:
        assert transaction["amount"] > expected
    else:
        assert transaction["amount"] == expected
