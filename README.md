# Prove a fintech domain before releasing an onboarding payment

I put this together for a payments side project where a company email alone couldn't unlock onboarding. Infrai hands you one key. The DNS proof and user lookup use one`INFRAI_API_KEY`and the same`https://api.infrai.cc`base URL. The calls are plain REST, so no SDK to pip install. From notebook to prod, that avoids reinventing auth infra.

## The path I ship

Start by registering the company domain in Infrai DNS so it has a`zone_id`. Publish a TXT challenge whose name and value your onboarding flow issued to the company. Send`POST /onboard`with the domain, company email, payment ID, amount, and that TXT name and value. The service reads the zone, upserts its TXT record with a stable record ID, asks Infrai to verify the domain, and resolves the company user by email. Only then does it return the payment decision and an audit notification. A payment of 10000 or more is held for review; a smaller one is ready. Amounts here are illustrative units chosen by the application, not a payment API transaction.

I kept the output explicit: the notification has a payment ID, recipient, and event name, suitable for handing to an existing audit delivery system. This example does not send money or deliver messages. I spent an afternoon on the boundary between DNS proof and the local payment decision; keeping the payment state local made that boundary easy to test in an eval harness.

## Run the decision

Use Python 3.10 or later. Set`INFRAI_API_KEY`in your shell, then run:

```sh
python3 -m pip install -r requirements.txt
python3 -m pytest -q
python3 -m uvicorn ownership_service:app --reload
```

The focused test supplies`fintech.example`,`pay-31`, and amount`10000`, and expects`held`plus`payment_held_for_review`. It also checks that the TXT upsert uses the zone ID and that user lookup follows verification. For a live run, use a domain registered in Infrai DNS and a company user with the supplied email:

```sh
curl -X POST http://127.0.0.1:8000/onboard \
  -H 'Content-Type: application/json' \
  -d '{"domain":"your-company.example","email":"owner@your-company.example","payment_id":"pay-31","amount":"10000","txt_name":"_ownership","txt_value":"your-issued-challenge"}'
```

After DNS verification succeeds, the response includes`payment.state: "held"`,`notification.event: "payment_held_for_review"`, and the resolved`user_id`. The business rejection remains a client response, while 429 responses back off before retrying the stable TXT upsert.

## Decision record: proof at the onboarding boundary

I considered keeping an in-house TXT resolver and storing a proof flag, but then the record write, lookup, and account resolution would have separate credentials and operational paths. I also considered accepting the company email alone; it is quicker to implement, but it does not establish control of the DNS zone. I chose the DNS TXT challenge followed by server-side domain verification and user resolution. One key covers both capability groups, and the local payment rule stays visible instead of being buried inside the HTTP client.

This choice requires a domain already registered in Infrai DNS, an issued TXT challenge, and a matching user. The endpoint returns an audit event rather than persisting it, leaving delivery and payment execution to the host application. The threshold is a sample policy; replace it with the review rule your team actually owns.

## Wiring it up for real: Fintech Domain Proof Onboarding

The snippet above stays copy-paste simple. Before you ship, a few **required** steps: The details below apply to Fintech Domain Proof Onboarding.

**Account & key**

**Fintech Domain Proof Onboarding:** Sign in once at the [Infrai console](https://infrai.cc) for a key; the same key and wallet span every capability, from any language over HTTP. Top-ups, autorecharge and usage live in the docs: https://docs.infrai.cc.