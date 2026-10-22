"""EMVCo merchant-presented QR (the format QR Ph builds on): parse, validate, rebuild.

Pure functions, no database. A payload is a flat list of tag-length-value fields
ending in tag 63 (CRC16-CCITT-FALSE over everything before the checksum)."""
import re

def crc16(data: bytes) -> int:
    crc = 0xFFFF
    for b in data:
        crc ^= b << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    return crc

def parse_tlv(s: str):
    out, i = [], 0
    while i < len(s):
        tag, ln = s[i:i + 2], s[i + 2:i + 4]
        if len(tag) < 2 or not ln.isdigit():
            raise ValueError("Malformed TLV")
        n = int(ln)
        val = s[i + 4:i + 4 + n]
        if len(val) != n:
            raise ValueError("Truncated TLV")
        out.append((tag, val))
        i += 4 + n
    return out

def tlv(tag: str, value: str) -> str:
    return f"{tag}{len(value):02d}{value}"

def build(objs) -> str:
    """Serialize fields (sorted by tag) and append a correct CRC."""
    body = "".join(tlv(t, v) for t, v in sorted((o for o in objs if o[0] != "63"), key=lambda o: o[0]))
    body += "6304"
    return body + f"{crc16(body.encode()):04X}"

def crc_ok(payload: str) -> bool:
    return len(payload) > 8 and payload[-8:-4] == "6304" and \
        f"{crc16(payload[:-4].encode()):04X}" == payload[-4:].upper()

def _accounts(objs):
    return [(t, v) for t, v in objs if "26" <= t <= "51"]

def analyze(payload: str) -> dict:
    """Summary of a payload. Raises ValueError if it isn't TLV at all."""
    objs = parse_tlv(payload.strip())
    d = dict(objs)
    add = dict(parse_tlv(d["62"])) if "62" in d else {}
    guis = []
    for _, v in _accounts(objs):
        try:
            guis.append(dict(parse_tlv(v)).get("00"))
        except ValueError:
            guis.append(None)
    try:
        amount = float(d["54"]) if "54" in d else None
    except ValueError:
        amount = None
    return {
        "is_emv": d.get("00") == "01" and bool(_accounts(objs)),
        "crc_valid": crc_ok(payload.strip()),
        "point_of_initiation": d.get("01"),
        "amount": amount,
        "merchant_name": d.get("59"),
        "merchant_city": d.get("60"),
        "guis": guis,
        "bill_number": add.get("01"),
        "reference_label": add.get("05"),
    }

def account_signature(payload: str) -> str:
    return "|".join(f"{t}:{v}" for t, v in _accounts(parse_tlv(payload.strip())))

def clean_order_id(order_id: str) -> str:
    oid = re.sub(r"[^A-Za-z0-9]", "", order_id or "")[:25]
    if not oid:
        raise ValueError("Order ID must contain letters or digits")
    return oid

def build_dynamic(payload: str, amount: float, order_id: str) -> str:
    """Turn the seller's own QR into a one-order QR: dynamic flag, fixed amount,
    and the order ID as bill number and reference label (additional data, tag 62)."""
    if not (0 < amount <= 9_999_999_999.99):
        raise ValueError("Amount out of range")
    objs = parse_tlv(payload.strip())
    old62 = dict(parse_tlv(dict(objs)["62"])) if "62" in dict(objs) else {}
    oid = clean_order_id(order_id)
    old62.update({"01": oid, "05": oid})
    new62 = "".join(tlv(t, v) for t, v in sorted(old62.items()))
    keep = [(t, "12" if t == "01" else v) for t, v in objs if t not in ("54", "62", "63")]
    return build(keep + [("54", f"{amount:.2f}"), ("62", new62)])
