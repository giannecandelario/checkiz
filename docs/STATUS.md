# Status: README claims reconciled against the code

Written 2026-10-23 against `fix/ui-runtime`. Suite: **170 tests passing** (`cd backend && pytest`, OCR stubbed). Rule: when this file, `README.md` and the code disagree, the code wins and both documents get fixed.

## Feature by feature

| Feature | Exists | Where | Test coverage |
|---|---|---|---|
| Receipt upload, OCR, field extraction | Yes | `backend/app/parser.py` (`run_ocr`, `parse_fields`, `locate_boxes`, `ocr_confidence`). `parse_fields` now also returns the printed `date` and `time` as strings; `app/consistency.py` decides what they mean | `test_verify.py::test_parse_fields`, `test_consistency.py::test_the_printed_date_and_time_are_read_into_the_fields` (stubbed OCR); real Tesseract verified in Docker on the synthetic samples only (once end to end, once on 2026-10-23 for the read score and the date/time fields) |
| Reference format validation | Yes | `backend/app/verify.py`, length from `config.REF_LENGTH` | `test_engine.py::test_missing_reference` |
| Replay protection (one reference, one order) | Yes | `ledger.consumed_order`, `verify.py` DUPLICATE branch | `test_engine.py::test_verified_then_duplicate`, `test_settle.py::test_one_payment_settles_one_order_only`, `test_real_receipt_cannot_be_reused_on_another_order` |
| Ledger match, late-alert resolution | Yes | `backend/app/ingest.py`, `verify.py::resolve_pending` | 3 tests in `test_engine.py`, 1 in `test_settle.py` |
| Order-bound QR Ph + centavo codes | Yes | `backend/app/qrph.py`, `qrstore.py`, `qr_orders` table | `test_qr.py` (5), `test_settle.py::test_auto_settle_without_screenshot`, `test_receipt_amount_must_match_issued_amount` |
| Alert feed: notification / SMS / paste, trust levels | Yes | `main.py` routes at lines 91, 101, 112; `CHECKIZ_APP_PACKAGES` allow-list; paste splits on blank lines | `test_engine.py`, `test_settle.py` trust tests, `test_api_key_protects_ledger` |
| `needs_app_check` persisted, incl. the late-alert path | Yes | `verifications.needs_app_check`, `verify.py:49`, `ingest.py` | `test_settle.py::test_sms_only_large_payment_needs_app_check`, `test_app_sourced_large_payment_needs_no_extra_check`, `test_review.py::test_late_sms_match_is_queued_for_app_check` |
| Review queue, acknowledge + reopen | Yes | `backend/app/review.py`, `GET /review`, `POST /review/{id}` | 8 tests in `test_review.py` |
| Packing list CSV, formula-injection neutralised | Yes | `backend/app/report.py`, `GET /orders/packing.csv` | `test_review.py::test_packing_csv_*` (2) |
| Per-order evidence timeline | Yes | `report.evidence`, `GET /orders/{id}/evidence` | `test_review.py::test_evidence_timeline_keeps_alert_text_out` |
| ELA + sharpness check | Yes, but **not separating the sample pair** | `backend/app/forensics.py` | Flag behaviour is tested; detection quality is not, and cannot be with synthetic samples |
| Dashboard, order board, OBS overlay | Yes | `frontend/index.html`, `overlay.html`, served by the API itself | No UI harness; but `test_serving.py` proves every page and helper is actually served and that all three load `api.js`. Panel rendering is still only looked at by hand |
| **Camera capture** | **Yes - README said Planned** | `frontend/camera.js` (getUserMedia + `<input capture>` fallback), wired at `index.html` and `qr.html` | 25 assertions executed in Node against a stubbed window: every refusal reason, the 0x0 startup race, live QR, and the no-`BarcodeDetector` path - three guards then mutated to confirm each one is load-bearing. **No real phone yet**, and the in-app browser here cannot grant camera permission at all |
| Pages served from the API origin | Yes | `main.py` `frontend_dir()` and the `StaticFiles` mount at `main.py:273`, mounted after every route | `test_serving.py` (16): root, three pages, two helpers, an API route beating the catch-all, and `/health` reporting `ui` |
| One rule for where the API is, and a real reason when a request fails | Yes | `frontend/api.js` - `CHECKIZ_API` (`?api=` > own origin > `localhost:8000`), `checkizProblem`, `checkizIsUnreachable`, `checkizWho`, `checkizDownload` | 50 assertions executed in Node against the file as it stands, with a stubbed `location`/`fetch`/`document`/`URL`, plus the dashboard's own `checkServer()` run the same way. Mutating away the same-origin rule, the foreign-server branch, the late revoke and the `"ocr" in h` guard each breaks its own assertion. The harness is not in the repo, so re-checking it means a browser or someone checking it in as a real UI test |
| `CHECKIZ_DB_PATH`, so two instances do not share one file | Yes | `db.py:_db_path()` | 4 of the 16 in `test_serving.py` (override, relative and `~` forms, the default, and that the pointed-at file is the one created) |
| **The server says when it cannot read receipts at all** | Yes | `parser.ocr_engine()` (one cached probe), `/health`'s `ocr`, a startup warning, `HTTP 503` on `/verify`, and a banner on the dashboard before the first upload | `test_no_ocr.py` (13): the probe's three answers and its caching, `/health` with and without an engine, the 503 carrying no verdict and writing no history row, the 422 for a blank order, the test that a **stubbed** reader still gets verdicts on a machine with no Tesseract, and two that the dashboard only warns when the server actually reports `ocr: null`. Reproduced live on :8000, then fixed, then reproduced as 503 - see "A server that could not read anything" |
| Retake hint on a poor photo | Yes | `parser.ocr_confidence` averages Tesseract's per-word scores; `verify.retake_hint` turns a score under `config.OCR_CONFIDENCE_MIN` into `hint` on the verdict, shown in the dashboard banner. `confidence` is on every verdict response; the hint is not stored | `test_confidence.py` (22): the average and each half of its row filter, a blank page as `None`, the floor as config, and four engine tests that pin the status while the hint appears. The **floor** has never been measured on a phone photo - see "Photo quality" |
| Startup warnings when `CHECKIZ_API_KEY` is unset or no Tesseract is installed | Yes | `main.py:49` | The API-key warning is not asserted by a test. The Tesseract one is only reached through `ocr_engine()`, which is tested; the printed line itself was observed in the server log, not asserted |
| `/health` | Yes | `main.py:80`, answering `ok`, `name`, `ui` and `ocr` | `test_serving.py::test_health_names_the_server_so_a_page_can_tell_it_apart`, `test_no_ocr.py` for `ocr`, plus the API smoke test |
| Plain-language verdict `label` field | Yes | `backend/app/labels.py`; `label` on every verdict response, late-alert resolution, auto-settlement result, history row, review item and evidence event; `verifications.label` column with migration; `/stats` also returns `by_label`; shown in `index.html` and `overlay.html`. Upload rejections (415/413) are HTTP errors and carry no verdict | `test_labels.py` (19). Status codes are unchanged and still asserted |
| Buyer pay page (`/pay/{order_id}`, `qr.png`, `pay.html`) | **No** | - | Brief Step 0 lists it; README claimed it Built |
| Scripted demo (`backend/demo.py`) | **No** | - | README's "Getting started" references a file that does not exist |
| `docs/DEVICE_TEST.md` | **No** | - | Referenced twice in the README |
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
(`main.py:273`, mounted after every API route), so there is one origin and no second
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

The UI's rendering (the verdict panels have still only been looked at by hand), the two Termux forwarders, real Tesseract behaviour (the samples have been put through it by hand in Docker; every test stubs the reader), the consistency thresholds and the confidence floor against genuine receipts, and anything requiring a wallet's actual alert wording. The 170 tests exercise verdict logic with stubbed OCR and hand-written alert text, so they prove the rules, not the parsing of a real provider.
