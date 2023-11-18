import os
import time
import datetime
import pandas as pd
from ytmusicapi import YTMusic


# Global Prams
# When True, will reuse playlist tsvs from last backup
SKIP_PLAYLIST_BACKUP = False
# Split radio playlists with at least this many likes
MIN_RADIO_LIKE_TO_SPLIT = 5
# Regnerate playlists with more than this amount of duplicates
DUPLICATE_THRESHOLD = 3
# For requesting large playlists from api
PLAYLIST_LIMIT = 6000

# Files
HEADER_FILE = 'oauth.json'
PLAYLIST_TSV_DIR = './playlists/'

# Track DB Files
TRACK_DB_FILE = '_tracks_db.tsv'
TRACKS_NO_META_FILE = '_tracks_no_meta.tsv'
LASTFM_PLAYCOUNT_FILE = '_ytmusic_lastfm_match_id_map.tsv'
TRACK_TSV_COLS = ['title', 'artist', 'album', 'likeStatus',
                  'duration', 'videoId', 'albumId', 'artistId']
TRACK_REMOVE_COLS = ['setVideoId', 'feedbackTokens']
PLAYLIST_METADATA_TSV_COLS = [
    'title', 'trackCount', 'duration', 'privacy', 'id']
# LIKE subset
LIKE_TRACKS_HEADER = ['title', 'album', 'artist']  # more compact/limited for _.tsvs
LIKE_TOKS = ['thumbs_up', ' like', ' likes', ' top']
LIKE_TRACKS_TSV_FILE = '_liked_tracks.tsv'

# NOT LIKE subset
NOT_LIKE_PREFIX = 'zz not like'
NOT_LIKE_TOKS = ['not like', ' dislike', 'thumbs_down']
NOT_LIKE_TRACKS_TSV_FILE = '_not_liked_tracks.tsv'
# Radio subset
RADIO_TOKS = [' radio', '_radio', '_indifferent']
RADIO_TO_LIKE_MAP_FILE = '_ytmusic_radio_to_like_pl_map.tsv'
# Other subsets
SKIP_STARTS_WITH_TOKS = ['zz']
ALBUM_TOKS = ['_albums', '  album']


# Manually Curated
# TODO: load this from some map? maybe repurpose radio like map? also see
LIKE_PLAYLISTS = ['Liked Music',
    'ambient', 'ambient Indie Synths', 'ambient modern like', 'beats', 'Beats indie Chill', 'beats instrumental',
    'blues', 'Bossa Nova', 'brass like', 'Brass n chill', 'Chillwave', 'electronic', 'electronic big beats',
    'electronic chill', 'electronic Dance', 'electronic Focus', 'electronic house french touch', 'electronic house funk',
    'electronic House Special', 'electronic Innerwaves', 'electronic new indie beats', 'electronic soft pad', 'Folk',
    'future bass', 'future beats', 'future garage', 'futurebeat_rap', 'garage rock', 'goth 1980s', 'Grunge', 'Hip Hop 1990s',
    'Hip Hop 2000s', 'Hip Hop Hits', 'Hip hop It Was a Good Day', 'hiphop', 'hiphop 2000s southern', 'hiphop jazzy',
    'hiphop modern', 'hiphop old school', 'hiphop soul good vibe', 'indie', 'Indie 1990s Rock', 'Indie 2000s', 'indie folk',
    'indie loose', 'jazz', 'jazz cool', 'jazz gloom smooth', 'jazz guitar', 'jazz noir', 'like_playlist', 'my balls your chill',
    'nudisco', 'nudisco smooth', 'Oldies', 'oldies 1950s', 'oldies 1960s', 'oldies doo wop', 'oldies Jukebox Vintage Party',
    'post rock slow core', 'Post-Punk 1970s-1980s', 'Produced By Dilla', 'Produced by DJ Premier', 'Produced by kanye',
    'psych rock modern', 'psychedelic classic rock', 'punk 1970s', 'Reggae', 'reggae classic', 'Reggae Dub', 'reggae modern',
    'rnb dj', 'rock 1950s roots', 'rock 1960s classic', 'rock 1967 Monterey Pop Festival', 'Rock 1980s Pop New Wave', 'rock 1990s',
    'rock instrumentals classic vintage', 'rock krautrock', 'rock modern chill', 'rock proto metal', 'rock stoner sludge dank',
    'Shoegaze', 'soul 1960s', 'Soul Classic Sunshine', 'soul funk', 'soul motown', 'trip hop', 'triphop bristol sound'
]


# Constants
VALID_TRACK_RATINGS = ('LIKE', 'DISLIKE', 'INDIFFERENT', 'NONE')
VALID_PLAYLIST_KINDS = ('LIKE', 'NOT_LIKE', 'INDIFFERENT',
                        'ALBUM', 'SKIP', 'YT_GENERATED')


# Format the date as "month-day-year"
DATE = datetime.datetime.now().strftime("%m-%d-%Y")

class YTMusicPlaylists:

    def __init__(self, header=HEADER_FILE,
                 playlist_tsv_dir=PLAYLIST_TSV_DIR,
                 lastfm_playcount_file=LASTFM_PLAYCOUNT_FILE,
                 track_db_file=TRACK_DB_FILE,
                 tracks_no_meta_file=TRACKS_NO_META_FILE,
                 like_tsv_file=LIKE_TRACKS_TSV_FILE,
                 not_like_tsv_file=NOT_LIKE_TRACKS_TSV_FILE,
                 radio_to_like_map_file=RADIO_TO_LIKE_MAP_FILE,
                 playlist_limit=PLAYLIST_LIMIT):
        self.playlist_tsv_dir = playlist_tsv_dir
        self.track_db_tsv = os.path.join(playlist_tsv_dir, track_db_file)
        self.tracks_no_meta_tsv = os.path.join(
            playlist_tsv_dir, tracks_no_meta_file)
        self.lastfm_tsv = os.path.join(playlist_tsv_dir, lastfm_playcount_file)
        self.not_like_tsv = os.path.join(playlist_tsv_dir, not_like_tsv_file)
        self.like_tsv = os.path.join(playlist_tsv_dir, like_tsv_file)
        self.playlist_limit = playlist_limit
        self._info_cache = {}
        self.yt = self.init_ytmusic_api(header)
        # Load small files right away
        self._radio_to_like_map = pd.read_csv(os.path.join(
            playlist_tsv_dir, radio_to_like_map_file), sep='\t')
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
            print(f'Multiple matches for: {value},',
                  f'choosing first result of:\n {res}')
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

    def playcount_sort_playlist(
            self, pl_info, max_playcount_str=50,
            ignore_banned=True, sleep_time=1, verbose=True):
        if not len(self._playcount_map):
            self._playcount_map = pd.read_csv(
                self.lastfm_tsv, sep='\t', index_col=0)
            if verbose:
                print(f'Loaded {self._playcount_map["lastfm_playcount"].sum()}',
                      f'playounts from {len(self._playcount_map)} tracks')

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
            move_like=False, min_num_like=MIN_RADIO_LIKE_TO_SPLIT,
            sleep=1, create_like_playlist=False,
            remove_dislike=True, remove_not_like=False):
        not_like_vids = self.banned_vid_set

        remove_dislike_tracks = []
        remove_not_like_tracks = []
        move_like_tracks = []
        pl_counters = {'name': pl_info['title'], 'removed_dislike': 0,
                       'moved_like': 0, 'removed_not_like': 0, 'like_and_not_like': 0}
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
            print(100*'*' + f'\n{pl_counters}')
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
            elif pl_info["title"].replace('radio', 'like') in self.playlist_titles:
                like_pl = pl_info["title"].replace('radio', 'like')
            if like_pl == None:
                if create_like_playlist:
                    like_pl = pl_info["title"].replace('radio', 'like')
                    like_pl_id = self.yt.create_playlist(
                        title=like_pl,
                        description=f'Created for dumping likes from {pl_info["title"]}',
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

        if remove_not_like and len(remove_not_like_tracks):
            if remove_dislike and len(remove_dislike_tracks):
                remove_not_like_tracks += remove_dislike_tracks

            status = self.yt.remove_playlist_items(
                pl_info["id"], remove_not_like_tracks)
            err_msg = f'Bad Status for {pl_info["id"]} remove {len(remove_not_like_tracks)} NOT LIKE tracks: {status}'
            assert str(status) == 'STATUS_SUCCEEDED', err_msg
            if verbose:
                print(f'Removed {len(remove_not_like_tracks)} NOT_LIKE '
                      f'entries from {pl_info["title"]}')
            time.sleep(sleep)

        elif remove_dislike and len(remove_dislike_tracks):
            status = self.yt.remove_playlist_items(
                pl_info["id"], remove_dislike_tracks)
            err_msg = f'Bad Status for {pl_info["id"]} remove {len(remove_dislike_tracks)} noly DISLIKE tracks: {status}'
            assert str(status) == 'STATUS_SUCCEEDED', err_msg
            if verbose:
                print(f'Removed {len(remove_dislike_tracks)} DISLIKE '
                      f'entries from {pl_info["title"]}')
            time.sleep(sleep)

        return pl_counters

    def playlist_rate_all_songs(self, pl_info, rating, sleep_time=0.5,
                                verbose=False, skip_if_dislike=False,
                                valid_ratings=VALID_TRACK_RATINGS):
        assert rating in valid_ratings
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
        if NOT_LIKE_PREFIX in name:
            return True
        for tok in not_like_toks:
            if tok in name:
                return True

    def _playlist_is_like(self, name,
                          like_toks=LIKE_TOKS, like_playlist_names=LIKE_PLAYLISTS):
        name = name.lower()
        if self._playlist_is_not_like(name):
            return False
        for t in like_playlist_names:
            if t.lower() == name:
                return True
        for tok in like_toks:
            if tok in name:
                return True

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
        if skip_playlist_tsv_backup:  # load last backup from file (faster)
            tracks_no_meta = pd.read_csv(
                self.tracks_no_meta_tsv, sep='\t', index_col=0)
        else:  # default do full backup
            tracks_no_meta = self.backup_playlists_and_collect_tracks(
                remove_disliked=True,
                include_library_tracks=True)
            tracks_no_meta.to_csv(self.tracks_no_meta_tsv,
                                  sep='\t', header=True)

        # Get ytmusic metadata for new tracks from tracks_no_meta, update tracks_db
        track_db = pd.read_csv(self.track_db_tsv, sep='\t', index_col=0)
        new_tracks_no_meta = self._track_db_new_or_newly_liked_tracks(
            track_db, tracks_no_meta)
        track_db = self._track_db_update(track_db, new_tracks_no_meta)
        track_db.to_csv(self.track_db_tsv, sep='\t', header=True)

        # Update combined like and not_like tsvs
        not_like_tracks = self.collect_all_not_like_tracks_from_tsvs()
        not_like_tracks.to_csv(self.not_like_tsv, sep='\t', header=True)
        like_tracks = self.collect_all_like_tracks_from_tsvs()
        like_tracks.to_csv(self.like_tsv, sep='\t', header=True)
        print(f'Completed in {(time.time() - start_time) / 60:.1f} minutes')

    def save_playlist_tsv(self, pl_info, track_cols=TRACK_TSV_COLS, remove_disliked=False, yt_user='Jake G'):
        tracks, metadata = self.parse_playlist(pl_info, verbose=True)
        tracks['playlists'] = pl_info['title']
        if remove_disliked:
            tracks_disliked = tracks.loc[tracks['likeStatus'] == 'DISLIKE']
            if (len(tracks_disliked) and
                    metadata['author']['name'] == yt_user):
                print('Removing %d tracks:\n%s' %
                      (len(tracks_disliked), tracks_disliked['title']))
                self.yt.remove_playlist_items(
                    metadata['id'], tracks_disliked.to_dict('records'))
                tracks = tracks.loc[tracks['likeStatus'] != 'DISLIKE']
        if len(tracks):
            tracks = tracks.sort_values(  # Sort tsv by like, then artist
                ['likeStatus', 'artist'], ascending=False)
            fname = os.path.join(
                self.playlist_tsv_dir, '%s.tsv' % pl_info['title'])
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
        print('Fetching and backing up playlists to %s (~10 min)' %
              self.playlist_tsv_dir)
        for i, row in self.playlists.iterrows():
            try:
                pl_title = self._decode(row['title'])
                print('\n\n(%d/%d)\t%s' %
                      (i+1, len(self.playlists), pl_title))
                playlist_info = self.playlist_get_info(
                    row['playlistId'], playlist_limit=song_lim, use_cache=True)
                if playlist_info['trackCount'] == 0:
                    print('Skipping: %s, due to zero tracks' % pl_title)
                    continue
                tracks, metadata = self.save_playlist_tsv(playlist_info,
                                                          remove_disliked=remove_disliked)
                all_playlist_info.append(metadata)
                all_tracks.append(tracks)
                print(90*'-')
            except Exception as e:
                print('Error in playlist %d: %s' % (i, e))
                print('Error in playlist title: %s' % pl_title)

        # Save playlist info
        playlist_info = pd.DataFrame(all_playlist_info)[metadata_cols]
        playlist_info.sort_values('title', ascending=False).to_csv(os.path.join(
            self.playlist_tsv_dir, '_playlists.tsv'), sep='\t', header=True)
        playlist_elapsed = (time.time() - start_time) / 60
        print('Backed up playlist metadata:\n%s' % playlist_info)
        print('Fetched playlist and saved playlist .tsv files in %d minutes' %
              playlist_elapsed)

        if include_library_tracks:
            t1 = time.time()
            print('Fetching library tracks (approx 7 min)...')
            library_tracks = self.parse_tracks(
                self.yt.get_library_songs(limit=song_lim))
            all_tracks.append(library_tracks)
            library_elapsed = (time.time() - t1) / 60
            print('Fetched and saved %d tracks to _library.tsv in %d minutes\n' %
                  (len(library_tracks), library_elapsed))
            library_tracks = library_tracks.sort_values('artist')
            fname = os.path.join(self.playlist_tsv_dir, '%s.tsv' % '_library')
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
        print('Backed up %d playlists and %d tracks in %d minutes to: %s' %
              (len(playlist_info), len(unique_tracks),
               elapsed_minutes, self.playlist_tsv_dir))
        return unique_tracks

    # Functions for aggregating from playlist tsvs
    def collect_all_like_tracks_from_tsvs(self, tsv_header=LIKE_TRACKS_HEADER):
        playlist_files = sorted(os.listdir(self.playlist_tsv_dir))
        like_playlists = [pl for pl in playlist_files
                          if self._playlist_is_like(pl.replace('.tsv', ''))]
        print('Found %d like playlists out of the %d total' %
              (len(like_playlists), len(playlist_files)))
        like_tracks = []
        for pl in like_playlists:
            track_df = pd.read_csv(os.path.join(
                self.playlist_tsv_dir, pl), sep='\t', index_col=0)
            tracks_db_liked = track_df.loc[track_df['likeStatus'] == 'LIKE']
            tracks_db_liked = tracks_db_liked.set_index('videoId', drop=True)
            like_tracks.append(tracks_db_liked)
            print('%s\t%0.1f%% currently liked (of %d total tracks) ' %
                  (pl, 100*len(tracks_db_liked)/len(track_df), len(track_df)))
        like_tracks = pd.concat(
            like_tracks).sort_values('artist')
        like_tracks = like_tracks.loc[
            ~like_tracks.index.duplicated(keep='first'), tsv_header]
        # Load already existing like list tsv
        like_tracks = pd.read_csv(self.like_tsv, sep='\t', index_col=0)
        assert_msg = 'Expected %s to have header %s, not: %s' % (
            self.like_tsv, tsv_header, like_tracks.columns)
        assert list(like_tracks.columns) == tsv_header, assert_msg
        # Update and save tsv, append new like tracks in db but not in like list
        new_like_tracks = like_tracks.loc[frozenset(
            like_tracks.index) - frozenset(like_tracks.index)]
        all_like_tracks = pd.concat([like_tracks, new_like_tracks])
        print('Updated liked tracks with %d new entries (from %d to %d).' % (
            len(new_like_tracks), len(like_tracks), len(all_like_tracks)))
        return like_tracks

    def collect_all_not_like_tracks_from_tsvs(self, tsv_header=LIKE_TRACKS_HEADER):
        playlist_files = sorted(os.listdir(self.playlist_tsv_dir))
        not_like_playlists = [pl for pl in playlist_files
                              if self._playlist_is_not_like(pl.replace('.tsv', ''))]
        print('Found %d not like playlists out of the %d total' %
              (len(not_like_playlists), len(playlist_files)))
        not_like_tracks = []
        for pl in not_like_playlists:
            tracks_db_not_liked = pd.read_csv(os.path.join(
                self.playlist_tsv_dir, pl), sep='\t', index_col=0)
            tracks_db_not_liked = tracks_db_not_liked.set_index('videoId', drop=True)
            not_like_tracks.append(tracks_db_not_liked)
        not_like_tracks = pd.concat(
            not_like_tracks).sort_values('artist')
        not_like_tracks = not_like_tracks.loc[~not_like_tracks.index.duplicated(
            keep='first'), tsv_header]
        print('Updated not liked tracks, contains %d entries.' %
              (len(not_like_tracks)))
        return not_like_tracks

    # Functions for dealing with track db tsv
    def _track_db_get_track_info(self, row):
        copy_song_cols = ['keywords', 'averageRating', 'viewCount', 'release']
        copy_album_cols = ['type', 'trackCount', 'duration', 'year']
        track_str = f"{row['artist']} - {row['album']} - {row['title']}"
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
                print(
                    f'\tSkipping release field, not a valid date: {track_str}')
                continue
            row[col] = song[col]
        if row['albumId'] and type(row['albumId']) == str:
            try:
                album = self.yt.get_album(row.albumId)
            except Exception as e:
                print(
                    f'ERROR running: get_album(albumID)\n{e} for row: {track_str}')
                return row
            if len(album['artists']):
                row['albumArtist'] = album['artists'][0]['name']
            elif len(album['tracks']) and len(album['tracks'][0]['artists']):
                row['albumArtist'] = album['tracks'][0]['artists'][0]['name']
            else:
                print(
                    f'\nERROR Failed: len(album["artists"]) for album:  {track_str}')
            for col in copy_album_cols:
                if col not in album:
                    continue
                new_col = f'album{col[0].upper()}{col[1:]}'
                if album[col]:
                    row[new_col] = album[col]
                else:
                    print(
                        f'\nERROR column {col} not in albums: {track_str}')
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
        for vid, row in new_tracks.iterrows():
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
        print('Scraped info for %d tracks' % len(tracks_w_info))

        track_db = pd.concat([track_db, tracks_w_info])
        track_db = self._track_db_dedupe(track_db, keep='last')
        track_db = track_db.sort_values(['artist', 'album'])
        elapsed_t = (time.time() - t0) / 60
        print('Finished in %d minutes' % elapsed_t)
        print('Track database now has %d tracks' % len(track_db))
        return track_db

    def _track_db_dedupe(self, track_db, keep='last'):
        # Remove exact duplicate rows, keep the first occurrence
        _length = len(track_db)
        track_db = track_db.drop_duplicates(keep=keep)
        print(f"Removed {_length - len(track_db)} exact duplicate rows")

        # Remove duplicates for rows, ignoring specific columns
        _length = len(track_db)
        ignore_cols = ['playlists',  'inLibrary',
                       'duration', 'artistId', 'albumId']
        track_db = track_db.drop_duplicates(
            subset=[c for c in track_db.columns if c not in ignore_cols], keep=keep)
        print(f"Removed { _length - len(track_db)} row duplicates",
              f"(ignoring columns: {ignore_cols})")
        _length = len(track_db)
        ignore_cols = ['title',  'album']
        track_db = track_db.drop_duplicates(
            subset=[c for c in track_db.columns if c not in ignore_cols], keep=keep)
        print(f"Removed { _length - len(track_db)} row duplicates",
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
