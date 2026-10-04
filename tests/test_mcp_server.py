import pytest

from mcp_server import server
from tests.conftest import load_mock

SESSIONS = load_mock("sessions.json")
TRANSACTIONS = load_mock("transactions.json")
RATES = load_mock("rates.json")
DEVICES = load_mock("devices.json")

TOOL_FUNCTIONS = [server.get_parking_session, server.get_payment_transaction, server.get_garage_rate, server.get_device_status]


@pytest.mark.parametrize("session", SESSIONS, ids=lambda s: s["session_id"])
def test_get_parking_session_returns_record(session):
    assert server.get_parking_session(session["session_id"]) == session


@pytest.mark.parametrize("transaction", TRANSACTIONS, ids=lambda t: t["transaction_id"])
def test_get_payment_transaction_returns_record(transaction):
    assert server.get_payment_transaction(transaction["transaction_id"]) == transaction


@pytest.mark.parametrize("rate", RATES, ids=lambda r: r["garage_id"])
def test_get_garage_rate_returns_record(rate):
    assert server.get_garage_rate(rate["garage_id"]) == rate


@pytest.mark.parametrize("device", DEVICES, ids=lambda d: d["garage_id"])
def test_get_device_status_returns_record(device):
    assert server.get_device_status(device["garage_id"]) == device


@pytest.mark.parametrize(
    "tool, arg, error",
    [
        (server.get_parking_session, "session_id", "session_not_found"),
        (server.get_payment_transaction, "transaction_id", "transaction_not_found"),
        (server.get_garage_rate, "garage_id", "garage_rate_not_found"),
        (server.get_device_status, "garage_id", "device_not_found"),
    ],
    ids=lambda v: getattr(v, "__name__", None),
)
@pytest.mark.parametrize("bad_id", ["SES-9999", "", "ses-1002", " SES-1002"])
def test_unknown_ids_return_not_found_error(tool, arg, error, bad_id):
    assert tool(bad_id) == {"error": error, arg: bad_id}


@pytest.mark.parametrize("tool", TOOL_FUNCTIONS, ids=lambda f: f.__name__)
def test_tools_have_descriptions(tool):
    # Bedrock rejects tool specs with an empty description.
    assert tool.__doc__ and tool.__doc__.strip()
