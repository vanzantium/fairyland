"""Tests for the drop-your-own-music layer."""

import pytest

from fairyland.app import create_app


@pytest.fixture
def client():
    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


@pytest.fixture
def music_dir(tmp_path, monkeypatch):
    d = tmp_path / "music"
    d.mkdir()
    (d / "first song.mp3").write_bytes(b"ID3fakeaudio")
    (d / "second.ogg").write_bytes(b"OggSfakeaudio")
    (d / "notes.txt").write_text("not audio")
    (d / "README.md").write_text("docs")
    monkeypatch.setenv("FAIRYLAND_MUSIC_DIR", str(d))
    return d


class TestMusicList:
    def test_only_audio_files_listed(self, client, music_dir):
        data = client.get("/music/list").get_json()
        names = {t["id"] for t in data["tracks"]}
        assert names == {"first song.mp3", "second.ogg"}
        titles = {t["title"] for t in data["tracks"]}
        assert titles == {"first song", "second"}

    def test_empty_when_dir_missing(self, client, monkeypatch, tmp_path):
        monkeypatch.setenv("FAIRYLAND_MUSIC_DIR", str(tmp_path / "nowhere"))
        data = client.get("/music/list").get_json()
        assert data["tracks"] == []

    def test_no_metadata_beyond_filename(self, client, music_dir):
        data = client.get("/music/list").get_json()
        for t in data["tracks"]:
            assert set(t.keys()) == {"id", "title"}


class TestMusicFile:
    def test_serves_listed_track(self, client, music_dir):
        r = client.get("/music/file/second.ogg")
        assert r.status_code == 200
        assert r.data == b"OggSfakeaudio"

    def test_unknown_track_404(self, client, music_dir):
        r = client.get("/music/file/ghost.mp3")
        assert r.status_code == 404

    def test_non_audio_rejected(self, client, music_dir):
        # the txt exists in the folder but is not a scanned track
        r = client.get("/music/file/notes.txt")
        assert r.status_code == 404

    def test_traversal_rejected(self, client, music_dir):
        r = client.get("/music/file/..%2FREADME.md")
        assert r.status_code == 404


class TestShuffleArc:
    """The full dealer arc through the API: 3 tracks -> silence+anchor -> exit."""

    def test_three_tracks_then_silence_then_exit(self, client, music_dir):
        sid = client.post("/session", json={"mode": "KID"}).get_json()["session_id"]
        tracks = client.get("/music/list").get_json()["tracks"]
        r = client.post("/shuffle/start", json={"session_id": sid, "tracks": tracks})
        assert r.get_json()["started"] is True

        played = []
        for _ in range(3):
            out = client.post("/shuffle/next", json={"session_id": sid}).get_json()
            assert out.get("track"), "expected a track"
            played.append(out["track"]["id"])

        silence = client.post("/shuffle/next", json={"session_id": sid}).get_json()
        assert silence["silence"] is True
        assert silence["anchor_cue"] is True

        exit_out = client.post("/shuffle/next", json={"session_id": sid}).get_json()
        assert exit_out["exit_cue"] is True
