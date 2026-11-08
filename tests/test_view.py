from builder import NOW, session

from herdtop.view import UNTAGGED, ViewState, home_path, rows, shown, tag


def labels(found) -> list[str]:
    return [r.label if r.group else r.session.title for r in found]


def test_flat_lists_the_newest_answer_first() -> None:
    old = session("old", answered=NOW - 100)
    new = session("new", answered=NOW)
    assert labels(rows([old, new], ViewState(group="flat"))) == ["new", "old"]


def test_by_title() -> None:
    found = rows([session("b"), session("A"), session("c")],
                 ViewState(group="flat", sort="title"))
    assert labels(found) == ["A", "b", "c"]


def test_groups_are_folded_until_opened() -> None:
    a1 = session("a1", "/work/a", answered=NOW)
    a2 = session("a2", "/work/a", answered=NOW - 10)
    b1 = session("b1", "/work/b", answered=NOW - 5)
    state = ViewState()
    assert labels(rows([a1, a2, b1], state)) == ["/work/a", "/work/b"]
    state.opened.add("/work/a")
    found = rows([a1, a2, b1], state)
    assert labels(found) == ["/work/a", "a1", "a2", "/work/b"]
    assert found[0].opened and not found[3].opened


def test_groups_by_title_sort_by_label() -> None:
    found = rows([session("x", "/work/b"), session("y", "/work/a")],
                 ViewState(sort="title"))
    assert labels(found) == ["/work/a", "/work/b"]


def test_by_tag() -> None:
    found = rows([session("[herdr] panel"), session("(cctop) port"),
                  session("plain")], ViewState(group="tag", all_open=True))
    assert [r.label for r in found if r.group] == ["[herdr]", "(cctop)", UNTAGGED]


def test_a_tag_holds_at_most_30_characters() -> None:
    assert tag("[" + "x" * 28 + "] title") == "[" + "x" * 28 + "]"
    assert tag("[" + "x" * 29 + "] title") == UNTAGGED
    assert tag("no [tag] at the head") == UNTAGGED


def test_a_filter_matches_every_word_and_opens_every_group() -> None:
    a = session("fix the parser", "/work/herdtop")
    b = session("fix the docs", "/work/other")
    state = ViewState(filter="fix herdtop")
    found = rows([a, b], state)
    assert labels(found) == ["/work/herdtop", "fix the parser"]


def test_a_subsequence_matches_only_when_no_substring_does() -> None:
    config = session("edit the config")
    cfg = session("cfg loader")
    assert shown([config, cfg], ViewState(filter="cfg")) == [cfg]
    assert shown([config], ViewState(filter="cfg")) == [config]
    assert shown([config], ViewState(filter="zzz")) == []


def test_unnamed_keeps_the_generated_titles() -> None:
    named = session("named")
    generated = session("generated", named=False)
    assert shown([named, generated], ViewState(unnamed=True)) == [generated]


def test_a_search_keeps_its_matches() -> None:
    a, b = session("a"), session("b")
    state = ViewState(group="flat", search=["x"], matches={b.path})
    assert labels(rows([a, b], state)) == ["b"]


def test_home_is_shown_as_a_tilde(home) -> None:
    assert home_path(str(home / "work")) == "~/work"
    assert home_path(str(home)) == "~"
    assert home_path("/srv") == "/srv"
    assert home_path(None) == "(unknown directory)"
