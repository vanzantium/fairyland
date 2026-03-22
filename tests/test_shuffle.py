"""Tests for the Proper Shuffle."""

from fairyland.engine.shuffle import ProperShuffle, Track


def _make_playlist(n=10):
    return [Track(id=str(i), title=f"Track {i}") for i in range(n)]


class TestProperShuffle:
    def test_golden_ratio_no_clustering(self):
        """Tracks should spread across the playlist, not cluster."""
        playlist = _make_playlist(10)
        shuffle = ProperShuffle(playlist)
        indices = []
        for _ in range(3):  # get 3 tracks before silence
            out = shuffle.next()
            assert out.track is not None
            indices.append(int(out.track.id))
        # all three should be different tracks
        assert len(set(indices)) == 3

    def test_silence_after_three_tracks(self):
        playlist = _make_playlist(10)
        shuffle = ProperShuffle(playlist)
        # play 3 tracks
        for _ in range(3):
            out = shuffle.next()
            assert out.track is not None
            assert not out.silence
        # 4th call should be silence
        out = shuffle.next()
        assert out.silence
        assert out.anchor_cue

    def test_exit_after_silence(self):
        playlist = _make_playlist(10)
        shuffle = ProperShuffle(playlist)
        for _ in range(3):
            shuffle.next()
        shuffle.next()  # silence
        out = shuffle.next()  # should signal exit
        assert out.exit_cue

    def test_empty_playlist(self):
        shuffle = ProperShuffle([])
        out = shuffle.next()
        assert out.exit_cue

    def test_reset(self):
        playlist = _make_playlist(5)
        shuffle = ProperShuffle(playlist)
        for _ in range(3):
            shuffle.next()
        shuffle.reset()
        out = shuffle.next()
        assert out.track is not None
        assert not out.silence
