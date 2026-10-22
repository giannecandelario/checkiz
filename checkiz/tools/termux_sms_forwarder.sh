#!/data/data/com.termux/files/usr/bin/bash
# Forwards incoming "received" payment SMS from the seller's Android phone to Checkiz.
# Needs Termux + Termux:API (pkg install termux-api jq curl) and SMS permission.
# UNTESTED on a device: try it with a test SMS first. See docs/SMS_FORWARDING.md.
API="${CHECKIZ_API:-http://192.168.1.10:8000}"   # your server's LAN address
KEY="${CHECKIZ_API_KEY:-}"
SEEN="$HOME/.checkiz_seen"
touch "$SEEN"

while true; do
  termux-sms-list -l 20 -t inbox \
    | jq -c '.[] | select(.body | test("received"; "i")) | {id: ._id, text: .body}' \
    | while read -r row; do
        id=$(echo "$row" | jq -r .id)
        grep -qx "$id" "$SEEN" && continue
        body=$(echo "$row" | jq -c '{text}')
        code=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$API/ledger/sms" \
          -H "Content-Type: application/json" ${KEY:+-H "X-API-Key: $KEY"} -d "$body")
        # 200 = stored, 400 = not a payment SMS; anything else, retry next loop
        case "$code" in 200|400) echo "$id" >> "$SEEN" ;; esac
      done
  sleep 10
done
