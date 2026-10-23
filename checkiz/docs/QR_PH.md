# QR Ph order references

QR Ph is built on the EMVCo merchant-presented QR format: a flat list of tag-length-value fields ending in a CRC16-CCITT-FALSE checksum (tag 63). Checkiz works at that layer to tie each payment to an order.

## What Checkiz does

1. **Register** your own "receive money" QR from GCash or Maya (scan it with the camera or upload an image).
2. **Generate** a one-order QR from it: point-of-initiation 11 (static) becomes 12 (dynamic), tag 54 gets the amount, and tag 62 gets the order ID as bill number and reference label. The merchant account fields are copied untouched and the CRC is recomputed. With "centavo code" on, the amount also gets a free `.01-.99` code so each open order has a unique amount.
3. If a receipt arrives with a centavo-coded amount that was issued for a different order, `/verify` adds a warning.

Account identifiers are never returned to the browser.

## Not verified yet

- Whether GCash or Maya honor the amount and reference fields on a personal QR, and whether the reference appears on the receipt or SMS. Test one dynamic QR with a real wallet first; the centavo code is the fallback because the amount always reaches the SMS.
- This was written from the general EMVCo format. It has not been checked against the official BSP QR Ph specification. Tests use a synthetic payload, not a real wallet QR.
- Browser camera access needs https or localhost. Elsewhere the app falls back to the phone's native camera via a file picker.
