from .config import ORDER_TTL_HOURS
from .db import get_conn

_RECENT = f"created_at > datetime('now', '-{int(ORDER_TTL_HOURS * 60)} minutes')"

def set_seller_qr(payload: str):
    with get_conn() as conn:
        conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('seller_qr', ?)", (payload,))

def get_seller_qr():
    with get_conn() as conn:
        r = conn.execute("SELECT value FROM settings WHERE key = 'seller_qr'").fetchone()
        return r["value"] if r else None

def next_free_amount(base: float) -> float:
    """Whole-peso base plus a free centavo code (.01-.99) so each open order has a unique amount."""
    whole = int(base)
    with get_conn() as conn:
        used = {round(r["amount"], 2) for r in conn.execute(
            f"SELECT amount FROM qr_orders WHERE coded = 1 AND status = 'OPEN' AND {_RECENT} "
            "AND CAST(amount AS INTEGER) = ?", (whole,))}
    for c in range(1, 100):
        a = round(whole + c / 100, 2)
        if a not in used:
            return a
    raise ValueError("No free centavo codes left for this amount")

def save_order(order_id: str, amount: float, coded: bool):
    with get_conn() as conn:
        conn.execute("INSERT OR REPLACE INTO qr_orders (order_id, amount, coded, status) VALUES (?, ?, ?, 'OPEN')",
                     (order_id, amount, int(coded)))

def find_coded_order_by_amount(amount: float):
    with get_conn() as conn:
        return conn.execute("SELECT * FROM qr_orders WHERE coded = 1 AND ABS(amount - ?) < 0.001",
                            (amount,)).fetchone()

def list_orders():
    with get_conn() as conn:
        return [dict(r) for r in conn.execute("SELECT * FROM qr_orders ORDER BY created_at DESC")]

def get_order(order_id: str):
    with get_conn() as conn:
        return conn.execute("SELECT * FROM qr_orders WHERE order_id = ?", (order_id,)).fetchone()

def find_open_coded_order(amount: float):
    """The one open, recent, centavo-coded order issued for exactly this amount."""
    with get_conn() as conn:
        return conn.execute(
            f"SELECT * FROM qr_orders WHERE coded = 1 AND status = 'OPEN' AND {_RECENT} "
            "AND ABS(amount - ?) < 0.001", (amount,)).fetchone()

def mark_paid(order_id: str, ref: str):
    with get_conn() as conn:
        conn.execute("UPDATE qr_orders SET status = 'PAID', paid_ref = ?, paid_at = datetime('now') "
                     "WHERE order_id = ?", (ref, order_id))
