# Real-device test protocol

**Nobody has run this protocol. Every table below is empty on purpose, and nothing in
this file is an observation.** It is written this way because the alternative - guessing
what a wallet sends in October 2026 - is what would make Checkiz wrong in front of a
judge or a seller.

What the code currently assumes, and cannot check without a phone:

| Assumption | Where it lives | What this protocol settles |
|---|---|---|
| A wallet still sends an SMS for an incoming payment | `tools/termux_sms_forwarder.sh`, `POST /ledger/sms` | Whether any SMS arrives at all |
| The wallet app posts a notification, and its Android package is `com.globe.gcash.android` / `com.paymaya` | `CHECKIZ_APP_PACKAGES`, `POST /ledger/notification` | The real package names, and whether the wording contains "received" |
| An alert reads like `You have received PHP 1,250.00 of GCash from JUAN D. Ref. No. 1002 849 130490.` | `app/ledger.py` `AMOUNT` / `REF` / `SENDER` / `INCOMING` | Whether the regexes match real wording |
| A reference is 13 digits | `CHECKIZ_REF_LENGTH` | The real length and digit grouping |
| A transactions screen is readable row by row | `app/history.py`, `POST /ledger/history-screenshot` | Which words the wallet prints per row, and whether the direction guard is right |
| A phone photo of a screen is readable at all, and what its ELA/sharpness look like | `CHECKIZ_OCR_CONFIDENCE_MIN`, `CHECKIZ_ELA_THRESHOLD`, `CHECKIZ_SHARPNESS_THRESHOLD` | See [CALIBRATION.md](CALIBRATION.md) - this is the one that gates the forensic claim |

## What you need

- The seller's Android phone, signed into the wallet you are testing, with the SIM that
  receives the wallet's SMS.
- Termux + Termux:API on that phone:
  ```bash
  pkg install termux-api jq curl
  ```
  Then grant, in Android settings: SMS permission (for the SMS steps) and
  **Notification access** to Termux:API (for the notification steps). Android shows the
  notification list only with that grant.
- A second device or account that can pay PHP 1.00 to the seller - a family member's
  wallet is enough. PHP 1.00 because a test that costs nothing gets run twice; a test
  that costs PHP 5,000 does not get run at all.
- Checkiz running with a key set:
  ```bash
  docker build -t checkiz .
  docker run --rm -p 8000:8000 \
    -e CHECKIZ_API_KEY=<some key> \
    -e CHECKIZ_DB_PATH=/tmp/device-test.db \
    checkiz
  ```
  The `-e` matters: an environment variable set on the shell that runs `docker run`
  does not reach the process inside the container.
  Note the phone and the server must be able to reach each other. On the same Wi-Fi, use
  the server's LAN address, e.g. `http://192.168.1.10:8000`.

## Part A - what does the phone actually receive?

Do each step once per wallet you support, and write the answer in the table.

1. On the phone, capture the current state so new items are identifiable:
   ```bash
   termux-sms-list -l 5 -t inbox | jq -r '.[].date'
   termux-notification-list | jq -r '.[].packageName'
   ```
   (The second one lists what is on the shade right now; it is not a log of everything
   that ever arrived, which is why step 4 re-reads it immediately after the payment.)
2. Have the second device pay **PHP 1.00** to the seller's wallet.
3. Wait 60 seconds - an SMS can be late.
4. Read both again and diff against step 1:
   ```bash
   termux-sms-list -l 5 -t inbox | jq '.[] | {date, address, body}'
   termux-notification-list | jq '.[] | {packageName, title, text}'
   ```
5. Record for each channel: **arrived / did not arrive**, and the exact `packageName`
   that posted the notification.
6. Copy the wording verbatim into the table. Keep the digits, but change them before the
   text goes anywhere near the repo: record the **length and grouping** of the reference
   (`13 digits, grouped 4-3-6`), not the value.
7. Repeat once more. Some wallets suppress a second alert inside a few minutes, and a
   single observation is the kind of thing that turns out to be the exception.

### Table A1 - channels

| Wallet | SMS arrives? | Notification arrives? | `packageName` | In-app inbox only? | Notes |
|---|---|---|---|---|---|
| GCash | | | | | |
| Maya | | | | | |
| (other) | | | | | |

### Table A2 - exact wording, digits changed

| Wallet | Channel | Text as printed (mask the digits) | "received"-type word present? | Reference shown? | Digits / grouping |
|---|---|---|---|---|---|
| | | | | | |
| | | | | | |

## Part B - does the parser agree with that wording?

Feed the text from Table A2 straight back in, from the phone or the laptop. Use the
**amount from the real alert** so a mismatch shows up as a wrong number rather than a
silent None.

```bash
curl -s -X POST $API/ledger/sms -H "Content-Type: application/json" \
  -H "X-API-Key: $KEY" \
  -d '{"text": "<paste the exact SMS body>"}'
```

Then, for a notification, with the package name you recorded in Table A1:

```bash
curl -s -X POST $API/ledger/notification -H "Content-Type: application/json" \
  -H "X-API-Key: $KEY" \
  -d '{"package": "<packageName from termux-notification-list>", "title": "<title>", "text": "<text>"}'
```

What each answer means:

- `200` with `"has_ref": true` - the alert is fully usable, including replay detection.
- `200` with `"has_ref": false` - the amount was read but no reference was found. Usually
  `CHECKIZ_REF_LENGTH` is wrong for this wallet, or the reference is printed with
  separators the regex does not expect. Try `CHECKIZ_REF_LENGTH=<real length>` and restart.
- `400` "Could not parse an incoming payment from that text" - the wording does not match
  `INCOMING` or `AMOUNT` in `app/ledger.py`. This is the result worth reporting even
  though it is a failure: it says the forwarder will never fill the ledger on this phone.
- `403` "Not a recognised wallet app" - the package name is real but not in
  `CHECKIZ_APP_PACKAGES`. Add it, restart, re-post.

Also run the forwarders themselves for one payment each and confirm a row reaches the
dashboard:

```bash
bash tools/termux_sms_forwarder.sh           # needs SMS permission
bash tools/termux_notification_forwarder.sh  # needs Notification access
```

### Table B - parser against real wording

| Wallet | Channel | Endpoint | HTTP | `has_ref` | amount read | what you changed |
|---|---|---|---|---|---|---|
| | | `/ledger/sms` | | | | |
| | | `/ledger/notification` | | | | |
| | | `/ledger/paste` (in-app inbox) | | | | |

## Part C - the transactions-screen fallback

This is the path that works when Part A comes back "neither".

1. Open the wallet's own **Transactions / Activity** list on the seller's phone - the
   screen with a row per payment, not a receipt for one payment.
2. Screenshot it. Note how many rows are on screen and whether both money in and money
   out appear.
3. Upload it on the dashboard under *Ledger*, or:
   ```bash
   curl -s -X POST $API/ledger/history-screenshot -H "X-API-Key: $KEY" \
     -F "file=@transactions.png"
   ```
4. Record `added`, and for every item in `skipped` its `reason` and the `raw` row text.
   A refusal is a normal, useful result - it means the parser found a money figure it
   would not sign for. **Read the `raw` text of each refusal**: if a real incoming
   payment was refused, that is a bug worth filing, with the wording attached.
5. Check the ledger table on the dashboard: the new rows must have
   `source = history`, and `printed_at` must show the time the wallet printed, not the
   time you uploaded. If they are the same, the screenshot's timestamps were not read.
6. Pay PHP 1.00 again, screenshot the same screen a second time, upload it, and confirm
   `added` does not double-count the payment you already imported.

### Table C - screenshot reads

| Device / wallet | Rows on screen | `added` | `skipped` reasons | Refs found? | `printed_at` correct? | Replay double-counted? |
|---|---|---|---|---|---|---|
| | | | | | | |

## Part D - a phone photo of a customer's screen

The path the seller actually uses at the counter, and the only one that has never been
measured. Take the photo with the *seller's* phone of the *buyer's* wallet screen showing
the PHP 1.00 payment, verify it against an order, and write down what came back.

1. Issue an order on the QR page for an amount that ends in a free centavo code.
2. Have the buyer pay it and show the wallet's own receipt/inbox screen.
3. Photograph it from the dashboard and submit.
4. Record: `status`, `message`, whether `hint` (the retake advice) came back, and the
   numbers - `forensics.ela`, `forensics.sharpness` and `confidence` in the same
   response.
5. Send that same photo through Messenger or Viber before uploading it - what the seller
   gets is a compressed copy, and compression moves these numbers.
6. Take several at different angles and in different light. Save the photos to a folder
   **outside this repo** (see Privacy below) and run the calibration script on them;
   [CALIBRATION.md](CALIBRATION.md) is the guide.

### Table D - phone photos

| Photo | Angle / light | Sent through | Verdict | ELA | Sharpness | Read confidence | Retake hint? |
|---|---|---|---|---|---|---|---|
| | | | | | | | |

## What to do with the answers

- Any Table A2 wording that returned `400` is the first bug to fix: the whole ledger feed
  depends on it, and it is the one thing no test in this repo can catch, because the
  tests use wording this file invented.
- A `packageName` that differs from the allow-list is a config change
  (`CHECKIZ_APP_PACKAGES`), not a code change.
- A reference length that differs is `CHECKIZ_REF_LENGTH`.
- Fill in the README's trust table and the "Measured so far" section **with the run
  date and the device**, and delete the sentence saying the channel is unconfirmed only
  when Table A1 says otherwise.
- Part D is what lets the forensics thresholds be stated as calibrated. Until it is
  filled, the README keeps saying they are not.

## Privacy

- PHP 1.00, from an account you control. Do not test against a stranger's payment.
- Do not commit a real screenshot, a real receipt photo, a real number, a real reference
  or a customer name to this repo - not even redacted, because redaction is easy to undo
  in a screenshot. Keep device samples in a folder outside the repo and put only masked
  wording and numbers in these tables.
- Never send those photos to a service you have not paid for and read the terms of. The
  optional AI reader is off by default for exactly this reason
  ([AI_PRIVACY.md](AI_PRIVACY.md)).
- The forwarders only read and post payment alerts, and the ledger stores the alert text
  it was given. If you stop using Checkiz, delete `CHECKIZ_DB_PATH`.
