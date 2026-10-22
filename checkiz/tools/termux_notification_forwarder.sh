#!/data/data/com.termux/files/usr/bin/bash
# Forwards wallet-app notifications (GCash, Maya) from the seller's Android phone to Checkiz.
# Reads the notification the wallet app itself posted, so a spoofed SMS sender ID cannot fake it.
# Needs Termux + Termux:API (pkg install termux-api jq curl) and "Notification access"
# granted to Termux:API in Android settings.
# UNTESTED on a device: try it with a real small payment first. See docs/SMS_FORWARDING.md.
API="${CHECKIZ_API:-http://192.168.1.10:8000}"
KEY="${CHECKIZ_API_KEY:-}"
SEEN="$HOME/.checkiz_seen_notif"
touch "$SEEN"

while true; do
  termux-notification-list \
    | jq -c '.[] | select(.packageName == "com.globe.gcash.android" or .packageName == "com.paymaya")
                 | select((.title + " " + .content) | test("received"; "i"))
                 | {key: (.key // (.id|tostring)), package: .packageName, title: (.title // ""), text: (.content // "")}' \
    | while read -r row; do
        k=$(echo "$row" | jq -r .key)
        grep -qxF "$k" "$SEEN" && continue
        body=$(echo "$row" | jq -c '{package, title, text}')
        code=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$API/ledger/notification" \
          -H "Content-Type: application/json" ${KEY:+-H "X-API-Key: $KEY"} -d "$body")
        # 200 = stored, 400/403 = not a payment or not a wallet app; anything else retry next loop
        case "$code" in 200|400|403) echo "$k" >> "$SEEN" ;; esac
      done
  sleep 5
done
