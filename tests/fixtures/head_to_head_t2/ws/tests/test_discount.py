from butler_sample.discount import apply_discount


def test_apply_discount_ten_percent():
    assert apply_discount(100.0, 0.1) == 90.0
