import pytest

from pdfserve.pdf_utils import parse_split_pages


def test_parse_split_pages():
    assert parse_split_pages("1-2,3,4-5") == [(1, 2), (3, 3), (4, 5)]
    assert parse_split_pages("1-2") == [(1, 2)]
    assert parse_split_pages("1") == [(1, 1)]
    assert parse_split_pages("1,2,3") == [(1, 1), (2, 2), (3, 3)]
    assert parse_split_pages("3,1-2") == [(3, 3), (1, 2)]
    assert parse_split_pages("1-1") == [(1, 1)]


def test_parse_wrong_format_split_pages():
    parse_split_pages("1-2,3,4-5,6")
    with pytest.raises(ValueError):
        parse_split_pages("1-2,3,4-5,")
    with pytest.raises(ValueError):
        parse_split_pages("1-2,3,4-5,6-")
    with pytest.raises(ValueError):
        parse_split_pages("1-2,6-7-8")
    with pytest.raises(ValueError):
        parse_split_pages("")
    with pytest.raises(ValueError):
        parse_split_pages("a,3,4")
    with pytest.raises(ValueError):
        parse_split_pages("4-3")
    with pytest.raises(ValueError):
        parse_split_pages("1-2,3,3-c,6")

    with pytest.raises(ValueError):
        parse_split_pages("1-2,3;3-4,6")
