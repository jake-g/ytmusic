"""Unit tests for ytmusic_library.py."""

import os
import shutil
import tempfile
import unittest
from unittest.mock import MagicMock
from unittest.mock import patch

import pandas as pd

from ytmusic_library import YTMusicPlaylists


class TestYTMusicUtils(unittest.TestCase):
    """Tests for utility functions and logic in YTMusicPlaylists."""

    def setUp(self):
        # Create a temporary directory for test TSV files to avoid overwriting real data
        self.test_dir = tempfile.mkdtemp()

        # Create a mock instance for tests that need self attributes
        # We patch __init__ so it doesn't try to connect to the API or load files
        with patch.object(YTMusicPlaylists, '__init__', return_value=None):
            self.yt_pl = YTMusicPlaylists()
            self.yt_pl._like_playlist_titles = ["my favorites", "top hits"]
            self.yt_pl.playlists = pd.DataFrame([
                {'title': 'my favorites', 'playlistId': 'pl1',
                    'author': 'Jake G', 'count': 10},
                {'title': 'rock radio', 'playlistId': 'pl2',
                    'author': 'Jake G', 'count': 20},
                {'title': 'zz not like rap', 'playlistId': 'pl3',
                    'author': 'Jake G', 'count': 5},
                {'title': 'great albums', 'playlistId': 'pl4',
                    'author': 'Jake G', 'count': 12},
                {'title': 'zz skip this', 'playlistId': 'pl5',
                    'author': 'Jake G', 'count': 0},
                {'title': 'YT Generated Mix', 'playlistId': 'pl6',
                    'author': float('nan'), 'count': 50}
            ])
            self.yt_pl.yt = MagicMock()
            self.yt_pl.playlist_limit = 4500
            self.yt_pl.playlist_tsv_dir = self.test_dir
            self.yt_pl.like_tsv = os.path.join(self.test_dir, '_liked_tracks.tsv')
            self.yt_pl.not_like_tsv = os.path.join(self.test_dir, '_not_liked_tracks.tsv')
            self.yt_pl.track_db_tsv = os.path.join(self.test_dir, '_tracks_db.tsv')
            self.yt_pl.duplicate_tracks_tsv = os.path.join(self.test_dir, '_duplicate_tracks.tsv')
            self.yt_pl.radio_count_file = os.path.join(self.test_dir, '_playlist_radio_counts.tsv')
            self.yt_pl.like_cleanup_file = os.path.join(self.test_dir, '_ytmusic_cleanup_like_playlists_results.tsv')
            self.yt_pl.radio_cleanup_file = os.path.join(self.test_dir, '_ytmusic_cleanup_radio_playlists_results.tsv')
            self.yt_pl.cleanup_counters_file = os.path.join(self.test_dir, '_ytmusic_cleanup_playlist_counters.tsv')

            self.yt_pl._info_cache = {}
            self.yt_pl.banned_vid_set = frozenset(['banned_1'])
            self.yt_pl._radio_to_like_map = pd.DataFrame([
                {'radio_playlist': 'rock radio', 'like_playlist': 'my favorites'}
            ])
            self.yt_pl.playlist_titles = frozenset(
                ['my favorites', 'rock radio', 'zz not like rap'])

    def tearDown(self):
        # Clean up the temporary directory after each test
        shutil.rmtree(self.test_dir)

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
        rows = [self.yt_pl.playlists.iloc[i]
                for i in range(len(self.yt_pl.playlists))]

        kinds = [self.yt_pl.infer_playlist_kind(r) for r in rows]

        expected_kinds = [
            'LIKE',          # my favorites
            'INDIFFERENT',   # rock radio
            # zz not like rap (starts with 'zz' which is in SKIP_STARTS_WITH_TOKS)
            'SKIP',
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

    def test_track_db_dedupe(self):
        """Test the three levels of track database deduplication."""
        data = {
            'title': ['Song A', 'Song A', 'Song A', 'Song B'],
            'artist': ['Artist A', 'Artist A', 'Artist A', 'Artist B'],
            'album': ['Album A', 'Album A', 'Album A', 'Album B'],
            'playlists': ['List 1', 'List 2', 'List 1', 'List 1'],
            'inLibrary': [True, False, True, True],
            'artistId': ['ID_A', 'ID_A', 'ID_A', 'ID_B'],
            'albumId': ['AL_A', 'AL_A', 'AL_A', 'AL_B']
        }
        df = pd.DataFrame(data, index=['vid_1', 'vid_1', 'vid_1', 'vid_2'])
        df.index.name = 'videoId'

        deduped = self.yt_pl._track_db_dedupe(df, keep='last')

        self.assertEqual(len(deduped), 2)
        self.assertIn('vid_1', deduped.index)
        self.assertIn('vid_2', deduped.index)
        self.assertEqual(deduped.loc['vid_1']['playlists'], 'List 1')
        self.assertEqual(deduped.loc['vid_1']['inLibrary'], True)

    @patch('os.replace')
    @patch('pandas.DataFrame.to_csv', autospec=True)
    def test_save_tsv_nan_handling_and_escaping(self, mock_to_csv, mock_os_replace):
        """Test that NaNs are converted to empty strings and special characters are escaped."""
        data = {
            'title': ['Song\tWith\tTabs', 'Normal Song', None],
            'artist': ['Artist A', 'Artist B', 'Artist C'],
            'album': ['Album\\With\\Backslash', 'Album B', float('nan')]
        }
        df = pd.DataFrame(data, index=['vid_1', 'vid_2', 'vid_3'])
        df.index.name = 'videoId'

        self.yt_pl._save_tsv(df, 'dummy_path.tsv', index=True)

        called_df = mock_to_csv.call_args[0][0] if mock_to_csv.call_args else None
        self.assertIsNotNone(called_df)

        # Verify NaN/None is filled with empty string
        self.assertEqual(called_df.loc['vid_3']['title'], '')
        self.assertEqual(called_df.loc['vid_3']['album'], '')

        # Verify tabs and backslashes are replaced
        self.assertEqual(called_df.loc['vid_1']['title'], 'Song With Tabs')
        self.assertEqual(called_df.loc['vid_1']
                         ['album'], 'Album/With/Backslash')

    def test_playlist_loc_first(self):
        """Test finding a playlist by column and value."""
        # Unique match
        res = self.yt_pl._playlist_loc_first('title', 'rock radio')
        self.assertIsNotNone(res)
        self.assertEqual(res['playlistId'], 'pl2')

        # No match
        res_none = self.yt_pl._playlist_loc_first('title', 'nonexistent')
        self.assertIsNone(res_none)

        # Multiple matches (should return first)
        self.yt_pl.playlists = pd.concat([
            self.yt_pl.playlists,
            pd.DataFrame(
                [{'title': 'rock radio', 'playlistId': 'pl2_dup', 'author': 'Jake G', 'count': 5}])
        ], ignore_index=True)
        res_dup = self.yt_pl._playlist_loc_first('title', 'rock radio')
        self.assertEqual(res_dup['playlistId'], 'pl2')

    def test_parse_tracks(self):
        """Test parsing raw track metadata from the API."""
        raw_tracks = [
            {
                'id': 'vid_123',
                'title': 'Song One',
                'artists': [{'name': 'Artist A', 'id': 'artist_a'}],
                'album': {'name': 'Album A', 'id': 'album_a'},
                'likeStatus': 'LIKE'
            },
            {
                'videoId': 'vid_456',
                'title': 'Song Two',
                'artists': [],
                'album': None,
                'likeStatus': 'INDIFFERENT'
            }
        ]
        parsed = self.yt_pl.parse_tracks(raw_tracks)

        self.assertEqual(len(parsed), 2)

        # Verify first track
        self.assertEqual(parsed.iloc[0]['videoId'], 'vid_123')
        self.assertEqual(parsed.iloc[0]['artist'], 'Artist A')
        self.assertEqual(parsed.iloc[0]['artistId'], 'artist_a')
        self.assertEqual(parsed.iloc[0]['album'], 'Album A')
        self.assertEqual(parsed.iloc[0]['albumId'], 'album_a')

        # Verify second track (missing/empty fields)
        self.assertEqual(parsed.iloc[1]['videoId'], 'vid_456')
        self.assertTrue(pd.isna(parsed.iloc[1]['artist']))
        self.assertTrue(pd.isna(parsed.iloc[1]['artistId']))
        self.assertEqual(parsed.iloc[1]['album'], '')
        self.assertTrue(pd.isna(parsed.iloc[1]['albumId']))

    def test_playlist_remove_duplicates(self):
        """Test removing duplicate and banned tracks from a playlist."""
        pl_info = {
            'id': 'pl_dup_1',
            'title': 'My Playlist',
            'tracks': [
                {'videoId': 'vid_1', 'setVideoId': 'set_1'},
                {'videoId': 'vid_2', 'setVideoId': 'set_2'},
                {'videoId': 'vid_1', 'setVideoId': 'set_3'},  # Duplicate of vid_1
                {'videoId': 'banned_1', 'setVideoId': 'set_4'},  # Banned track
            ]
        }

        # Call the method with duplicate_threshold = 1
        self.yt_pl.playlist_remove_duplicates(
            pl_info, duplicate_threshold=1, verbose=False)

        # Verify that yt.remove_playlist_items was called with the correct duplicate & banned tracks
        self.yt_pl.yt.remove_playlist_items.assert_called_once_with(
            playlistId='pl_dup_1',
            videos=[
                {'videoId': 'vid_1', 'setVideoId': 'set_3'},
                {'videoId': 'banned_1', 'setVideoId': 'set_4'}
            ]
        )

    @patch.object(YTMusicPlaylists, 'playlist_get_info')
    def test_clean_up_radio_playlist(self, mock_get_info):
        """Test splitting a radio playlist into LIKE vs RADIO and removing dislikes."""
        radio_pl_info = {
            'id': 'pl2',
            'title': 'rock radio',
            'tracks': [
                {'videoId': 'vid_like_1', 'likeStatus': 'LIKE'},
                {'videoId': 'vid_dislike_1', 'likeStatus': 'DISLIKE'},
                {'videoId': 'vid_indifferent_1', 'likeStatus': 'INDIFFERENT'},
                # Banned/not-liked
                {'videoId': 'banned_1', 'likeStatus': 'INDIFFERENT'}
            ]
        }

        # Mock get_info calls
        mock_get_info.side_effect = lambda playlist_id, **kwargs: {
            'pl2': radio_pl_info,
            'pl1': {'id': 'pl1', 'title': 'my favorites', 'tracks': []}
        }.get(playlist_id, {})

        # Set up mock status returned by add_playlist_items
        self.yt_pl.yt.add_playlist_items.return_value = {
            'status': 'STATUS_SUCCEEDED'}
        self.yt_pl.yt.remove_playlist_items.return_value = 'STATUS_SUCCEEDED'

        # Run cleanup
        counters = self.yt_pl.clean_up_radio_playlist(
            pl_info=radio_pl_info,
            verbose=False,
            move_like=True,
            min_num_like=0,  # Force move even if only 1 like
            create_like_playlist=True,
            remove_dislike=True,
            remove_not_like=True
        )

        # Verify counters
        self.assertEqual(counters['moved_like'], 1)
        self.assertEqual(counters['removed_dislike'], 1)
        self.assertEqual(counters['removed_not_like'], 1)

        # Verify that LIKE tracks were added to the target "my favorites" playlist (pl1)
        self.yt_pl.yt.add_playlist_items.assert_called_once_with(
            playlistId='pl1',
            videoIds=['vid_like_1'],
            duplicates=False
        )

        # Verify that the moved LIKE track was removed from the radio playlist
        # AND that the DISLIKE + NOT_LIKE tracks were removed
        self.yt_pl.yt.remove_playlist_items.assert_any_call(
            'pl2',
            [{'videoId': 'vid_like_1', 'likeStatus': 'LIKE'}]
        )
        self.yt_pl.yt.remove_playlist_items.assert_any_call(
            'pl2',
            [
                {'videoId': 'banned_1', 'likeStatus': 'INDIFFERENT'},
                {'videoId': 'vid_dislike_1', 'likeStatus': 'DISLIKE'}
            ]
        )

    @patch.object(YTMusicPlaylists, 'playlist_from_yt_vids')
    @patch.object(YTMusicPlaylists, '_read_tsv')
    def test_playlist_from_tsv(self, mock_read_tsv, mock_from_vids):
        """Test creating a playlist from a TSV file, including banned track filtering."""
        # Mock TSV data
        data = {
            'videoId': ['vid_1', 'vid_2', 'banned_1', 'vid_2']
        }
        df = pd.DataFrame(
            data, index=['track_1', 'track_2', 'track_3', 'track_4'])
        df.index.name = 'trackId'
        mock_read_tsv.return_value = df

        # 1. Test standard run (should filter out 'banned_1' and duplicates)
        self.yt_pl.playlist_from_tsv(
            'test_playlist.tsv', ignore_banned=False, sleep=0)

        # Verify it read the correct file
        mock_read_tsv.assert_called_with('test_playlist.tsv', index_col=0)

        # Verify it called playlist_from_yt_vids with the filtered set: {'vid_1', 'vid_2'}
        called_vids = mock_from_vids.call_args[0][0]
        self.assertEqual(set(called_vids), {'vid_1', 'vid_2'})
        self.assertNotIn('banned_1', called_vids)

        # 2. Test with ignore_banned=True (should keep 'banned_1')
        mock_from_vids.reset_mock()
        self.yt_pl.playlist_from_tsv(
            'test_playlist.tsv', ignore_banned=True, sleep=0)
        called_vids_ignored = mock_from_vids.call_args[0][0]
        self.assertEqual(set(called_vids_ignored), {
                         'vid_1', 'vid_2', 'banned_1'})

    @patch.object(YTMusicPlaylists, '_save_tsv')
    @patch.object(YTMusicPlaylists, 'parse_playlist')
    def test_save_playlist_tsv(self, mock_parse, mock_save_tsv):
        """Test parsing and exporting a playlist to TSV, including dislike removal."""
        # Mock track DataFrame
        tracks_data = {
            'title': ['Song A', 'Song B', 'Song C'],
            'artist': ['Artist A', 'Artist B', 'Artist C'],
            'album': ['Album A', 'Album B', 'Album C'],
            'likeStatus': ['LIKE', 'DISLIKE', 'INDIFFERENT'],
            'videoId': ['vid_1', 'vid_2', 'vid_3'],
            'albumId': ['al_1', 'al_2', 'al_3'],
            'artistId': ['ar_1', 'ar_2', 'ar_3']
        }
        df = pd.DataFrame(tracks_data)
        metadata = {'id': 'pl_123', 'title': 'My Playlist'}
        mock_parse.return_value = (df, metadata)

        pl_info = {'title': 'My Playlist', 'playlistId': 'pl_123'}

        # Test with remove_disliked=True
        tracks, meta = self.yt_pl.save_playlist_tsv(
            pl_info, remove_disliked=True)

        # Verify that the DISLIKE track (vid_2) was removed via API
        self.yt_pl.yt.remove_playlist_items.assert_called_once()

        # Verify that the saved DataFrame doesn't have the DISLIKE track
        self.assertEqual(len(tracks), 2)
        self.assertNotIn('vid_2', tracks['videoId'].values)

        # Verify that _save_tsv was called with the correct path and sorted tracks
        expected_path = os.path.join(
            self.yt_pl.playlist_tsv_dir, "My Playlist.tsv")
        mock_save_tsv.assert_called_once_with(
            unittest.mock.ANY, expected_path, index=False)

    @patch.object(YTMusicPlaylists, '_save_tsv')
    @patch.object(YTMusicPlaylists, 'parse_playlist')
    def test_save_playlist_tsv_not_owned(self, mock_parse, mock_save_tsv):
        """YT-generated mixes (owned=False, id=None) must not hit the API."""
        df = pd.DataFrame({
            'title': ['Song A', 'Song B'],
            'artist': ['Artist A', 'Artist B'],
            'album': ['Album A', 'Album B'],
            'likeStatus': ['LIKE', 'DISLIKE'],
            'videoId': ['vid_1', 'vid_2'],
            'albumId': ['al_1', 'al_2'],
            'artistId': ['ar_1', 'ar_2'],
        })
        metadata = {'id': None, 'owned': False, 'title': 'Chill Supermix'}
        mock_parse.return_value = (df, metadata)

        tracks, _ = self.yt_pl.save_playlist_tsv(
            {'title': 'Chill Supermix', 'playlistId': 'RDTMAK'},
            remove_disliked=True)

        self.yt_pl.yt.remove_playlist_items.assert_not_called()
        # Track stays on YT, so it stays in the TSV too.
        self.assertEqual(len(tracks), 2)
        mock_save_tsv.assert_called_once()

    @patch('os.path.exists')
    @patch.object(YTMusicPlaylists, 'playlist_get_info')
    @patch.object(YTMusicPlaylists, 'save_playlist_tsv')
    @patch.object(YTMusicPlaylists, '_read_tsv')
    def test_backup_playlists_incremental(self, mock_read_tsv, mock_save, mock_get_info, mock_exists):
        """Test that playlist backup skips API fetch if local TSV count matches API count."""
        mock_exists.return_value = True

        # Local TSV has 10 tracks with all required columns
        local_df = pd.DataFrame([
            {
                'videoId': f'vid_{i}',
                'artist': f'Artist {i}',
                'album': f'Album {i}',
                'title': f'Song {i}',
                'likeStatus': 'LIKE',
                'albumId': f'al_{i}',
                'artistId': f'ar_{i}'
            } for i in range(10)
        ])
        # We need to return different DataFrames based on the path.
        # But to keep it simple, we can return local_df (len 10) for all.
        # pl1 ('my favorites') has count=10 (matches local_df len 10) -> should skip!
        # pl2 ('rock radio') has count=20 (mismatches local_df len 10) -> should fetch!
        mock_read_tsv.return_value = local_df

        # Mock save_playlist_tsv to avoid actual saves, returning all metadata_cols
        mock_metadata = {
            'id': 'pl2',
            'title': 'rock radio',
            'privacy': 'PUBLIC',
            'description': 'rock',
            'trackCount': 20,
            'author': 'Jake G'
        }
        mock_save.return_value = (local_df, mock_metadata)

        # Call backup (we set include_library_tracks=False to avoid empty library tracks errors)
        self.yt_pl.backup_playlists_and_collect_tracks(
            remove_disliked=False, include_library_tracks=False)

        # Verify pl1 (id='pl1') was skipped (not in get_info calls)
        # Verify pl2 (id='pl2') was fetched (is in get_info calls)
        called_playlist_ids = [call[0][0] for call in mock_get_info.call_args_list]
        self.assertNotIn('pl1', called_playlist_ids)
        self.assertIn('pl2', called_playlist_ids)

    @patch('ytmusic_library.PLAYLIST_BACKUP_FULL_RUN', True)
    @patch('os.path.exists')
    @patch.object(YTMusicPlaylists, 'playlist_get_info')
    @patch.object(YTMusicPlaylists, 'save_playlist_tsv')
    @patch.object(YTMusicPlaylists, '_read_tsv')
    def test_backup_playlists_full_run(self, mock_read_tsv, mock_save, mock_get_info, mock_exists):
        """Test that playlist backup fetches all playlists from API if PLAYLIST_BACKUP_FULL_RUN is True."""
        mock_exists.return_value = True

        local_df = pd.DataFrame([
            {
                'videoId': f'vid_{i}',
                'artist': f'Artist {i}',
                'album': f'Album {i}',
                'title': f'Song {i}',
                'likeStatus': 'LIKE',
                'albumId': f'al_{i}',
                'artistId': f'ar_{i}'
            } for i in range(10)
        ])
        mock_read_tsv.return_value = local_df

        # Mock save_playlist_tsv to avoid actual saves
        mock_metadata_1 = {
            'id': 'pl1',
            'title': 'my favorites',
            'privacy': 'PUBLIC',
            'description': 'favs',
            'trackCount': 10,
            'author': 'Jake G'
        }
        mock_metadata_2 = {
            'id': 'pl2',
            'title': 'rock radio',
            'privacy': 'PUBLIC',
            'description': 'rock',
            'trackCount': 20,
            'author': 'Jake G'
        }
        mock_save.side_effect = [(local_df, mock_metadata_1), (local_df, mock_metadata_2)]

        # Call backup
        self.yt_pl.backup_playlists_and_collect_tracks(
            remove_disliked=False, include_library_tracks=False)

        # Verify that both pl1 and pl2 were fetched from the API (since FULL_RUN is True)
        called_playlist_ids = [call[0][0] for call in mock_get_info.call_args_list]
        self.assertIn('pl1', called_playlist_ids)
        self.assertIn('pl2', called_playlist_ids)

    @patch('ytmusic_library.CHECKPOINT_INTERVAL', 2)
    @patch.object(YTMusicPlaylists, '_track_db_get_track_info')
    @patch.object(YTMusicPlaylists, '_save_tsv')
    @patch.object(YTMusicPlaylists, '_track_db_dedupe')
    def test_track_db_update_checkpointing(self, mock_dedupe, mock_save_tsv, mock_get_info):
        """Test that _track_db_update saves checkpoints and final database correctly."""
        track_db = pd.DataFrame(columns=['title', 'artist', 'album'])
        new_tracks = pd.DataFrame([
            {'title': 'Song 1', 'artist': 'Artist 1', 'album': 'Album 1'},
            {'title': 'Song 2', 'artist': 'Artist 2', 'album': 'Album 2'},
            {'title': 'Song 3', 'artist': 'Artist 3', 'album': 'Album 3'}
        ], index=['vid_1', 'vid_2', 'vid_3'])
        new_tracks.index.name = 'videoId'

        mock_get_info.side_effect = lambda row: {
            'videoId': row.name,
            'title': row['title'],
            'artist': row['artist'],
            'album': row['album']
        }
        mock_dedupe.side_effect = lambda df, **kwargs: df
        self.yt_pl.track_db_tsv = 'mock_track_db.tsv'

        self.yt_pl._track_db_update(track_db, new_tracks, verbose=True)

        # Verify checkpoint dedupe called with verbose=False
        mock_dedupe.assert_any_call(unittest.mock.ANY, keep='last', verbose=False)

        # Verify final dedupe called with default verbose=True
        mock_dedupe.assert_any_call(unittest.mock.ANY, keep='last')

        # Verify self._save_tsv was called for both checkpoint (i=2) and final save
        self.assertEqual(mock_save_tsv.call_count, 2)


    def test_remove_deleted_playlist_tsvs_safety_guard(self):
        """Test that prune is skipped if playlist list is empty or too small."""
        self.yt_pl.playlists = pd.DataFrame([])
        # Create a dummy TSV in the temp directory
        dummy_file = os.path.join(self.test_dir, "dummy_playlist.tsv")
        with open(dummy_file, "w", encoding="utf-8") as f:
            f.write("test")

        removed = self.yt_pl.remove_deleted_playlist_tsvs(dry_run=False)
        self.assertEqual(removed, [])
        self.assertTrue(os.path.exists(dummy_file))

    def test_remove_deleted_playlist_tsvs_pruning(self):
        """Test pruning deleted playlists while protecting active and internal TSVs."""
        # Active playlists: my favorites, rock radio, zz not like rap, great albums, zz skip this, YT Generated Mix
        active_file_1 = os.path.join(self.test_dir, "my favorites.tsv")
        active_file_2 = os.path.join(self.test_dir, "rock radio.tsv")
        deleted_file_1 = os.path.join(self.test_dir, "old deleted playlist.tsv")
        deleted_file_2 = os.path.join(self.test_dir, "purged mix.tsv")
        internal_file_1 = os.path.join(self.test_dir, "_tracks_db.tsv")
        internal_file_2 = os.path.join(self.test_dir, "_playlists.tsv")
        non_tsv_file = os.path.join(self.test_dir, "notes.txt")

        for f in [active_file_1, active_file_2, deleted_file_1, deleted_file_2,
                  internal_file_1, internal_file_2, non_tsv_file]:
            with open(f, "w", encoding="utf-8") as fh:
                fh.write("sample content")

        removed = self.yt_pl.remove_deleted_playlist_tsvs(dry_run=False)

        # Verify deleted files were removed
        self.assertIn("old deleted playlist.tsv", removed)
        self.assertIn("purged mix.tsv", removed)
        self.assertFalse(os.path.exists(deleted_file_1))
        self.assertFalse(os.path.exists(deleted_file_2))

        # Verify active and internal files were preserved
        self.assertTrue(os.path.exists(active_file_1))
        self.assertTrue(os.path.exists(active_file_2))
        self.assertTrue(os.path.exists(internal_file_1))
        self.assertTrue(os.path.exists(internal_file_2))
        self.assertTrue(os.path.exists(non_tsv_file))

    def test_remove_deleted_playlist_tsvs_dry_run(self):
        """Test that dry_run identifies deleted TSVs without removing them from disk."""
        deleted_file = os.path.join(self.test_dir, "abandoned_mix.tsv")
        with open(deleted_file, "w", encoding="utf-8") as f:
            f.write("sample")

        removed = self.yt_pl.remove_deleted_playlist_tsvs(dry_run=True)
        self.assertIn("abandoned_mix.tsv", removed)
        self.assertTrue(os.path.exists(deleted_file))

    def test_remove_deleted_playlist_tsvs_sanitization(self):
        """Parameterized test verifying special characters and sanitized quotes in titles."""
        cases = [
            ('Rock "Anthems"', "Rock 'Anthems'.tsv"),
            ("90's Grunge", "90's Grunge.tsv"),
            ("Special & Cool Radio", "Special & Cool Radio.tsv"),
        ]
        for raw_title, expected_filename in cases:
            with self.subTest(title=raw_title, filename=expected_filename):
                test_playlists = self.yt_pl.playlists.copy()
                test_playlists = pd.concat([test_playlists, pd.DataFrame([{
                    'title': raw_title,
                    'playlistId': 'pl_special',
                    'author': 'Jake G',
                    'count': 10
                }])], ignore_index=True)
                self.yt_pl.playlists = test_playlists

                test_path = os.path.join(self.test_dir, expected_filename)
                with open(test_path, "w", encoding="utf-8") as f:
                    f.write("content")

                removed = self.yt_pl.remove_deleted_playlist_tsvs(dry_run=False)
                self.assertNotIn(expected_filename, removed)
                self.assertTrue(os.path.exists(test_path))

    def test_playlist_get_info_unbrowsable_radio(self):
        """Test that KeyError: contents for unbrowsable radio mixes returns empty playlist cleanly."""
        self.yt_pl.yt.get_playlist.side_effect = KeyError("Unable to find 'contents'")
        res = self.yt_pl.playlist_get_info("VLRDEM87t6wGDSjPDwdghYsFky9g", use_cache=False)
        self.assertEqual(res['id'], "VLRDEM87t6wGDSjPDwdghYsFky9g")
        self.assertEqual(res['trackCount'], 0)
        self.assertEqual(res['tracks'], [])

    @patch.object(YTMusicPlaylists, 'get_playlist_counts')
    def test_update_radio_counts(self, mock_counts):
        """Test update_radio_counts calculates and writes _playlist_radio_counts.tsv."""
        mock_counts.return_value = pd.DataFrame([
            {'title': 'rock radio', 'track_count': 20, 'privacy': 'PUBLIC', 'playlist_id': 'pl2'}
        ])
        df = self.yt_pl.update_radio_counts(verbose=False, use_local_tsvs=True)
        self.assertEqual(len(df), 1)
        self.assertTrue(os.path.exists(self.yt_pl.radio_count_file))
        saved_df = pd.read_csv(self.yt_pl.radio_count_file, sep="\t")
        self.assertEqual(len(saved_df), 1)
        self.assertEqual(saved_df.iloc[0]['title'], 'rock radio')

    @patch.object(YTMusicPlaylists, 'clean_playlists')
    def test_run_playlist_cleanup(self, mock_clean):
        """Test run_playlist_cleanup executes clean_playlists and writes output files."""
        dummy_df = pd.DataFrame([{'result': 'ok'}])
        mock_clean.return_value = (dummy_df, dummy_df, dummy_df)
        res_like, res_radio, res_counters = self.yt_pl.run_playlist_cleanup(do_dry_run=True)
        self.assertEqual(len(res_like), 1)
        self.assertTrue(os.path.exists(self.yt_pl.like_cleanup_file))
        self.assertTrue(os.path.exists(self.yt_pl.radio_cleanup_file))
        self.assertTrue(os.path.exists(self.yt_pl.cleanup_counters_file))

    def test_album_get_info_and_search_album_caching(self):
        """Test album_get_info and search_album filter singles/years and cache in _info_cache."""
        self.yt_pl.yt.search.return_value = [
            {'browseId': 'b_single', 'type': 'Single', 'year': '2026'},
            {'browseId': 'b_2025', 'type': 'Album', 'year': '2025'},
            {'browseId': 'b_2026', 'type': 'Album', 'year': '2026'},
        ]
        self.yt_pl.yt.get_album.return_value = {
            'title': 'Matched 2026',
            'year': '2026',
            'trackCount': 2,
        }

        alb1 = self.yt_pl.search_album('Artist Album', year=2026)
        alb2 = self.yt_pl.search_album('Artist Album', year=2026)
        self.assertEqual(alb1['title'], 'Matched 2026')
        self.assertIs(alb1, alb2)
        self.yt_pl.yt.search.assert_called_once()
        self.yt_pl.yt.get_album.assert_called_once_with('b_2026')

    def test_get_albums_tracks_and_meta(self):
        """Test get_albums_tracks_and_meta reuses search_album, _info_cache, and parse_tracks."""
        self.yt_pl.yt.search.return_value = [
            {'browseId': 'b_gorillaz', 'type': 'Album', 'year': '2026'}
        ]
        self.yt_pl.yt.get_album.return_value = {
            'year': '2026',
            'trackCount': 2,
            'tracks': [
                {
                    'videoId': 'v1',
                    'title': 'Song 1',
                    'likeStatus': 'LIKE',
                    'artists': [{'name': 'Gorillaz', 'id': 'ar1'}],
                    'album': {'name': 'The Mountain', 'id': 'al1'},
                },
                {
                    'videoId': 'v2',
                    'title': 'Song 2',
                    'likeStatus': 'DISLIKE',
                    'artists': [{'name': 'Gorillaz', 'id': 'ar1'}],
                    'album': {'name': 'The Mountain', 'id': 'al1'},
                },
            ],
        }
        self.yt_pl.yt.get_song.side_effect = [
            {'videoDetails': {'viewCount': '1000'}},
            {'videoDetails': {'viewCount': '500'}},
        ]

        entries = pd.DataFrame(
            index=['Gorillaz - The Mountain', 'Skip Artist - Skip Album']
        )
        tracks_df, meta_df = self.yt_pl.get_albums_tracks_and_meta(
            entries,
            year=2026,
            skip_names=('Skip Artist - Skip Album',),
            verbose=False,
        )
        self.assertEqual(len(tracks_df), 2)
        self.assertEqual(tracks_df.iloc[0]['artist'], 'Gorillaz')
        self.assertAlmostEqual(
            float(meta_df.loc['Gorillaz - The Mountain', 'my_like_score']),
            5.0,
        )
        self.assertEqual(
            int(meta_df.loc['Gorillaz - The Mountain', 'yt_total_views']),
            1500,
        )

    @patch('time.sleep')
    def test_configure_ytmusic_session_retries_html_403(self, mock_sleep):
        """Test _configure_ytmusic_session retries transient 403 HTML and raises on exhaustion."""
        mock_yt = MagicMock()
        resp_403 = MagicMock(status_code=403, reason='Forbidden', text='<html>Sorry...</html>')
        resp_200 = MagicMock(status_code=200, reason='OK', text='{"contents": {}}')
        mock_yt._session.post.side_effect = [resp_403, resp_200]

        self.yt_pl._configure_ytmusic_session(mock_yt, max_retries=3)
        res = mock_yt._session.post('https://music.youtube.com/youtubei/v1/browse')
        self.assertEqual(res.status_code, 200)
        mock_sleep.assert_called_once_with(1.0)

        mock_yt2 = MagicMock()
        mock_yt2._session.post.return_value = resp_403
        self.yt_pl._configure_ytmusic_session(mock_yt2, max_retries=2)
        with self.assertRaises(RuntimeError):
            mock_yt2._session.post('https://music.youtube.com/youtubei/v1/browse')

    def test_browser_auth_update_parse_curl_input(self):
        """Test parse_curl_input extracts cookies, auth, and optional headers."""
        from browser_auth_update import parse_curl_input

        lines = [
            "curl 'https://music.youtube.com/youtubei/v1/browse?prettyPrint=false' \\",
            "  -H 'authorization: SAPISIDHASH 123_abc' \\",
            "  -H 'x-goog-visitor-id: visitor123' \\",
            "  -b 'VISITOR_INFO1_LIVE=xyz; __Secure-3PAPISID=sapisid_val; SID=sid_val' \\",
            "  --data-raw '{\"browseId\":\"FEmusic_library_landing\"}'",
        ]
        res = parse_curl_input(lines)
        self.assertEqual(res['Authorization'], 'SAPISIDHASH 123_abc')
        self.assertEqual(res['x-goog-visitor-id'], 'visitor123')
        self.assertIn('__Secure-3PAPISID=sapisid_val', res['Cookie'])



class PlaylistMergeTests(unittest.TestCase):
    """playlist_from_yt_vids merges; albums_to_playlist resolves + merges."""

    def setUp(self):
        with patch.object(YTMusicPlaylists, '__init__', return_value=None):
            self.yt_pl = YTMusicPlaylists()
        self.yt_pl.yt = MagicMock()
        self.yt_pl.playlists = pd.DataFrame(
            [{'title': 'y 2024 top 50 albums', 'playlistId': 'pl_old'}])
        self.yt_pl.playlist_titles = set(self.yt_pl.playlists['title'])
        self.yt_pl._info_cache = {}
        self.yt_pl.playlist_tsv_dir = tempfile.mkdtemp()

    @patch('ytmusic_library.time.sleep')
    def test_update_only_adds_missing_vids(self, _sleep):
        self.yt_pl.yt.get_playlist.return_value = {
            'id': 'pl_old', 'title': 'y 2024 top 50 albums',
            'tracks': [{'videoId': 'v1'}, {'videoId': 'vX'}]}
        pl_id = self.yt_pl.playlist_from_yt_vids(
            ['v1', 'v2', 'v2'], 'y 2024 top 50 albums', sleep=0)
        self.assertEqual(pl_id, 'pl_old')
        self.yt_pl.yt.add_playlist_items.assert_called_once_with(
            playlistId='pl_old', videoIds=['v2'], duplicates=False)
        self.yt_pl.yt.create_playlist.assert_not_called()

    @patch('ytmusic_library.time.sleep')
    def test_create_chunks_large_playlist(self, _sleep):
        self.yt_pl.yt.create_playlist.return_value = 'pl_new'
        self.yt_pl.playlist_get_info = MagicMock(return_value={'tracks': []})
        vids = [f'v{i}' for i in range(120)]
        pl_id = self.yt_pl.playlist_from_yt_vids(vids, 'big pl', sleep=0)
        self.assertEqual(pl_id, 'pl_new')
        self.assertEqual(
            len(self.yt_pl.yt.create_playlist.call_args.kwargs['video_ids']),
            50)
        self.assertEqual(self.yt_pl.yt.add_playlist_items.call_count, 2)

    @patch('ytmusic_library.time.sleep')
    def test_albums_to_playlist(self, _sleep):
        self.yt_pl.search_album = MagicMock(side_effect=[
            {'browseId': 'a', 'tracks': [{'videoId': 'v1'}, {'videoId': 'v2'}]},
            None, None,  # second album not found (year + fallback)
        ])
        self.yt_pl.playlist_from_yt_vids = MagicMock(return_value='pl_old')
        self.yt_pl.save_playlist_tsv = MagicMock()
        self.yt_pl.playlist_get_info = MagicMock(return_value={'id': 'pl_old'})
        pl_id, found, missing = self.yt_pl.albums_to_playlist(
            [('A', 'One'), ('a', 'one'), ('B', 'Two')],
            'y 2024 top 50 albums', year=2024)
        self.assertEqual((pl_id, found, missing), ('pl_old', 1, ['B - Two']))
        self.yt_pl.playlist_from_yt_vids.assert_called_once()
        self.assertEqual(
            self.yt_pl.playlist_from_yt_vids.call_args[0][0], ['v1', 'v2'])
        self.yt_pl.save_playlist_tsv.assert_called_once()


class BugfixRegressionTests(unittest.TestCase):
  """Regression tests for private tracks, NaN title backfill, and local TSVs."""

  def setUp(self):
    self._tmp = tempfile.TemporaryDirectory()
    self.addCleanup(self._tmp.cleanup)
    with patch.object(YTMusicPlaylists, '__init__', return_value=None):
      self.yt_pl = YTMusicPlaylists()
    self.yt_pl.yt = MagicMock()
    self.yt_pl._info_cache = {}
    self.yt_pl.playlist_tsv_dir = self._tmp.name
    self.yt_pl.duplicate_tracks_tsv = os.path.join(self._tmp.name, '_dup.tsv')
    self.yt_pl.playlists = pd.DataFrame([
        {'title': 'Liked Music', 'playlistId': 'LM', 'count': float('nan'),
         'author': float('nan')},
        {'title': 'my mix', 'playlistId': 'p1', 'count': 1, 'author': 'Jake G'},
    ])

  def test_private_track_and_invalid_album_do_not_retry(self):
    """Verifies private uploads skip API calls and MPRE errors do not retry."""
    row = pd.Series(
        {
            'title': 'Track 11',
            'artist': 'Jay Dee',
            'artistId': float('nan'),
            'albumId': 'FEmusic_library_privately_owned_release_detail123',
        },
        name='v_priv',
    )
    out = self.yt_pl._track_db_get_track_info(row)
    self.assertEqual(out['title'], 'Track 11')
    self.yt_pl.yt.get_song.assert_not_called()
    self.yt_pl.yt.get_album.assert_not_called()

    self.yt_pl.yt.get_album.side_effect = Exception(
        'Invalid browseId provided. This must start with MPRE.'
    )
    with self.assertRaises(Exception):
      self.yt_pl.album_get_info('OLAK5uy_bad')
    self.assertEqual(self.yt_pl.yt.get_album.call_count, 1)

  def test_track_db_requeues_missing_titles(self):
    """Verifies missing titles in track_db are re-queued from tracks_no_meta."""
    track_db = pd.DataFrame(
        {'title': [float('nan'), 'Valid'], 'likeStatus': ['LIKE', 'LIKE']},
        index=pd.Index(['v1', 'v2'], name='videoId'),
    )
    no_meta = pd.DataFrame(
        {'title': ['Choke Enough', 'Valid'], 'likeStatus': ['LIKE', 'LIKE']},
        index=pd.Index(['v1', 'v2'], name='videoId'),
    )
    queued = self.yt_pl._track_db_new_or_newly_liked_tracks(track_db, no_meta)
    self.assertEqual(list(queued.index), ['v1'])
    self.assertEqual(queued.loc['v1', 'title'], 'Choke Enough')

  def test_local_tsv_preserves_title_column(self):
    """Verifies playlist_get_info(use_local_tsvs=True) keeps title column."""
    tsv = os.path.join(self._tmp.name, 'my mix.tsv')
    pd.DataFrame([{'title': 'TEXAS HOLD EM', 'videoId': 'v1'}]).to_csv(
        tsv, sep='\t', index=False
    )
    info = self.yt_pl.playlist_get_info('p1', use_local_tsvs=True)
    self.assertEqual(info['tracks'][0]['title'], 'TEXAS HOLD EM')
    self.assertEqual(
        self.yt_pl.infer_playlist_kind(self.yt_pl.playlists.iloc[0]),
        'YT_GENERATED',
    )


if __name__ == '__main__':
    unittest.main()
