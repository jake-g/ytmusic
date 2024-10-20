import os
import time
import datetime
import unicodedata
import random
import pandas as pd
from collections import defaultdict
from ytmusicapi import YTMusic


# Global Prams
# When True, will reuse playlist tsvs from last backup
SKIP_PLAYLIST_BACKUP = False
# Regnerate playlists with more than this amount of duplicates
DUPLICATE_THRESHOLD = 3
# For requesting large playlists from api
PLAYLIST_LIMIT = 5000

# Settings for automated radio playlist like dislike not like cleanup.
SKIP_PLAYLIST_CLEAN = True #####################
PLAYLIST_CLEAN_RM_NOT_LIKE_AND_DISLIKE = False #####################
PLAYLIST_CLEAN_MOVE_LIKE =False #####################
PLAYLIST_CLEAN_CREATE_LIKE_PLAYLIST = False #####################
PLAYLIST_CLEAN_DRY_RUN = False
PLAYLIST_CLEAN_SKIP_IF_DISLIKE = True
PLAYLIST_CLEAN_MIN_LIKE_TO_SPLIT = 10
PLAYLIST_CLEAN_LIKE_MIN_LIKE_PCT = 80
PLAYLIST_CLEAN_NOT_LIKE_MAX_LIKE_PCT = 20
PLAYLIST_CLEAN_RADIO_MAX_LIKE_PCT = 50
PLAYLIST_CLEAN_DUPLICATE_THRESH = 5
PLAYLIST_SKIP_STARTS_WITH = ['zz not like']
PLAYLIST_CLEAN_SKIP_KINDS = ('SKIP', 'ALBUM', 'YT_GENERATED')

# Files
HEADER_FILE = 'oauth.json'
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

# For get_like_not_like_tracks_to_review()
MANUALLY_RATED_TSV_FILE = '_ytmusic_new_like_and_not_like_manual_rated.tsv'
NEED_RATE_TSV_FILE = '_ytmusic_new_like_and_not_like_need_manual_rating.tsv'
# For get_playlist_counts()
PLAYLIST_RADIO_COUNT_TSV_FILE = '_playlist_radio_counts.tsv'
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


class YTMusicPlaylists:

    def __init__(self, header=HEADER_FILE,
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
        self.playlist_tsv_dir = playlist_tsv_dir
        self._valid_playlist_kinds = valid_playlist_kinds
        self._valid_ratings = valid_track_ratings
        # Paths
        jn = os.path.join
        self.track_db_tsv = jn(playlist_tsv_dir, track_db_file)
        self.tracks_no_meta_tsv = jn(playlist_tsv_dir, tracks_no_meta_file)
        self.lastfm_tsv = jn(playlist_tsv_dir, lastfm_playcount_file)
        self.not_like_tsv = jn(playlist_tsv_dir, not_like_tsv_file)
        self.like_tsv = jn(playlist_tsv_dir, like_tsv_file)
        self.manual_rate_tsv = jn(playlist_tsv_dir, manual_rate_tsv)
        self.need_rate_tsv = jn(playlist_tsv_dir, need_rate_tsv)
        self.radio_count_file = jn(playlist_tsv_dir, radio_count_file)
        self.radio_cleanup_file = jn(playlist_tsv_dir, radio_cleanup_file)
        self.like_cleanup_file = jn(playlist_tsv_dir, like_cleanup_file)
        self.cleanup_counters_file = jn(
            playlist_tsv_dir, cleanup_counters_file)
        self.like_playlist_file = jn(playlist_tsv_dir, like_playlist_file)
        self.playlist_limit = playlist_limit
        self.radio_like_map_file = jn(playlist_tsv_dir, radio_to_like_map_file)
        self._info_cache = {}
        self.yt = self.init_ytmusic_api(header)
        # Load small files right away
        self._like_playlist_titles = pd.read_csv(self.like_playlist_file, sep='\t')[
            'title'].str.lower().tolist()
        self._radio_to_like_map = pd.read_csv(
            self.radio_like_map_file, sep='\t')
        self.banned_vid_set = frozenset(pd.read_csv(
            self.not_like_tsv, sep='\t', index_col=0).index)
        # Load this later, intialize empty for now
        self._playcount_map = pd.DataFrame([])
        # fetch playlists (needed for many downstream function, takes some time)
        self.playlists = pd.DataFrame(
            self.yt.get_library_playlists(limit=playlist_limit))
        self.playlist_titles = frozenset(self.playlists['title'])

    def init_ytmusic_api(self, header):
        print(f'Using header file: {header}')
        return YTMusic(header)

    def test_ytmusic_api(self, verbose=True):
        t0 = time.time()
        assert (self.yt)
        # Don't Think Twice, It's All Right	Bob Dylan
        assert (self.yt.get_song('Kv7K9ghgcgA'))
        assert (self.yt.get_library_playlists(limit=1))
        assert (self.yt.get_library_albums())
        assert (self.yt.get_library_artists())
        if verbose:
            print(f'Test Passed in {(time.time() - t0):0.2f} seconds')
            import ytmusicapi as ytmusicapi
            print(f'Using ytmusicapi version: {ytmusicapi.__version__}')

    # Playlist related Functions
    def query_by_title(self, title):
        return self._playlist_loc_first(col='title', value=title)

    def query_by_playlistId(self, playlistId):
        return self._playlist_loc_first(col='playlistId', value=playlistId)

    def _playlist_loc_first(self, col, value):
        res = self.playlists.loc[self.playlists[col] == value]
        if len(res) == 0:
            print(f'No playlist with {col}: {value}')
        elif len(res) > 1:
            print(f'Multiple matches for: {value}, choosing',
                  f'first result of:\n {res[['title', 'count']]}')
        return res.iloc[0]

    def get_playlists_by_privacy(self, privacy='PUBLIC',
                                 skip_if_contains=('z_', 'zz_',
                                                   'zzz_', 'yyz_')):
        out_playlists = []
        for i, p in self.playlists.iterrows():
            if len(p) == self.playlist_limit:
                continue  # skip giant playlist
            for sk in skip_if_contains:
                if sk in p:
                    continue
            metadata = self.playlist_get_info(p["playlistId"])
            if metadata['privacy'] == privacy:
                out_playlists.append(p)
                print(f'Found {privacy.lower()} playlist named: {p["title"]}')
        return pd.concat(out_playlists)

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

    def get_playlist_counts(self, verbose=False, filter_title=None):
        count_df_cols = ['title', 'track_count', 'privacy', 'playlist_id']
        # 'duration_hours',
        playlists = []
        print('Getting playlist track count for playlists (takes ~5 minutes)')
        if filter_title:
            print(f'Only for playlists with {filter_title} in the title')
        for i, row in self.playlists.iterrows():
            if filter_title and filter_title.lower() not in row.title.lower():
                if verbose:
                    print(f'{i}: Skipping: {row.title},',
                          f'filter: {filter_title}')
                continue
            playlist_info = self.playlist_get_info(row['playlistId'])
            playlists.append({
                'title': row['title'],
                'playlist_id': row['playlistId'],
                'track_count': len(playlist_info.get('tracks', [])),
                'privacy': playlist_info.get('privacy', ''),
                # 'duration_hours': round(float(playlist_info.get('duration_seconds', 1)) / 3600)
            })
            if verbose:
                print(f'{i}: {playlists[-1]}')
        return pd.DataFrame(playlists)[count_df_cols].sort_values('track_count')

    # Generate a tsv for tracks to review LIKE/NOT_LIKE status
    def get_like_not_like_tracks_to_review(self):
        review_cols = ['category', 'manual_rating', 'likeStatus', 'title', 'album', 'artist',
                       'date_modified', 'playlists', 'averageRating', 'viewCount', 'release',
                       'albumYear', 'albumType', 'albumTrackCount', 'keywords', 'fuzzy_track_id']
        import sys
        module_path = os.path.abspath(os.path.join('../music-sources-unified'))
        if module_path not in sys.path:
            sys.path.append(module_path)
        import unify_lib as uni

        all_df = pd.read_csv(self.track_db_tsv, sep='\t', index_col=0)
        all_df['fuzzy_track_id'] = all_df.apply(
            uni.make_ytmusic_fuzzy_slugified_track_id, axis=1)

        like_df = pd.read_csv(self.like_tsv, sep='\t', index_col=0)
        not_like_df = pd.read_csv(self.not_like_tsv, sep='\t', index_col=0)

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
        # LIKE
        like_fuzzy_ids = frozenset(like_df['fuzzy_track_id'])
        like_impacted_playlists = []
        new_likes = set()
        skip_not_like = set()
        print('Processing LIKE tracks (takes ~10 minutes)')
        for fuzzy_track_id in like_fuzzy_ids:
            matches = all_df.loc[all_df['fuzzy_track_id'] == fuzzy_track_id]
            if not len(matches):
                continue
            for match in matches.itertuples():
                if match.likeStatus == 'LIKE' or match.Index in like_vids:
                    continue
                if match.Index in not_like_vids:
                    skip_not_like.add(match.Index)
                    continue
                new_likes.add(match.Index)
                if not pd.isna(match.playlists):
                    like_impacted_playlists.append(match.playlists)
        print(f' Found {len(new_likes)} new tracks to LIKE')
        print(f' Found {len(skip_not_like)} tracks to LIKE',
              f'but already in NOT LIKE', flush=True)

        # NOT_LIKE
        not_like_fuzzy_ids = frozenset(not_like_df['fuzzy_track_id'])
        not_like_impacted_playlists = []
        new_not_likes = set()
        skip_is_like = set()
        print('\nProcessing NOT LIKE tracks (takes ~3 minutes)')
        for fuzzy_track_id in not_like_fuzzy_ids:
            matches = all_df.loc[all_df['fuzzy_track_id'] == fuzzy_track_id]
            if not len(matches):
                continue
            for match in matches.itertuples():
                if match.Index in not_like_vids:
                    continue
                if match.Index in like_vids or match.Index in new_likes:
                    skip_is_like.add(match.Index)
                    continue
                new_not_likes.add(match.Index)
                if not pd.isna(match.playlists):
                    not_like_impacted_playlists.append(match.playlists)

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

        # Load previous manual ratings and remove duplicates
        manual_picks = pd.read_csv(
            self.manual_rate_tsv, sep='\t', index_col=0).drop_duplicates(keep='first')
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
        # Original notes
        # need_like: Most of these were LIKE, but some overridden to NOT_LIKE or INDIFFERENT (around 2000)
        # need_not_like: Most of these were NOT_LIKE, but some overridden t0 INDIFFERENT (around 4000)
        # need_like_but_is_not_like: Manualy reviewed (around 100)
        # need_not_like_but_is_like: Manualy reviewed (around 100)
        need_review = pd.concat([v.assign(category=k)
                                for k, v in like_not_like_res.items()])
        print(f'{len(need_review)} entries need like or not like manual review')
        need_review['manual_rating'] = ''
        need_review = need_review.drop_duplicates(keep='last')
        need_review[review_cols].to_csv(Y.need_rate_tsv, sep='\t', index=True)
        return need_review

    def playlist_get_info(self, playlistId,
                          playlist_limit=PLAYLIST_LIMIT, use_cache=True):
        if not playlist_limit:
            playlist_limit = self.playlist_limit
        if use_cache and playlistId in self._info_cache:
            info = self._info_cache[playlistId]
        else:
            info = self.yt.get_playlist(playlistId, limit=playlist_limit)
            self._info_cache[playlistId] = info
        return info

    def playlist_from_yt_vids(self, vids, pl_name=None, sleep=3, public='PRIVATE', desc='',
                              dry=False, set_rating=None, remove_dupes=False, verbose=False,
                              sort_by=None):

        print(f'\nGenerating {pl_name} ytmusic playlist for {
              len(vids)} tracks')
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
            print(f'Updated {pl_name} playlist with {len(vids)} tracks, playlist id:',
                  f'{pl_id}...waiting {sleep} seconds...')
        else:  # Create new
            if not dry:
                pl_id = self.yt.create_playlist(
                    title=pl_name, description=desc,
                    privacy_status=public, video_ids=vids
                )
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
        assert tsv_path.endswith('.tsv')
        df = pd.read_csv(tsv_path, sep='\t', index_col=0)
        if not pl_name:
          pl_name = os.path.basename(tsv_path).split('.tsv')[0]
        if sort_by_index:
            df = df.sort_index()
        if ignore_banned:
            vids = df.videoId
        else:
            vids = frozenset(df.videoId.unique()) - self.banned_vid_set
        desc = f'Matched local tsv playlist: {pl_name}'
        self.playlist_from_yt_vids(vids, pl_name, sleep, public, desc, dry)

    def parse_tracks(self, track_list):
        tracks = pd.DataFrame(track_list)
        tracks['artistId'] = tracks['artists'].dropna().apply(
            lambda x: x[0]['id'])  # TODO handle > 1 artist
        tracks['artist'] = tracks['artists'].dropna().apply(
            lambda x: x[0]['name'])
        tracks['albumId'] = tracks['album'].dropna().apply(lambda x: x['id'])
        tracks['album'] = tracks['album'].dropna().apply(lambda x: x['name'])
        tracks = tracks.drop('thumbnails', axis=1)
        tracks = tracks.drop('artists', axis=1)
        return tracks

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
            self._playcount_map = pd.read_csv(
                self.lastfm_tsv, sep='\t', index_col=0)
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

    def clean_up_radio_playlist(
            self, pl_info, verbose=False,
            move_like=False, min_num_like=10,
            sleep=1, create_like_playlist=False,
            remove_dislike=True, remove_not_like=False):
        not_like_vids = self.banned_vid_set

        remove_dislike_tracks = []
        remove_not_like_tracks = []
        move_like_tracks = []

        # Get counters
        pl_counters = {'removed_dislike': 0, 'moved_like': 0,
                       'removed_not_like': 0, 'like_and_not_like': 0}
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
        if verbose:
            _counters = {k: v for k, v in pl_counters.items() if v > 0}
            print(f"Radio playlist {pl_info['title']} counters: {_counters}")

        # Take action
        # Handle flagged tracks
        if 'radio' not in pl_info["title"]:
            print(f'Skipping {pl_info["title"]} modifications,',
                  f'only playlists with "radio" in name supported')
            return pl_counters
        if move_like and len(move_like_tracks) > min_num_like:
            # Create like playlist and add from 'move_like_tracks'
            like_pl_id = None
            like_vids = [t['videoId'] for t in move_like_tracks]
            like_pl = None
            like_pl_matches = self._radio_to_like_map.loc[
                self._radio_to_like_map['radio_playlist'] == pl_info["title"]].dropna()
            if len(like_pl_matches):  # Nan or mapping
                like_pl = like_pl_matches.iloc[0]['like_playlist']
            elif pl_info["title"].replace(' radio', '') in self.playlist_titles:
                like_pl = pl_info["title"].replace(' radio', '')
            if like_pl == None:
                if create_like_playlist:
                    pl_str = f'{pl_info["title"]} [{DATE}]'
                    like_pl = pl_info["title"].replace(' radio', '')
                    like_pl_id = self.yt.create_playlist(
                        title=like_pl.strip(),
                        description=f'Favorite tracks from {pl_str}',
                        privacy_status='PRIVATE', video_ids=like_vids)
                    if verbose:
                        print(f'Created LIKE playlist for '
                              f'{pl_info["title"]}: {like_pl}')
                    time.sleep(2*sleep)
            else:
                like_pl_id = self.query_by_title(like_pl).playlistId
                like_orig_vids = frozenset([t['videoId'] for t in
                                            self.playlist_get_info(
                                                like_pl_id, use_cache=True).get('tracks', [])
                                            ])
                like_new_vids = frozenset(like_vids) - like_orig_vids
                like_dedupe_num = len(like_vids) - len(like_new_vids)
                if like_dedupe_num > 0:
                    like_vids = list(like_new_vids)
                if len(like_vids):
                    status = self.yt.add_playlist_items(
                        playlistId=like_pl_id, videoIds=like_vids, duplicates=False)
                    err_msg = (f'Bad Status for {pl_info["title"]} add '
                               f'{len(move_like_tracks)} LIKE tracks: {status}')
                    assert status['status'] == 'STATUS_SUCCEEDED', err_msg
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

            status = self.yt.remove_playlist_items(
                pl_info["id"], move_like_tracks)
            err_msg = (f'Bad Status for {pl_info["id"]} remove '
                       f'{len(move_like_tracks)} LIKE tracks: {status}')
            assert str(status) == 'STATUS_SUCCEEDED', err_msg
            time.sleep(sleep)
            if verbose:
                print(f'Moved {len(move_like_tracks)} LIKE entries '
                      f'from {pl_info["title"]} to {like_pl_id}')

        if remove_not_like and len(remove_not_like_tracks):
            if remove_dislike and len(remove_dislike_tracks):
                remove_not_like_tracks += remove_dislike_tracks
            status = self.yt.remove_playlist_items(
                pl_info["id"], remove_not_like_tracks)
            err_msg = (f'Bad Status for {pl_info["id"]} remove '
                       f'{len(remove_not_like_tracks)} NOT LIKE tracks: {status}')
            assert str(status) == 'STATUS_SUCCEEDED', err_msg
            if verbose:
                print(f'Removed {len(remove_not_like_tracks)} NOT_LIKE '
                      f'entries from {pl_info["title"]}')
            time.sleep(sleep)

        elif remove_dislike and len(remove_dislike_tracks):
            status = self.yt.remove_playlist_items(
                pl_info["id"], remove_dislike_tracks)
            err_msg = (f'Bad Status for {pl_info["id"]} remove '
                       f'{len(remove_dislike_tracks)} noly DISLIKE tracks: {status}')
            assert str(status) == 'STATUS_SUCCEEDED', err_msg
            if verbose:
                print(f'Removed {len(remove_dislike_tracks)} DISLIKE '
                      f'entries from {pl_info["title"]}')
            time.sleep(sleep)
        return pl_counters

    def clean_playlists(self, do_dry_run=False, verbose=False, move_like=True,
                        min_num_like=10, sleep=1, create_like_playlist=True,
                        remove_not_like=True, remove_dislike=True,
                        playlist_skip_kinds=('SKIP', 'ALBUM', 'YT_GENERATED'),
                        skip_if_dislike=True, like_playlist_min_like_pct=80,
                        not_like_playlist_max_like_pct=20,
                        radio_playlist_max_like_pct=50, duplicate_threshold=5,
                        playlist_skip_starts_with=['zz not like']):
        pl_ct = defaultdict(int)
        like_results, radio_results = {}, {}
        playlists_kinds = {k: set() for k in self._valid_playlist_kinds}
        n_playlists = len(self.playlists)
        print(f'Attempting to clean {n_playlists} playlists')
        for i, p in self.playlists.iterrows():
            if (i+1) % 100 == 0:
                print(f'{i+1} of {n_playlists} playlists processed', flush=True)
            pl_ct['playlists_processed'] += 1
            for skip_str in playlist_skip_starts_with:
                if p.title.startswith(skip_str):
                    pl_ct[f'playlist_skip_starts_with_{skip_str}'] += 1
                    print(f' SKIPPING playlist: {p.title}',
                          f'starts with {skip_str}')
                    continue

            if verbose:
                print(f"Playlist: {p.title} ({p.playlistId})",
                      f"has {p['count']} tracks")

            # Infer playlist kind from title, default to LIKE if nothing inferred
            pl_kind = self.infer_playlist_kind(p)

            # Maybe skip playlist right away
            # Skip when unable to infer kind (ideally this is not called)
            if not pl_kind:
                pl_ct['playlist_kind_not_inferred'] += 1
                print(f'SKIPPING playlist: {p.title} can not infer kind',
                      f'for playlist need manual fix (add to _like_playlists.tsv?)')
                continue
            pl_ct[f'playlist_kind_is_{pl_kind.lower()}'] += 1

            # Decide to skip playlist based on playlist kind
            playlists_kinds[pl_kind].add(p.title)
            if pl_kind in playlist_skip_kinds:
                pl_ct['playlist_kind_in_playlist_skip_list'] += 1
                if verbose:
                    print(f'SKIPPING playlist: {p.title} as it is',
                          f'a kind flagged for skipping: {pl_kind}')
                continue

            # Query playlist tracks and other metadata
            p_info = self.playlist_get_info(
                p.playlistId, playlist_limit=self.playlist_limit)
            if 'tracks' not in p_info:  # try without cache
                p_info = self.playlist_get_info(
                    p.playlistId, playlist_limit=self.playlist_limit, use_cache=False)
                if 'tracks' not in p_info:
                    pl_ct['playlist_is_empty'] += 1
                    print(f'SKIPPING playlist: {
                          p.title} No "tracks" key in playlist')

                continue
            if p_info['trackCount'] == 0:
                pl_ct['playlist_is_empty'] += 1
                print(f'SKIPPING playlist: {p.title} No tracks in playlist')
                continue
            # Check max length of playlist
            if len(p_info['tracks']) >= self.playlist_limit:
                pl_ct[f'playlist_has_>{self.playlist_limit}_limit'] += 1
                print(f'SKIPPING playlist: {p.title} which has',
                      f'{self.playlist_limit} or more tracks ({len(p_info["tracks"])})')
                continue
            # Check playlist privacy
            if p_info['privacy'] == 'PUBLIC':
                pl_ct['playlist_is_public'] += 1
                print(f'SKIPPING playlist: {p.title} which has',
                      f'privacy: {p_info["privacy"]}')
                continue
            elif p_info['privacy'] == 'UNLISTED':
                pl_ct['playlist_privacy_is_unlisted'] += 1
                if verbose:
                    print(f' playlist: {p.title} has',
                          f'privacy {p_info["privacy"]}')

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
                print(f'WARNING NOT OK playlist: {p.title} of kind {pl_kind}',
                      f'({like_percent}% liked) has: {
                    len(ratings["LIKE"])} likes,',
                    f'{len(ratings["DISLIKE"])} dislikes,',
                    f'{len(ratings["INDIFFERENT"])} indifferent,',
                    f'{len(ratings["NONE"])} none')

            # Potentially alter playlist, or generate new playlists
            if do_dry_run:
                continue

            # Remove duplicates from playlist
            new_pl_id = self.playlist_remove_duplicates(
                p_info, duplicate_threshold, verbose=verbose)
            if p.playlistId != new_pl_id:
                p.playlistId = new_pl_id
                pl_ct['playlist_removed_duplicates'] += 1
                p_info = self.playlist_get_info(
                    new_pl_id, playlist_limit=self.playlist_limit, use_cache=False)

            # Like all tracks in playlist if kind is LIKE
            if pl_kind == 'LIKE':
                like_results[p.title] = self.playlist_rate_all_songs(
                    p_info, rating=pl_kind, skip_if_dislike=skip_if_dislike,
                    verbose=verbose, sleep_time=sleep)
                continue
            # Split radio playlist into LIKE vs RADIO
            elif pl_kind == 'INDIFFERENT':
                radio_results[p.title] = self.clean_up_radio_playlist(
                    pl_info=self.playlist_get_info(
                        p.playlistId, use_cache=True),
                    verbose=verbose, sleep=sleep,
                    move_like=move_like, min_num_like=min_num_like,
                    create_like_playlist=create_like_playlist,
                    remove_dislike=remove_dislike,  remove_not_like=remove_not_like)
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

    def playlist_rate_all_songs(self, pl_info, rating, sleep_time=0.5,
                                verbose=False, skip_if_dislike=False,
                                valid_ratings=VALID_TRACK_RATINGS):
        assert rating in valid_ratings
        if verbose:
            print(f'Playlist {pl_info["title"]}: Found',
                  f'{len(pl_info["tracks"])} tracks to rate as {rating}')
        rate_ct = {'track_rated': 0, 'track_skip_dislike': 0,
                   'track_already_rated': 0}
        for track in pl_info["tracks"]:
            if skip_if_dislike and track["likeStatus"] == 'DISLIKE':
                rate_ct['track_skip_dislike'] += 1
                continue
            if track["likeStatus"] == rating:
                rate_ct['track_already_rated'] += 1
                continue
            if verbose:
                print(f'Setting rating for {track["videoId"]} to {rating}')
            self.yt.rate_song(track["videoId"], rating=rating)
            rate_ct['track_rated'] += 1
            time.sleep(sleep_time)
        if verbose:
            print(f'Playlist {pl_info["title"]}: Rated {rate_ct["track_rated"]}',
                  f'of {len(pl_info["tracks"])} tracks as {rating}')
        return rate_ct

    def playlist_remove_duplicates(self, pl_info,
                                   duplicate_threshold=DUPLICATE_THRESHOLD,
                                   sleep_time=0.5, verbose=False, shuffle=False):
        if verbose:
            print(f'Playlist {pl_info["title"]}: Found {len(pl_info["tracks"])}',
                  'tracks to check for duplicates')
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
            time.sleep(sleep_time)
            print(f'Playlist {pl_info["title"]}: {n_dupes} duplicate tracks',
                  f'removed ({len(tracks_to_keep)} of {len(pl_info["tracks"])} unique)')
        return pl_info['id']

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
                    track["artists"][0]["name"].lower() if track.get("artists") else "",
                    track["album"]["name"].lower() if track.get("album") else "",
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
        self.yt.remove_playlist_items(playlistId=playlist_id, videos=tracks_to_remove)

        # Adjust sleep time based on number of tracks and API limits
        sleep_time_adjusted = 0.5 + (len(playlist["tracks"]) // 100) * 0.5
        time.sleep(sleep_time_adjusted)

        video_ids_sorted = [track["videoId"] for track in playlist["tracks"]]
        self.yt.add_playlist_items(playlistId=playlist_id, videoIds=video_ids_sorted)

        print(
            f"Playlist {playlist_id} sorted by {sort_by} "
            f"{'(reversed)' if reverse else ''}."
        )
        return playlist_id

    def playlist_get_all_like_playlists(self):
        like_playlists_ids = {}
        for i, row in self.playlists.iterrows():
            if self._playlist_is_like(row.title):
                like_playlists_ids[row.title] = row.playlistId
        return like_playlists_ids

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
        assert pl_kind in valid_playlist_kinds
        # Not OK Cases
        if pl_kind == 'LIKE' and like_percent <= like_min_pct:
            return False
        elif pl_kind == 'RADIO' and like_percent >= radio_max_pct:
            return False
        elif pl_kind == 'NOT_LIKE' and like_percent >= notlike_max_pct:
            return False
        return True

    def _playlist_is_not_like(self, name,
                              not_like_toks=NOT_LIKE_TOKS):
        name = name.lower()
        if name.startswith('_'):
            return False
        if NOT_LIKE_PREFIX in name:
            return True
        for tok in not_like_toks:
            if tok in name:
                return True

    def _playlist_is_like(self, name, like_toks=LIKE_TOKS):
        name = name.lower()
        if name.startswith('_'):
            return False
        if name.endswith('albums'):
            return False
        if self._playlist_is_not_like(name):
            return False
        for t in self._like_playlist_titles:
            if t.lower() == name:
                return True
        for tok in like_toks:
            if tok in name:
                return True
        return False

    def _playlist_is_radio(self, name, radio_toks=RADIO_TOKS):
        name = name.lower()
        if self._playlist_is_like(name):
            return False
        for tok in radio_toks:
            if tok in name:
                return True

    def _playlist_is_albums(self, name, album_toks=ALBUM_TOKS):
        name = name.lower()
        for tok in album_toks:
            if tok in name:
                return True

    def _playlist_skip_starts_with(self, name, start_toks=SKIP_STARTS_WITH_TOKS):
        name = name.lower()
        for tok in start_toks:
            if name.startswith(tok):
                return True

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
            tracks_no_meta.to_csv(self.tracks_no_meta_tsv,
                                  sep='\t', header=True)

        # Reload tsb dbs
        track_db = pd.read_csv(self.track_db_tsv, sep='\t', index_col=0)
        tracks_no_meta = pd.read_csv(
            self.tracks_no_meta_tsv, sep='\t', index_col=0)
        # Get ytmusic metadata for new tracks from tracks_no_meta, update tracks_db
        new_tracks_no_meta = self._track_db_new_or_newly_liked_tracks(
            track_db, tracks_no_meta)
        track_db = self._track_db_update(track_db, new_tracks_no_meta)
        track_db.to_csv(self.track_db_tsv, sep='\t', header=True)

        # Update combined like and not_like tsvs
        not_like_tracks = self.collect_all_not_like_tracks_from_tsvs()
        not_like_tracks.to_csv(self.not_like_tsv, sep='\t', header=True)
        like_tracks = self.collect_all_like_tracks_from_tsvs()
        like_tracks.to_csv(self.like_tsv, sep='\t', header=True)

        # Update like or not_like tracks that need manual review
        need_review = self.get_like_not_like_tracks_to_review()
        need_review.to_csv(self.need_rate_tsv, sep='\t', index=True)

        # Update playlist counts for radio playlists
        radio_counts_df = Y.get_playlist_counts(
            filter_title='radio', verbose=False)
        radio_counts_df.to_csv(self.radio_count_file, sep='\t', index=False)

        # General automated task playlist todos
        # TODO add playlist to super playlists if exist see pdf
        # TODO auto generate some date based like playlists
        # TODO move based on playcount (if not LIKE infer NOT_LIKE based on large playcount)

        # Clean radio playlists, move like, dislike, not_like.
        if not SKIP_PLAYLIST_CLEAN:
            like_results, radio_results, pl_counters = self.clean_playlists(
                verbose=False, sleep=1,
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
        if len(tracks):  # Sort tsv by like, then artist
            tracks = tracks.sort_values(
                ['likeStatus', 'artist'], ascending=False)
            fname = os.path.join(self.playlist_tsv_dir, f"{
                                 pl_info['title']}.tsv")
            tracks[track_cols].to_csv(fname, sep='\t', header=True)
        return tracks, metadata

    def backup_playlists_and_collect_tracks(self,
                                            remove_disliked=False,
                                            include_library_tracks=True,
                                            song_lim=PLAYLIST_LIMIT,
                                            track_cols=TRACK_TSV_COLS,
                                            metadata_cols=PLAYLIST_METADATA_TSV_COLS,
                                            track_remove_cols=TRACK_REMOVE_COLS):

        # Backs up library playlists and returns playlist info summary df,
        # also collects all unique tracks and returns track df.
        all_playlist_info = []
        all_tracks = []
        start_time = time.time()
        print(f'Fetching and backing up playlists to',
              f'{self.playlist_tsv_dir} (~10 min)')
        for i, row in self.playlists.iterrows():
            try:
                pl_title = self._decode(row['title'])
                print(
                    f'\n\n({i+1}/{len(self.playlists)})\t{pl_title}', flush=True)
                playlist_info = self.playlist_get_info(
                    row['playlistId'], playlist_limit=song_lim, use_cache=True)
                if playlist_info['trackCount'] == 0:
                    print(f'Skipping: {pl_title}, due to zero tracks')
                    continue
                tracks, metadata = self.save_playlist_tsv(
                    playlist_info, remove_disliked=remove_disliked)
                all_playlist_info.append(metadata)
                all_tracks.append(tracks)
                print(90*'-')
            except Exception as e:
                print(f'Error in playlist {i}: {e}')
                print(f'Error in playlist title: {pl_title}')

        # Save playlist info
        playlist_info = pd.DataFrame(all_playlist_info)[metadata_cols]
        playlist_info.sort_values('title', ascending=False).to_csv(os.path.join(
            self.playlist_tsv_dir, '_playlists.tsv'), sep='\t', header=True)
        playlist_elapsed = (time.time() - start_time) / 60
        print(f'Backed up playlist metadata:\n{playlist_info}')
        print(f'Fetched playlist and saved playlist .tsv files',
              f'in {playlist_elapsed:.2f} minutes')

        if include_library_tracks:
            t1 = time.time()
            print('Fetching library tracks (approx 7 min)...')
            library_tracks = self.parse_tracks(
                self.yt.get_library_songs(limit=song_lim))
            all_tracks.append(library_tracks)
            library_elapsed = (time.time() - t1) / 60
            print(f'Fetched and saved {len(library_tracks)} tracks',
                  f'to _library.tsv in {library_elapsed:.2f} minutes\n')
            library_tracks = library_tracks.sort_values('artist')
            fname = os.path.join(self.playlist_tsv_dir, '_library.tsv')
            library_tracks[track_cols].to_csv(fname, sep='\t', header=True)

        def _merge_duplicates(group):
            _row = group.iloc[0]
            if 'playlists' in group:
                _row['playlists'] = list(group['playlists'].values)
            return _row
        unique_tracks = pd.concat(all_tracks).groupby(
            'videoId').apply(_merge_duplicates).set_index('videoId')
        unique_tracks = unique_tracks.drop(track_remove_cols, axis=1)
        unique_tracks = unique_tracks.sort_values(
            ['likeStatus', 'artist'], ascending=False)
        elapsed_minutes = (time.time() - start_time) / 60.0
        print(f'Backed up {len(playlist_info)} playlists and {len(unique_tracks)}',
              f'tracks in {elapsed_minutes:.2f} minutes to: {self.playlist_tsv_dir}')
        return unique_tracks

    # Functions for aggregating from playlist tsvs
    def collect_all_like_tracks_from_tsvs(self, tsv_header=LIKE_TRACKS_HEADER):
        playlist_files = sorted(os.listdir(self.playlist_tsv_dir))
        like_playlists = [pl for pl in playlist_files
                          if self._playlist_is_like(pl.replace('.tsv', ''))]
        print(f'Found {len(like_playlists)} like playlists out of '
              f'the {len(playlist_files)} total')
        like_tracks = []
        for pl in like_playlists:
            track_df = pd.read_csv(os.path.join(
                self.playlist_tsv_dir, pl), sep='\t', index_col=0)
            tracks_db_liked = track_df.loc[track_df['likeStatus'] == 'LIKE']
            tracks_db_liked = tracks_db_liked.set_index('videoId', drop=True)
            like_tracks.append(tracks_db_liked)
            liked_percent = 100 * len(tracks_db_liked) / len(track_df)
            if liked_percent < 80:
                print('\nWARNING: Low Like Percentage!')
            print(f'{pl}\t{liked_percent:0.1f}% currently liked '
                  f'(of {len(track_df)} total tracks)')
        like_tracks = pd.concat(
            like_tracks).sort_values('artist')
        like_tracks = like_tracks.loc[
            ~like_tracks.index.duplicated(keep='first'), tsv_header]
        # Load already existing like list tsv
        like_tracks = pd.read_csv(self.like_tsv, sep='\t', index_col=0)
        assert_msg = (f'Expected {self.like_tsv} to have header {tsv_header}, '
                      f'not: {like_tracks.columns}')
        assert list(like_tracks.columns) == tsv_header, assert_msg
        # Update and save tsv, append new like tracks in db but not in like list
        new_like_tracks = like_tracks.loc[frozenset(
            like_tracks.index) - frozenset(like_tracks.index)]
        all_like_tracks = pd.concat([like_tracks, new_like_tracks])
        print(f'Updated liked tracks with {len(new_like_tracks)} new entries '
              f'(from {len(like_tracks)} to {len(all_like_tracks)}).', flush=True)
        return like_tracks

    def collect_all_not_like_tracks_from_tsvs(self, tsv_header=LIKE_TRACKS_HEADER):
        playlist_files = sorted(os.listdir(self.playlist_tsv_dir))
        not_like_playlists = [pl for pl in playlist_files
                              if self._playlist_is_not_like(pl.replace('.tsv', ''))]
        print(f'Found {len(not_like_playlists)} not like playlists',
              f'out of the {len(playlist_files)} total', flush=True)
        not_like_tracks = []
        for pl in not_like_playlists:
            tracks_db_not_liked = pd.read_csv(os.path.join(
                self.playlist_tsv_dir, pl), sep='\t', index_col=0)
            tracks_db_not_liked = tracks_db_not_liked.set_index(
                'videoId', drop=True)
            not_like_tracks.append(tracks_db_not_liked)
        not_like_tracks = pd.concat(
            not_like_tracks).sort_values('artist')
        not_like_tracks = not_like_tracks.loc[~not_like_tracks.index.duplicated(
            keep='first'), tsv_header]
        print(f'Updated not liked tracks, contains',
              f'{len(not_like_tracks)} entries.', flush=True)
        return not_like_tracks

    # Functions for dealing with track db tsv
    def _track_db_get_track_info(self, row):
        copy_song_cols = ['keywords', 'averageRating', 'viewCount', 'release']
        copy_album_cols = ['type', 'trackCount', 'year']  # 'duration',
        track_str = f"{row['artist']} - {row['album']} - {row['title']}"
        track_str = unicodedata.normalize(
          'NFKD', track_str).encode('ascii', 'ignore').decode('ascii')

        if type(row['artistId']) != str:
            print(f'\nERROR: row["artistId"] not a str for row: {track_str}')
            return row
        elif 'privately_owned' in row['artistId']:
            print(f'\nSkipping privately owned track for row: {track_str}')
            return row
        song = self.yt.get_song(row.name)
        for col in copy_song_cols:
            if col not in song:
                continue
            if col == 'release' and not self._is_valid_date(song['release']):
                print(f'\tSkipping release field,',
                      f'not a valid date: {track_str}')
                continue
            row[col] = song[col]
        if row['albumId'] and type(row['albumId']) == str:
            try:
                album = self.yt.get_album(row.albumId)
            except Exception as e:
                print(f'ERROR running: get_album(albumID)\n',
                      f'{e} for row: {track_str}')
                return row
            if len(album['artists']):
                row['albumArtist'] = album['artists'][0]['name']
            elif len(album['tracks']) and len(album['tracks'][0]['artists']):
                row['albumArtist'] = album['tracks'][0]['artists'][0]['name']
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
        return row

    def _track_db_new_or_newly_liked_tracks(self, track_db, tracks_no_meta):
        new_track_ids = set(tracks_no_meta.index) - set(track_db.index)
        # Update likes on existing tracks
        existing = tracks_no_meta[~tracks_no_meta.isin(new_track_ids)]
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

    def _track_db_update(self, track_db, new_tracks):
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
            print(f"({i}/{len(new_tracks)}): {track_str}")
        tracks_w_info = pd.DataFrame(tracks_w_info)
        tracks_w_info['date_modified'] = DATE
        print(f'Scraped info for {len(tracks_w_info)} tracks')
        track_db = pd.concat([track_db, tracks_w_info])
        track_db = self._track_db_dedupe(track_db, keep='last')
        track_db = track_db.sort_values(['artist', 'album'])
        elapsed_t = (time.time() - t0) / 60
        print(f'Finished in {elapsed_t:0.1f} minutes')
        print(f'Track database now has {len(track_db)} tracks')
        return track_db

    def _track_db_dedupe(self, track_db, keep='last'):
        # Remove exact duplicate rows, keep the first occurrence
        _length = len(track_db)
        track_db = track_db.drop_duplicates(keep=keep)
        print(f"Removed {_length - len(track_db)} exact duplicate rows")

        # Remove duplicates for rows, ignoring specific columns
        _length = len(track_db)
        ignore_cols = ['playlists',  'inLibrary',  'artistId', 'albumId']
        # 'duration',
        track_db = track_db.drop_duplicates(
            subset=[c for c in track_db.columns if c not in ignore_cols], keep=keep)
        print(f"Removed {_length - len(track_db)} row duplicates",
              f"(ignoring columns: {ignore_cols})")
        _length = len(track_db)
        ignore_cols = ['title',  'album']
        track_db = track_db.drop_duplicates(
            subset=[c for c in track_db.columns if c not in ignore_cols], keep=keep)
        print(f"Removed {_length - len(track_db)} row duplicates",
              f"(ignoring columns: {ignore_cols})")

        # Remove duplicate index rows (ignoring other columns)
        _length = len(track_db)
        track_db = track_db[~track_db.index.duplicated(keep=keep)]
        print(f"Removed {_length - len(track_db)} duplicate index rows")
        print(f"Final length of track_db: {len(track_db)}")
        return track_db

    def _is_valid_date(self, date_str):
        try:
            datetime.datetime.strptime(date_str, '%Y-%m-%d')
            return True
        except ValueError:
            return False

    def _decode(self, string, encode_key='latin-1', decode_key='windows-1252'):
        return str(string).encode(encode_key, errors='replace').decode(
            decode_key, errors='replace')


if __name__ == "__main__":
    print('Running main ytmusic library backup task')
    # TODO track each run in a log and perhaps have a run monthly that runs if 30 days haave past
    Y = YTMusicPlaylists(header=HEADER_FILE, playlist_tsv_dir=PLAYLIST_TSV_DIR)
    Y.run_backup(skip_playlist_tsv_backup=SKIP_PLAYLIST_BACKUP)
