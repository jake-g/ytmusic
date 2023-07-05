import os
import time
import pandas as pd
from ytmusicapi import YTMusic

PLAYLIST_LIMIT = 6000
MIN_RADIO_LIKE_TO_SPLIT = 10
VALID_TRACK_RATINGS = ('LIKE', 'DISLIKE', 'INDIFFERENT', 'NONE')
VALID_PLAYLIST_KINDS = ('LIKE', 'NOT_LIKE', 'INDIFFERENT',
                        'ALBUM', 'SKIP', 'YT_GENERATED')

# regnerate playlists with more than this amount of duplicates
DUPLICATE_THRESHOLD = 3

HEADERS = 'headers_auth.json'
NOT_LIKE_TSV = 'playlists/_not_liked_tracks.tsv'
RADIO_TO_LIKE_PL_TSV = 'playlists/_ytmusic_radio_to_like_pl_map.tsv'
PLAYLIST_TSV_COLUMNS = ['title', 'artist', 'album', 'likeStatus',
                        'duration', 'videoId', 'albumId', 'artistId']


class YTMusicPlaylists:

    def __init__(self, header=HEADERS, playcount_map=None,
                 not_like_tsv=NOT_LIKE_TSV,
                 radio_to_like_map_tsv=RADIO_TO_LIKE_PL_TSV,
                 playlist_limit=PLAYLIST_LIMIT):
        print(f'Using header file: {header}')
        self.yt = YTMusic(header)
        self.playlist_limit = playlist_limit
        self._valid_ratings = VALID_TRACK_RATINGS
        self._valid_playlist_kinds = VALID_PLAYLIST_KINDS
        self._info_cache = {}
        self._playcount_map = pd.DataFrame([])
        if playcount_map != None:
            self._playcount_map = self.get_playcount_map(playcount_map)
        self._radio_to_like_map = pd.DataFrame([])
        if radio_to_like_map_tsv != None:
            self._radio_to_like_map = pd.read_csv(
                radio_to_like_map_tsv, sep='\t')
        self.banned_vid_set = set()
        if not_like_tsv != None:
            self.banned_vid_set = frozenset(pd.read_csv(
                not_like_tsv, sep='\t', index_col=0).index)
        self.playlists = pd.DataFrame(
            self.yt.get_library_playlists(limit=playlist_limit))

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

    def _playlist_loc_first(self, col, value):
        res = self.playlists.loc[self.playlists[col] == value]
        if len(res) == 0:
            print(f'No playlist with {col}: {value}')
        elif len(res) > 1:
            print(f'Multiple matches for: {value},',
                  f'choosing first result of:\n {res}')
        return res.iloc[0]

    def query_by_title(self, title):
        return self._playlist_loc_first(col='title', value=title)

    def query_by_playlistId(self, playlistId):
        return self._playlist_loc_first(col='playlistId', value=playlistId)

    def get_playcount_map(self, map_tsv, verbose=True):
        playcount_map = pd.read_csv(map_tsv, sep='\t', index_col=0)
        if verbose:
            print(f'Loaded {playcount_map["lastfm_playcount"].sum()}',
                  f'playounts from {len(playcount_map)} tracks')
        return playcount_map

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

    def get_playlist_counts(self, verbose=False, filter_title=None):
        playlists = []
        for i, row in self.playlists.iterrows():
            if filter_title and filter_title.lower() not in row.title.lower():
                if verbose:
                    print(f'{i}: Skipping: {row.title}, filter: {filter_title}')
                continue
            playlist_info = self.playlist_get_info(row['playlistId'])
            playlists.append({
                'title': row['title'],
                'playlist_id': row['playlistId'],
                'track_count': len(playlist_info.get('tracks', [])),
                'privacy': playlist_info.get('privacy', ''),
                'duration_hours': round(float(playlist_info.get('duration_seconds', 1)) / 3600)
            })
            if verbose:
                print(f'{i}: {playlists[-1]}')
        return pd.DataFrame(playlists).sort_values('track_count', ascending=False)

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

    def playlist_from_tsv(self, tsv_path, sort_by_index=True, ignore_banned=False):
        assert tsv_path.endswith('.tsv')
        df = pd.read_csv(tsv_path, sep='\t', index_col=0)
        pl_name = os.path.basename(tsv_path).split('.tsv')[0]
        print(f'\nGenerating {pl_name} ytmusic playlist for {len(df)} tracks')
        if sort_by_index:
            df = df.sort_index()
        if ignore_banned:
            vids = df.videoId
        else:
            vids = frozenset(df.videoId.unique()) - self.banned_vid_set

        desc = f'Matched {len(vids)} tracks from local tsv playlist: {pl_name}'
        pl_id = self.yt.create_playlist(
            title=pl_name,  description=desc,
            privacy_status='PRIVATE', video_ids=list(vids))
        print(f'Saved {len(vids)} {pl_name} tracks playlist with id: {pl_id}')

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

    def playcount_sort_playlist(self, pl_info, max_playcount_str=50, ignore_banned=True, sleep_time=1):

        if not len(self._playcount_map):
            print('ERROR: playcount_sort sorting requires initializing the',
                  'lastfm playcount map using self.load_playcount_map()')
            return
        desc = f'generated from {pl_info["title"]} sorting by lastfm playcount'
        tracks = pd.DataFrame(pl_info.get('tracks', None))
        tracks = tracks.set_index('videoId', drop=True)
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
        print(f'Created sorted pl: {pl_id}, and ',
              f'deleted original pl: {pl_info["id"]}')
        return pc

    def clean_up_radio_playlist(
            self, pl_info, verbose=False,
            move_like=True, min_num_like=MIN_RADIO_LIKE_TO_SPLIT,
            sleep=1, create_like_playlist=True,
            remove_not_like_and_dislike=True):
        not_like_vids = self.banned_vid_set

        remove_tracks = []
        move_like_tracks = []
        pl_counters = {'name': pl_info['title'], 'removed_dislike': 0,
                       'moved_like': 0, 'removed_not_like': 0, 'like_and_not_like': 0}
        for track in pl_info.get('tracks', []):
            if track['likeStatus'] == 'DISLIKE':
                pl_counters['removed_dislike'] += 1
                remove_tracks.append(track)
            elif track['likeStatus'] == 'LIKE':
                pl_counters['moved_like'] += 1
                move_like_tracks.append(track)
                if track['videoId'] in not_like_vids:
                    pl_counters['like_and_not_like'] += 1
            elif track['videoId'] in not_like_vids:
                pl_counters['removed_not_like'] += 1
                remove_tracks.append(track)
        if verbose:
            print(100*'*' + f'\n{pl_counters}')
        # Handle flagged tracks
        like_pl = self._radio_to_like_map.loc[
            self._radio_to_like_map['radio_playlist'] == pl_info["title"]].iloc[0]['like_playlist']

        if move_like and len(move_like_tracks) > min_num_like:
            # Create like playlist and add from 'move_like_tracks'
            like_pl_id = None
            like_vids = [t['videoId'] for t in move_like_tracks]
            if pd.isna(like_pl):
                if create_like_playlist:
                    like_pl = pl_info["title"].replace('radio', 'like')
                    like_pl_id = self.yt.create_playlist(
                        title=like_pl,  description=f'Created for dumping likes from {pl_info["title"]}',
                        privacy_status='PRIVATE', video_ids=like_vids)
                    if verbose:
                        print(f'Created LIKE playlist for '
                              f'{pl_info["title"]}: {like_pl}')
                    time.sleep(2*sleep)
            else:
                like_pl_id = self.query_by_title(like_pl).playlistId
                like_orig_vids = frozenset([t['videoId'] for t in self.playlist_get_info(
                    like_pl_id, use_cache=True).get('tracks', [])])
                like_new_vids = frozenset(like_vids) - like_orig_vids
                like_dedupe_num = len(like_vids) - len(like_new_vids)
                if like_dedupe_num > 0:
                    like_vids = list(like_new_vids)
                if len(like_vids):
                    status = self.yt.add_playlist_items(
                        playlistId=like_pl_id, videoIds=like_vids, duplicates=False)
                    err_msg = f'Bad Status for {pl_info["title"]} add {len(move_like_tracks)} LIKE tracks: {status}'
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
            err_msg = f'Bad Status for {pl_info["id"]} remove {len(move_like_tracks)} LIKE tracks: {status}'
            assert str(status) == 'STATUS_SUCCEEDED', err_msg
            time.sleep(sleep)
            if verbose:
                print(f'Moved {len(move_like_tracks)} LIKE entries '
                      f'from {pl_info["title"]} to {like_pl_id}')

        if remove_not_like_and_dislike and len(remove_tracks):
            status = self.yt.remove_playlist_items(
                pl_info["id"], remove_tracks)
            err_msg = f'Bad Status for {pl_info["id"]} remove {len(remove_tracks)} NOT LIKE tracks: {status}'
            assert str(status) == 'STATUS_SUCCEEDED', err_msg
            if verbose:
                print(f'Removed {len(remove_tracks)} NOT_LIKE '
                      f'entries from {pl_info["title"]}')
            time.sleep(sleep)

        return pl_counters

    def playlist_rate_all_songs(self, pl_info, rating, sleep_time=0.5,
                                verbose=False, skip_if_dislike=False):
        assert rating in self._valid_ratings
        if verbose:
            print(f'Playlist {pl_info["title"]}: Found',
                  f'{len(pl_info["tracks"])} tracks to rate as {rating}')
        rate_count = 0
        for track in pl_info["tracks"]:
            if skip_if_dislike and track["likeStatus"] == 'DISLIKE':
                continue
            if track["likeStatus"] == rating:
                continue
            if verbose:
                print(f'Setting rating for {track["videoId"]} to {rating}')
            self.yt.rate_song(track["videoId"], rating=rating)
            rate_count += 1
            time.sleep(sleep_time)
        print(f'Playlist {pl_info["title"]}: Rated {rate_count}',
              f'of {len(pl_info["tracks"])} tracks as {rating}')

    def playlist_remove_duplicates(self, pl_info,
                                   duplicate_threshold=DUPLICATE_THRESHOLD,
                                   sleep_time=0.5, verbose=False):
        if verbose:
            print(f'Playlist {pl_info["title"]}: Found {pl_info["tracks"]}',
                  'tracks to check for duplicates')
        track_ids = [t['videoId'] for t in pl_info['tracks']]
        tracks_unique = frozenset(track_ids) - self.banned_vid_set
        n_dupes = len(track_ids)-len(tracks_unique)
        if n_dupes >= duplicate_threshold:
            new_id = self.yt.create_playlist(
                title=str(pl_info['title']),
                description=str(pl_info['description']),
                video_ids=list(tracks_unique)
            )
            time.sleep(sleep_time)
            self.yt.delete_playlist(playlistId=pl_info['id'])
            time.sleep(sleep_time)
            print(f'Playlist {pl_info["title"]}: {n_dupes} duplicate tracks',
                  f'removed ({len(tracks_unique)} of {len(track_ids)} unique)')
            return new_id
        return pl_info['id']

    def playlist_get_all_like_playlists(self):
        like_playlists_ids = {}
        for i, row in self.playlists.iterrows():
            if self._playlist_is_like(row.title.lower()):
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
        elif self._playlist_is_dislike(p_row.title):
            return 'NOT_LIKE'
        elif self._playlist_is_like(p_row.title):
            return 'LIKE'
        return None  # handle this case when using result

    def _is_playlist_kind_ok(self, pl_kind, like_percent,
                             like_min_pct=80, notlike_max_pct=20,
                             radio_max_pct=50):
        # Not OK Cases
        if pl_kind == 'LIKE' and like_percent <= like_min_pct:
            return False
        elif pl_kind == 'RADIO' and like_percent >= radio_max_pct:
            return False
        elif pl_kind == 'NOT_LIKE' and like_percent >= notlike_max_pct:
            return False
        return True

    def _playlist_is_dislike(self, name,
                             dislike_toks=('not like', ' dislike',
                                           'thumbs_down')):
        name = name.lower()
        for tok in dislike_toks:
            if tok in name:
                return True

    def _playlist_is_like(self, name,
                          like_toks=('thumbs_up', ' like',
                                     ' top', ' likes')):
        name = name.lower()
        if self._playlist_is_dislike(name):
            return False
        for tok in like_toks:
            if tok in name:
                return True

    def _playlist_is_radio(self, name,
                           radio_toks=(' radio', '_radio',
                                       '_indifferent')):
        name = name.lower()
        if self._playlist_is_like(name):
            return False
        for tok in radio_toks:
            if tok in name:
                return True

    def _playlist_is_albums(self, name, album_toks=('_albums', '  album')):
        name = name.lower()
        for tok in album_toks:
            if tok in name:
                return True

    def _playlist_skip_starts_with(self, name, start_toks=('zz_')):
        name = name.lower()
        for tok in start_toks:
            if name.startswith(tok):
                return True
