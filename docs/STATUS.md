# Status: README claims reconciled against the code

Written 2026-10-23, last reconciled against `feat/device-and-calibration`. Suite: **197 tests passing** (`cd backend && pytest`, OCR stubbed). Rule: when this file, `README.md` and the code disagree, the code wins and both documents get fixed.

## Feature by feature

| Feature | Exists | Where | Test coverage |
|---|---|---|---|
| Receipt upload, OCR, field extraction | Yes | `backend/app/parser.py` (`run_ocr`, `parse_fields`, `locate_boxes`, `ocr_confidence`). `parse_fields` now also returns the printed `date` and `time` as strings; `app/consistency.py` decides what they mean | `test_verify.py::test_parse_fields`, `test_consistency.py::test_the_printed_date_and_time_are_read_into_the_fields` (stubbed OCR); real Tesseract verified in Docker on the synthetic samples only (once end to end, once on 2026-10-23 for the read score and the date/time fields) |
| Reference format validation | Yes | `backend/app/verify.py`, length from `config.REF_LENGTH` | `test_engine.py::test_missing_reference` |
| Replay protection (one reference, one order) | Yes | `ledger.consumed_order`, `verify.py` DUPLICATE branch | `test_engine.py::test_verified_then_duplicate`, `test_settle.py::test_one_payment_settles_one_order_only`, `test_real_receipt_cannot_be_reused_on_another_order` |
| Ledger match, late-alert resolution | Yes | `backend/app/ingest.py`, `verify.py::resolve_pending` | 3 tests in `test_engine.py`, 1 in `test_settle.py` |
| Order-bound QR Ph + centavo codes | Yes | `backend/app/qrph.py`, `qrstore.py`, `qr_orders` table | `test_qr.py` (5), `test_settle.py::test_auto_settle_without_screenshot`, `test_receipt_amount_must_match_issued_amount` |
| Alert feed: notification / SMS / paste, trust levels | Yes | `main.py` routes at lines 112, 122, 133; `CHECKIZ_APP_PACKAGES` allow-list; paste splits on blank lines | `test_engine.py`, `test_settle.py` trust tests, `test_api_key_protects_ledger` |
| `added` counts payments the ledger did not already hold | Yes | `ledger.add_entry` returns `cursor.rowcount > 0` (the insert was already `INSERT OR IGNORE`, so the information existed and was being thrown away), threaded through `ingest_alert` as `stored`; `/ledger/history-screenshot` reports `added`, `already_in_ledger` and `unmatched`, `/ledger/paste` reports `added` | `test_history.py::test_the_same_screenshot_twice_adds_one_payment`, `::test_a_payment_an_sms_already_reported_is_not_counted_again`, `::test_the_screenshot_reports_what_it_added_and_what_it_refused`. Found by the live Docker run, not by a test - see "Corrections" |
| **Transactions-screenshot fallback** (brief task 5) | Yes | `backend/app/history.py` (`scan`, `parse_history_rows`, `to_entry`, `screenshot`), `POST /ledger/history-screenshot` at `main.py:146`, ledger column `printed_at` (`db.py` migration), upload control in `frontend/index.html` | `test_history.py` (24): rows read across separate lines, money-out refused, a figure with no direction word refused, the closest-word direction rule in both directions, no sender names taken, refusals reported, `source="history"` end to end, a history payment settling a coded order while still being told to confirm in the app, `printed_at` kept apart from `received_at`, replay adds nothing (both from the same screen and against a reference an SMS already stored), 400/413/415/503, API key, and that the dashboard can reach it. **Real Tesseract run once**, on a synthetic rendered transactions screen (see "The fallback, run for real") |
| `needs_app_check` persisted, incl. the late-alert path | Yes | `verifications.needs_app_check`, `verify.py:49`, `ingest.py` | `test_settle.py::test_sms_only_large_payment_needs_app_check`, `test_app_sourced_large_payment_needs_no_extra_check`, `test_review.py::test_late_sms_match_is_queued_for_app_check` |
| Review queue, acknowledge + reopen | Yes | `backend/app/review.py`, `GET /review`, `POST /review/{id}` | 8 tests in `test_review.py` |
| Packing list CSV, formula-injection neutralised | Yes | `backend/app/report.py`, `GET /orders/packing.csv` | `test_review.py::test_packing_csv_*` (2) |
| Per-order evidence timeline | Yes | `report.evidence`, `GET /orders/{id}/evidence` | `test_review.py::test_evidence_timeline_keeps_alert_text_out` |
| ELA + sharpness check | Yes, but **not separating the sample pair** | `backend/app/forensics.py` | Flag behaviour is tested; detection quality is not, and cannot be with synthetic samples |
| Dashboard, order board, OBS overlay | Yes | `frontend/index.html`, `overlay.html`, served by the API itself | No UI harness; but `test_serving.py` proves every page and helper is actually served and that all three load `api.js`. Panel rendering is still only looked at by hand |
| **Camera capture** | **Yes - README said Planned** | `frontend/camera.js` (getUserMedia + `<input capture>` fallback), wired at `index.html` and `qr.html` | 25 assertions executed in Node against a stubbed window: every refusal reason, the 0x0 startup race, live QR, and the no-`BarcodeDetector` path - three guards then mutated to confirm each one is load-bearing. **No real phone yet**, and the in-app browser here cannot grant camera permission at all |
| Pages served from the API origin | Yes | `main.py` `frontend_dir()` and the `StaticFiles` mount at `main.py:325`, mounted after every route | `test_serving.py` (17): root, three pages, two helpers, an API route beating the catch-all, `/health` reporting `ui`, and that the pages actually call `checkizKey` |
| The API key is remembered for the tab and reloads the page | Yes | `api.js:checkizKey()` (`sessionStorage`, not `localStorage`), wired in `index.html` before its first request and in `qr.html` before `loadSeller()`; the overlay is untouched because it takes `?key=` | 17 assertions executed in Node against a stubbed DOM (restore, never overwrite what is typed, save, remove when cleared, one debounced reload per burst of keystrokes, survives blocked storage, no-ops with no box) plus the two page wirings; six mutations, each breaking its own assertion. One of them (`test_serving.py::test_the_api_key_box_is_wired_to_remember_and_reload`) is in the repo so a page cannot quietly stop using the helper. Then re-run in a real browser - see "The key box that remembered nothing" |
| One rule for where the API is, and a real reason when a request fails | Yes | `frontend/api.js` - `CHECKIZ_API` (`?api=` > own origin > `localhost:8000`), `checkizProblem`, `checkizIsUnreachable`, `checkizWho`, `checkizDownload` | 50 assertions executed in Node against the file as it stands, with a stubbed `location`/`fetch`/`document`/`URL`, plus the dashboard's own `checkServer()` run the same way. Mutating away the same-origin rule, the foreign-server branch, the late revoke and the `"ocr" in h` guard each breaks its own assertion. The harness is not in the repo, so re-checking it means a browser or someone checking it in as a real UI test |
| `CHECKIZ_DB_PATH`, so two instances do not share one file | Yes | `db.py:_db_path()` | 4 of the 17 in `test_serving.py` (override, relative and `~` forms, the default, and that the pointed-at file is the one created) |
| **The server says when it cannot read receipts at all** | Yes | `parser.ocr_engine()` (one cached probe), `/health`'s `ocr`, a startup warning, `HTTP 503` on `/verify`, and a banner on the dashboard before the first upload | `test_no_ocr.py` (13): the probe's three answers and its caching, `/health` with and without an engine, the 503 carrying no verdict and writing no history row, the 422 for a blank order, the test that a **stubbed** reader still gets verdicts on a machine with no Tesseract, and two that the dashboard only warns when the server actually reports `ocr: null`. Reproduced live on :8000, then fixed, then reproduced as 503 - see "A server that could not read anything" |
| Retake hint on a poor photo | Yes | `parser.ocr_confidence` averages Tesseract's per-word scores; `verify.retake_hint` turns a score under `config.OCR_CONFIDENCE_MIN` into `hint` on the verdict, shown in the dashboard banner. `confidence` is on every verdict response; the hint is not stored | `test_confidence.py` (22): the average and each half of its row filter, a blank page as `None`, the floor as config, and four engine tests that pin the status while the hint appears. The **floor** has never been measured on a phone photo - see "Photo quality" |
| Startup warnings when `CHECKIZ_API_KEY` is unset or no Tesseract is installed | Yes | `main.py:49` | The API-key warning is not asserted by a test. The Tesseract one is only reached through `ocr_engine()`, which is tested; the printed line itself was observed in the server log, not asserted |
| `/health` | Yes | `main.py:80`, answering `ok`, `name`, `ui` and `ocr` | `test_serving.py::test_health_names_the_server_so_a_page_can_tell_it_apart`, `test_no_ocr.py` for `ocr`, plus the API smoke test |
| Plain-language verdict `label` field | Yes | `backend/app/labels.py`; `label` on every verdict response, late-alert resolution, auto-settlement result, history row, review item and evidence event; `verifications.label` column with migration; `/stats` also returns `by_label`; shown in `index.html` and `overlay.html`. Upload rejections (415/413) are HTTP errors and carry no verdict | `test_labels.py` (19). Status codes are unchanged and still asserted |
| Buyer pay page (`/pay/{order_id}`, `qr.png`, `pay.html`) | **No** | - | Brief Step 0 lists it; README claimed it Built |
| `docs/DEVICE_TEST.md` (brief task 5's protocol) | **Yes, and every table in it is empty** | Four parts: A observes which channels a PHP 1.00 payment actually arrives on (`termux-sms-list`, `termux-notification-list` for the package name), B posts that wording into `/ledger/sms` and `/ledger/notification`, C runs the screenshot fallback, D uploads a phone photo of a customer's screen. Privacy section: PHP 1.00 only, no real screenshot or reference committed, samples kept outside the repo | Not testable here, and not claimed: **nobody has run it**. The file opens by saying so. `test_history.py::test_the_dashboard_can_upload_a_transactions_screen` only proves the fallback is reachable from the page |
| `docs/CALIBRATION.md` + `backend/calibrate.py` (brief task 6) | Yes | The guide says what to collect (5+ per group, including the phone-photo and Messenger/Viber-compressed copies), where to run the script (the Docker image, because this machine has no Tesseract), and the rule that a threshold is only proposed at n>=3 per group **and** real separation. `calibrate.py` gained `--markdown` (the README-shaped table), `--at ELA SHARPNESS` (false alarms / caught / missed, as counts with the file names), a no-engine guard that exits 2, and `no boxes` instead of a flattering `0.00` | No test covers the script itself. It has been run - see "Calibration: what the script has actually measured" - but only on the two shipped synthetic samples, which is n=1 per group and therefore prints no threshold |
| Scripted demo (`backend/demo.py`) | **No** | - | README's "Getting started" references a file that does not exist |
| Exact-file reuse check (SHA-256 of the upload) | Yes | `backend/app/fingerprint.py`, `verifications.sha256` + index, runs before the reference gate in `verify.py` | `test_fingerprint.py` (7), incl. the limits pinned below |
| Image perceptual hash (dHash) | **No - measured and rejected** | - | See "Perceptual hash: the measurement" below |
| Alert-free consistency checks | Yes, as **signals only** | `backend/app/consistency.py` (4 pure checks), collected in `verify._verify`, returned as `signals` on every verdict, stored in `verifications.signals` (+ `printed_at`), shown in the dashboard banner, review queue, evidence timeline and as a count on the overlay. Every threshold is a config value | `test_consistency.py` (50): each check on its own, then the same verdict with and without a signal, storage, and the legacy-row path. **No real receipt has been through them** - see "Signals: what was decided and why" |
| AI-assisted reader, `eval/run_eval.py`, `docs/AI_EVAL.md` | **No** | - | Brief task 7, gated and last priority |
| Staff mode, PINs, `/reconcile/daily` | **No** | - | Explicitly Deferred in the brief |

## Corrections made while reconciling

- **Camera capture was under-claimed** as Planned in the README and in the roadmap. It is built and used by two pages. The gap it left - the "retake for a clearer photo" hint, which needed an OCR confidence signal the parser did not produce - is now closed: `parser.ocr_confidence` supplies the number and the hint rides on the verdict.
- **The buyer pay page was over-claimed** as Built. It is Planned until someone builds it; nothing in `main.py` or `frontend/` serves it.
- **`backend/demo.py` does not exist**, so the README's scripted-demo command would fail on a clean checkout.
- Two source links in the README could not be verified as written: the Mynt notice is at `newsroom/...` (`news-draft/...` returns 404), and BDO plus one Inquirer link are unreachable from here (connection failure and 403). They are marked as unverified rather than silently kept.
- The README linked `[Status](#status)`, which has no matching heading. Now points at this file.
- Two STATUS rows attributed engine tests to `test_verify.py`, which holds only the three parse tests. Corrected against the actual test files.
- Verdict labels (brief task 1) are built. One mapping decision is not spelled out by the brief: `SUSPECTED_FAKE` is also returned for an unreadable image or a missing reference, and those are labelled "Can't confirm yet" rather than "Likely edited", because nothing was contradicted. The README's verdict table was rewritten to match, and the messages under the label still say what to do.
- The label wording was checked by rendering `index.html` and `overlay.html` against a throwaway database holding one verdict per label (2026-10-23, local servers, seeded rows rather than real OCR - Tesseract is not installed on this machine). That is a manual look, not a test: the UI still has no automated coverage.
- Two UI strings still named GCash/Maya as if the tool were limited to them (the dashboard subtitle and the QR registration hint). Reworded; the alert-text placeholder keeps its GCash example because it is an example.
- Two README sentences said the receipt parser reads only a reference and an amount ("there is no time field yet", and the same claim in the AI section as something a model would have to prove). Both became false the moment the consistency checks needed a printed time: `parse_fields` now returns `date` and `time`. The AI paragraph now claims only what is left - that a model has to prove it reads a glare-covered phone photo better.
- **"Receipt upload and OCR extraction | Built, tested"** read as though the parsing itself were tested. It is not: every test stubs the reader, because Tesseract is not installed on this machine. The row now says tested with the OCR stubbed and names where real Tesseract was actually run (the Docker image, the synthetic samples).
- **"the Docker build"** was listed under what no test covers. It has now been run once for the path this round changed - `docker build`, `docker run -p 8123:8000`, `/health` reporting `ocr: "5.5.0"`, `GET /` serving the dashboard, and one real upload returning `VERIFIED`. Removed from that list and recorded in "A server that could not read anything". It is one run on synthetic data, not a Docker test suite.
- **`added` counted rows the parser read, not rows the ledger gained.** The first live upload of a transactions screen answered `{"added": 2, ...}` when one of the two references was already in the ledger as an SMS - and the stored row kept `source: "sms"`, while the response echoed `source: "history"` for it. A seller reading "2 payments" would think a re-screenshot was a second payment. `INSERT OR IGNORE` already knew the difference (`rowcount` 0 vs 1) and `add_entry` threw it away. Now `added` counts new rows only, the repeats are named in `already_in_ledger`, and `/ledger/paste` uses the same honest number. Two tests pin it, and both were written after the live run showed the wrong answer.
- **A 0-byte upload crashed `/verify` with a 500.** `cv2.imdecode` returns None for junk bytes but *raises* `(-215:Assertion failed) !buf.empty()` on an empty buffer, so the one input shape the guard did not cover was the one a truncated camera capture or a dropped file produces. Found by writing the fallback's "not a picture" test first: it failed with a 500 traceback. `parser.load_image` now returns None for empty bytes, `/verify` answers its existing "Unreadable image" verdict, and the screenshot endpoint answers 415. Two tests for `load_image`, one for each endpoint.
- **A direction test that passed for the wrong reason.** With the money-out guard deleted entirely, all 19 tests still passed: the `Sent PHP 500.00` row was being refused by the *no-direction-word* guard, so nothing asserted that outgoing money is excluded on purpose. The rule was rewritten to the closest direction word in the row's window, the test text was given a wallet word so only the direction guard can refuse it, and two more tests were added (a payment listed next to an outgoing row, and a tie). Removing the guard then failed 5 tests.
- **`docs/DEVICE_TEST.md` was recorded here as not existing** while README referenced it twice. It exists now, and its tables are empty; the row above says which is claimed and which is not.
- **A defect was reported to the owner from reading the code, and half of it was wrong.** The claim was that the dashboard's key box "is dead until you click something". The box was indeed not remembered anywhere, but the dashboard refetches every panel every 5 seconds (`index.html`'s `setInterval`), so a typed key *did* fill the tables on its own. Reading `hdr()` and the absence of a change handler, and not reading past line 310, produced a confident wrong half. What the browser run actually showed: the QR page said "Invalid or missing API key" at open and retried nothing, and any reload or page switch lost the key. Both are in "The key box that remembered nothing", along with the assertion that would have caught the wrong half earlier.

## The fallback, run for real

The suite stubs the reader, so the row parser had only ever seen text typed by hand. It was run against real Tesseract 5.5.0 in the Docker image on 2026-10-23, on a **synthetic** screen: `/tmp/mk_transactions_screen.py` (Pillow, not in the repo) drew a 720x900 "Transactions" list with three rows - Received PHP 1,250.00 / ref 1002 849 130490, Sent PHP 500.00 / ref 1002 849 130491, Received PHP 150.37 / ref 1002 849 130492 - and the PNG was posted to `POST /ledger/history-screenshot` over HTTP. No wallet produced this image and it is not a wallet's layout; what it proves is that the parser works on text that came out of an OCR engine rather than out of a test.

What Tesseract handed back and what the parser did with it, from the first response (fresh container database, so `seed.py` had already stored the 1,250.00 reference as an SMS alert):

```
added 1
already_in_ledger ['1002849130490']
unmatched ['1002849130490', '1002849130492']
skipped [('money out', 500.0)]
```

- The reference the engine read was **grouped, not contiguous** - `"Ref No. 1002 849 130491"` - and the raw string stored with the refused row shows it verbatim. The reader splits digit groups, so grouping is not a problem for this path. Worth knowing because the grouped form is what a real wallet prints.
- The outgoing row was refused for the right reason and reported, not silently dropped. `PHP 150.37` became one new ledger row with `source: "history"`, and `GET /ledger` showed its printed time kept separate from the server's clock: `1002849130492 history 150.37 'Oct 21, 2026 18:41 PM'`.
- Both received amounts are listed `unmatched` because the seeded mock orders do not carry those centavo codes. That is the correct answer, not a gap: a payment with no order of its own is stored and waits.
- Uploading the same screenshot again answered `added 0 already ['1002849130490', '1002849130492']` - the replay adds nothing.
- The same file posted with no `X-API-Key` answered **401**.

Before the `added` fix above, this same run answered `added: 2` on a database that already held one of the two references, which is how the overstatement was caught. A second live run against a container that was still writing into the gitignored `backend/checkiz.db` (the mount was read-write) showed `already_in_ledger` reporting both and the stored 1,250.00 row keeping `source: "sms"`; that row was deleted afterwards and the file left with its 4 seeded rows. The third run used `-e CHECKIZ_DB_PATH=/tmp/live.db` with the backend mounted `:ro`, which is the way to do this without touching a host database.

## The key box that remembered nothing

The owner asked for a live run in an external browser, so the demo server was started with `CHECKIZ_API_KEY` set - the configuration the docs recommend. Two things fell out of it, both observed in a browser rather than inferred:

- The QR page said **"Invalid or missing API key"** at open and never asked again. `qr.html` calls `loadSeller()` once, at the bottom of the script, and the key box was empty at that moment because nothing carried it over from the dashboard. The seller's own QR section sat on that sentence until some other action happened to retry it.
- The key lived only in the box. Reload the dashboard, or walk to the QR page, and it was gone - so on a keyed server the secret gets retyped per page and per refresh.

What was **not** true: the dashboard's box being dead. It refetches every panel every 5 seconds, so a typed key filled the tables on its own; the interval was invisible to me until I looked at what the browser actually did. See the corrections bullet above.

The fix is `checkizKey(onChange)` in `api.js`, called before each page's first request: it puts a key remembered in this tab into the box, saves what is typed, and tells the page to reload its data. Three decisions worth stating:

- **`sessionStorage`, not `localStorage`.** Closing the tab forgets the secret. A shop till is often shared, and a key that survives the browser session is a key someone else can read from the box tomorrow. The repo test asserts `localStorage.getItem`/`setItem` never appear.
- **Debounced at 400 ms.** The obvious wiring reloads on every `input` event, which is four requests per keystroke - twenty keystrokes is eighty requests before the seller finishes pasting.
- **The overlay is left alone.** It has no box; it takes `?key=` in the OBS URL, which is the only way an OBS browser source can be configured.

Executed, in a real browser against a fresh origin (`http://localhost:8081`, same image): before, `key: ""`, `stored: null`, `ledger: 0` rows. After typing the key, `sessionStorage` held it and the panels reloaded off the 5-second grid (a burst 31 ms after the interval's own batch, which is the handler, not the timer). Reloading the same tab: `key: "demotest"` already in the box and the ledger's 2 rows already drawn, no 401 banner. Then `qr.html` in the same tab: **"No QR registered yet."** - a real answer from the keyed API - where it used to say the key was missing.

The harness ran 17 assertions and six mutations. The first pass at it had a decorative assertion: deleting `if (!box) return;` broke nothing, because the stub's `getElementById` handed back a box even in the "no box on the page" case. Fixed the stub, and that mutation now fails with *"Cannot read properties of null (reading 'addEventListener')"* - the same class of hole as the direction test above, found the same way.

Re-run after the commit, against a freshly built image on `:8082` so no cached script could be involved, and this time the whole path a seller walks was watched rather than only the key box: at open, `checkizKey` was a loaded function, the box empty, nothing stored, and the 401 banner naming the address. Typing the key stored it and drew the ledger's 2 seeded rows with no click. Reloading: the box already held it and the tables were full before anything was touched. Walking to `qr.html` in the same tab: it carried over, and the section that used to read "Invalid or missing API key" read "No QR registered yet." With the storage cleared and the page reopened, the QR page did show the missing-key error - and typing the key retried it on its own, which is the half the reload test cannot show. Then `samples/real.png` answered **Verified** against the seeded alert (ELA 5.78, sharpness 4.08, 1703 ms, two signals listed without changing the verdict), `samples/edited.png` on another order answered **Reused** on the reference with `ELA -`, the transactions screen added 1 and named the 1 it already had and the 1 money-out row it refused, and the evidence timeline and "reviewed" button both worked through the keyed API. Console: one 401, the deliberate one.

The camera is still the one part of this page that nothing here can exercise. It was not re-tested in this run: the browser this was driven from cannot grant camera permission at all - recorded under the camera row above - and there is no phone attached.

## Calibration: what the script has actually measured

Brief task 6 says do not invent numbers, so the record of what exists is short. The rewritten `calibrate.py` was run in the Docker image against the only receipts in this repo - the two synthetic samples in `samples/`, one clean and one with the amount redrawn - on 2026-10-23. The date the script prints is the container's UTC date, 2026-10-22. What follows is its output, with the two long suggestion lines re-wrapped for width and the six `summary()` lines between them left out:

```
# Tesseract 5.5.0  run 2026-10-22  thresholds ELA > 8.0, sharpness > 6.0  retake floor 60.0  n real=1 edited=1
file=real.png   ref=1002849130490  amount=1250.0  ela=5.78  sharp=4.08  read=94.5  boxes=4  ms=738
file=edited.png ref=1002849130490  amount=9250.0  ela=5.82  sharp=4.08  read=94.6  boxes=4  ms=635

CHECKIZ_ELA_THRESHOLD: n=1/1 is too few to set a threshold on. The groups do not overlap here
(real max 5.78 < edited min 5.82), but two samples that happen to differ is not a signal -
measure more before changing it.

CHECKIZ_SHARPNESS_THRESHOLD: n=1/1 is too few to set a threshold on. They overlap (real max
4.08 >= edited min 4.08), and with this few samples even that is not yet a conclusion.
```

So the ELA groups are 0.04 apart and the sharpness groups are identical - on a pair of images one script drew. Pointing `--at 5.8 4.09` at them reports "false alarms: 0 of 1, caught: 1 of 1, missed: 0 of 1", which is exactly the number that must not go in the README: one clean page and one redrawn page cannot tell you a rate, and a threshold placed 0.02 under a single genuine reading is a coin flip. The script refuses to suggest one at n<3 per group, and the refusal is the output.

Nothing else has been measured. `samples_real/` and `samples_edited/` do not exist, no genuine receipt has been through the forensics, `docs/CALIBRATION_RESULTS.md` has not been written, and the README keeps "the forensic check did not separate the two". The guide's job is to make the next run produce a table that can replace that sentence; until someone collects samples, the sentence stays.


## Perceptual hash: the measurement that killed it

Brief task 2 asked for a dHash so a repeat could be caught even when OCR misreads
the reference. Measured on 2026-10-23 with the synthetic receipts in `samples/`
(same template, differing only in digits, which is what real receipts look like),
16x16 grid = 256 bits:

| Variant | Distance |
|---|---|
| same file, re-encoded JPEG q80 | 5 (2.0%) |
| same file, scaled to 75% | 1 (0.4%) |
| same file, 1% border crop | 12 (4.7%) |
| same file, 1px blur | 2 (0.8%) |
| **different** receipt, one reference digit changed | 0 (0.0%) |
| **different** receipt, several reference digits changed | 1 (0.4%) |
| same receipt photographed at an angle / with glare | 39-57 (15-22%) |

There is no usable threshold: a different payment of the same amount is *closer*
to another receipt than a re-saved copy is to its own original. Repeating the test
at 32x32 and 64x64 kept the overlap (at 64x64: re-encode 17 bits vs different
reference 6-21 bits, out of 4096). And the case that matters most in the field - a
phone photo of a screen - is 15-22% apart, so it would not be caught anyway.

Shipping it would label genuine payments "Reused". So it is not built. What is
built is the one comparison with no false positives: the identical file, byte for
byte, arriving again for another order (`SHA-256`), which still works when OCR
reads nothing. Its limit is re-encoded copies, and `test_fingerprint.py` pins that
behaviour instead of hiding it.

## Re-running the sample generator changes the samples

`make_samples.py` writes pixels that depend on the fonts installed (it tries
DejaVuSans, then Arial, then Pillow's default bitmap font). Regenerating
`samples/real.png` and `samples/edited.png` on this machine changed 8.4% and 7.8%
of the pixels, which is enough to move the ELA and sharpness numbers in the README
table. The committed files are what those numbers were measured on; if someone
regenerates them, the measured table has to be re-run and re-stated.

## Signals: what was decided and why

Brief task 3 asked for consistency checks that need no alert, "labelled as signals,
not proof". Four things had to be decided, and each one changed what the check can
honestly claim:

- **A reference-length check would have been dead code.** `REF_RE` is built from
  `config.REF_LENGTH`, so a reference the parser returns always has the expected
  length and the check could never fire. It now also does the looser look
  (`REF_RUN_RE`, 8-20 digit runs) and reports the closest number when no reference
  was found at all: *"No 13-digit reference found; the closest number read was
  100284913049, 12 digits"*. That is the message a seller can act on, and it fires
  on the real path - including when OCR mistakes a phone number for a reference.
- **`PHP` and `₱` are not amount labels.** The amount regex only matches a number
  that already carries a currency token, so counting the token as the label makes
  the layout check pass on every receipt and measure nothing. The default label
  list is field words (`amount`, `total`, `paid`, ...). Consequence, stated plainly:
  a receipt that prints `PHP 500.00` with no field word raises a signal. Shops that
  see that as noise add the token to `CHECKIZ_AMOUNT_LABELS`.
- **A time with no date is not checked.** `20:05` could be ten minutes ago or last
  night. A date with no time is compared in whole days, so a 48-hour window does
  not fire on a receipt dated yesterday.
- **The clock is not UTC.** Receipts carry wall-clock time; comparing them with a
  UTC server clock reports about 8 hours of age on every receipt. `CHECKIZ_TZ_OFFSET_HOURS`
  (default 8) is the shop's own clock, and a 30-minute future tolerance absorbs the
  gap between a buyer's phone and the seller's machine.

Three more things worth recording:

- The checks cannot change a status, and that is enforced by the old suite: making
  a signal override the verdict fails **35 tests, 27 of them pre-existing** (`test_engine.py`,
  `test_settle.py`, `test_review.py`, `test_labels.py`, `test_qr.py`, `test_fingerprint.py`) -
  the rules the alerts feed were already asserting. Turning one check off on its own
  fails 2-9 tests (reference format 2, printed time 3, the near-miss look 4, layout 7,
  the aggregate 9, persisting them 5), so none of them is decoration. Each number above
  is a run, not an estimate, and the tree was restored afterwards.
- One engine test failed the first time it ran in the afternoon and passed in the
  morning: it stamped a fixed date on the receipt and compared it against the
  machine's real clock. Engine tests that read a stamped receipt now pin
  `consistency.shop_now`. Any future test that forgets to will be time-dependent.
- The four example messages in the README's signals table are the strings the code
  actually returns, printed by calling the four checks with those inputs rather
  than written by hand. The clock is asserted in both directions through the engine:
  a stale stamp (`test_the_receipts_own_clock_is_checked_against_the_shops`) and a
  stamp later than this clock (`test_a_stamp_from_later_today_does_not_change_the_verdict`),
  each with the status pinned as well as the reason.

The dashboard banner, review queue, evidence panel and overlay count were then
looked at in a browser against a throwaway database with OCR stubbed (2026-10-23,
`/tmp` database, port 8013) - a receipt stamped 08:05 while the machine read 04:49
rendered as *"Can't confirm yet / Receipt says 2026-10-23 08:05 AM / ⓘ One thing to
check / • Receipt shows 2026-10-23 08:05 AM, later than this clock"*. That is a
manual look at the wording and layout, not a test.

What is **not** known: whether any of these thresholds is right. The amount range,
the 48-hour window and the label words have never been run against a genuine
receipt, and no wallet's real receipt template is in this repo. They are plausible
defaults until task 5 (real-device alert wording) and task 6 (calibration) replace
them with measured ones.

## Photo quality: the one number that is allowed to say "retake"

Brief task 4 asked for a "retake for a clearer photo" hint when OCR confidence is
low. Tesseract already scores every word it returns, so the engine only had to
average those scores and be honest about what the average means:

- `parser.ocr_confidence` averages only the rows that are both a word and scored.
  Measured on `samples/real.png` under the Docker Tesseract: 44 rows back, 20 of
  them structure with no text and `conf` -1. Averaging all 44 gives **51.1**; the
  words alone give **94.5**. With the unfiltered mean, every clean photo of every
  real receipt would sit under the floor of 60 and be told to retake. A blank page
  returns `None`, not 0, for the same reason - no advice is the honest answer about
  a picture the reader never saw, and it is also why the stubbed OCR in the other
  test files (boxes with no score column) cannot grow an advice line.
- The hint is a separate response field (`hint`), never a signal and never a
  status. `confidence` is on every verdict, the hint only when there is one, and
  neither is stored: they describe one attempt at one photo, useful only while the
  cashier still holds the phone. Letting the score change the verdict fails 5 tests
  (the only ones that read a scored photo), and each half of the row filter above
  has its own test that fails if it is dropped.
- Measured with the Docker image's Tesseract 5.5.0 on the two shipped samples
  (2026-10-23): `real.png` read **94.5** over 24 words (min 85), `edited.png`
  **94.6** (min 85). Both are far above the floor of 60, and **the edited copy
  scored a fraction higher than the real one** - which is the point: this number
  measures legibility, and using it as evidence about authenticity would be a
  fabrication. The same run extracted `Oct 22, 2026` and `10:14 AM` from real OCR
  rather than a stub, so the date/time fields added for task 3 now have one
  non-stub observation behind them, on synthetic pages.
- Not measured: a phone photo of a wallet screen, in glare, at an angle. The floor
  of 60 sits below everything this repo has actually observed and is otherwise a
  guess; task 6 owns replacing it with a measured threshold.

The banner was looked at in the browser against a throwaway `/tmp` database with
OCR stubbed at 34/100 (2026-10-23, port 8014): the verdict stayed `Reused`, and the
hint rendered as its own dark box between the message and the signals -
*"📷 Retake for a clearer photo: this one read at 34/100. Fill the frame with the
receipt, hold the screen square to the camera, and tilt it away from glare."* The
screenshot tool was unavailable in the in-app browser this time, so the check was
the rendered DOM text plus the computed style (`display:block`, `8px 10px` padding,
`rgba(0,0,0,.22)` on the banner colour), not a picture.

## The runtime round: what broke when the pages were actually opened

The owner reported two bugs - "the redirect does not work (pages fail to load)" and "the
camera feature is not working". Both were real, and the first was not one bug:

- **Port 8000 belonged to another project.** Two dev servers for Vitalsort were listening
  on 8000 and 8001. Checkiz's dashboard defaulted to `http://localhost:8000`, so every
  request reached *that* server: `POST /verify` answered 501, `GET /history` answered 404
  with HTML. The page said "Can't reach the API" while something was answering - the
  message was wrong, and unverifiable from the seller's side. The owner was asked, agreed
  to free the ports, and the two processes were stopped; 8000 and 8001 are Checkiz's again.
  Restarting them is `python3 -m http.server 8000` in `Vitalsort-App/frontend` and
  `python3 -m uvicorn main:app --port 8001 --ws websockets` in `Vitalsort-App/backend`.
- **The API never served the UI.** `docker run -p 8000:8000 checkiz` contained no pages at
  all, so a dashboard required a second web server, and `index.html` ↔ `qr.html` links only
  worked if that server happened to be running. That is the "page fails to load" half.
- **`qr.html` hardcoded `http://localhost:8000`**, with no `?api=` escape like the other pages.
- **The QR download could not work.** `/qr/generate` returns the PNG as a `data:` URL and the
  page put that straight into `<a download>`, which Chrome and Safari refuse. The button
  looked dead.
- **The camera helper failed silently.** `.catch(fallback)` reported nothing; the fallback
  `<input>` was never attached to the document; and Capture could fire while the `<video>`
  was still 0x0, handing over a blank photo the server then called unreadable.

Fixes, in the order a seller meets them: the backend serves `frontend/` itself
(`main.py:325`, mounted after every API route), so there is one origin and no second
server; `frontend/api.js` gives all three pages the same rule for finding the API and turns
every failure into a sentence that names the address, the HTTP status, the content type and
the likely cause, backed by `/health` now answering `{"ok": true, "name": "checkiz",
"ui": true}` so a page can say *which* server it reached; a failed `/verify` shows
**"Not checked"** in the amber class instead of painting the banner red, because a
connection problem is not a suspected fake; the QR page downloads through a Blob rather
than a `data:` link; `camera.js` states the reason (https-or-localhost, permission refused,
another app holding the camera, no rear camera, an unnamed failure quoting its own name),
waits for a real frame size, and attaches the native picker before clicking it;
`CHECKIZ_DB_PATH` lets a second instance have its own file.

What was executed, and where it stops:

- **157 pytest**, 16 of them new in `tests/test_serving.py`. They fail if the mount goes
  before the API routes, if `frontend/` is not copied into the image, if a page stops
  loading `api.js`, or if `_db_path()` stops honouring the environment.
- The three pages and both helpers were fetched over HTTP from a running server
  (`GET /`, `/qr.html`, `/overlay.html`, `/api.js` → 200 with the expected content types;
  `/docs` still FastAPI's; an unknown path 404s as JSON), and `/review` returned live data.
- `api.js` and `camera.js` were then run in Node against a stubbed `location` / `fetch` /
  `document` / `URL` - **22 and 25 assertions, all passing** - and four guards were mutated
  away (the same-origin rule, the foreign-server branch, the late revoke, the 0x0 wait) to
  confirm each one breaks its own assertion rather than passing by accident. That harness is
  **not in the repo**: it lives in this session only, so re-verification needs a browser or
  someone checking it in as a real UI test. (The `api.js` half was re-run against the current
  file the next round and grew to 50 assertions - see "A server that could not read anything".)
- **Not done: no click-through.** Browser navigation was blocked in this environment, so the
  dashboard's panels, the packing download, the QR button and the camera prompt have not
  been pressed in a real page this round - and the camera has never been tried on a phone,
  which is the only place the new reason messages will show what they are for.

## A server that could not read anything, and the wrong accusation it caused

The same run that found the port clash found a second, worse pair of defects - one in
the backend, one in my own frontend message. Both reproduced against the live server on
`:8000`, not from reading code.

- **`POST /verify` answered 500 text/plain "Internal Server Error".** This machine has no
  Tesseract, so `run_ocr` raised `pytesseract.TesseractNotFoundError` inside the engine,
  which reached the client as an unhandled crash. The seller saw a red banner about their
  photo for a fact about the server.
- **`checkizProblem` then said "Something else is listening on that port".** A 500 from
  Checkiz arrives as `text/plain`, which is the same shape as a reply from some other
  program, and the message drew the wrong conclusion from it. Checkiz's own crash was
  reported as a stranger squatting on the port - while the stranger diagnosis is exactly
  what `/health` exists to settle.

What changed:

- `parser.ocr_engine()` probes once and caches, returning the version string or `None`. It
  costs a subprocess, so it is not called per upload; a test that calls it five times
  asserts the probe ran once.
- `/health` answers `ocr`. A server with no engine is still a healthy, reachable server, so
  the route stays 200 and the field goes null.
- The dashboard reads it before the first upload: *"This server cannot read any receipt
  yet."* `checkServer()` only touches the banner, and a server that does not answer leaves
  it hidden, because the tables already report that.
- `/verify` catches `TesseractNotFoundError` and answers **503 JSON** naming Tesseract,
  saying *"Nothing about this photo was checked"*. It is caught where the engine actually
  fails, not at the door: an up-front "this machine has no Tesseract, refuse everything"
  check would break the stubbed-OCR suite, which is the only reason the verdict rules are
  testable here at all. One test pins exactly that - no engine, stubbed reader, still
  `VERIFIED`.
- Nothing is written. The 503 has no `status` or `label` and `/history` stays empty, so an
  unread photo cannot become a fake-receipt row. `log_verdict` runs after `_verify`, so
  this falls out of the existing order rather than needing a guard.
- `main.py` also refuses a blank `order_id` with **422** before spending an OCR pass: with no
  order there is nothing to reconcile against and the row would be unfindable. (Observed
  while testing: curl drops an all-whitespace form field, so the request FastAPI rejected
  came back as its own "Field required" 422, not my sentence. Both are 422 JSON; the
  pytest asserts my message by sending the field blank, which is what a browser does.)
- `checkizProblem` now states only what a response proves - address, status, content type,
  and that it was not the JSON expected. The *who is answering* conclusion moved into
  `checkizWho`, which is the only call that can make it.
- `checkizWho` gained a third answer. The harness assertion that expected a 500-on-`/health`
  response to still be recognised as Checkiz failed, and the reason was a real bug rather
  than a wrong test: `main`'s `/health` is `{"ok": true}` with no `name`, so this branch's
  pages tell a genuine Checkiz running one branch behind that *"another program is holding
  that port"*. It now says that server is Checkiz from before `/health` named itself.

- The dashboard made the *same* mistake one layer up, caught while re-reading the diff
  rather than by any test: `$("ocr").hidden = !!h.ocr` shows "Tesseract is not installed on
  that machine" for a server that simply has no `ocr` field - which is what `main` answers.
  A working machine would have been accused of a fault it never reported. It now warns only
  on `ocr: null`, and says nothing otherwise.

Executed: **170 pytest**, 13 new in `tests/test_no_ocr.py`. Three mutation runs, each
restored afterwards: removing the 503 guard fails 2 tests; removing the `ocr` field, the
probe cache and the 422 guard in one pass fails 5 (`ocr` field 3, cache 1, 422 1); reverting
the banner to `!!h.ocr` fails the one test that pins it. **50 assertions** in the Node
harness, against the current `api.js` re-read from disk each time, including the dashboard's
own `checkServer()` extracted and run against six stubbed `/health` answers (engine present,
`ocr: null`, an empty version string, the field absent, main's `{"ok": true}`, server gone).
Live on `:8000` after restarting the server:
`/health` → `{"ok":true,"name":"checkiz","ui":true,"ocr":null}`, `samples/real.png` →
**503 application/json** with the Tesseract sentence, `/history` → `[]`. The startup log
carries both warnings (they need `PYTHONUNBUFFERED=1` to appear before the first request
flushes stdout - observed both ways).

The same round retired the "Docker build untested" gap, at least for the path this fix is
about. `docker build` then `docker run -p 8123:8000` gave: `/health` →
`{"ok":true,"name":"checkiz","ui":true,"ocr":"5.5.0"}` (the field reports a real engine, so
the null on this machine is the absence and not a broken probe), `GET /` → 200 `text/html`
(the pages are in the image and served by the API, so `docker run` alone is a working
dashboard), and `samples/real.png` uploaded over HTTP → **200 `VERIFIED`** through real
Tesseract 5.5.0, reading `1250.00` / `1002849130490` / `Oct 22, 2026` / `10:14 AM` at
confidence 94.5 in 665 ms. That is the synthetic sample against the seeded mock ledger, so
it verifies the plumbing end to end - it says nothing about a wallet's receipt, and the two
layout signals it raised ("no reference label beside it", "no amount label beside it") are
the sample's own wording, which is the calibration gap in "Signals" above, not a new bug.

## What no test covers

The UI's rendering (the verdict panels have still only been looked at by hand), the two Termux forwarders, real Tesseract behaviour (the samples and one synthetic transactions screen have been put through it by hand in Docker; every test stubs the reader), the consistency thresholds and the confidence floor against genuine receipts, and anything requiring a wallet's actual alert wording. The 197 tests exercise verdict logic with stubbed OCR and hand-written alert text, so they prove the rules, not the parsing of a real provider.

Three things this round added and still does not cover:

- **`calibrate.py` is not tested at all.** Its guards are the ones that matter - no Tesseract, no samples, no boxes, n<3 - and each was only ever checked by running it and reading what it printed. A future edit can make it invent a threshold and no test would notice.
- **`docs/DEVICE_TEST.md` has no results in it.** Every table is empty because nobody has run the protocol, and nothing in the file is an observation. The parser tests use alert text written to match an assumption about what a wallet says.
- **The screenshot fallback has been run on one synthetic screen, once.** Not on a wallet's Transactions list, not on a phone photo of a screen, not on a crooked or scrolled list, and not on a screen whose rows have a balance column beside the amount - which is the shape `test_a_balance_column_does_not_beat_the_amount` only guesses at.

## Two things the live run found that are not fixed

The pages and `api.js` are served with `ETag` and `Last-Modified` but **no `Cache-Control`**. Chrome then keeps running the copy it already has: during this very round the tab on `:8080` reported `typeof checkizKey === "undefined"` after the server had been rebuilt with it, and only a different origin (`:8081`) showed the new code. A seller who updates the server can therefore still be running the old page - which is confusing in exactly the way this repo keeps documenting. The fix is one response header on the static mount (`no-cache`, so the browser revalidates and gets a 304 when nothing changed); it is not applied because the owner has not asked for it, and no test would notice either way. The second live run went around it the same way, on purpose: a freshly built image (`checkiz:verify`) on a third port, `:8082`, so the browser could not be showing anything but the committed code.

**The dashboard rebuilds every panel's rows every 5 seconds, and a review-queue button can be gone by the time the click lands.** Observed twice in one session: asked to click "why" on order #102, the browser reported *"Node is detached from document"* both times, on a node reference taken seconds earlier from the same row. The handler is delegated on `#review`, so a click on a live node works - clicking it that way opened the evidence timeline and then cleared the queue - and the rows look identical across a refresh, so a seller would not see anything wrong. What is **not** known is how often a human cursor loses that race; nothing was measured, and this is an observation, not a rate. The fix would be to update rows in place, or to hold the refresh while the seller is working in the queue. Not applied, and no test covers it.
