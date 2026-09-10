from app.ingestion.pipeline import decide_action


def test_decide_action_new_document_is_insert():
    assert decide_action(None, "hash1") == "insert"


def test_decide_action_unchanged_hash_is_skip():
    assert decide_action("hash1", "hash1") == "skip"


def test_decide_action_changed_hash_is_update():
    assert decide_action("hash1", "hash2") == "update"
