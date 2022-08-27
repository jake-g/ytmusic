import os
import time
import pandas as pd
from ytmusicapi import YTMusic


class YTMusicPlaylists:

    def __init__(self, header='../headers_auth.json', playlist_limit=2000):
        self.yt = YTMusic(header)
        self.playlist_limit = playlist_limit
        self.playlists = pd.DataFrame(
            self.yt.get_library_playlists(limit=playlist_limit))
        self._valid_ratings = ('LIKE', 'DISLIKE', 'INDIFFERENT')
        self._info_cache = {}

    def _playlist_loc_first(self, col, value):
        res = self.playlists.loc[self.playlists[col] == value]
        if len(res) == 0:
            print(f'No playlist with {col}: {value}')
        elif len(res) > 1:
            print((f'multiple matches for : {value}, '
                   f'choosing first result of:\n {res}'))
        return res.iloc[0]

    def query_by_title(self, title):
        return self._playlist_loc_first(col='title', value=title)

    def query_by_playlistId(self, playlistId):
        return self._playlist_loc_first(col='playlistId', value=playlistId)

    def get_playlists_by_privacy(self, privacy='PUBLIC',
                                 skip_if_contains=('z_', 'zz_', 'zzz_')):
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

    def playlist_get_info(self, playlistId,
                          playlist_limit=None, use_cache=True):
        if not playlist_limit:
            playlist_limit = self.playlist_limit
        if use_cache and playlistId in self._info_cache:
            info = self._info_cache[playlistId]
        else:
            info = self.yt.get_playlist(playlistId, limit=playlist_limit)
            self._info_cache[playlistId] = info
        return info

    def playlist_from_tsv(self, tsv_path):
        assert tsv_path.enswith('.tsv')
        df = pd.read_csv(tsv_path, sep='\t', index_col=0)
        pl_name = os.path.basename(tsv_path).split('.tsv')[0]
        print(f'\nGenerating {pl_name} ytmusic playlist for {len(df)} tracks')
        vids = df.videoId.unique().tolist()
        desc = (f'Matched {len(vids)} tracks from '
                f'{pl_name} manually uploaded from local tsv.')
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

    def create_rating_playlist_subset(self, tracks, name, rating, min_ids=0):
        assert rating in self._valid_ratings
        filtered_tracks = tracks.loc[tracks['likeStatus'] == rating]
        video_ids = filtered_tracks['videoId'].unique().tolist()
        if len(video_ids) > min_ids:
            pl_id = self.yt.create_playlist(
                title=name + ' ' + rating.lower(),
                description='generated from %s includes %s subset' % (
                    name, rating),
                privacy_status='PRIVATE',
                video_ids=video_ids
            )
            return pl_id

    def create_like_and_unrated_rating_playlist_subset(self, playlist_name,
                                                       verbose=False,
                                                       sleep_time=10):
        playlist = self.query_by_title(playlist_name)
        if verbose:
            print((f'Sorting {playlist_name} ({playlist["playlistId"]}) '
                   f'into like and indifferent'))
        tracks, metadata = self.parse_playlist(
            playlist_meta=self.playlist_get_info(playlist["playlistId"]))
        res_indif = self.create_rating_playlist_subset(
            tracks, playlist_name, 'INDIFFERENT')
        time.sleep(sleep_time)
        res_like = self.create_rating_playlist_subset(
            tracks, playlist_name, 'LIKE')
        time.sleep(sleep_time)
        self.yt.delete_playlist(playlist['playlistId'])
        if verbose:
            print((f'Created like playlist ({res_like}) and '
                   f'unrated playlist ({res_indif})\nDeleted original '
                   f'playlist: {playlist_name} ({playlist["playlistId"]})'))

    def playlist_rate_all_songs(self, playlistId, rating,
                                sleep_time=0.5, verbose=False):
        assert rating in self._valid_ratings
        playlist = self.query_by_playlistId(playlistId)
        playlist_meta = self.playlist_get_info(playlistId)
        num_tracks = len(playlist_meta["tracks"])
        if verbose:
            print((f'Found {num_tracks} tracks to rate as {rating} in '
                   f'playlist: {playlist["title"]} ({playlistId})'))
        rate_count = 0
        for track in playlist_meta["tracks"]:
            if track["likeStatus"] == rating:
                continue
            if verbose:
                print(f'Setting rating for {track["videoId"]} to {rating}')
            self.yt.rate_song(track["videoId"], rating=rating)
            rate_count += 1
            time.sleep(sleep_time)
        print((f'Rated {rate_count} of {num_tracks} tracks as {rating} in ',
               f'playlist {playlist["title"]} ({playlistId})'))

    def _playlist_is_dislike(self, name):
        name = name.lower()
        if 'not like' in name:
            return True
        if ' dislike' in name:
            return True
        if 'thumbs_down' in name:
            return True

    def _playlist_is_like(self, name):
        name = name.lower()
        if self._playlist_is_dislike(name):
            return False
        if 'thumbs_up' in name:
            return True
        if ' like' in name or ' likes' in name:
            return True
        if ' top' in name:
            return True

    def playlist_get_all_like_playlists(self):
        like_playlists_ids = {}
        for i, row in self.playlists.iterrows():
            if self._playlist_is_like(row.title.lower()):
                like_playlists_ids[row.title] = row.playlistId
        return like_playlists_ids
