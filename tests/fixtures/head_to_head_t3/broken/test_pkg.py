from pkg.client import Client


def test_rename_get_data():
    c = Client()
    assert hasattr(c, "get_data")
    assert not hasattr(c, "getData")
