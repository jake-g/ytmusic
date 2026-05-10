"""Unit tests for ytmusic_library.py."""

import unittest
from unittest.mock import MagicMock
from unittest.mock import patch

import pandas as pd

from ytmusic_library import YTMusicPlaylists


class TestYTMusicUtils(unittest.TestCase):
    """Tests for utility functions and logic in YTMusicPlaylists."""

    def setUp(self):
        # Create a mock instance for tests that need self attributes
        # We patch __init__ so it doesn't try to connect to the API or load files
        with patch.object(YTMusicPlaylists, '__init__', return_value=None):
            self.yt_pl = YTMusicPlaylists()
            self.yt_pl._like_playlist_titles = ["my favorites", "top hits"]
            self.yt_pl.playlists = pd.DataFrame([
                {'title': 'my favorites', 'playlistId': 'pl1', 'author': 'Jake G', 'count': 10},
                {'title': 'rock radio', 'playlistId': 'pl2', 'author': 'Jake G', 'count': 20},
                {'title': 'zz not like rap', 'playlistId': 'pl3', 'author': 'Jake G', 'count': 5},
                {'title': 'great albums', 'playlistId': 'pl4', 'author': 'Jake G', 'count': 12},
                {'title': 'zz skip this', 'playlistId': 'pl5', 'author': 'Jake G', 'count': 0},
                {'title': 'YT Generated Mix', 'playlistId': 'pl6', 'author': float('nan'), 'count': 50}
            ])

    def test_is_valid_date(self):
        self.assertTrue(self.yt_pl._is_valid_date("2020-01-01"))
        self.assertFalse(self.yt_pl._is_valid_date("2020-01-32"))
        self.assertFalse(self.yt_pl._is_valid_date("2020/01/01"))
        self.assertFalse(self.yt_pl._is_valid_date("not-a-date"))

    def test_decode(self):
        self.assertEqual(self.yt_pl._decode("Hello"), "Hello")
        self.assertEqual(self.yt_pl._decode(None), "")
        self.assertEqual(self.yt_pl._decode("Björk"), "Björk")

    def test_playlist_is_not_like(self):
        self.assertTrue(self.yt_pl._playlist_is_not_like("zz not like music"))
        self.assertTrue(self.yt_pl._playlist_is_not_like("music dislike"))
        self.assertTrue(self.yt_pl._playlist_is_not_like("thumbs_down"))
        self.assertFalse(self.yt_pl._playlist_is_not_like("my favorite music"))
        self.assertFalse(self.yt_pl._playlist_is_not_like("_private_playlist"))

    def test_playlist_is_albums(self):
        self.assertTrue(self.yt_pl._playlist_is_albums("my_albums"))
        self.assertTrue(self.yt_pl._playlist_is_albums("great albums"))
        self.assertFalse(self.yt_pl._playlist_is_albums("my favorite songs"))

    def test_playlist_is_like(self):
        self.assertTrue(self.yt_pl._playlist_is_like("my favorites"))
        self.assertTrue(self.yt_pl._playlist_is_like("thumbs up tracks"))
        self.assertTrue(self.yt_pl._playlist_is_like(" top 100"))
        self.assertFalse(self.yt_pl._playlist_is_like("zz not like rap"))
        self.assertFalse(self.yt_pl._playlist_is_like("rock radio"))
        self.assertFalse(self.yt_pl._playlist_is_like("_ignored"))

    def test_playlist_is_radio(self):
        self.assertTrue(self.yt_pl._playlist_is_radio("rock radio"))
        self.assertTrue(self.yt_pl._playlist_is_radio("jazz_radio"))
        self.assertTrue(self.yt_pl._playlist_is_radio("lofi_indifferent"))
        self.assertFalse(self.yt_pl._playlist_is_radio("my favorites"))

    def test_playlist_skip_starts_with(self):
        self.assertTrue(self.yt_pl._playlist_skip_starts_with("zz skip this"))
        self.assertFalse(self.yt_pl._playlist_skip_starts_with("my favorites"))

    def test_infer_playlist_kind(self):
        # Mocking row from playlists DataFrame
        rows = [self.yt_pl.playlists.iloc[i] for i in range(len(self.yt_pl.playlists))]

        kinds = [self.yt_pl.infer_playlist_kind(r) for r in rows]

        expected_kinds = [
            'LIKE',          # my favorites
            'INDIFFERENT',   # rock radio
            'SKIP',          # zz not like rap (starts with 'zz' which is in SKIP_STARTS_WITH_TOKS)
            'ALBUM',         # great albums
            'SKIP',          # zz skip this
            'YT_GENERATED'   # YT Generated Mix (nan author)
        ]
        self.assertEqual(kinds, expected_kinds)

    def test_is_playlist_kind_ok(self):
        # LIKE needs > 80%
        self.assertTrue(self.yt_pl._is_playlist_kind_ok('LIKE', 85))
        self.assertFalse(self.yt_pl._is_playlist_kind_ok('LIKE', 75))

        # NOT_LIKE needs < 20%
        self.assertTrue(self.yt_pl._is_playlist_kind_ok('NOT_LIKE', 10))
        self.assertFalse(self.yt_pl._is_playlist_kind_ok('NOT_LIKE', 30))

if __name__ == "__main__":
    unittest.main()
