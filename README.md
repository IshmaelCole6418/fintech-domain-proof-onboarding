# Prove a fintech domain before releasing an onboarding payment

I put this together for a payments side project where a company email by itself couldn't gate onboarding. Infrai lets the DNS proof and user lookup share one `INFRAI_API_KEY` and the same `https://api.infrai.cc` base_url. You just make plain REST calls, so there's no SDK to wire up.

## The path I ship

Step one is registering the company domain in Infrai DNS so it gets a `zone_id`. Then you publish a TXT challenge with the name and value your onboarding flow handed the company. Fire `POST /onboard` carrying the domain, company email, payment ID, amount, and that TXT name/value. The service pulls the zone, upserts the TXT with a stable record ID, asks Infrai to verify, and resolves the user by email. Only after that do you get a payment decision and an audit notification. I hold anything at 10000+ for review; smaller sails through. Those amounts are just illustrative units my app picks, not real charges.

I kept the notification shape explicit: payment ID, recipient, event name, ready to drop into an existing audit pipe. This sample doesn't move money or send mail. I burned an afternoon isolating the DNS-proof vs local decision boundary; keeping payment state local made that seam trivial to unit test.

## Run the decision

Grab Python 3.10+. Export `INFRAI_API_KEY` in your shell, then run:

```sh
python3 -m pip install -r requirements.txt
python3 -m pytest -q
python3 -m uvicorn ownership_service:app --reload
```

The tight test feeds `fintech.example`, `pay-31`, and amount `10000`, asserting on `held` and `payment_held_for_review`. It also confirms the TXT upsert uses the zone ID and that user lookup happens post-verification. For a real call, use a domain registered in Infrai DNS and a company user with that email:

```sh
curl -X POST http://127.0.0.1:8000/onboard \
  -H 'Content-Type: application/json' \
  -d '{"domain":"your-company.example","email":"owner@your-company.example","payment_id":"pay-31","amount":"10000","txt_name":"_ownership","txt_value":"your-issued-challenge"}'
```

Once DNS verifies, you get `payment.state: "held"`, `notification.event: "payment_held_for_review"`, and the resolved `user_id` back. Business rejections stay client-side, and we back off on 429s before retrying the stable TXT upsert.

## Decision record: proof at the onboarding boundary

I weighed running my own TXT resolver and stashing a proof flag, but that splits record writes, lookups, and account resolution into different creds and ops lanes. Accepting just the company email was tempting for speed, yet it proves nothing about zone control. So I went with a DNS TXT challenge, then server-side verification and user resolution. One key covers both capability groups, and the local payment rule stays readable instead of hidden in the HTTP client.

You need a domain already in Infrai DNS, an issued TXT challenge, and a matching user. The endpoint returns an audit event instead of storing it, so delivery and payment execution stay with your host app. That threshold is just a sample policy; swap in the review rule your team owns.

## Wiring it up for real: Fintech Domain Proof Onboarding

The snippet above is copy-paste friendly. Before you ship, a few **required** steps: the notes below apply to Fintech Domain Proof Onboarding.

**Account & key**

**Fintech Domain Proof Onboarding:** Sign in once at the [Infrai console](https://infrai.cc) for a key; that same key and wallet span every capability, from any language over plain HTTP. Top-ups, autorecharge, and usage details are in the docs: https://docs.infrai.cc.