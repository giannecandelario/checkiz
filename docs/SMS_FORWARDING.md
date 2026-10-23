# Payment alert feed

Checkiz fills its ledger from the seller's incoming payment alerts, so nobody has to open the wallet or banking app during a stream. Any provider that raises a notification or sends an SMS can feed it; the parser wording is what varies. The ledger is only as good as this feed, so there are four ways in, in order of trust.

| Source | Endpoint | Trust | Notes |
|---|---|---|---|
| Wallet app notification | `POST /ledger/notification` | Highest. Android sets the package name, so it can't be faked by a texter. | Works even if the wallet stops sending SMS. Alerts without a reference number are accepted. |
| SMS | `POST /ledger/sms` | Medium. Sender IDs can be spoofed. | Large payments seen only by SMS return `needs_app_check`. |
| Pasted text | `POST /ledger/paste` | Medium. Typed by the seller. | Fallback when neither of the above arrives. Paste several alerts separated by a blank line, for example from the in-app inbox. |
| Screenshot of the seller's own Transactions screen | `POST /ledger/history-screenshot` | Lowest. `history`: read off an image by OCR, unsigned, and a reference can attach to the wrong row on a crooked list. | The fallback when nothing arrives at all. Reads the list row by row, keeps the wallet's printed time in `printed_at`, refuses money-out rows and says why. Large payments seen only here still return `needs_app_check`. Upload it on the dashboard under *Ledger*. |

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

## Screenshot of your own transaction list

When nothing arrives at all - no SMS, no Termux, notification access you would rather not grant - the seller opens the wallet's own Transactions/Activity list, screenshots it, and uploads that to `POST /ledger/history-screenshot` (the dashboard does it under *Ledger*). `app/history.py` reads it row by row, because a transaction list is a table, not a sentence: the direction word, the figure, the reference and the time sit on separate lines.

```bash
curl -s -X POST http://localhost:8000/ledger/history-screenshot \
  -H "X-API-Key: <your key>" -F "file=@transactions.png"
```

What it does and does not do:

- **Rows alternate money in and money out.** Direction is decided by which word sits
  *closest* to the amount, so a payment listed under an outgoing neighbour is still a
  payment. A row the parser cannot place is refused and reported in `skipped` with its
  reason and the row text it read - never quietly dropped.
- **The wallet's printed time is kept separate** (`printed_at`) from the time Checkiz
  saw it (`received_at`). A screenshot of yesterday's list does not become today's income.
- **No names are extracted.** A transactions screen shows the other party to every
  payment the seller has ever made; only the one row that became an entry is stored, and
  its sender field is left empty.
- **Re-uploading the same screen adds nothing.** The first copy of a reference wins, and
  the answer says so in `already_in_ledger` rather than counting the payment twice.
- **A payment with no readable reference still becomes an entry**, under a synthetic key,
  and loses replay detection - the same trade pasted alerts make.
- `added` counts rows the ledger did not already hold. A reference it already had is
  listed in `already_in_ledger` instead of being counted as income again.

## What happens when an alert arrives

1. It is stored once. Re-sending the same alert is harmless.
2. If a receipt with the same reference was waiting, that order is settled.
3. Otherwise, if one open order was issued for exactly that amount, the order is settled from the alert alone (see "Order-bound payments" in the README).
4. If the alert came from SMS, pasted text or a transactions screenshot rather than the wallet app, and the amount is at or above `CHECKIZ_CONFIRM_ABOVE`, the order is marked `needs_app_check` and appears on the reconciliation review list (`GET /review`) and on the packing list with `confirm_in_app=YES`.

## Safety

- Set `CHECKIZ_API_KEY`. Without it, anyone who can reach the server can post fake alerts. The server prints a warning at startup if it is unset. The forwarder commands above send it as an `X-API-Key` header; the dashboard and QR page send the same header from the key box at the top, which the browser remembers until that tab is closed.
- `CHECKIZ_CONFIRM_ABOVE` (default 2000) is the amount above which a non-app alert asks the seller to confirm in the wallet app.
- Outgoing alerts ("you have sent...") are ignored.
- SMS and notification access need the phone owner's explicit permission. Forward only payment alerts, and store only what matching needs.
