from app.ledger import parse_sms
from app.parser import parse_fields

def test_parse_fields():
    f = parse_fields("Amount PHP 1,250.00\nRef No. 1002 849 130490")
    assert f["amount"] == 1250.00
    assert f["ref"] == "1002849130490"

def test_parse_sms():
    sms = "You have received PHP 1,250.00 of GCash from JUAN D. Ref. No. 1002 849 130490."
    e = parse_sms(sms)
    assert e and e["ref"] == "1002849130490" and e["amount"] == 1250.00

def test_parse_sms_rejects_garbage():
    assert parse_sms("hello world") is None
