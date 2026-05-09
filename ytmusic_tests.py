"""Unit tests for ytmusic_library.py."""

import unittest

from ytmusic_library import YTMusicPlaylists


class TestYTMusicUtils(unittest.TestCase):
  """Tests for utility functions in YTMusicPlaylists."""

  def test_is_valid_date(self):
    self.assertTrue(YTMusicPlaylists._is_valid_date(None, "2020-01-01"))
    self.assertFalse(YTMusicPlaylists._is_valid_date(None, "2020-01-32"))
    self.assertFalse(YTMusicPlaylists._is_valid_date(None, "2020/01/01"))
    self.assertFalse(YTMusicPlaylists._is_valid_date(None, "not-a-date"))

  def test_decode(self):
    self.assertEqual(YTMusicPlaylists._decode(None, "Hello"), "Hello")
    self.assertEqual(YTMusicPlaylists._decode(None, None), "")
    self.assertEqual(YTMusicPlaylists._decode(None, "Björk"), "Björk")

  def test_playlist_is_not_like(self):
    self.assertTrue(YTMusicPlaylists._playlist_is_not_like(None, "zz not like music"))
    self.assertTrue(YTMusicPlaylists._playlist_is_not_like(None, "music dislike"))
    self.assertFalse(YTMusicPlaylists._playlist_is_not_like(None, "my favorite music"))
    self.assertFalse(YTMusicPlaylists._playlist_is_not_like(None, "_private_playlist"))

  def test_playlist_is_albums(self):
    self.assertTrue(YTMusicPlaylists._playlist_is_albums(None, "my_albums"))
    self.assertTrue(YTMusicPlaylists._playlist_is_albums(None, "great albums"))
    self.assertFalse(YTMusicPlaylists._playlist_is_albums(None, "my favorite songs"))


if __name__ == "__main__":
  unittest.main()
