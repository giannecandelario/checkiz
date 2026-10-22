# Payment alert feed

Checkiz fills its ledger from the seller's incoming payment alerts, so nobody has to open GCash or Maya during a stream. The ledger is only as good as this feed, so there are three ways in, in order of trust.

| Source | Endpoint | Trust | Notes |
|---|---|---|---|
| Wallet app notification | `POST /ledger/notification` | Highest. Android sets the package name, so it can't be faked by a texter. | Works even if the wallet stops sending SMS. Alerts without a reference number are accepted. |
| SMS | `POST /ledger/sms` | Medium. Sender IDs can be spoofed. | Large payments seen only by SMS return `needs_app_check`. |
| Pasted text | `POST /ledger/paste` | Medium. Typed by the seller. | Fallback when neither of the above arrives. Paste several alerts separated by a blank line, for example from the in-app inbox. |

Check what your own phone receives today. GCash has changed how it sends alerts before, so don't assume SMS is still arriving.

## Notification forwarder (recommended)

```bash
curl -X POST http://localhost:8000/ledger/notification \
  -H "Content-Type: application/json" -H "X-API-Key: <your key>" \
  -d '{"package": "com.globe.gcash.android", "title": "GCash", "text": "You have received PHP 150.37 of GCash from JUAN D."}'
```

`tools/termux_notification_forwarder.sh` polls the phone's notifications and posts the wallet app's "received" alerts. It needs Termux:API and Notification access, and it is untested on a device. Allowed packages are set with `CHECKIZ_APP_PACKAGES` (default `com.globe.gcash.android,com.paymaya`); confirm the package names on your phone.

## SMS forwarder

Any Android app that forwards SMS to a webhook works. Point it at `/ledger/sms` with the body `{"text": "<message body>"}`. `tools/termux_sms_forwarder.sh` does the same by polling the inbox (untested on a device).

## What happens when an alert arrives

1. It is stored once. Re-sending the same alert is harmless.
2. If a receipt with the same reference was waiting, that order is settled.
3. Otherwise, if one open order was issued for exactly that amount, the order is settled from the alert alone (see "Order-bound payments" in the README).

## Safety

- Set `CHECKIZ_API_KEY`. Without it, anyone who can reach the server can post fake alerts. The server prints a warning at startup if it is unset.
- `CHECKIZ_CONFIRM_ABOVE` (default 2000) is the amount above which a non-app alert asks the seller to confirm in the wallet app.
- Outgoing alerts ("you have sent...") are ignored.
- SMS and notification access need the phone owner's explicit permission. Forward only payment alerts, and store only what matching needs.
