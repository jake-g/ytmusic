import ast
from collections import Counter
from collections import defaultdict
import datetime
import functools
import io
import json
import os
import random
import sys
import time
import unicodedata

import pandas as pd
from ytmusicapi import YTMusic
from ytmusicapi.auth.oauth.credentials import OAuthCredentials

# Force stdout to use UTF-8 and replace characters it can't encode
# This prevents the UnicodeEncodeError during print() calls.
# Only wrap the stream if we are in a standard terminal and NOT in IPython/Jupyter
if hasattr(sys.stdout, 'buffer'):
    sys.stdout = io.TextIOWrapper(
        sys.stdout.buffer, encoding='utf-8', errors='replace')


# When True, will reuse playlist tsvs from last backup
SKIP_PLAYLIST_BACKUP = False
# Regnerate playlists with more than this amount of duplicates
DUPLICATE_THRESHOLD = 3
# For requesting large playlists from api
PLAYLIST_LIMIT = 4500
# Save checkpoint during track scraping every N tracks
CHECKPOINT_INTERVAL = 500
# Chunk size when processing items in batches (e.g. removing from a playlist) to avoid API errors
PROCESS_CHUNK_SIZE = 100

# Settings for automated radio playlist like dislike not like cleanup.
SKIP_PLAYLIST_CLEAN = False
PLAYLIST_CLEAN_RM_NOT_LIKE_AND_DISLIKE = True
PLAYLIST_CLEAN_MOVE_LIKE = True
PLAYLIST_CLEAN_CREATE_LIKE_PLAYLIST = True
PLAYLIST_CLEAN_DRY_RUN = False
# Force-rate songs in LIKE playlists to be LIKE on server. If your liked library exceeds
# the 20,000 song limit (FIFO), setting True will cause an endless unliking/re-liking loop.
PLAYLIST_CLEAN_FORCE_RATE_LIKES = False

# If True, performs a FULL backup (ignores local TSVs and refetches all playlists, track
# counts, and tracklists from the API). If False, performs an INCREMENTAL backup (skips
# API fetches for playlists whose local TSV track count matches the server's count).
PLAYLIST_BACKUP_FULL_RUN = False
PLAYLIST_SLEEP = 0.5
PLAYLIST_START_INDEX = 0
PLAYLIST_CLEAN_SKIP_IF_DISLIKE = True
PLAYLIST_CLEAN_MIN_LIKE_TO_SPLIT = 20
PLAYLIST_CLEAN_LIKE_MIN_LIKE_PCT = 80
PLAYLIST_CLEAN_NOT_LIKE_MAX_LIKE_PCT = 20
PLAYLIST_CLEAN_RADIO_MAX_LIKE_PCT = 50
PLAYLIST_CLEAN_DUPLICATE_THRESH = 5
PLAYLIST_SKIP_STARTS_WITH = ('zz not like', 'y ', 'zp ', 'zq ')
PLAYLIST_CLEAN_SKIP_KINDS = ('SKIP', 'ALBUM', 'YT_GENERATED')

# Files
HEADER_FILE = 'browser.json'  # Updated to use browser auth
CLIENT_FILE = 'client_auth.json'  # legacy as of 2026
PLAYLIST_TSV_DIR = './playlists/'

# Track DB Files
TRACK_DB_FILE = '_tracks_db.tsv'
TRACKS_NO_META_FILE = '_tracks_no_meta.tsv'
LASTFM_PLAYCOUNT_FILE = '_ytmusic_lastfm_playcount.tsv'
TRACK_TSV_COLS = ['title', 'artist', 'album', 'likeStatus',
                  'videoId', 'albumId', 'artistId']  # 'duration',
TRACK_REMOVE_COLS = ['setVideoId', 'feedbackTokens']
PLAYLIST_METADATA_TSV_COLS = [
    'title', 'trackCount', 'privacy', 'id']  # 'duration',
LIKE_TRACKS_HEADER = ['title', 'album', 'artist']

# LIKE subset
LIKE_TOKS = ['thumbs up', ' like', '_like', ' likes', ' top']
LIKE_TRACKS_TSV_FILE = '_liked_tracks.tsv'

# NOT LIKE subset
NOT_LIKE_PREFIX = 'zz not like'
NOT_LIKE_TOKS = ['not like', '_not_like', ' dislike', 'thumbs_down']
NOT_LIKE_TRACKS_TSV_FILE = '_not_liked_tracks.tsv'
# Radio subset
RADIO_TOKS = [' radio', '_radio', '_indifferent']
RADIO_TO_LIKE_MAP_FILE = '_ytmusic_radio_to_like_pl_map.tsv'
# Other subsets
SKIP_STARTS_WITH_TOKS = ['zz']
ALBUM_TOKS = ['_albums', '  album', 'albums']
# Quoting for TSV track list files
TSV_TRACK_QUOTING = 3

# For get_like_not_like_tracks_to_review()
MANUALLY_RATED_TSV_FILE = '_ytmusic_new_like_and_not_like_manual_rated.tsv'
NEED_RATE_TSV_FILE = '_ytmusic_new_like_and_not_like_need_manual_rating.tsv'
PLAYLIST_RADIO_COUNT_TSV_FILE = '_playlist_radio_counts.tsv'
# Duplicate tracks we don't want to re-scrape
DUPLICATE_TRACKS_TSV_FILE = '_ytmusic_duplicate_tracks.tsv'
# Results for automated radio playlist like dislike not like cleanup.
RADIO_PLAYLIST_CLEANUP_TSV_FILE = '_ytmusic_cleanup_radio_playlists_results.tsv'
LIKE_PLAYLIST_CLEANUP_TSV_FILE = '_ytmusic_cleanup_like_playlists_results.tsv'
PLAYLIST_CLEANUP_COUNTERS_TSV_FILE = '_ytmusic_cleanup_playlist_counters.tsv'

# Playlists for liked tracks
LIKE_PLAYLISTS_TSV_FILE = '_like_playlists.tsv'

# Constants
VALID_TRACK_RATINGS = ('LIKE', 'DISLIKE', 'INDIFFERENT', 'NONE')
VALID_PLAYLIST_KINDS = ('LIKE', 'NOT_LIKE', 'INDIFFERENT',
                        'ALBUM', 'SKIP', 'YT_GENERATED')


# Format the date as "month-day-year"
DATE = time.strftime('%m-%d-%Y')


def retry(retries=3, delay=2, backoff=2, exceptions=(Exception,)):
    """Decorator to retry a function if it raises specified exceptions."""
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            t_delay = delay
            for attempt in range(retries):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    if attempt == retries - 1:
                        raise
                    print(f"WARNING: API call {func.__name__} failed: {e}. Retrying in {t_delay}s (Attempt {attempt + 1}/{retries})...")
                    time.sleep(t_delay)
                    t_delay *= backoff
        return wrapper
    return decorator


class YTMusicPlaylists:

    def __init__(self, header=HEADER_FILE, client=CLIENT_FILE,
                 playlist_tsv_dir=PLAYLIST_TSV_DIR,
                 lastfm_playcount_file=LASTFM_PLAYCOUNT_FILE,
                 track_db_file=TRACK_DB_FILE,
                 tracks_no_meta_file=TRACKS_NO_META_FILE,
                 like_tsv_file=LIKE_TRACKS_TSV_FILE,
                 not_like_tsv_file=NOT_LIKE_TRACKS_TSV_FILE,
                 need_rate_tsv=NEED_RATE_TSV_FILE,
                 like_playlist_file=LIKE_PLAYLISTS_TSV_FILE,
                 radio_to_like_map_file=RADIO_TO_LIKE_MAP_FILE,
                 radio_count_file=PLAYLIST_RADIO_COUNT_TSV_FILE,
                 radio_cleanup_file=RADIO_PLAYLIST_CLEANUP_TSV_FILE,
                 like_cleanup_file=LIKE_PLAYLIST_CLEANUP_TSV_FILE,
                 cleanup_counters_file=PLAYLIST_CLEANUP_COUNTERS_TSV_FILE,
                 manual_rate_tsv=MANUALLY_RATED_TSV_FILE,
                 valid_playlist_kinds=VALID_PLAYLIST_KINDS,
                 valid_track_ratings=VALID_TRACK_RATINGS,
                 playlist_limit=PLAYLIST_LIMIT):
        self.playlist_tsv_dir = os.path.abspath(playlist_tsv_dir)
        self._valid_playlist_kinds = valid_playlist_kinds
        self._valid_ratings = valid_track_ratings
        # Paths
        jn = os.path.join
        self.track_db_tsv = jn(self.playlist_tsv_dir, track_db_file)
        self.tracks_no_meta_tsv = jn(self.playlist_tsv_dir, tracks_no_meta_file)
        self.lastfm_tsv = jn(self.playlist_tsv_dir, lastfm_playcount_file)
        self.not_like_tsv = jn(self.playlist_tsv_dir, not_like_tsv_file)
        self.like_tsv = jn(self.playlist_tsv_dir, like_tsv_file)
        self.manual_rate_tsv = jn(self.playlist_tsv_dir, manual_rate_tsv)
        self.need_rate_tsv = jn(self.playlist_tsv_dir, need_rate_tsv)
        self.radio_count_file = jn(self.playlist_tsv_dir, radio_count_file)
        self.radio_cleanup_file = jn(self.playlist_tsv_dir, radio_cleanup_file)
        self.like_cleanup_file = jn(self.playlist_tsv_dir, like_cleanup_file)
        self.cleanup_counters_file = jn(
            self.playlist_tsv_dir, cleanup_counters_file)
        self.like_playlist_file = jn(self.playlist_tsv_dir, like_playlist_file)
        self.playlist_limit = playlist_limit
        self.radio_like_map_file = jn(self.playlist_tsv_dir, radio_to_like_map_file)
        self.duplicate_tracks_tsv = jn(self.playlist_tsv_dir, DUPLICATE_TRACKS_TSV_FILE)
        self._info_cache = {}
        self.yt = self.init_ytmusic_api(header, client)
        # In-memory caching for liked/not-liked tracks to minimize disk I/O
        self._like_df = None
        self._not_like_df = None
        # Load small files right away
        self._like_playlist_titles = self._read_tsv(
            self.like_playlist_file, index_col=None)['title'].str.lower().tolist()
        self._radio_to_like_map = self._read_tsv(
            self.radio_like_map_file, index_col=None)
        self.banned_vid_set = frozenset(
            self._get_not_like_df().index)
        # Load this later, intialize empty for now
        self._playcount_map = pd.DataFrame([])
        # fetch playlists (needed for many downstream function, takes some time)
        self.playlists = pd.DataFrame(
            self.yt.get_library_playlists(limit=playlist_limit))
        self.playlist_titles = frozenset(self.playlists['title'])

    def _get_like_df(self):
        """Returns the in-memory cached like DataFrame, loading it if not already cached."""
        if self._like_df is None:
            self._like_df = self._read_tsv(self.like_tsv)
        return self._like_df

    def _get_not_like_df(self):
        """Returns the in-memory cached not-like DataFrame, loading it if not already cached."""
        if self._not_like_df is None:
            self._not_like_df = self._read_tsv(self.not_like_tsv)
        return self._not_like_df

    def _invalidate_playlist_cache(self, playlist_id):
        """Removes the playlist from the metadata cache if it exists."""
        if hasattr(self, '_info_cache') and playlist_id in self._info_cache:
            del self._info_cache[playlist_id]

    def init_ytmusic_api(self, header, client):
        # Browser oauth: http://ytmusicapi.readthedocs.io/en/stable/setup/browser.html
        # Old tv client oauth: https://ytmusicapi.readthedocs.io/en/stable/setup/oauth.html
        #    https://console.cloud.google.com/apis/credentials?project=graceful-alpha-154201
        filename = os.path.basename(header).lower()

        if filename == 'browser.json':
            print(f'Using header file: {header}')
            print(' Browser Authentication (cookies). Skipping OAuth client init.')
            return YTMusic(header)

        elif filename == 'oauth.json':
            print(f'Using header file: {header}')
            print(f'Parsing client auth file: {client}',
                  '(Requires client_secret)')
            oauth_creds = self._get_client_credentials_from_json(client)
            return YTMusic(header, oauth_credentials=oauth_creds)

        else:
            raise ValueError(
                f"Unknown header filename: '{header}'. "
                f"The script expects strictly 'browser.json' (for browser auth) "
                f"or 'oauth.json' (for OAuth)."
            )

    def test_ytmusic_api(self, verbose=True):
        t0 = time.time()
        if not self.yt:
            raise RuntimeError("YTMusic client is not initialized.")
        if not self.yt.get_song('Kv7K9ghgcgA'):
            raise RuntimeError("Failed to fetch test song. Authentication might be invalid.")
        if not self.yt.get_library_playlists(limit=1):
            raise RuntimeError("Failed to fetch library playlists. Authentication might be invalid.")
        if not self.yt.get_library_albums():
            raise RuntimeError("Failed to fetch library albums. Authentication might be invalid.")
        if not self.yt.get_library_artists():
            raise RuntimeError("Failed to fetch library artists. Authentication might be invalid.")
        if verbose:
            print(f'Test Passed in {(time.time() - t0):0.2f} seconds')
            import ytmusicapi as ytmusicapi
            print(f'Using ytmusicapi version: {ytmusicapi.__version__}')

    def _get_client_credentials_from_json(self, file_path: str) -> OAuthCredentials:
        """
        Parses a JSON file and creates a GoogleCredentials object from the 'installed' section."""
        with open(file_path, 'r') as f:
            data = json.load(f)
        return OAuthCredentials(client_id=data["installed"]["client_id"], client_secret=data["installed"]["client_secret"])

    # Playlist related Functions
    def query_by_title(self, title):
        return self._playlist_loc_first(col='title', value=title)

    def query_by_playlistId(self, playlistId):
        return self._playlist_loc_first(col='playlistId', value=playlistId)

    def _playlist_loc_first(self, col, value):
        res = self.playlists.loc[self.playlists[col] == value]
        if len(res) == 0:
            print(f'WARNING: No playlist with {col}: {value}')
            return None  # Return None instead of crashing
        elif len(res) > 1:
            print(f'Multiple matches for: {value}, choosing',
                  f'first result of:\n {res[["title", "count"]]}')
        return res.iloc[0]

    def get_playlists_by_privacy(
            self, privacy='PUBLIC',
            skip_if_contains=('zz not', 'zzz ', 'yyz ', 'Episodes for ', 'Liked Music', 'Podcast Queue')):
        rows = []
        for i, p in self.playlists.iterrows():
            if len(p) == self.playlist_limit:
                continue
            if any(sk.lower() in p.title.lower() for sk in skip_if_contains):
                continue
            m = self.playlist_get_info(p["playlistId"])
            if m['privacy'] == privacy:
                # Log
                stats = f"{m.get('trackCount')} tracks, {m.get('views')} views, {m.get('duration')}"
                desc = str(m.get('description', '')).replace('\n', ' ')[:40]
                print(f"Found {privacy.lower()}: '{p['title']}', Stats: {stats},",
                      f"Description: {desc}... | [{p['playlistId']}]")

                # Build row: Merge original data + Flattened Meta + Raw Meta
                row = p.to_dict()
                row.update({
                    'views': int(m.get('views') or 0),  # Handle None for sort
                    'trackCount': m.get('trackCount'),
                    'duration': m.get('duration'),
                    'author': m.get('author', {}).get('name'),
                    'metadata': m
                })
                rows.append(row)
        return pd.DataFrame(rows).sort_values('views', ascending=False)

    def rename_playlist(self, playlist_id, new_name):
        """Renames a playlist on YouTube Music given its ID."""
        try:
            self.yt.edit_playlist(playlistId=playlist_id, title=new_name)
            print(f"Renamed playlist with ID '{playlist_id}' to '{new_name}'")
        except Exception as e:
            print(f"Error renaming playlist with ID '{playlist_id}': {e}")

    def find_playlists_with_special_chars(self, special_chars=["_", "/", ".", ":", ","]):
        """Prints playlists containing any of the specified special characters."""
        for i, row in self.playlists.iterrows():
            playlist_name = row['title']
            if any(char in playlist_name for char in special_chars):
                print(f"Playlist: {playlist_name} has a",
                      f"special character in {special_chars}.")

    def get_playlist_counts(self, verbose=False, filter_title=None, use_local_tsvs=False):
        count_df_cols = ['title', 'track_count', 'privacy', 'playlist_id']
        # 'duration_hours',
        playlists = []

        matching_rows = self.playlists
        if filter_title:
            matching_rows = self.playlists[
                self.playlists['title'].str.lower().str.contains(filter_title.lower(), na=False)
            ]
        total_to_process = len(matching_rows)

        if filter_title:
            print(f'Getting playlist track count for {total_to_process} playlists matching "{filter_title}"', flush=True)
        else:
            print(f'Getting playlist track count for all {total_to_process} playlists (takes ~5 minutes)', flush=True)

        processed = 0
        t0 = time.time()
        for i, row in self.playlists.iterrows():
            if filter_title and filter_title.lower() not in row.title.lower():
                if verbose:
                    print(f'{i}: Skipping: {row.title},',
                          f'filter: {filter_title}')
                continue

            eta = self._get_eta(t0, processed, total_to_process)
            eta_str = f" (~{eta})" if eta else ""
            print(f"[{processed+1}/{total_to_process}]{eta_str} Getting count for {row.title}...", flush=True)

            track_count = None
            privacy = row.get('privacy', '')

            if use_local_tsvs:
                tsv_filename = f"{row['title']}.tsv".replace('"', "'")
                tsv_path = os.path.join(self.playlist_tsv_dir, tsv_filename)
                if os.path.exists(tsv_path):
                    try:
                        local_df = self._read_tsv(tsv_path)
                        track_count = len(local_df)
                    except Exception:
                        pass

            if track_count is None:
                playlist_info = self.playlist_get_info(row['playlistId'])
                track_count = len(playlist_info.get('tracks', []))
                privacy = playlist_info.get('privacy', '')

            playlists.append({
                'title': row['title'],
                'playlist_id': row['playlistId'],
                'track_count': track_count,
                'privacy': privacy,
                # 'duration_hours': round(float(playlist_info.get('duration_seconds', 1)) / 3600)
            })
            processed += 1
            if verbose:
                print(f'{i}: {playlists[-1]}')
        return pd.DataFrame(playlists)[count_df_cols].sort_values(['track_count', 'title'], ascending=True)

    # Generate a tsv for tracks to review LIKE/NOT_LIKE status
    def get_like_not_like_tracks_to_review(self):
        review_cols = ['category', 'manual_rating', 'likeStatus', 'title', 'album', 'artist',
                       'date_modified', 'playlists', 'averageRating', 'viewCount', 'release',
                       'albumYear', 'albumType', 'albumTrackCount', 'keywords', 'fuzzy_track_id']
        module_path = os.path.abspath(os.path.join('../music-sources-unified'))
        if module_path not in sys.path:
            sys.path.append(module_path)
        import unify_lib as uni

        # Step 1: Normalize track database and assign fuzzy IDs for cross-matching
        all_df = self._read_tsv(self.track_db_tsv, use_track_defaults=True)
        all_df['fuzzy_track_id'] = all_df.apply(
            uni.make_ytmusic_fuzzy_slugified_track_id, axis=1)

        like_df = self._get_like_df()
        not_like_df = self._get_not_like_df()

        print(f'Loaded {len(like_df)} like, {len(not_like_df)} not like entries,',
              f'and {len(all_df)} total tracks')
        like_df = all_df.loc[all_df.index.isin(like_df.index)]
        not_like_df = all_df.loc[all_df.index.isin(not_like_df.index)]
        print(f'Loaded {len(not_like_df)} not like entries,',
              f'that have an entry in ALL_TRACKS')
        not_like_df = not_like_df.loc[not_like_df['likeStatus'] != 'LIKE']
        print(f'Keeping {len(not_like_df)} not like after remove LIKE')

        not_like_vids = frozenset(not_like_df.index)
        like_vids = frozenset(like_df.index)

        # Step 2: Find tracks to LIKE (matched via fuzzy ID but not yet marked LIKE)
        like_fuzzy_ids = frozenset(like_df['fuzzy_track_id'])
        like_impacted_playlists = []
        new_likes = set()
        skip_not_like = set()
        print('Processing LIKE tracks...', flush=True)
        # Vectorized matching for LIKE tracks
        matched_like_df = all_df.loc[all_df['fuzzy_track_id'].isin(like_fuzzy_ids)]

        # Filter out already liked tracks
        new_likes_df = matched_like_df.loc[
            (matched_like_df['likeStatus'] != 'LIKE') &
            (~matched_like_df.index.isin(like_vids))
        ]

        # Split into new_likes and skip_not_like
        skip_not_like_df = new_likes_df.loc[new_likes_df.index.isin(not_like_vids)]
        new_likes_df = new_likes_df.loc[~new_likes_df.index.isin(not_like_vids)]

        new_likes = set(new_likes_df.index)
        skip_not_like = set(skip_not_like_df.index)
        like_impacted_playlists = new_likes_df['playlists'].dropna().tolist()

        # Print warnings for missing fuzzy IDs
        found_like_fuzzy_ids = frozenset(matched_like_df['fuzzy_track_id'])
        missing_like_fuzzy_ids = like_fuzzy_ids - found_like_fuzzy_ids
        for fuzzy_id in missing_like_fuzzy_ids:
            print(f"WARNING: Liked track with fuzzy ID '{fuzzy_id}'",
                  "not found in main track database. Skipping...", flush=True)

        print(f' Found {len(new_likes)} new tracks to LIKE')
        print(f' Found {len(skip_not_like)} tracks to LIKE',
              f'but already in NOT LIKE', flush=True)

        # Step 3: Find tracks to NOT LIKE (matched via fuzzy ID but not yet marked NOT LIKE)
        not_like_fuzzy_ids = frozenset(not_like_df['fuzzy_track_id'])
        not_like_impacted_playlists = []
        new_not_likes = set()
        skip_is_like = set()
        print('\nProcessing NOT LIKE tracks...', flush=True)
        # Vectorized matching for NOT LIKE tracks
        matched_not_like_df = all_df.loc[all_df['fuzzy_track_id'].isin(not_like_fuzzy_ids)]

        # Filter out already not-liked tracks
        new_not_likes_df = matched_not_like_df.loc[~matched_not_like_df.index.isin(not_like_vids)]

        # Split into new_not_likes and skip_is_like (if in like_vids or new_likes)
        skip_is_like_df = new_not_likes_df.loc[
            new_not_likes_df.index.isin(like_vids) |
            new_not_likes_df.index.isin(new_likes)
        ]
        new_not_likes_df = new_not_likes_df.loc[
            ~(new_not_likes_df.index.isin(like_vids) |
              new_not_likes_df.index.isin(new_likes))
        ]

        new_not_likes = set(new_not_likes_df.index)
        skip_is_like = set(skip_is_like_df.index)
        not_like_impacted_playlists = new_not_likes_df['playlists'].dropna().tolist()

        # Print warnings for missing fuzzy IDs
        found_not_like_fuzzy_ids = frozenset(matched_not_like_df['fuzzy_track_id'])
        missing_not_like_fuzzy_ids = not_like_fuzzy_ids - found_not_like_fuzzy_ids
        for fuzzy_id in missing_not_like_fuzzy_ids:
            print(f"WARNING: Not-Like track with fuzzy ID '{fuzzy_id}'",
                  "not found in main track database. Skipping...", flush=True)

        print(f' Found {len(new_not_likes)} new tracks to NOT LIKE')
        print(f' Found {len(skip_is_like)} tracks to NOT LIKE',
              f'but they are already in LIKE', flush=True)

        # optional extra info
        def display_top_impacted_playlist_df(impacted_playlists, top_n=10):
            df = pd.DataFrame(impacted_playlists, columns=['encoded_list'])
            df['encoded_list'] = df['encoded_list'].dropna(
            ).str.replace('[nan]', "['nan']")
            df['decoded_list'] = df['encoded_list'].str.lstrip(
                '[').str.rstrip(']').str.split(', ')
            df = df.explode('decoded_list')
            df['decoded_list'] = df['decoded_list'].str.strip("'")
            print(f"\nTop {top_n} playlists impacted:")
            print(df['decoded_list'].value_counts().head(top_n))

        display_top_impacted_playlist_df(like_impacted_playlists, top_n=10)
        # display_top_impacted_playlist_df(not_like_impacted_playlists, top_n=10)

        # Step 4: Subtract previously reviewed manual ratings to avoid redundant reviews
        manual_picks = self._read_tsv(
            self.manual_rate_tsv).drop_duplicates(keep='first')
        old_like = manual_picks.loc[manual_picks['manual_rating'] == 'LIKE']
        old_not_like = manual_picks.loc[manual_picks['manual_rating'] == 'NOT_LIKE']
        print(f'Loaded {len(manual_picks)} manually labeled entries, '
              f'{len(old_like)} are LIKE, {len(old_not_like)} NOT_LIKE')
        old_like_vids = frozenset(old_like.index)
        old_not_like_vids = frozenset(old_not_like.index)
        old_all = old_like_vids & old_not_like_vids

        # Compare old and new
        new_likes_len = len(new_likes)
        new_likes -= old_like_vids
        print(f'Reduced new LIKE from {new_likes_len} to {len(new_likes)}'
              f' entries after removing reviewed matches')
        new_not_likes_len = len(new_not_likes)
        new_not_likes -= old_not_like_vids
        print(f'Reduced new NOT_LIKE from {new_not_likes_len} to {len(new_not_likes)}'
              f' entries after removing reviewed matches')
        skip_not_like_len = len(skip_not_like)
        skip_not_like -= old_all
        print(f'Reduced skip_not_like from {skip_not_like_len} to {len(skip_not_like)}'
              f' entries after removing reviewed matches')
        skip_is_like_len = len(skip_is_like)
        skip_is_like -= old_all
        print(f'Reduced skip_is_like from {skip_is_like_len} to {len(skip_is_like)}'
              f' entries after removing reviewed matches')

        # Manually screeen these in sheets, llabel as LIKE, INDIFFERENT or NOT_LIKE
        like_not_like_res = {
            'need_like': all_df.loc[all_df.index.isin(new_likes)],
            'need_like_but_is_not_like': all_df.loc[all_df.index.isin(skip_not_like)],
            'need_not_like': all_df.loc[all_df.index.isin(new_not_likes)],
            'need_not_like_but_is_like': all_df.loc[all_df.index.isin(skip_is_like)],
        }

        # Manually screeen these in sheets, llabel as LIKE, INDIFFERENT or NOT_LIKE
        need_review = pd.concat([v.assign(category=k)
                                for k, v in like_not_like_res.items()])
        print(f'{len(need_review)} entries need like or not like',
              'manual review', flush=True)
        need_review['manual_rating'] = ''
        need_review = need_review.drop_duplicates(keep='last')
        need_review[review_cols].to_csv(
            self.need_rate_tsv, sep='\t', index=True)
        return need_review

    @retry(retries=3, delay=1)
    def playlist_get_info(self, playlistId,
                          playlist_limit=PLAYLIST_LIMIT, use_cache=True,
                          use_local_tsvs=False):
        if not playlist_limit:
            playlist_limit = self.playlist_limit
        if use_cache and playlistId in self._info_cache:
            info = self._info_cache[playlistId]
        else:
            info = None
            if use_local_tsvs:
                # Find title in self.playlists
                match = self.playlists.loc[self.playlists['playlistId'] == playlistId]
                if len(match):
                    title = match.iloc[0]['title']
                    tsv_filename = f"{title}.tsv".replace('"', "'")
                    tsv_path = os.path.join(self.playlist_tsv_dir, tsv_filename)
                    if os.path.exists(tsv_path):
                        try:
                            local_df = self._read_tsv(tsv_path)
                            info = {
                                'id': playlistId,
                                'playlistId': playlistId,
                                'title': title,
                                'privacy': match.iloc[0].get('privacy', 'PRIVATE'),
                                'trackCount': len(local_df),
                                'tracks': local_df.to_dict('records')
                            }
                            self._info_cache[playlistId] = info
                        except Exception as e:
                            print(f"Warning: Failed to read local TSV for {title}: {e}")
            if info is None:
                info = self.yt.get_playlist(playlistId, limit=playlist_limit)
                self._info_cache[playlistId] = info
        return info

    def playlist_from_yt_vids(self, vids, pl_name=None, sleep=3, public='PRIVATE', desc='',
                              dry=False, set_rating=None, remove_dupes=False, verbose=False,
                              sort_by=None):

        print(f'\nGenerating {pl_name} ytmusic playlist for {len(vids)} tracks')
        if desc == '':
          desc = f'{len(vids)} tracks from {pl_name} [{DATE}]'
        if dry:
            print('DRY:', end=' ')
        pl_id = None
        if pl_name in self.playlists['title'].unique():
            # Update existing
            pl_id = self.query_by_title(pl_name).playlistId
            if not dry:
                _ = self.yt.add_playlist_items(
                    playlistId=pl_id, videoIds=vids, duplicates=False)
                self._invalidate_playlist_cache(pl_id)
            print(f'Updated {pl_name} playlist with {len(vids)} tracks, playlist id:',
                  f'{pl_id}...waiting {sleep} seconds...')
        else:  # Create new
            if not dry:
                pl_id = self.yt.create_playlist(
                    title=pl_name, description=desc,
                    privacy_status=public, video_ids=vids
                )
                self.playlist_titles = self.playlist_titles | {pl_name}
            print(f'Saved {pl_name} playlist with {len(vids)} tracks and playlist id:',
                  f'{pl_id}, waiting {sleep} seconds...')
        time.sleep(sleep)

        if dry:
            print(f'Set rating to: {set_rating},',
                  f'remove duplicates: {remove_dupes},',
                  f'sort by: {sort_by}')
        else:
            pl_info = self.playlist_get_info(pl_id, use_cache=False)
            if remove_dupes:
                self.playlist_remove_duplicates(
                    pl_info, duplicate_threshold=DUPLICATE_THRESHOLD,
                    verbose=verbose, sleep_time=sleep)
            if set_rating:
                _ = self.playlist_rate_all_songs(
                    pl_info, rating=set_rating, skip_if_dislike=True,
                    verbose=verbose, sleep_time=sleep)
            if sort_by:
                self.sort_playlist(pl_id, sort_by=sort_by)

        return pl_id

    def playlist_from_tsv(self, tsv_path, sort_by_index=True,
                          ignore_banned=False, pl_name=None, sleep=3,
                          public='PRIVATE', dry=False):
        if not tsv_path.endswith('.tsv'):
            raise ValueError(f"Playlist path must end with .tsv: {tsv_path}")
        df = self._read_tsv(tsv_path, index_col=0)
        if not pl_name:
          pl_name = os.path.basename(tsv_path).split('.tsv')[0]
        if sort_by_index:
            df = df.sort_index()
        if ignore_banned:
            vids = df.videoId
        else:
            vids = frozenset(df.videoId.unique()) - self.banned_vid_set
        desc = f'Matched local tsv playlist: {pl_name}'
        self.playlist_from_yt_vids(
            list(vids), pl_name, sleep, public, desc, dry)

    def parse_tracks(self, track_list):
        tracks = pd.DataFrame(track_list)
        if tracks.empty:
            print(f"WARNING: Track list is empty")
            return tracks

        # Ensure videoId exists even if the API returned 'id'
        if 'videoId' not in tracks.columns:
            if 'id' in tracks.columns:
                tracks['videoId'] = tracks['id']
        elif 'id' in tracks.columns:
            tracks['videoId'] = tracks['videoId'].fillna(tracks['id'])

        # Helper to handle missing objects (returns None if x is empty/None)
        try:
            # tracks['artist'] = tracks['artists'].apply(  # concat All artist
            #     lambda x: " & ".join([a['name'] for a in x]) if x else "")
            tracks['artist'] = tracks['artists'].apply(  # get first artist
                lambda x: x[0].get('name') if x else None)
            tracks['artistId'] = tracks['artists'].apply(
                lambda x: x[0].get('id') if x else None)
            tracks['albumId'] = tracks['album'].apply(
                lambda x: x.get('id') if x else None)
            tracks['album'] = tracks['album'].apply(
                lambda x: x.get('name') if x else "")
        except Exception as e:
            # Grab the first videoId as a hint to where the list broke
            hint_vid = "Unknown"
            if 'videoId' in tracks.columns and not tracks.empty:
                hint_vid = tracks['videoId'].iloc[0]
            print("WARNING: Metadata Parse Error",
                  f"near track ID {hint_vid}: {e}")

        return tracks.drop(columns=['thumbnails', 'artists'], errors='ignore')

    def parse_playlist(self, playlist_meta, verbose=False):
        playlist_meta.pop('thumbnails', None)
        track_list = playlist_meta.pop('tracks', None)
        if verbose:
            print(pd.DataFrame.from_dict(playlist_meta, orient='index'))
        tracks = self.parse_tracks(track_list)
        return tracks, playlist_meta

    def playcount_sort_playlist(
            self, pl_info, max_playcount_str=50,
            ignore_banned=True, sleep_time=1, verbose=True):
        if not len(self._playcount_map):
            self._playcount_map = self._read_tsv(self.lastfm_tsv)
            if verbose:
                print(f'Loaded {self._playcount_map["lastfm_playcount"].sum()}',
                      f'playounts from {len(self._playcount_map)} tracks')
        pl_str = f'{pl_info["title"]} [{DATE}]'
        tracks = pd.DataFrame(pl_info.get('tracks', None))
        tracks = tracks.set_index('videoId', drop=True)
        desc = f'generated sorting by lastfm playcount for {pl_str}'
        if not ignore_banned:
            orig_len = len(tracks)
            tracks = tracks.loc[~tracks.index.isin(self.banned_vid_set)]
            desc += f'\n\nremoved {orig_len - len(tracks)} ' + \
                f'banned tracks, keeping {len(tracks)}'
        tracks = tracks.join(self._playcount_map).sort_values(
            'lastfm_playcount', ascending=False)
        # generate description string with top playcounts
        pc = tracks.loc[tracks['lastfm_playcount']
                        > 0].head(max_playcount_str)
        pc_str = pc['lastfm_playcount'].astype(
            int).astype('str') + '\t|  ' + pc['title']
        desc += f'\n\nTop {len(pc)} Playcounts:\t\n' + \
            '\n'.join(pc_str.to_list())
        video_ids = list(tracks.index)
        pl_id = self.yt.create_playlist(
            title=pl_info["title"], description=desc,
            privacy_status='PRIVATE', video_ids=video_ids)
        time.sleep(sleep_time)
        self.yt.delete_playlist(pl_info["id"])
        time.sleep(sleep_time)
        print(f'Created sorted pl: {pl_str} {pl_id}, and ',
              f'deleted original pl: {pl_info["id"]}')
        return pc

    def _read_tsv(self, filepath, index_col=0, use_track_defaults=False, low_memory=False):
        """Helper to read TSV files with consistent defaults."""
        kwargs = {'low_memory': low_memory}
        if use_track_defaults:
            kwargs.update({
                'quoting': TSV_TRACK_QUOTING,
                'on_bad_lines': 'warn',
                'low_memory': False
            })
        return pd.read_csv(filepath, sep='\t', index_col=index_col, **kwargs)

    def _collect_tracks_from_playlists(self, playlist_filter_fn, track_filter_fn=None, tsv_header=LIKE_TRACKS_HEADER, print_stats=False):
        """Common logic to collect and merge tracks from a filtered subset of playlist TSVs."""
        playlist_files = sorted(os.listdir(self.playlist_tsv_dir))
        filtered_playlists = [pl for pl in playlist_files
                              if playlist_filter_fn(pl.replace('.tsv', ''))]

        print_label = "like" if playlist_filter_fn == self._playlist_is_like else "not like"
        print(
            f'Found {len(filtered_playlists)} {print_label} playlists out of the {len(playlist_files)} total')

        tracks_list = []
        for pl in filtered_playlists:
            track_df = self._read_tsv(
                os.path.join(self.playlist_tsv_dir, pl),
                index_col=None,
                use_track_defaults=True
            )
            total_len = len(track_df)

            if track_filter_fn:
                track_df = track_filter_fn(track_df)

            tracks_db_filtered = track_df.set_index('videoId', drop=True)
            tracks_list.append(tracks_db_filtered)

            if print_stats:
                liked_percent = 100 * \
                    len(tracks_db_filtered) / total_len if total_len > 0 else 0
                if liked_percent < 80:
                    print('\nWARNING: Low Like Percentage!')
                print(
                    f'{pl}\t{liked_percent:0.1f}% currently liked (of {total_len} total tracks)', flush=True)

        if not tracks_list:
            df = pd.DataFrame(columns=tsv_header)
            df.index.name = 'videoId'
            return df

        combined_tracks = pd.concat(tracks_list).sort_values('artist')
        combined_tracks = combined_tracks.loc[
            ~combined_tracks.index.duplicated(keep='first'), tsv_header]
        return combined_tracks

    @retry(retries=3, delay=2)
    def remove_playlist_items_chunked(
        self, playlist_id, tracks, chunk_size=PROCESS_CHUNK_SIZE, sleep=1, label="tracks", verbose=False
    ):
        """Removes tracks from a playlist in chunks to avoid API/size errors."""
        if not tracks:
            return
        self._invalidate_playlist_cache(playlist_id)
        for i in range(0, len(tracks), chunk_size):
            chunk = tracks[i:i + chunk_size]
            try:
                status = self.yt.remove_playlist_items(playlist_id, chunk)
                err_msg = (f'Bad Status for {playlist_id} remove '
                           f'{len(chunk)} {label} tracks: {status}')
                if str(status) != 'STATUS_SUCCEEDED':
                    raise RuntimeError(err_msg)
                if verbose:
                    print(
                        f'  -> Removed {len(chunk)} {label} entries from playlist {playlist_id}')
                time.sleep(sleep)
            except Exception as e:
                print(
                    f"  -> Warning: Failed to remove chunk of {label} tracks: {e}")

    def clean_up_radio_playlist(
            self, pl_info, verbose=False,
            move_like=False, min_num_like=10,
            sleep=1, create_like_playlist=False,
            remove_dislike=True, remove_not_like=False,
            use_local_tsvs=True):
        not_like_vids = self.banned_vid_set

        remove_dislike_tracks = []
        remove_not_like_tracks = []
        move_like_tracks = []

        # Get counters
        pl_counters = {'removed_dislike': 0, 'moved_like': 0,
                       'removed_not_like': 0, 'like_and_not_like': 0}
        # Step 1: Categorize tracks based on their current likeStatus
        for track in pl_info.get('tracks', []):
            if track['likeStatus'] == 'DISLIKE':
                pl_counters['removed_dislike'] += 1
                remove_dislike_tracks.append(track)
            elif track['likeStatus'] == 'LIKE':
                pl_counters['moved_like'] += 1
                move_like_tracks.append(track)
                if track['videoId'] in not_like_vids:
                    pl_counters['like_and_not_like'] += 1
            elif track['videoId'] in not_like_vids:
                pl_counters['removed_not_like'] += 1
                remove_not_like_tracks.append(track)
        # Check if we actually need to do any modifications
        has_removals = (
            (move_like and len(move_like_tracks) > min_num_like) or
            (remove_not_like and len(remove_not_like_tracks) > 0) or
            (remove_dislike and len(remove_dislike_tracks) > 0)
        )

        if not has_removals:
            return pl_counters

        if verbose:
            # Estimate time: ~1.5s per batch add/remove chunk of 100
            num_ops = 0
            if move_like and len(move_like_tracks) > min_num_like:
                num_ops += (len(move_like_tracks) // PROCESS_CHUNK_SIZE) + 2
            num_ops += sum(
                (len(t) // PROCESS_CHUNK_SIZE) + 1
                for t in [remove_not_like_tracks, remove_dislike_tracks]
                if t
            )
            est = int(num_ops * 1.5)
            est_str = f"{est // 60}m {est % 60}s" if est >= 60 else f"{est}s"
            print(
                f'Playlist {pl_info["title"]}: '
                f'Cleaning tracks (approx {est_str})...'
            )

        # If loaded from local TSV, we must fetch from API to get setVideoIds
        if len(pl_info.get('tracks', [])) > 0 and 'setVideoId' not in pl_info['tracks'][0]:
            pl_info = self.playlist_get_info(pl_info['id'], playlist_limit=self.playlist_limit, use_cache=False)

            # Re-categorize with live info to get correct setVideoIds
            remove_dislike_tracks = []
            remove_not_like_tracks = []
            move_like_tracks = []
            for track in pl_info.get('tracks', []):
                if track['likeStatus'] == 'DISLIKE':
                    remove_dislike_tracks.append(track)
                elif track['likeStatus'] == 'LIKE':
                    move_like_tracks.append(track)
                elif track['videoId'] in not_like_vids:
                    remove_not_like_tracks.append(track)

        # Step 2: Apply playlist type constraints (only "radio" or "albums" playlists can be modified)
        if 'radio' not in pl_info["title"] and 'albums' not in pl_info["title"]:
            print(f'Skipping {pl_info["title"]} modifications,',
                  f'only playlists with "radio" or "albums" in name supported')
            return pl_counters
        if move_like and len(move_like_tracks) > min_num_like:
            # Step 3: Identify or create the target "like" playlist for moved tracks
            like_pl_id = None
            like_vids = [t['videoId'] for t in move_like_tracks]
            like_pl = None
            # Identify source type for replacement
            suffix = ' radio' if ' radio' in pl_info["title"] else ' albums'
            like_pl_matches = self._radio_to_like_map.loc[
                self._radio_to_like_map['radio_playlist'] == pl_info["title"]].dropna()
            if len(like_pl_matches):  # Nan or mapping
                like_pl = like_pl_matches.iloc[0]['like_playlist']
            elif pl_info["title"].replace(suffix, '') in self.playlist_titles:
                like_pl = pl_info["title"].replace(suffix, '')
            if like_pl == None:
                if create_like_playlist:
                    pl_str = f'{pl_info["title"]} [{DATE}]'
                    like_pl = pl_info["title"].replace(suffix, '')
                    like_pl_id = self.yt.create_playlist(
                        title=like_pl.strip(),
                        description=f'Favorite tracks from {pl_str}',
                        privacy_status='PRIVATE', video_ids=like_vids)
                    self.playlist_titles = self.playlist_titles | {like_pl.strip()}
                    if verbose:
                         print(f'Created LIKE playlist for '
                               f'{pl_info["title"]}: {like_pl}')
                    time.sleep(2*sleep)
            else:
                like_pl_id = None
                res = self.query_by_title(like_pl)
                if res is not None:
                    like_pl_id = res.playlistId
                if like_pl_id is None:
                    if create_like_playlist:
                        print(
                            f"Mapped LIKE playlist '{like_pl}' not found. Creating it...")
                        like_pl_id = self.yt.create_playlist(
                            title=like_pl.strip(),
                            description=f'Favorite tracks from {pl_info["title"]} [{DATE}]',
                            privacy_status='PRIVATE', video_ids=like_vids)
                        self.playlist_titles = self.playlist_titles | {like_pl.strip()}
                        time.sleep(2 * sleep)
                        # We just added them all
                        like_orig_vids = frozenset(like_vids)
                    else:
                        print(
                            f"WARNING: Mapped LIKE playlist '{like_pl}' does not exist! Skipping LIKE move.")
                        return {}
                else:
                    like_orig_vids = frozenset([t['videoId'] for t in
                                                self.playlist_get_info(
                                                    like_pl_id, use_cache=True,
                                                    use_local_tsvs=use_local_tsvs).get('tracks', [])
                                                ])
                like_new_vids = frozenset(like_vids) - like_orig_vids
                like_dedupe_num = len(like_vids) - len(like_new_vids)
                if like_dedupe_num > 0:
                    like_vids = list(like_new_vids)
                if len(like_vids):
                    status = self.yt.add_playlist_items(
                        playlistId=like_pl_id, videoIds=like_vids, duplicates=False)
                    if status.get('status') == 'STATUS_SUCCEEDED':
                        if like_pl_id in self._info_cache:
                            new_tracks_added = [t for t in move_like_tracks if t['videoId'] in like_new_vids]
                            self._info_cache[like_pl_id]['tracks'].extend(new_tracks_added)
                            self._info_cache[like_pl_id]['trackCount'] = len(self._info_cache[like_pl_id]['tracks'])
                    else:
                        self._invalidate_playlist_cache(like_pl_id)
                    err_msg = (f'Bad Status for {pl_info["title"]} add '
                               f'{len(move_like_tracks)} LIKE tracks: {status}')
                    if status.get('status') != 'STATUS_SUCCEEDED':
                        raise RuntimeError(err_msg)
                    # Somtimes this still fails, fallback is to reemove like pl mapping so it generates a fresh pl
                    # TODO if this happens copy the create playlist fallback here
                    time.sleep(sleep)
                elif verbose:
                    print(f'No new LIKE tracks to add to playlist '
                          f'{like_pl_id}')

            if like_pl_id == None:
                if verbose:
                    print(f'No LIKE playlist for {pl_info["title"]}, ',
                          f'so not moving {len(move_like_tracks)} LIKE tracks')
                return {}

            # Step 4: Remove the moved LIKE tracks from the source radio playlist
            self.remove_playlist_items_chunked(
                pl_info["id"], move_like_tracks, sleep=sleep, label="LIKE", verbose=verbose)
            if verbose and len(move_like_tracks):
                print(f'Moved {len(move_like_tracks)} LIKE entries '
                      f'from {pl_info["title"]} to {like_pl_id}')

        # Step 5: Remove NOT_LIKE / DISLIKE tracks from the source radio playlist
        if remove_not_like and len(remove_not_like_tracks):
            if remove_dislike and len(remove_dislike_tracks):
                remove_not_like_tracks += remove_dislike_tracks

            self.remove_playlist_items_chunked(
                pl_info["id"], remove_not_like_tracks, sleep=sleep, label="NOT_LIKE", verbose=verbose)
            if verbose and len(remove_not_like_tracks):
                print(f'Removed {len(remove_not_like_tracks)} NOT_LIKE '
                      f'entries from {pl_info["title"]}')

        elif remove_dislike and len(remove_dislike_tracks):
            self.remove_playlist_items_chunked(
                pl_info["id"], remove_dislike_tracks, sleep=sleep, label="DISLIKE", verbose=verbose)
            if verbose and len(remove_dislike_tracks):
                print(f'Removed {len(remove_dislike_tracks)} DISLIKE '
                      f'entries from {pl_info["title"]}')
        return pl_counters

    def clean_playlists(self, do_dry_run=False, verbose=False, move_like=True,
                        min_num_like=10, sleep=1, create_like_playlist=True,
                        remove_not_like=True, remove_dislike=True,
                        playlist_skip_kinds=PLAYLIST_CLEAN_SKIP_KINDS,
                        skip_if_dislike=True, like_playlist_min_like_pct=80,
                        not_like_playlist_max_like_pct=20,
                        radio_playlist_max_like_pct=50, duplicate_threshold=5,
                        playlist_skip_starts_with=PLAYLIST_SKIP_STARTS_WITH,
                        use_local_tsvs=True):
        """
        Cleans up playlists by moving liked/disliked tracks to appropriate locations.
        """
        pl_ct = Counter()
        like_results, radio_results = {}, {}
        playlists_kinds = {k: set() for k in self._valid_playlist_kinds}
        n_playlists = len(self.playlists)
        start_time = time.time()
        print(f'Attempting to clean {n_playlists} playlists')
        for i, p in self.playlists.iterrows():
            if i < PLAYLIST_START_INDEX:
                continue
            eta = self._get_eta(start_time, i, n_playlists)
            eta_str = f" (~{eta})" if eta else ""
            pl_ct['playlists_processed'] += 1

            # Correctly skip outer loop using a boolean flag
            skip_playlist = False
            for skip_str in playlist_skip_starts_with:
                if p.title.startswith(skip_str):
                    pl_ct[f'playlist_skip_starts_with_{skip_str}'] += 1
                    print(f'[{i+1}/{n_playlists}]{eta_str} SKIPPING: {p.title} (starts with {skip_str})')
                    skip_playlist = True
                    break
            if skip_playlist:
                continue

            # Check playlist privacy early using library metadata
            if p.get('privacy') == 'PUBLIC':
                pl_ct['playlist_is_public'] += 1
                print(f'[{i+1}/{n_playlists}]{eta_str} SKIPPING: {p.title} (privacy is PUBLIC)')
                continue

            # Check playlist count early using library metadata
            if 'count' in p and (pd.isna(p['count']) or p['count'] == 0):
                pl_ct['playlist_is_empty'] += 1
                print(f'[{i+1}/{n_playlists}]{eta_str} SKIPPING: {p.title} (empty)')
                continue

            # Infer playlist kind from title, default to LIKE if nothing inferred
            pl_kind = self.infer_playlist_kind(p)

            # Maybe skip playlist right away
            # Skip when unable to infer kind (ideally this is not called)
            if not pl_kind:
                pl_ct['playlist_kind_not_inferred'] += 1
                print(f'[{i+1}/{n_playlists}]{eta_str} SKIPPING: {p.title} (cannot infer kind)')
                continue
            pl_ct[f'playlist_kind_is_{pl_kind.lower()}'] += 1

            # Decide to skip playlist based on playlist kind
            playlists_kinds[pl_kind].add(p.title)
            if pl_kind in playlist_skip_kinds:
                pl_ct['playlist_kind_in_playlist_skip_list'] += 1
                print(f'[{i+1}/{n_playlists}]{eta_str} SKIPPING: {p.title} (kind: {pl_kind})')
                continue

            # Query playlist tracks and other metadata
            p_info = None
            if use_local_tsvs:
                tsv_filename = f"{p.title}.tsv".replace('"', "'")
                tsv_path = os.path.join(self.playlist_tsv_dir, tsv_filename)
                if os.path.exists(tsv_path):
                    try:
                        local_df = self._read_tsv(tsv_path)
                        p_info = {
                            'id': p.playlistId,
                            'playlistId': p.playlistId,
                            'title': p.title,
                            'privacy': p.get('privacy', 'PRIVATE'),
                            'trackCount': len(local_df),
                            'tracks': local_df.to_dict('records')
                        }
                    except Exception:
                        pass

            if p_info is None:
                try:
                    print(f"[{i+1}/{n_playlists}]{eta_str} Local TSV missing. Fetching from API: {p.title}...", flush=True)
                    p_info = self.playlist_get_info(
                        p.playlistId, playlist_limit=self.playlist_limit)
                    if 'tracks' not in p_info:  # try without cache
                        p_info = self.playlist_get_info(
                            p.playlistId, playlist_limit=self.playlist_limit, use_cache=False)
                except Exception as e:
                    pl_ct['playlist_fetch_failed'] += 1
                    print(f'[{i+1}/{n_playlists}]{eta_str} ERROR: Failed to fetch playlist info for {p.title}: {e}')
                    continue

            if 'tracks' not in p_info:
                pl_ct['playlist_is_empty'] += 1
                print(f'[{i+1}/{n_playlists}]{eta_str} SKIPPING: {p.title} (no tracks key)')
                continue
            if p_info['trackCount'] == 0:
                pl_ct['playlist_is_empty'] += 1
                print(f'[{i+1}/{n_playlists}]{eta_str} SKIPPING: {p.title} (empty)')
                continue
            # Check max length of playlist
            if len(p_info['tracks']) >= self.playlist_limit:
                pl_ct[f'playlist_has_>{self.playlist_limit}_limit'] += 1
                print(f'[{i+1}/{n_playlists}]{eta_str} SKIPPING: {p.title} (exceeds limit: {len(p_info["tracks"])})')
                continue
            # Check playlist privacy
            if p_info['privacy'] == 'PUBLIC':
                pl_ct['playlist_is_public'] += 1
                print(f'[{i+1}/{n_playlists}]{eta_str} SKIPPING: {p.title} (privacy is PUBLIC)')
                continue

            # Get ratings for playlist tracks
            ratings = {k: set() for k in self._valid_ratings}
            for track in p_info["tracks"]:
                pl_ct['track_processed'] += 1
                if track["likeStatus"] not in ratings.keys():
                    pl_ct['track_rating_is_none'] += 1
                    ratings['NONE'].add(track["videoId"])
                else:
                    pl_ct['track_rating_exists'] += 1
                    ratings[track["likeStatus"]].add(track["videoId"])

            # See if playlist is correctly flagged as LIKE or RADIO
            like_percent = round(
                100*len(ratings["LIKE"])/len(p_info["tracks"]))
            if not self._is_playlist_kind_ok(pl_kind, like_percent,
                                             like_playlist_min_like_pct,
                                             not_like_playlist_max_like_pct,
                                             radio_playlist_max_like_pct):
                pl_ct['playlist_kind_not_ok'] += 1
                print(f'WARNING NOT OK playlist: {p.title} of kind {pl_kind} '
                      f'({like_percent}% liked) has: {len(ratings["LIKE"])} likes, '
                      f'{len(ratings["DISLIKE"])} dislikes, '
                      f'{len(ratings["INDIFFERENT"])} indifferent, '
                      f'{len(ratings["NONE"])} none')

            # Potentially alter playlist, or generate new playlists
            if do_dry_run:
                continue

            # Remove duplicates from playlist
            n_dupes = self.playlist_remove_duplicates(
                p_info, duplicate_threshold, verbose=verbose)
            if n_dupes > 0:
                pl_ct['playlist_removed_duplicates'] += 1

            # Like all tracks in playlist if kind is LIKE
            if pl_kind == 'LIKE':
                if PLAYLIST_CLEAN_FORCE_RATE_LIKES:
                    rate_ct = self.playlist_rate_all_songs(
                        p_info, rating=pl_kind, skip_if_dislike=skip_if_dislike,
                        verbose=verbose, sleep_time=sleep)
                else:
                    rate_ct = {
                        'track_rated': 0,
                        'track_skip_dislike': 0,
                        'track_already_rated': len(p_info["tracks"])
                    }
                like_results[p.title] = rate_ct

                dupe_str = f" (removed {n_dupes} duplicates)" if n_dupes > 0 else ""
                print(
                    f'[{i+1}/{n_playlists}]{eta_str} Playlist {p.title}: '
                    f'Checked {len(p_info["tracks"])} tracks{dupe_str}... '
                    f'Rated {rate_ct["track_rated"]} new tracks as LIKE '
                    f'({rate_ct["track_already_rated"]} already rated, '
                    f'{rate_ct["track_skip_dislike"]} skipped dislike)'
                )
                continue
            elif pl_kind == 'INDIFFERENT':
                rate_ct = self.clean_up_radio_playlist(
                    pl_info=p_info,
                    verbose=verbose, sleep=sleep,
                    move_like=move_like, min_num_like=min_num_like,
                    create_like_playlist=create_like_playlist,
                    remove_dislike=remove_dislike,  remove_not_like=remove_not_like,
                    use_local_tsvs=use_local_tsvs)
                radio_results[p.title] = rate_ct

                dupe_str = f" (removed {n_dupes} duplicates)" if n_dupes > 0 else ""
                changes_str = []
                if rate_ct.get('moved_like', 0) > 0:
                    changes_str.append(f"moved {rate_ct['moved_like']} LIKE")
                if rate_ct.get('removed_not_like', 0) > 0:
                    changes_str.append(f"removed {rate_ct['removed_not_like']} NOT_LIKE")
                if rate_ct.get('removed_dislike', 0) > 0:
                    changes_str.append(f"removed {rate_ct['removed_dislike']} DISLIKE")

                if changes_str:
                    clean_str = "... Cleaned: " + ", ".join(changes_str)
                else:
                    clean_str = "... No changes"
                print(
                    f'[{i+1}/{n_playlists}]{eta_str} Playlist {p.title}: '
                    f'Checked {len(p_info["tracks"])} tracks{dupe_str}'
                    f'{clean_str}'
                )
                continue

        # Package results
        pl_ct = pd.DataFrame.from_dict(dict(pl_ct), orient='index')
        pl_ct.columns = ['count']
        print(f'Final Playlist Cleanup Counters:\n{pl_ct}')

        like_results = pd.DataFrame(like_results).T
        if 'track_rated' in like_results.columns:
            like_results = like_results.sort_values(
                'track_rated', ascending=False)

        radio_results = pd.DataFrame(radio_results).T
        if 'moved_like' in like_results.columns:
            radio_results = radio_results.sort_values('moved_like')
        radio_results['total_changes'] = radio_results.sum(axis=1)
        radio_results = radio_results.sort_values(
            'total_changes', ascending=False)
        return like_results, radio_results, pl_ct

    def _safe_sleep(self, seconds: float, jitter_ratio: float = 0.3) -> None:
        """Sleeps for a given duration with random jitter to mimic human behavior."""
        if seconds <= 0:
            return
        jitter = random.uniform(-seconds * jitter_ratio, seconds * jitter_ratio)
        actual_sleep = max(0.05, seconds + jitter)
        time.sleep(actual_sleep)

    def playlist_rate_all_songs(self, pl_info, rating, sleep_time=0.5,
                                verbose=False, skip_if_dislike=False,
                                valid_ratings=VALID_TRACK_RATINGS):
        if rating not in valid_ratings:
            raise ValueError(f"Invalid rating '{rating}'. Expected one of: {valid_ratings}")

        tracks_to_rate = []
        already_rated = 0
        skipped_dislike = 0
        for track in pl_info["tracks"]:
            if skip_if_dislike and track.get("likeStatus") == 'DISLIKE':
                skipped_dislike += 1
                continue
            if track.get("likeStatus") == rating:
                already_rated += 1
                continue
            tracks_to_rate.append(track)

        num_to_rate = len(tracks_to_rate)
        if num_to_rate > 0 and verbose:
            # Estimate time: (sleep_time + 0.5s avg API latency) per track
            est = int(num_to_rate * (sleep_time + 0.5))
            est_str = f"{est // 60}m {est % 60}s" if est >= 60 else f"{est}s"
            print(
                f'Playlist {pl_info["title"]}: {num_to_rate} tracks '
                f'to rate as {rating} (approx {est_str})...'
            )

        rate_ct = {
            'track_rated': 0,
            'track_skip_dislike': skipped_dislike,
            'track_already_rated': already_rated
        }

        for track in tracks_to_rate:
            self.yt.rate_song(track["videoId"], rating=rating)
            rate_ct['track_rated'] += 1
            self._safe_sleep(sleep_time)

        return rate_ct

    def playlist_remove_duplicates(self, pl_info,
                                   duplicate_threshold=DUPLICATE_THRESHOLD,
                                   sleep_time=0.5, verbose=False, shuffle=False):
        # 1. Check if we actually have duplicates
        unique_vids = set(t['videoId'] for t in pl_info['tracks'])
        num_duplicates = len(pl_info['tracks']) - len(unique_vids)

        if num_duplicates < duplicate_threshold and not shuffle:
            return 0

        # 2. We have duplicates. If loaded from local TSV, we must fetch from API to get setVideoIds
        if len(pl_info['tracks']) > 0 and 'setVideoId' not in pl_info['tracks'][0]:
            pl_info = self.playlist_get_info(pl_info['id'], playlist_limit=self.playlist_limit, use_cache=False)

        track_ids = [(t['videoId'], t['setVideoId'])
                     for t in pl_info['tracks']]

        if shuffle:
            tracks_unique = list(
                frozenset([t[0] for t in track_ids]) - self.banned_vid_set)
            # Need to map back to original setVideoIds after shuffle, might lose order here
            set_video_id_map = {t[0]: t[1] for t in track_ids}
            tracks_to_keep = [{'videoId': vid, 'setVideoId': set_video_id_map.get(
                vid)} for vid in tracks_unique]
        else:
            seen = set()
            tracks_to_keep = [
                x for x in pl_info['tracks'] if x['videoId'] not in seen and not seen.add(
                    x['videoId']) and x['videoId'] not in self.banned_vid_set
            ]

        tracks_to_remove = [
            track for track in pl_info['tracks'] if track not in tracks_to_keep]
        n_dupes = len(tracks_to_remove)

        if n_dupes >= duplicate_threshold:
            self.yt.remove_playlist_items(
                playlistId=pl_info['id'], videos=tracks_to_remove)
            self._safe_sleep(sleep_time)
            self._invalidate_playlist_cache(pl_info['id'])
            pl_info['tracks'] = tracks_to_keep
            pl_info['trackCount'] = len(tracks_to_keep)
        else:
            n_dupes = 0
        return n_dupes

    def sort_playlist(self, playlist_id, sort_by="artist", reverse=False):
        """Sorts a playlist by artist, album, like status, or randomly."""
        playlist = self.yt.get_playlist(playlistId=playlist_id)
        if not playlist or "tracks" not in playlist:
            print(
                f"Error: Could not retrieve playlist or playlist is empty {playlist_id}."
            )
            return None

        if sort_by == "artist":
            playlist["tracks"].sort(
                key=lambda track: (
                    track["artists"][0]["name"].lower(
                    ) if track.get("artists") else "",
                    track["album"]["name"].lower(
                    ) if track.get("album") else "",
                ),
                reverse=reverse,
            )
        elif sort_by == "album":
            playlist["tracks"].sort(
                key=lambda track: track["album"]["name"].lower()
                if track.get("album")
                else "",
                reverse=reverse,
            )
        elif sort_by == "likeStatus":
            playlist["tracks"].sort(
                key=lambda track: track.get("likeStatus", ""), reverse=reverse
            )
        elif sort_by == "random":
            random.shuffle(playlist["tracks"])
        else:
            print(f"Error: Invalid sort_by value: {sort_by}")
            return None

        # Remove all items and re-add in sorted order
        tracks_to_remove = playlist["tracks"]
        self.yt.remove_playlist_items(
            playlistId=playlist_id, videos=tracks_to_remove)

        # Adjust sleep time based on number of tracks and API limits
        sleep_time_adjusted = 0.5 + (len(playlist["tracks"]) // 100) * 0.5
        time.sleep(sleep_time_adjusted)

        video_ids_sorted = [track["videoId"] for track in playlist["tracks"]]
        self.yt.add_playlist_items(
            playlistId=playlist_id, videoIds=video_ids_sorted)

        print(
            f"Playlist {playlist_id} sorted by {sort_by} "
            f"{'(reversed)' if reverse else ''}."
        )
        self._invalidate_playlist_cache(playlist_id)
        return playlist_id

    def playlist_get_all_like_playlists(self):
        like_playlists_ids = {}
        for i, row in self.playlists.iterrows():
            if self._playlist_is_like(row.title):
                like_playlists_ids[row.title] = row.playlistId
        return like_playlists_ids

    def playlist_get_all_radio_playlists(self):
        radio_playlists_ids = {}
        for i, row in self.playlists.iterrows():
            if self._playlist_is_radio(row.title):
                radio_playlists_ids[row.title] = row.playlistId
        return radio_playlists_ids

    def infer_playlist_kind(self, p_row):
        if str(p_row.author) == 'nan':  # (auto generated by yt)
            return 'YT_GENERATED'
        elif self._playlist_is_albums(p_row.title):
            return 'ALBUM'
        elif self._playlist_skip_starts_with(p_row.title):
            return 'SKIP'
        elif self._playlist_is_radio(p_row.title):
            return 'INDIFFERENT'
        elif self._playlist_is_not_like(p_row.title):
            return 'NOT_LIKE'
        elif self._playlist_is_like(p_row.title):
            return 'LIKE'
        return None  # handle this case when using result

    def _is_playlist_kind_ok(self, pl_kind, like_percent,
                             like_min_pct=80, notlike_max_pct=20,
                             radio_max_pct=50, valid_playlist_kinds=VALID_PLAYLIST_KINDS):
        if pl_kind not in valid_playlist_kinds:
            raise ValueError(f"Invalid playlist kind '{pl_kind}'. Expected one of: {valid_playlist_kinds}")
        # Not OK Cases
        if pl_kind == 'LIKE' and like_percent <= like_min_pct:
            return False
        elif pl_kind == 'RADIO' and like_percent >= radio_max_pct:
            return False
        elif pl_kind == 'NOT_LIKE' and like_percent >= notlike_max_pct:
            return False
        return True

    def _playlist_is_not_like(self, name, not_like_toks=NOT_LIKE_TOKS):
        name = name.lower()
        if name.startswith('_'):
            return False
        if NOT_LIKE_PREFIX in name:
            return True
        return any(tok in name for tok in not_like_toks)

    def _playlist_is_like(self, name, like_toks=LIKE_TOKS):
        name = name.lower()
        if name.startswith('_') or name.endswith('albums'):
            return False
        if self._playlist_is_not_like(name):
            return False
        if any(t.lower() == name for t in self._like_playlist_titles):
            return True
        return any(tok in name for tok in like_toks)

    def _playlist_is_radio(self, name, radio_toks=RADIO_TOKS):
        name = name.lower()
        if self._playlist_is_like(name):
            return False
        return any(tok in name for tok in radio_toks)

    def _playlist_is_albums(self, name, album_toks=ALBUM_TOKS):
        name = name.lower()
        return any(tok in name for tok in album_toks)

    def _playlist_skip_starts_with(self, name, start_toks=SKIP_STARTS_WITH_TOKS):
        name = name.lower()
        return any(name.startswith(tok) for tok in start_toks)

    # Backup Job for yt playlists, library and weekly management
    def run_backup(self, skip_playlist_tsv_backup=SKIP_PLAYLIST_BACKUP):
        start_time = time.time()
        # Backup playlists and fetch (or load from file) all playlist
        # and library tracks. The set of tracks are missing ytmusic
        # metadata like release year.
        if not skip_playlist_tsv_backup:  # regenerate tracks_no_meta
            tracks_no_meta = self.backup_playlists_and_collect_tracks(
                remove_disliked=True,
                include_library_tracks=True)
            self._save_tsv(tracks_no_meta, self.tracks_no_meta_tsv)

        # Reload tsb dbs
        track_db = self._read_tsv(self.track_db_tsv, use_track_defaults=True)
        tracks_no_meta = self._read_tsv(
            self.tracks_no_meta_tsv, use_track_defaults=True)
        # Get ytmusic metadata for new tracks from tracks_no_meta, update tracks_db
        new_tracks_no_meta = self._track_db_new_or_newly_liked_tracks(
            track_db, tracks_no_meta)
        track_db = self._track_db_update(track_db, new_tracks_no_meta)
        self._save_tsv(track_db, self.track_db_tsv)

        # Update combined like and not_like tsvs
        not_like_tracks = self.collect_all_not_like_tracks_from_tsvs()
        self._save_tsv(not_like_tracks, self.not_like_tsv)
        self._not_like_df = not_like_tracks  # Update cache
        like_tracks = self.collect_all_like_tracks_from_tsvs()
        self._save_tsv(like_tracks, self.like_tsv)
        self._like_df = like_tracks  # Update cache

        # Update like or not_like tracks that need manual review
        need_review = self.get_like_not_like_tracks_to_review()
        need_review.to_csv(self.need_rate_tsv, sep='\t', index=True)

        # Update playlist counts for radio playlists
        radio_counts_df = self.get_playlist_counts(
            filter_title='radio', verbose=False, use_local_tsvs=not PLAYLIST_BACKUP_FULL_RUN)
        radio_counts_df.to_csv(self.radio_count_file, sep='\t', index=False)

        # General automated task playlist todos
        # TODO add playlist to super playlists if exist see pdf
        # TODO auto generate some date based like playlists
        # TODO move based on playcount (if not LIKE infer NOT_LIKE based on large playcount)

        # Clean radio playlists, move like, dislike, not_like.
        if not SKIP_PLAYLIST_CLEAN:
            like_results, radio_results, pl_counters = self.clean_playlists(
                verbose=True, sleep=PLAYLIST_SLEEP,
                do_dry_run=PLAYLIST_CLEAN_DRY_RUN,
                move_like=PLAYLIST_CLEAN_MOVE_LIKE,
                min_num_like=PLAYLIST_CLEAN_MIN_LIKE_TO_SPLIT,
                create_like_playlist=PLAYLIST_CLEAN_CREATE_LIKE_PLAYLIST,
                remove_dislike=PLAYLIST_CLEAN_RM_NOT_LIKE_AND_DISLIKE,
                remove_not_like=PLAYLIST_CLEAN_RM_NOT_LIKE_AND_DISLIKE,
                playlist_skip_kinds=PLAYLIST_CLEAN_SKIP_KINDS,
                skip_if_dislike=PLAYLIST_CLEAN_SKIP_IF_DISLIKE,
                like_playlist_min_like_pct=PLAYLIST_CLEAN_LIKE_MIN_LIKE_PCT,
                not_like_playlist_max_like_pct=PLAYLIST_CLEAN_NOT_LIKE_MAX_LIKE_PCT,
                radio_playlist_max_like_pct=PLAYLIST_CLEAN_RADIO_MAX_LIKE_PCT,
                duplicate_threshold=PLAYLIST_CLEAN_DUPLICATE_THRESH,
                playlist_skip_starts_with=PLAYLIST_SKIP_STARTS_WITH
            )
            like_results.to_csv(self.like_cleanup_file, sep='\t')
            radio_results.to_csv(self.radio_cleanup_file, sep='\t')
            pl_counters.to_csv(self.cleanup_counters_file, sep='\t')

        print(f'Completed in {(time.time() - start_time) / 60:.1f}',
              'minutes', flush=True)

    def _save_tsv(self, df, path, index=True):
        df = df.copy()
        # 1. Ensure index alignment
        if index and df.index.name is None:
            df.index.name = 'videoId'

        # Fill NaN values with empty strings before converting to string
        df = df.fillna('')

        # Prevent backslashes from escaping tabs and breaking TSV columns
        df = df.astype(str).replace(
            {r'\t': ' ', r'[\r\n]+': ' ', '"': "'", r'\\': '/'}, regex=True)

        # 3. Save as the strict text grid atomically to avoid file locks
        tmp_path = path + '.tmp'
        df.to_csv(tmp_path, sep='\t', index=index,
                  quoting=TSV_TRACK_QUOTING, encoding='utf-8')
        os.replace(tmp_path, path)

    def save_playlist_tsv(self, pl_info, track_cols=TRACK_TSV_COLS,
                          remove_disliked=False):
        tracks, metadata = self.parse_playlist(pl_info, verbose=True)
        tracks['playlists'] = pl_info['title']
        if remove_disliked:
            tracks_disliked = tracks.loc[tracks['likeStatus'] == 'DISLIKE']
            # metadata['author']['name'] == 'Jake G' # author storage changed in yt?
            if len(tracks_disliked):
                try:
                  print(f'Removing {len(tracks_disliked)}',
                        f'tracks:\n{tracks_disliked["title"]}')
                  self.yt.remove_playlist_items(
                      metadata['id'], tracks_disliked.to_dict('records'))
                  tracks = tracks.loc[tracks['likeStatus'] != 'DISLIKE']
                except Exception as e:
                  print(f"Failed to remove dislike, error:\n{e}")
        if len(tracks):  # Sort tsv deterministically by adding tie-breakers
            fname = os.path.join(
                self.playlist_tsv_dir, f"{pl_info['title']}.tsv")
            # Filter columns and sort before saving
            tracks = tracks[track_cols + ['playlists']].sort_values(
                ['likeStatus', 'artist', 'album', 'title', 'videoId'], ascending=False
            )   # index=False if videoId is a col
            self._save_tsv(tracks, fname, index=False)
        return tracks, metadata

    def backup_playlists_and_collect_tracks(self,
                                            remove_disliked=False,
                                            include_library_tracks=True,
                                            song_lim=PLAYLIST_LIMIT,
                                            track_cols=TRACK_TSV_COLS,
                                            metadata_cols=PLAYLIST_METADATA_TSV_COLS,
                                            track_remove_cols=TRACK_REMOVE_COLS):
        """
        Backs up library playlists and returns a unique tracks DataFrame.
        """
        all_playlist_info = []
        all_tracks = []
        start_time = time.time()
        print(f'Fetching and backing up playlists to:\n'
              f'  {os.path.abspath(self.playlist_tsv_dir)}\n'
              f'(skips unchanged, up to ~10 min)')
        for i, row in self.playlists.iterrows():
            eta = self._get_eta(start_time, i, len(self.playlists))
            eta_str = f" (~{eta})" if eta else ""
            try:
                pl_title = self._decode(row['title'])
                print(f'[{i+1}/{len(self.playlists)}]{eta_str} {pl_title}', flush=True)
                if i < PLAYLIST_START_INDEX:
                    print(f'Skipping {i}: {pl_title}...')
                    continue

                # Check for incremental backup
                tsv_filename = f"{pl_title}.tsv".replace('"', "'")
                tsv_path = os.path.join(self.playlist_tsv_dir, tsv_filename)

                api_track_count = 0
                if 'count' in row and not pd.isna(row['count']):
                    try:
                        api_track_count = int(row['count'])
                    except ValueError:
                        pass

                # Check if TSV exists and matches the count
                if not PLAYLIST_BACKUP_FULL_RUN and os.path.exists(tsv_path) and api_track_count > 0:
                    try:
                        local_df = self._read_tsv(tsv_path)
                        if len(local_df) == api_track_count:
                            print(f'Skipping API fetch: {pl_title} matches local TSV count ({api_track_count} tracks)')
                            metadata = {
                                'id': row['playlistId'],
                                'title': row['title'],
                                'description': row.get('description', ''),
                                'trackCount': api_track_count,
                                'author': row.get('author', '')
                            }
                            all_playlist_info.append(metadata)
                            all_tracks.append(local_df)
                            continue
                    except Exception as e:
                        print(f"Warning: Failed to read local TSV for {pl_title}: {e}. Falling back to API fetch.")

                # Fallback to full API fetch and save
                playlist_info = self.playlist_get_info(
                    row['playlistId'], playlist_limit=song_lim, use_cache=True)
                if playlist_info.get('trackCount', 0) == 0:
                    print(f'Skipping: {pl_title}, due to zero tracks')
                    continue
                tracks, metadata = self.save_playlist_tsv(
                    playlist_info, remove_disliked=remove_disliked)
                all_playlist_info.append(metadata)
                all_tracks.append(tracks)

                if PLAYLIST_SLEEP:
                    actual_sleep = (
                        PLAYLIST_SLEEP + random.uniform(-PLAYLIST_SLEEP, PLAYLIST_SLEEP) / 2)
                    print(f'Sleeping {actual_sleep:.1f} seconds.')
                    time.sleep(actual_sleep)
                print(90*'-')
            except Exception as e:
                print(f'Error in playlist {i}: {e}')
                print(f'Error in playlist title: {pl_title}')

        # Package playlist metadata
        playlist_info = pd.DataFrame(all_playlist_info)[metadata_cols]
        playlist_info = playlist_info.replace(  # Sanitize titles and descriptions
            {r'[\t\n\r]': ' ', '"': "'"}, regex=True)
        playlist_info.sort_values('title', ascending=False).to_csv(
            os.path.join(self.playlist_tsv_dir, '_playlists.tsv'), sep='\t', header=True)
        playlist_elapsed = (time.time() - start_time) / 60
        print(f'Backed up playlist metadata:\n{playlist_info}')
        print(f'Fetched playlist metadata in {playlist_elapsed:.2f} minutes')

        # Fetch Library Tracks
        if include_library_tracks:
            t1 = time.time()
            print('Fetching library tracks (approx 7 min)...')
            library_tracks = self.parse_tracks(
                self.yt.get_library_songs(limit=song_lim))
            library_tracks = library_tracks.replace(  # Sanitize titles and descriptions
                {r'[\t\n\r]': ' ', '"': "'"}, regex=True)
            all_tracks.append(library_tracks)
            library_elapsed = (time.time() - t1) / 60
            print(f'Fetched {len(library_tracks)} tracks in',
                  f'{library_elapsed:.2f} minutes\n')
            library_tracks = library_tracks.sort_values('artist')
            fname = os.path.join(self.playlist_tsv_dir, '_library.tsv')
            self._save_tsv(library_tracks[track_cols], fname, index=False)

        print("\nNormalizing and Concatenating tracks...")
        cleaned_tracks = []
        for i, df in enumerate(all_tracks):
            df = df.reset_index(drop=True)
            if 'videoId' not in df.columns and 'Unnamed: 0' in df.columns:
                df = df.rename(columns={'Unnamed: 0': 'videoId'})
            if 'videoId' in df.columns:
                if isinstance(df['videoId'], pd.DataFrame):
                    temp_vids = df['videoId'].iloc[:, 0]
                    df = df.drop(columns='videoId')
                    df['videoId'] = temp_vids

                df['videoId'] = df['videoId'].astype(str)
                cleaned_tracks.append(df.dropna(subset=['videoId']))
            else:
                found = False
                for col in df.columns:
                    if str(col).lower() == 'videoid':
                        df = df.rename(columns={col: 'videoId'})
                        df['videoId'] = df['videoId'].astype(str)
                        cleaned_tracks.append(df.dropna(subset=['videoId']))
                        found = True
                        break
        combined_df = pd.concat(cleaned_tracks, ignore_index=True)
        dupe_cols = combined_df.columns.duplicated()
        combined_df = combined_df.loc[:, ~dupe_cols].copy()
        print(f"Deduplicating {len(combined_df)} tracks...")
        combined_df = combined_df.sort_values(
            ['likeStatus', 'artist'], ascending=[False, True])
        unique_tracks = combined_df.drop_duplicates(
            subset=['videoId']).set_index('videoId')
        if 'playlists' in combined_df.columns:
            pl_merge = combined_df.groupby('videoId')['playlists'].apply(lambda x: list(set(
                [item for sublist in x.dropna().apply(lambda p: ast.literal_eval(p) if isinstance(p, str) and p.startswith('[') else [p])
                 for item in (sublist if isinstance(sublist, list) else [sublist])]
            )))
            unique_tracks['playlists'] = pl_merge
        elapsed_minutes = (time.time() - start_time) / 60.0
        print(f'Backed up {len(playlist_info)} playlists and {len(unique_tracks)}',
              f'unique tracks\nJob completed in {elapsed_minutes:.2f} minutes to:',
              f'{self.playlist_tsv_dir}')
        return unique_tracks

    # Functions for aggregating from playlist tsvs
    def collect_all_like_tracks_from_tsvs(self, tsv_header=LIKE_TRACKS_HEADER):
        collected_like_tracks = self._collect_tracks_from_playlists(
            self._playlist_is_like,
            track_filter_fn=lambda df: df.loc[df['likeStatus'] == 'LIKE'],
            tsv_header=tsv_header,
            print_stats=True
        )

        # Load already existing like list tsv
        like_tracks_existing = self._get_like_df()
        assert_msg = (f'Expected {self.like_tsv} to have header {tsv_header}, '
                      f'not: {like_tracks_existing.columns}')
        if list(like_tracks_existing.columns) != tsv_header:
            raise ValueError(assert_msg)

        # Update and save tsv, append new like tracks in db but not in like list
        new_like_tracks = collected_like_tracks.loc[frozenset(
            collected_like_tracks.index) - frozenset(like_tracks_existing.index)]
        all_like_tracks = pd.concat([like_tracks_existing, new_like_tracks])

        print(f'Updated liked tracks with {len(new_like_tracks)} new entries '
              f'(from {len(like_tracks_existing)} to {len(all_like_tracks)}).', flush=True)
        return all_like_tracks

    def collect_all_not_like_tracks_from_tsvs(self, tsv_header=LIKE_TRACKS_HEADER):
        not_like_tracks = self._collect_tracks_from_playlists(
            self._playlist_is_not_like,
            tsv_header=tsv_header,
            print_stats=False
        )
        print(
            f'Updated not liked tracks, contains {len(not_like_tracks)} entries.', flush=True)
        return not_like_tracks

    # Functions for dealing with track db tsv
    @retry(retries=3, delay=1)
    def _track_db_get_track_info(self, row):
        copy_song_cols = ['keywords', 'averageRating', 'viewCount', 'release']
        copy_album_cols = ['type', 'trackCount', 'year']  # 'duration',
        # Safe extraction if strings are missing
        track_str = f"{row.get('artist', '')} - {row.get('album', '')} - {row.get('title', '')}"
        track_str = unicodedata.normalize(
            'NFKD', track_str).encode('ascii', 'ignore').decode('ascii')
        # Safely handle missing artistId (NaN from TSV)
        raw_id = row.get('artistId')
        # Force it to be a string, or an empty string if it's missing/NaN
        artist_id = str(raw_id) if pd.notna(raw_id) else ""
        if not artist_id:
            track_title = row.get('title', 'Unknown Title')
            # Normalize and encode to ASCII to strip accents for the terminal log
            safe_title = unicodedata.normalize('NFKD', str(track_title)).encode(
                'ascii', 'ignore').decode('ascii')
            print(f'WARNING: Missing artistId (NaN) for track:',
                  f'"{safe_title}". Processing anyway...')
        elif 'privately_owned' in artist_id:
            print(f'\nSkipping privately owned track...')
        try:
            song = self.yt.get_song(row.name)  # row.name is videoId
        except Exception as e:
            print(
                f"WARNING: Failed to fetch song info for videoId {row.name} ({track_str}): {e}")
            return row

        for col in copy_song_cols:
            if col not in song:
                continue
            if col == 'release' and not self._is_valid_date(song['release']):
                print(f'\tSkipping release field,',
                      f'not a valid date: {track_str}')
                continue
            row[col] = song[col]
        album_id = row.get('albumId')
        # Safely check if albumId exists and is valid before fetching
        if pd.notna(album_id) and str(album_id).strip() not in ['', 'nan', 'None']:
            try:
                album = self.yt.get_album(str(album_id))
            except Exception as e:
                print(f'ERROR running: get_album(albumID)\n',
                      f'{e} for row: {track_str}')
                return row
            # Get values or default to empty list if they are None
            album_artists = album.get('artists') or []
            album_tracks = album.get('tracks') or []
            if len(album_artists):
                row['albumArtist'] = album_artists[0]['name']
            elif len(album_tracks) and len(album_tracks[0].get('artists') or []):
                row['albumArtist'] = album_tracks[0]['artists'][0]['name']
            else:
                print(f'\nERROR Failed: len(album["artists"])',
                      f'for album:  {track_str}')
            for col in copy_album_cols:
                if col not in album:
                    continue
                new_col = f'album{col[0].upper()}{col[1:]}'
                if album[col]:
                    row[new_col] = album[col]
                else:
                    print(f'\nERROR column {col} not in',
                          f'albums: {track_str}')
        else:
            print("Warning: No valid albumId found for track:",
                  f"{track_str}. Skipping album metadata.")
        return row

    def _track_db_new_or_newly_liked_tracks(self, track_db, tracks_no_meta):
        ignored = set()
        if os.path.exists(self.duplicate_tracks_tsv):
            ignored = set(self._read_tsv(self.duplicate_tracks_tsv, index_col=None)['videoId'])
        new_track_ids = set(tracks_no_meta.index) - set(track_db.index) - ignored
        # Find existing tracks whose status changed to LIKE, and queue them for re-scraping
        existing = tracks_no_meta[~tracks_no_meta.index.isin(new_track_ids)]
        tracks_no_meta_liked = existing[existing['likeStatus'] == 'LIKE']
        track_db_not_liked = track_db[track_db['likeStatus'] != 'LIKE']
        new_track_rating = set(track_db_not_liked.index) & set(
            tracks_no_meta_liked.index)
        print(f'Re-adding {len(new_track_rating)} tracks now LIKE')
        track_db = track_db[~track_db.index.isin(new_track_rating)]
        new_track_ids |= new_track_rating
        # Get metadata for new/changed traks
        new_tracks_no_meta = tracks_no_meta.loc[list(new_track_ids)]
        return new_tracks_no_meta

    def _track_db_update(self, track_db, new_tracks, verbose=False):
        print(f"Track database has {len(track_db)} tracks")
        print(f"Found {len(new_tracks)} unique new tracks")
        i = 0
        tracks_w_info = []
        t0 = time.time()
        for _, row in new_tracks.iterrows():
            i += 1
            tracks_w_info.append(self._track_db_get_track_info(row))
            track_str = self._decode(
                f"{row['artist']} - {row['album']} - {row['title']}")
            if 'likeStatus' in row:
                track_str += self._decode(f" -> {row['likeStatus']}")
            if 'albumYear' in row:
                track_str += self._decode(f" ({row['albumYear']})")

            # if 'averageRating' in row:
            #     track_str += self._decode(f" rating={round(row['averageRating'],2)}")
            # if 'release' in row:
            #     track_str += self._decode(f" ({row['release']})")
            # if 'albumType' in row:
            #     track_str += self._decode(f" | {row['albumType']}")

            # Calculate dynamic ETA
            eta = self._get_eta(t0, i, len(new_tracks), min_idx=6)
            eta_str = f" (~{eta})" if eta else ""

            print(f"[{i}/{len(new_tracks)}]{eta_str} {track_str}")

            # Save checkpoint to allow seamless resuming if interrupted
            if i % CHECKPOINT_INTERVAL == 0:
                checkpoint_df = pd.concat(
                    [track_db, pd.DataFrame(tracks_w_info)])
                checkpoint_df = self._track_db_dedupe(
                    checkpoint_df, keep='last', verbose=False)
                self._save_tsv(checkpoint_df, self.track_db_tsv)
                if verbose:
                    print(f"Saved checkpoint at {i}/{len(new_tracks)} tracks")

        tracks_w_info = pd.DataFrame(tracks_w_info)
        tracks_w_info['date_modified'] = DATE
        # Strip tabs/newlines, and swap double quotes for single quotes
        tracks_w_info = tracks_w_info.replace(
            {r'[\t\n\r]': ' ', '"': "'"}, regex=True)
        print(f'Scraped info for {len(tracks_w_info)} tracks')
        track_db = pd.concat([track_db, tracks_w_info])
        track_db = self._track_db_dedupe(track_db, keep='last')
        track_db = track_db.sort_values(['artist', 'album'])
        # Ensure final save is written
        self._save_tsv(track_db, self.track_db_tsv)
        elapsed_t = (time.time() - t0) / 60
        print(f'Finished in {elapsed_t:0.1f} minutes')
        print(f'Track database now has {len(track_db)} tracks')
        return track_db

    def _track_db_dedupe(self, track_db, keep='last', verbose=True):
      original_ids = set(track_db.index)
      stats_msgs = []

      # 1. Exact row duplicates
      prev_len = len(track_db)
      track_db = track_db.drop_duplicates(keep=keep)
      stats_msgs.append(
          f"Removed {prev_len - len(track_db)} exact duplicate rows")

      # 2. Duplicate subsets ignoring specific columns
      for ignore in [['playlists', 'inLibrary', 'artistId', 'albumId'],
                     ['title', 'album']]:
        prev_len = len(track_db)
        cols = [c for c in track_db.columns if c not in ignore]
        track_db = track_db.drop_duplicates(subset=cols, keep=keep)
        stats_msgs.append(
            f"Removed {prev_len - len(track_db)} row duplicates "
            f"(ignoring columns: {ignore})"
        )

      # 3. Duplicate index rows
      prev_len = len(track_db)
      track_db = track_db[~track_db.index.duplicated(keep=keep)]
      stats_msgs.extend([
          f"Removed {prev_len - len(track_db)} duplicate index rows",
          f"Final length of track_db: {len(track_db)}"
      ])

      if verbose:
        print("\n".join(stats_msgs))

      # Save removed videoIds as duplicates to prevent re-scraping them
      removed_ids = original_ids - set(track_db.index)
      if removed_ids:
          self._add_to_duplicate_tracks(removed_ids)

      return track_db

    def _add_to_duplicate_tracks(self, video_ids):
        existing = set()
        if os.path.exists(self.duplicate_tracks_tsv):
            existing = set(self._read_tsv(self.duplicate_tracks_tsv, index_col=None)['videoId'])
        new_ids = set(video_ids) - existing
        if new_ids:
            df = pd.DataFrame(sorted(list(existing | new_ids)), columns=['videoId'])
            self._save_tsv(df, self.duplicate_tracks_tsv, index=False)

    def _is_valid_date(self, date_str):
        try:
            datetime.datetime.strptime(date_str, '%Y-%m-%d')
            return True
        except ValueError:
            return False

    def _decode(self, string):
        if not string:
            return ""
        # Convert to string and ensure it's treated as UTF-8
        # We use 'backslashreplace' or 'replace' to ensure the print()
        # statement never hits a character it can't handle.
        try:
            return str(string).encode('utf-8', errors='ignore').decode('utf-8')
        except Exception:
            return str(string)

    def _get_eta(self, start_time, current, total, min_idx=1):
        if current < min_idx:
            return ""
        elapsed = time.time() - start_time
        avg_time = elapsed / current
        remaining = total - current
        return f"{((remaining * avg_time) / 60):.1f}m"


if __name__ == "__main__":
    import argparse

    import ytmusicapi as yt

    parser = argparse.ArgumentParser(
        description="YTMusic Library Backup & Automation")
    parser.add_argument("--skip-backup", action="store_true",
                        help="Skip backing up playlists to TSV")
    parser.add_argument("--no-log", action="store_true",
                        help="Disable logging to ytmusic_library.log")
    args = parser.parse_args()

    # Automatically redirect stdout/stderr to log file and console (like tee)
    if not args.no_log:
        class Tee:
            def __init__(self, filename):
                self.file = open(filename, 'w', encoding='utf-8')
                self.stdout = sys.stdout

            def write(self, data):
                self.file.write(data)
                self.stdout.write(data)
                self.file.flush()
                self.stdout.flush()

            def flush(self):
                self.file.flush()
                self.stdout.flush()

        sys.stdout = Tee("ytmusic_library.log")
        sys.stderr = sys.stdout

    print('Running main ytmusic library backup task')
    print("Pandas Version:", pd.__version__)
    print("YTMusic Version:", yt.__version__)
    print("Date:", DATE)

    # TODO track each run in a log and perhaps have a run monthly that runs if 30 days haave past
    Y = YTMusicPlaylists(header=HEADER_FILE, playlist_tsv_dir=PLAYLIST_TSV_DIR)
    Y.run_backup(
        skip_playlist_tsv_backup=args.skip_backup or SKIP_PLAYLIST_BACKUP)
