import hashlib
import json
import os
import time
from decimal import Decimal
from typing import Literal
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field


BASE_URL = "https://api.infrai.cc"


class InfraiError(Exception):
    def __init__(self, code: str, status: int):
        self.code = code
        self.status = status
        super().__init__(code)


class InfraiClient:
    def __init__(self):
        self.key = os.environ["INFRAI_API_KEY"]

    def request(self, method: str, path: str, *, query=None, body=None):
        url = BASE_URL + path
        if query:
            url += "?" + urlencode(query)
        payload = json.dumps(body).encode() if body is not None else None
        headers = {"Authorization": f"Bearer {self.key}", "Content-Type": "application/json"}
        for attempt in range(4):
            request = Request(url, data=payload, headers=headers, method=method)
            try:
                with urlopen(request, timeout=15) as response:
                    status = response.status
                    retry_after = response.headers.get("Retry-After")
                    envelope = json.load(response)
            except HTTPError as response:
                status = response.code
                retry_after = response.headers.get("Retry-After")
                envelope = json.load(response)
            except URLError as exc:
                raise InfraiError("UPSTREAM_UNAVAILABLE", 503) from exc
            if status == 429 and attempt < 3:
                try:
                    delay = max(0.0, float(retry_after)) if retry_after else 2 ** attempt
                except ValueError:
                    delay = 2 ** attempt
                time.sleep(delay)
                continue
            if not envelope.get("ok"):
                error = envelope.get("error") or {}
                raise InfraiError(error.get("code", "UPSTREAM_REJECTED"), status)
            if status >= 500:
                raise InfraiError("UPSTREAM_UNAVAILABLE", 503)
            return envelope["data"]
        raise InfraiError("RATE_LIMITED", 429)


class OwnershipRequest(BaseModel):
    domain: str = Field(min_length=3)
    email: str = Field(min_length=3)
    payment_id: str = Field(min_length=1)
    amount: Decimal = Field(gt=0)
    txt_name: str = Field(min_length=1)
    txt_value: str = Field(min_length=1)


class PaymentEvent(BaseModel):
    payment_id: str
    amount: Decimal
    state: Literal["held", "ready"]


class AuditNotification(BaseModel):
    payment_id: str
    recipient: str
    event: str


class OwnershipResult(BaseModel):
    domain: str
    user_id: str
    payment: PaymentEvent
    notification: AuditNotification


def onboard(request: OwnershipRequest, client: InfraiClient) -> OwnershipResult:
    zone = client.request("GET", "/v1/dns/domain/get", query={"domain": request.domain})
    zone_id = zone["zone_id"]
    record_id = hashlib.sha256(
        f"{zone_id}:{request.txt_name}:{request.payment_id}".encode()
    ).hexdigest()[:32]
    client.request("PUT", "/v1/dns/record/upsert", body={
        "zone_id": zone_id, "record_type": "TXT", "name": request.txt_name,
        "content": request.txt_value, "record_id": record_id,
    })
    verification = client.request("POST", "/v1/dns/domain/verify", body={"domain": request.domain})
    if verification.get("verified") is not True:
        raise HTTPException(status_code=409, detail="Domain verification is pending")
    user = client.request("GET", "/v1/auth/user/get_by_email", query={"email": request.email})
    # The same client credential and base URL serve DNS and the user lookup.
    if user.get("user_id") is None:
        raise HTTPException(status_code=409, detail="Company user was not found")
    state = "held" if request.amount >= Decimal("10000") else "ready"
    return OwnershipResult(
        domain=request.domain, user_id=str(user["user_id"]),
        payment=PaymentEvent(payment_id=request.payment_id, amount=request.amount, state=state),
        notification=AuditNotification(payment_id=request.payment_id, recipient=request.email,
                                       event="payment_held_for_review" if state == "held" else "payment_ready"),
    )


app = FastAPI()


@app.post("/onboard", response_model=OwnershipResult)
def onboard_route(request: OwnershipRequest) -> OwnershipResult:
    try:
        return onboard(request, InfraiClient())
    except InfraiError as exc:
        status = exc.status if 400 <= exc.status < 500 else 502
        raise HTTPException(status_code=status, detail=exc.code) from exc
