from herdtop.text import cut, cut_left, one_line, pad, rpad, width


def test_width_counts_terminal_columns() -> None:
    assert width("abc") == 3
    assert width("日本") == 4
    assert width("é") == 1
    assert width("a‍b") == 2


def test_cut() -> None:
    assert cut("abcdef", 6) == "abcdef"
    assert cut("abcdef", 4) == "abc…"
    assert cut("日本語", 4) == "日…"
    assert cut("abc", 0) == ""


def test_cut_left_keeps_the_end() -> None:
    assert cut_left("/home/me/work/project", 10) == "…k/project"
    assert cut_left("short", 10) == "short"


def test_pad() -> None:
    assert pad("日本", 6) == "日本  "
    assert rpad("ab", 4) == "  ab"
    assert pad("abcdef", 4) == "abc…"


def test_one_line() -> None:
    assert one_line(" a\n b\tc ") == "a b c"
