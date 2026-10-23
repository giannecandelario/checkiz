# Calibration guide (task 6: real numbers or no claim)

## Where this stands today

The README says **"the forensic check did not separate the two"** about the shipped
synthetic sample pair, and it stays saying that until someone runs the steps below on
genuine receipts. `CHECKIZ_ELA_THRESHOLD` (8.0) and `CHECKIZ_SHARPNESS_THRESHOLD` (6.0)
are starting points chosen before any measurement, not calibrated values.

The script is `backend/calibrate.py`. It prints what it measured and nothing else: a
group with no samples produces no numbers, an image where the amount or reference box
could not be located prints `no boxes` instead of a score of `0.00`, and a suggested
threshold only appears when the two groups actually separate with enough samples behind
them. **If your run says the groups overlap, that is the result - write it down and stop.
It is a finding, not a failed task.**

### Measured 2026-10-23: a phone photo moves ELA *down*

Four synthetic files, run through the Docker Tesseract against an empty ledger (the
numbers are in the README's "A genuine receipt, a week old, photographed"):

| Copy | ELA | Flagged at 8.0? |
|---|---|---|
| rendered receipt, saved straight from the generator | 5.78 | no |
| the same page photographed on a phone (angle, moiré, glare, noise, JPEG q62) | 2.55 | no |
| amount redrawn, saved straight | 5.76 | no |
| amount redrawn, photographed | 2.42 | no |

Photographing a genuine receipt cut its score in half, and the edited copy followed the
same curve. `ela_ratio` is the recompression error inside the field boxes divided by the
error across the whole image, and camera noise raises that whole-image baseline - so the
denominator, not the edit, decides where a photographed page lands.

Two consequences for whoever runs this for real:

- **Do not expect the phone-photo group to sit above the clean-screenshot group.** The
  genuine folder needs both forms of the same page, and the comparison that matters is
  genuine-photographed against edited-photographed. A run that only compares clean
  screenshots against each other measures the wrong thing and looks like it worked.
- **Compare like with like when you propose a threshold.** A number that separates two
  groups of unsaved screenshots is not a threshold for the photos a counter actually
  receives. If you record a threshold, record which form it was measured on.

Since 2026-10-23 a flag on its own no longer calls a receipt fake - it is a `warning`
line and the receipt waits as `Can't confirm yet` - so the false-alarm cost in section 4
is now a seller reading one extra line, not a customer argument about an accusation.
That makes a *lower* threshold cheaper to live with; it does not make an unmeasured one
correct.

## 1. What to collect

Two folders. At least **five of each** - fewer than three per group and the script
refuses to suggest anything, because a pair of images that happen to differ is not a
signal.

**Genuine** (`samples_real/`) - receipts that left the wallet untouched:

- a screenshot from the wallet app itself,
- a screenshot of the in-app inbox,
- a **phone photo of somebody else's screen** (this is the case the repo has never
  measured, and the one the seller actually uses at the counter),
- one copy of each of those *after* being sent through Messenger or Viber. This matters:
  it is the same picture with no edit in it, so any jump in ELA is the chat app, not a
  forger. Keep the pre-compression copy too.

**Edited** (`samples_edited/`) - the same genuine images with the money changed, by
whatever a customer would actually use:

- change the amount only, then the reference only, then both,
- do it in one normal phone editor and in one desktop editor, and re-save at a couple of
  quality levels,
- name the file for what was done, e.g. `edit-07-amount-phone-editor-q80.jpg`.

Do not use a file as both genuine and edited. Do not edit and then re-save over the
original.

**Privacy:** real receipts carry real names, numbers and references. Keep both folders
**outside this repository** - `.gitignore` covers `samples_real/` and `samples_edited/`
if you insist on putting them beside the code, but a folder in your home directory is
better. Never commit one, and never send one to a service you have not paid for and read
the terms of.

## 2. Run it

From the repo root, using the Docker image (this is what has Tesseract; the machine you
code on probably does not, and the script exits with that message rather than printing
blanks):

```bash
docker build -t checkiz .
docker run --rm \
  -v "$HOME/receipt-samples":/samples:ro \
  -v "$PWD/backend":/src:ro \
  -w /src checkiz python calibrate.py \
    --real /samples/samples_real --edited /samples/samples_edited \
    --markdown --at 8.0 6.0 \
    > docs/CALIBRATION_RESULTS.md
```

- `-v ... :ro` - the script only reads your samples; keep it that way.
- `--markdown` appends the table in the shape the README uses.
- `--at 8.0 6.0` scores those two current defaults against your samples: how many
  genuine receipts would have been cried about, and how many edited ones would have been
  missed. Run it again with any candidate threshold before you adopt it.
- The run date it prints is the container's date, which is UTC. If that matters to you,
  add the local date at the top of the file.

## 3. What goes where

`docs/CALIBRATION_RESULTS.md` is created by the redirect above and holds the raw run:
every image, its numbers, the group summaries, the threshold verdicts. Commit that file -
it is numbers, not receipts. It is the evidence the README's claim rests on.

Then, and only then, the README:

1. Paste the `| Sample | Group | ELA | ... |` block under **"Measured so far (honest)"**,
   replacing nothing - the existing rows stay as what the synthetic pair showed.
2. Update the sentence above it with the n, the wallets and the device, the way the
   current sentence does for the synthetic pair.
3. If the groups separated, change `CHECKIZ_ELA_THRESHOLD` / `CHECKIZ_SHARPNESS_THRESHOLD`
   defaults in `backend/app/forensics.py`, note the new value and the n it came from in
   the README, and re-run the suite (`cd backend && pytest`).
4. If they did not, the README keeps "the forensic check did not separate" - and says so
   with your n and date instead of the synthetic pair's.

## 4. Picking a threshold

- Adopt one only when `n >= 3` per group and the groups separate.
- Choose the midpoint the script suggests, then immediately run `--at` on it and read the
  **false-alarm count first**. A genuine receipt flagged as suspected fake costs the shop
  a customer argument; a missed edit is caught by the ledger match anyway, which is the
  primary check. When the two counts trade off, prefer fewer false alarms and say so in
  the README.
- A threshold tuned to one wallet or one phone is that wallet's and that phone's. Record
  which, or the number will be read as general when it is not.
- `CHECKIZ_OCR_CONFIDENCE_MIN` (60) comes from the same run: it is the **Read score**
  column. Both shipped synthetic samples read about 94, so nothing near 60 has ever been
  observed on a real photo. Phone photos in bad light are the test for it.

## 5. What cannot be calibrated this way

Edit detection on a *generated* receipt - an image that never came from a wallet at all -
is not testable by comparing real against edited copies of real ones. Checkiz's position
is that the ledger match and the order binding are the primary checks and the forensics
are secondary; a calibration run that shows overlap does not weaken that, it explains it.
