from beecli import speakers, to_ms, unwrap, utterances, word_count


def test_to_ms_accepts_every_format():
    ms = 1760800000000
    assert to_ms(ms) == ms
    assert to_ms(ms / 1000) == ms
    assert to_ms(str(ms)) == ms
    assert to_ms("2025-10-18T15:06:40Z") == ms
    assert to_ms("2025-10-18T15:06:40+00:00") == ms
    for bad in (None, "", "soon", 42, True):
        assert to_ms(bad) is None


def test_utterances_prefer_final_and_sort():
    conv = {"conversation": {"transcriptions": [
        {"realtime": True, "utterances": [{"text": "draft", "speaker": "s1", "spoken_at": 1}]},
        {"realtime": False, "utterances": [
            {"id": 2, "text": " second ", "speaker": "SPEAKER_2", "spoken_at": "2025-10-18T15:06:50Z"},
            {"id": 1, "text": "first", "speaker": "SPEAKER_1", "spoken_at": 1760800000},
            {"id": 3, "text": "  ", "speaker": "SPEAKER_1", "spoken_at": 1760800020},
            {"id": 4, "text": "no speaker", "start": 1760800030000},
        ]},
    ]}}
    items = utterances(conv)
    assert [u["text"] for u in items] == ["first", "second", "no speaker"]
    assert items[0]["at"] == 1760800000000 and items[2]["speaker"] == "unknown"
    assert word_count(items) == 4
    assert speakers(items) == ["SPEAKER_1", "SPEAKER_2", "unknown"]


def test_empty_and_unwrap():
    assert utterances({}) == [] and utterances({"transcriptions": []}) == []
    assert unwrap({"conversations": [1]}, "conversations") == [1]
    assert unwrap([1], "conversations") == [1]
