from decimal import Decimal

from ownership_service import OwnershipRequest, onboard


class StubClient:
    def __init__(self):
        self.calls = []

    def request(self, method, path, *, query=None, body=None):
        self.calls.append((method, path, query, body))
        if path == "/v1/dns/domain/get":
            return {"zone_id": "zone-42"}
        if path == "/v1/dns/domain/verify":
            return {"verified": True}
        if path == "/v1/auth/user/get_by_email":
            return {"user_id": "user-7"}
        return {}


def test_large_payment_waits_for_review_after_domain_proof():
    client = StubClient()
    request = OwnershipRequest(domain="fintech.example", email="owner@fintech.example",
                               payment_id="pay-31", amount=Decimal("10000"),
                               txt_name="_ownership", txt_value="proof-token")
    result = onboard(request, client)
    assert result.payment.state == "held"
    assert result.notification.event == "payment_held_for_review"
    assert result.user_id == "user-7"
    assert client.calls[1][3]["zone_id"] == "zone-42"
    assert client.calls[1][3]["record_type"] == "TXT"
    assert client.calls[1][3]["record_id"]
    assert client.calls[2][1] == "/v1/dns/domain/verify"
    assert client.calls[3][2] == {"email": "owner@fintech.example"}


def test_small_payment_is_ready():
    client = StubClient()
    result = onboard(OwnershipRequest(domain="fintech.example", email="owner@fintech.example",
                        payment_id="pay-32", amount=Decimal("25"), txt_name="_ownership",
                        txt_value="proof-token"), client)
    assert result.payment.state == "ready"
    assert result.notification.event == "payment_ready"
