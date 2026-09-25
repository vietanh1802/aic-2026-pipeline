# backend/tests/test_ocr_search_terms.py
"""ocr_search.search_terms() against ocr_search.search() on a small synthetic corpus.

search_terms() is the one-scan, many-terms sibling of search(). With ONE term it
must reproduce search() exactly (same frames, same whole-phrase flags, same order
under search()'s ranking key), including the quirk that a term with no word
character matches every frame. The full-corpus (179,728 frames) version of this
check is an ad hoc script, see the task report."""
import pytest

from app import ocr_search
from app.ocr_search import _strip_marks

TEXTS = {
    "V1-0000-1.jpg" : "Quán ăn Chợ Lớn",
    "V1-0000-2.jpg" : "chợ nổi và quán ăn",
    "V1-0000-3.jpg" : "THỂ THAO 2018 (1,5) kg",
    "V2-0000-1.jpg" : "Nước sôi, thịt bò",
    "V2-0000-2.jpg" : "nuoc soi thit bo",
    "V2-0000-3.jpg" : "Lửa nước - Đường đi Đà Nẵng",
    "V3-0000-1.jpg" : "a",
    "V3-0000-2.jpg" : "xin chào 🙂 ngò",
    "V3-0000-3.jpg" : "CHỢ CHỢ chợ",
}


@pytest.fixture(autouse=True)
def corpus(monkeypatch) :
    """Real backing dicts of ocr_search, filled the way _load() fills them: display
    text verbatim, comparison text lowercased, the no-marks side also folded."""
    monkeypatch.setattr(ocr_search, "_loaded", True)
    monkeypatch.setattr(ocr_search, "_display", dict(TEXTS))
    monkeypatch.setattr(ocr_search, "_haystack", {
        "with_marks" : {name : text.lower() for name, text in TEXTS.items()},
        "no_marks" : {name : _strip_marks(text).lower() for name, text in TEXTS.items()}})


def _search(term : str, strip : bool) -> list[tuple[str, bool]] :
    """(frame, whole phrase) rows of search() in its own order, no row limit."""
    result = ocr_search.search(term, limit = 10 ** 6, strip_diacritics = strip)
    return [(row["name"], row["exact_phrase"]) for row in result["results"]]


def _ordered(found : dict, index : int) -> list[tuple[str, bool]] :
    """One term's rows of search_terms(), sorted with search()'s ranking key: whole
    phrase first, then shorter display text, then frame name."""
    rows = [(name, phrase, length) for name, (length, matches) in found.items() for term, phrase in matches if term == index]
    rows.sort(key = lambda row : (not row[1], row[2], row[0]))
    return [(name, phrase) for name, phrase, _length in rows]


QUERIES = ["chợ", "Chợ Lớn", "cho lon", "lớn chợ", "quán ăn", "ăn quán", "chợ chợ", "nuoc", "nước", "THỂ THAO",
           "2018", "1,5", "1 5", "(", "-", ",", "🙂", "a", "đường", "duong", "ngò", "ngo", "không có", "", "   "]


@pytest.mark.parametrize("strip", [False, True])
@pytest.mark.parametrize("query", QUERIES)
def test_one_term_reproduces_search_exactly(query, strip) :
    assert _ordered(ocr_search.search_terms([query], strip), 0) == _search(query, strip)


def test_the_synthetic_corpus_really_exercises_the_cases() :
    assert len(_search("chợ", False)) == 3 and _search("cho lon", True)[0] == ("V1-0000-1.jpg", True)
    assert dict(_search("lớn chợ", False)) == {"V1-0000-1.jpg" : False}   # scattered words
    assert len(_search("(", False)) == len(TEXTS)                         # the quirk: no word, every frame
    assert _search("", False) == [] and _search("   ", True) == []


@pytest.mark.parametrize("strip", [False, True])
def test_several_terms_give_each_term_its_own_search_result(strip) :
    terms = ["chợ", "nước", "quán ăn", "THỂ THAO", "không có"]
    found = ocr_search.search_terms(terms, strip)
    for index, term in enumerate(terms) :
        assert _ordered(found, index) == _search(term, strip), term


def test_matches_are_listed_in_term_order_and_carry_the_display_length() :
    found = ocr_search.search_terms(["nước", "lửa", "đường"], False)
    length, matches = found["V2-0000-3.jpg"]
    assert length == len(TEXTS["V2-0000-3.jpg"]) and matches == [(0, True), (1, True), (2, True)]
    assert found["V2-0000-1.jpg"] == (len(TEXTS["V2-0000-1.jpg"]), [(0, True)])
    assert "V1-0000-1.jpg" not in found


def test_exact_and_folded_modes_differ_only_by_the_folding() :
    assert set(ocr_search.search_terms(["nuoc"], False)) == {"V2-0000-2.jpg"}
    assert set(ocr_search.search_terms(["nuoc"], True)) == {"V2-0000-1.jpg", "V2-0000-2.jpg", "V2-0000-3.jpg"}
    assert set(ocr_search.search_terms(["NƯỚC"], False)) == {"V2-0000-1.jpg", "V2-0000-3.jpg"}  # uppercase is lowered


def test_word_order_changes_only_the_phrase_flag() :
    same_order = ocr_search.search_terms(["quán ăn"], False)
    swapped = ocr_search.search_terms(["ăn quán"], False)
    assert set(same_order) == set(swapped) == {"V1-0000-1.jpg", "V1-0000-2.jpg"}   # the same frames hold both words
    assert all(matches == [(0, True)] for _length, matches in same_order.values())
    assert all(matches == [(0, False)] for _length, matches in swapped.values())
    found = ocr_search.search_terms(["lớn chợ"], False)
    assert found == {"V1-0000-1.jpg" : (len(TEXTS["V1-0000-1.jpg"]), [(0, False)])}


def test_a_term_without_word_characters_is_a_literal_phrase_next_to_other_terms() :
    found = ocr_search.search_terms(["(", "chợ"], False)
    assert [name for name, (_length, matches) in found.items() if any(term == 0 for term, _ in matches)] == ["V1-0000-3.jpg"]
    assert found["V1-0000-3.jpg"][1] == [(0, True)]
    assert set(found) == {"V1-0000-1.jpg", "V1-0000-2.jpg", "V1-0000-3.jpg", "V3-0000-3.jpg"}
    assert set(ocr_search.search_terms(["-", "a"], False)) >= {"V2-0000-3.jpg"}      # "-" appears in one frame only
    assert "V2-0000-1.jpg" not in {name for name, (_l, m) in ocr_search.search_terms(["-", "zzz"], False).items()}


def test_a_blank_term_matches_nothing_and_does_not_count_as_a_second_term() :
    assert ocr_search.search_terms(["", "  "], False) == {}
    only_paren = ocr_search.search_terms(["", "("], False)
    assert set(only_paren) == set(TEXTS)                       # one real term: search()'s quirk stays
    assert all(matches[0][0] == 1 for _length, matches in only_paren.values())  # indices follow the input list
    assert ocr_search.search_terms([], False) == {}


def test_search_itself_is_untouched() :
    """search() keeps its own contract: rows, counts and the all-words rule."""
    result = ocr_search.search("chợ lớn", limit = 5, strip_diacritics = False)
    assert (result["phrase_matches"], result["all_word_matches"]) == (1, 1)
    assert result["results"][0]["name"] == "V1-0000-1.jpg" and result["results"][0]["exact_phrase"] is True
