from app.verify import event_ids_exist, quote_in_text


def test_quote_must_really_be_in_the_text():
    text = "Test: EXAMPLE_TEST_A\nResult: 120"
    assert quote_in_text("result:  120", text)          # spacing and case do not matter
    assert not quote_in_text("Result: 999", text)       # invented value is rejected
    assert not quote_in_text("", text)


def test_event_ids_must_exist():
    assert event_ids_exist(["E1", "E2"], {"E1", "E2", "E3"})
    assert not event_ids_exist(["E9"], {"E1"})
    assert not event_ids_exist([], {"E1"})
