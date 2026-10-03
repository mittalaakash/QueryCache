from scripts.confluence_read_page import to_text


def test_to_text_paragraphs_become_lines():
    assert to_text("<p>one</p><p>two</p>") == "one\ntwo"


def test_to_text_list_items_get_dash_marker():
    assert to_text("<ul><li><p>a</p></li><li><p>b</p></li></ul>") == "- a\n- b"


def test_to_text_table_cells_are_pipe_separated():
    html = "<table><tr><th>k</th><th>v</th></tr><tr><td>x</td><td>1</td></tr></table>"
    assert to_text(html) == "k | v |\nx | 1 |"
