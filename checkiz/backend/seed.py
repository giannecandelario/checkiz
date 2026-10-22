from app.db import init_db
from app.ledger import add_entry

init_db()
add_entry({"ref": "1002849130490", "amount": 1250.00, "sender": "JUAN D.", "raw": "demo"})
add_entry({"ref": "2003951240871", "amount": 850.00, "sender": "MARIA S.", "raw": "demo"})
print("Seeded ledger")
