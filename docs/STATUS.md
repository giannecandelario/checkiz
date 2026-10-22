# Status: README claims reconciled against the code

Written 2026-10-23 against `feat/product-hardening` at `1a45bf4`. Suite: **43 tests passing** (`cd backend && pytest`, OCR stubbed). Rule: when this file, `README.md` and the code disagree, the code wins and both documents get fixed.

## Feature by feature

| Feature | Exists | Where | Test coverage |
|---|---|---|---|
| Receipt upload, OCR, field extraction | Yes | `backend/app/parser.py` (`run_ocr`, `parse_fields`, `locate_boxes`) | `test_engine.py::test_parse_fields` (stubbed OCR); real Tesseract verified once, in Docker, on the synthetic samples only |
| Reference format validation | Yes | `backend/app/verify.py`, length from `config.REF_LENGTH` | `test_verify.py::test_missing_reference` |
| Replay protection (one reference, one order) | Yes | `ledger.consumed_order`, `verify.py` DUPLICATE branch | `test_verify.py::test_verified_then_duplicate`, `test_settle.py::test_one_payment_settles_one_order_only`, `test_real_receipt_cannot_be_reused_on_another_order` |
| Ledger match, late-alert resolution | Yes | `backend/app/ingest.py`, `verify.py::resolve_pending` | 3 tests in `test_verify.py`, 1 in `test_settle.py` |
| Order-bound QR Ph + centavo codes | Yes | `backend/app/qrph.py`, `qrstore.py`, `qr_orders` table | `test_qr.py` (5), `test_settle.py::test_auto_settle_without_screenshot`, `test_receipt_amount_must_match_issued_amount` |
| Alert feed: notification / SMS / paste, trust levels | Yes | `main.py` routes at lines 62, 72, 83; `CHECKIZ_APP_PACKAGES` allow-list; paste splits on blank lines | `test_engine.py`, `test_settle.py` trust tests, `test_api_key_protects_ledger` |
| `needs_app_check` persisted, incl. the late-alert path | Yes | `verifications.needs_app_check`, `verify.py:111`, `ingest.py` | `test_settle.py::test_sms_only_large_payment_needs_app_check`, `test_app_sourced_large_payment_needs_no_extra_check`, `test_review.py::test_late_sms_match_is_queued_for_app_check` |
| Review queue, acknowledge + reopen | Yes | `backend/app/review.py`, `GET /review`, `POST /review/{id}` | 8 tests in `test_review.py` |
| Packing list CSV, formula-injection neutralised | Yes | `backend/app/report.py`, `GET /orders/packing.csv` | `test_review.py::test_packing_csv_*` (2) |
| Per-order evidence timeline | Yes | `report.evidence`, `GET /orders/{id}/evidence` | `test_review.py::test_evidence_timeline_keeps_alert_text_out` |
| ELA + sharpness check | Yes, but **not separating the sample pair** | `backend/app/forensics.py` | Flag behaviour is tested; detection quality is not, and cannot be with synthetic samples |
| Dashboard, order board, OBS overlay | Yes | `frontend/index.html`, `overlay.html` | None - no UI test harness in the repo |
| **Camera capture** | **Yes - README said Planned** | `frontend/camera.js` (getUserMedia + `<input capture>` fallback), wired at `index.html:95` and `qr.html:64` | None; and untestable here because the in-app browser denies camera permission |
| Startup warning when `CHECKIZ_API_KEY` unset | Yes | `main.py:28` | Not asserted by a test |
| `/health` | Yes | `main.py:48` | Yes, in the API smoke test |
| Plain-language verdict `label` field | **No** | - | Brief task 1. No `label` key exists in any response |
| Buyer pay page (`/pay/{order_id}`, `qr.png`, `pay.html`) | **No** | - | Brief Step 0 lists it; README claimed it Built |
| Scripted demo (`backend/demo.py`) | **No** | - | README's "Getting started" references a file that does not exist |
| `docs/DEVICE_TEST.md` | **No** | - | Referenced twice in the README |
| Image perceptual hash | **No** | - | Brief task 2 |
| Alert-free consistency checks | **No** | - | Brief task 3 |
| AI-assisted reader, `eval/run_eval.py`, `docs/AI_EVAL.md` | **No** | - | Brief task 7, gated and last priority |
| Staff mode, PINs, `/reconcile/daily` | **No** | - | Explicitly Deferred in the brief |

## Corrections made while reconciling

- **Camera capture was under-claimed** as Planned in the README and in the roadmap. It is built and used by two pages. The remaining gap is only the "retake for a clearer photo" hint, which needs an OCR confidence signal the parser does not currently produce.
- **The buyer pay page was over-claimed** as Built. It is Planned until someone builds it; nothing in `main.py` or `frontend/` serves it.
- **`backend/demo.py` does not exist**, so the README's scripted-demo command would fail on a clean checkout.
- Two source links in the README could not be verified as written: the Mynt notice is at `newsroom/...` (`news-draft/...` returns 404), and BDO plus one Inquirer link are unreachable from here (connection failure and 403). They are marked as unverified rather than silently kept.
- The README links `[Status](#status)`, which has no matching heading.

## What no test covers

The UI, the two Termux forwarders, the Docker build, real Tesseract behaviour, and anything requiring a wallet's actual alert wording. The 43 tests exercise verdict logic with stubbed OCR and hand-written alert text, so they prove the rules, not the parsing of a real provider.
