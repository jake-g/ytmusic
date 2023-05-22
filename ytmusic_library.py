import os
import time
import pandas as pd
from ytmusicapi import YTMusic

PLAYLIST_LIMIT = 6000
MIN_RADIO_LIKE_TO_SPLIT = 8
VALID_TRACK_RATINGS = ('LIKE', 'DISLIKE', 'INDIFFERENT', 'NONE')
VALID_PLAYLIST_KINDS = ('LIKE', 'NOT_LIKE', 'INDIFFERENT',
                        'ALBUM', 'SKIP', 'YT_GENERATED')

# regnerate playlists with more than this amount of duplicates
DUPLICATE_THRESHOLD = 3


class YTMusicPlaylists:

    def __init__(self, header='headers_auth.json', playcount_map=None,
                 not_like_tsv='playlists/xx not like.tsv',
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
        self.banned_vid_set = set()
        if not_like_tsv != None:
            self.banned_vid_set = frozenset(pd.read_csv(
                not_like_tsv, sep='\t', index_col=0).videoId)
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

    def create_rating_playlist_subset(self, tracks, orig_name, new_name,
                                      rating, min_ids=0, playcount_sort=False, ignore_banned=False,
                                      max_playcount_str=50):
        assert rating in self._valid_ratings
        desc = f'generated from {orig_name} includes {rating} subset'
        tracks = tracks.loc[tracks['likeStatus']
                            == rating].set_index('videoId')
        if playcount_sort:
            if not len(self._playcount_map):
                print('WARNING: playcount_sort sorting requires initializing the',
                      'lastfm playcount map using self.load_playcount_map()')
            else:
                tracks = tracks.join(self._playcount_map).sort_values(
                    'lastfm_playcount', ascending=False)
                # generate description string with top playcounts
                pc = tracks.loc[tracks['lastfm_playcount']
                                > 0].head(max_playcount_str)
                pc_str = pc['lastfm_playcount'].astype(
                    int).astype('str') + '\t|  ' + pc['title']
                desc += f'\n\nTop {len(pc)} Playcounts:\t\n' + \
                    '\n'.join(pc_str.to_list())
        if ignore_banned:
            video_ids = tracks.index
        else:
            video_ids = frozenset(tracks.index.unique()) - self.banned_vid_set
        if len(video_ids) <= min_ids:
            return None, len(video_ids)
        pl_id = self.yt.create_playlist(
            title=new_name, description=desc,
            privacy_status='PRIVATE', video_ids=list(video_ids)
        )
        return pl_id, len(video_ids)

    def move_likes_from_radio_playlist(self, pl_info,
                                       min_n_like=MIN_RADIO_LIKE_TO_SPLIT,
                                       sleep_time=3, verbose=False, playcount_sort=True,
                                       ignore_banned=True):
        tracks = pd.DataFrame(pl_info.get('tracks', None))
        if verbose:
            print(f'Sorting {pl_info["title"]} ({pl_info["id"]}) with',
                  f'{len(tracks)} tracks into like and indifferent')
        orig_name = pl_info["title"]
        like_pl_name = orig_name
        if 'radio' in like_pl_name:
            like_pl_name = like_pl_name.replace('radio', 'like')
        else:
            like_pl_name += '_like'
        res_like, n_like = self.create_rating_playlist_subset(
            tracks, orig_name, like_pl_name, 'LIKE',
            min_ids=min_n_like
        )
        if res_like is None:
            print(f'Not splitting playlist {orig_name}, ',
                  f'not enough likes ({n_like})')
            return
        time.sleep(sleep_time)
        indiff_pl_name = orig_name
        if 'radio' not in indiff_pl_name:
            indiff_pl_name += '_radio'
        res_indif, n_indif = self.create_rating_playlist_subset(
            tracks, orig_name, indiff_pl_name, 'INDIFFERENT', min_ids=0, playcount_sort=playcount_sort,
            ignore_banned=ignore_banned)
        if res_indif is None:
            print(f'ERROR: Radio Playlist {indiff_pl_name} was',
                  f'not created, skip deleting original : {orig_name}')
            return
        time.sleep(sleep_time)
        self.yt.delete_playlist(pl_info["id"])
        print(f'Created like playlist: {like_pl_name} ({n_like}) and',
              f'indifferent playlist: {indiff_pl_name} ({n_indif} entries),',
              f'deleted original playlist: {orig_name} ({len(tracks)} entries)')

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
