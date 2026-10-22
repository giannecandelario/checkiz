# AI reading: provider and privacy notes

Status: planning notes, not legal advice. Re-check the linked pages before relying on them.

## Decision

- **Default: local OCR (Tesseract).** Free, no data leaves the device, works offline, cannot fail mid-demo.
- **Optional cloud reader to evaluate: Gemini API.** Off by default. Test data only on the free (unpaid) quota. Real receipts only through a billed Cloud project with consent.
- Other cloud providers (for example Google Cloud Vision, which lists a monthly free allowance) have **not** been assessed for data terms.

## What was read (2026-10-23)

Gemini API Additional Terms of Service, effective March 23, 2026 (last updated 2026-04-28): https://ai.google.dev/gemini-api/terms
Earlier version, effective November 20, 2025, for comparison: https://ai.google.dev/gemini-api/terms-archive/terms_11_20_25
Available regions (Philippines is listed; last updated 2026-04-28): https://ai.google.dev/gemini-api/docs/available-regions

**Not read:** the Google APIs Terms of Service, the Data Processing Addendum, the Privacy Policy, the Prohibited Use Policy, the "Data logging and sharing" page, and Google Cloud Vision's terms. They are referenced by the terms above and may add conditions.

## What the Gemini terms say (summary in our words)

Unpaid services (free quota and Google AI Studio):
- Submitted content and responses are used to provide, improve and develop Google products and machine learning technologies.
- Human reviewers may read, annotate and process input and output. Google says it disconnects the data from the account, API key and Cloud project first.
- The terms tell developers not to submit sensitive, confidential or personal information to unpaid services.
- The license you grant covers files such as images and documents.
- Users in the EEA, Switzerland and the UK get the paid-service data terms even on free quota. This does not apply to the Philippines.

Paid services (Gemini API accessed through a Cloud project with an active billing account):
- Prompts and responses, including files such as images, are not used to improve Google products, and are processed under Google's data processing addendum.
- Prompts and responses are logged for a limited period, solely to detect and prevent policy violations and meet legal or regulatory disclosures.
- Data may be stored transiently or cached in any country where Google or its agents have facilities. For Philippine users, consider cross-border transfer rules and say so in the consent notice.
- Other account, billing and usage data stay under Google's controller terms and Privacy Policy.

Other conditions:
- Developers must be 18+. The API client must not be directed at, or likely to be accessed by, people under 18.
- The service is described as for developers building for professional or business purposes, not consumer use.
- The terms disclaim accuracy: generated content may be wrong, so do not rely on it unchecked.
- Changes between versions: the November 2025 version made all use "paid" once a Cloud Billing account was activated; the March 2026 version ties paid status to access through a Cloud project with an active billing account. Use an API key from a billed project for real data, and re-check before demos.

## Rules for this project

1. Never send a real customer's or seller's receipt to an unpaid service.
2. Use unpaid quota only with synthetic receipts or the owner's own receipts.
3. Real user receipts only via a billed project, behind a consent notice that names the provider, says the image is sent for reading, mentions possible storage in other countries, and can be revoked.
4. Send the minimum: strip metadata, downscale, crop to the fields needed where practical. Do not store images. Do not log payloads.
5. The AI reader never decides a verdict.

## Open questions (verify before enabling)

- Current pricing, and whether any free quota still applies on a billed project.
- Whether the "Data logging and sharing" page changes anything for our use.
- Philippine privacy requirements for cross-border processing (NPC guidance). Get advice from your school or the organizers.
