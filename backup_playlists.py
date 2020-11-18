
import os
import pandas as pd
from ytmusicapi import YTMusic
import time


def parse_tracks(track_list):
    tracks = pd.DataFrame(track_list)
    tracks['artistId'] = tracks['artists'].dropna().apply(
        lambda x: x[0]['id'])  # TODO handle > 1 artist
    tracks['artist'] = tracks['artists'].dropna().apply(lambda x: x[0]['name'])
    tracks['albumId'] = tracks['album'].dropna().apply(lambda x: x['id'])
    tracks['album'] = tracks['album'].dropna().apply(lambda x: x['name'])
    return tracks


def parse_playlist(yt, playlist_meta):
    playlist_meta.pop('thumbnails', None)
    track_list = playlist_meta.pop('tracks', None)
    print(pd.DataFrame.from_dict(playlist_meta, orient='index'))
    tracks = parse_tracks(track_list)
    return tracks, playlist_meta


def merge_duplicates(group):
    _playlists = list(group['playlists'].values)
    row = group.iloc[0]
    row['playlists'] = _playlists
    return row


def backup_playlists_and_collect_tracks(yt, backup_dir, remove_disliked=False, include_library_tracks=True, song_lim=100000, playlist_lim=500, yt_user='Jake G'):
    # Backs up library playlists and returns playlist info summary df, also collects all unique tracks and returns track df.
    playlist_tsv_cols = ['title', 'artist', 'album',
                         'likeStatus', 'duration', 'videoId', 'albumId', 'artistId']
    metadata_tsv_cols = ['title', 'trackCount', 'duration', 'privacy', 'id']
    all_playlist_info = []
    all_tracks = []
    start_time = time.time()
    print('Backing up playlists to %s' % backup_dir)
    playlists = pd.DataFrame(yt.get_library_playlists(limit=playlist_lim))
    for i, row in playlists.iterrows():
        print('\n\n(%d/%d)\t%s' % (i+1, len(playlists), row['title']))
        playlist = yt.get_playlist(row['playlistId'], limit=song_lim)
        if playlist['trackCount'] == 0:
            print('Skipping: %s, due to zero tracks' % playlist['title'])
            continue

        tracks, metadata = parse_playlist(yt, playlist)
        all_playlist_info.append(metadata)
        tracks['playlists'] = playlist['title']
        all_tracks.append(tracks)

        if remove_disliked:
            tracks_disliked = tracks.loc[tracks['likeStatus'] == 'DISLIKE']
            if len(tracks_disliked) and metadata['author']['name'] == yt_user:
                print('Removing %d tracks:\n%s' %
                      (len(tracks_disliked), tracks_disliked['title']))
                yt.remove_playlist_items(
                    metadata['id'], tracks_disliked.to_dict('records'))
                tracks = tracks.loc[tracks['likeStatus'] != 'DISLIKE']

        tracks[playlist_tsv_cols].to_csv(
            os.path.join(backup_dir, '%s.tsv' % playlist['title']), sep='\t', header=True)
        print(90*'-')

    if include_library_tracks:
        library_tracks = parse_tracks(yt.get_library_songs(limit=song_lim))
        all_tracks.append(library_tracks)
        library_tracks[playlist_tsv_cols].to_csv(
            os.path.join(backup_dir, '%s.tsv' % 'library'), sep='\t', header=True)

    unique_tracks = pd.concat(all_tracks).groupby(
        'videoId').apply(merge_duplicates).set_index('videoId')
    playlist_info = pd.DataFrame(all_playlist_info)[metadata_tsv_cols]
    playlist_info.to_csv(os.path.join(
        backup_dir, '_playlists.tsv'), sep='\t', header=True)
    elapsed_minutes = (time.time() - start_time) / 60.0
    print('Backed up playlist metadata:\n%s' % playlist_info)
    print('Backed up %d playlists in %d minutes to: %s' %
          (len(playlist_info), elapsed_minutes, backup_dir))
    return unique_tracks


def get_track_info(yt, row):
    copy_cols = ['keywords', 'averageRating', 'viewCount', 'release']
    if type(row['albumId']) == str and 'privately_owned' not in row['albumId']:
        try:
            song = yt.get_song(row.name)
            for col in copy_cols:
                if col in song:
                    row[col] = song[col]
        except Exception as e:
            print('Failed to get track info: %s\n%s' % (e, row))
    return row


def get_tracks_info(yt, track_df):
    i = 0
    tracks_w_info = []
    for vid, row in track_df.iterrows():
        i += 1
        print('(%d/%d): %s - %s - %s' % (i, len(track_df),
                                         row['artist'], row['album'], row['title']))
        tracks_w_info.append(get_track_info(yt, row))

    print('Scraped info for %d tracks' % len(tracks_w_info))
    return pd.DataFrame(tracks_w_info)


if __name__ == "__main__":
    BACKUP_DIR = './playlists/'
    TRACKS_TSV = '_tracks.tsv'
    AUTH = 'headers_auth.json'

    yt_api = YTMusic(AUTH)
    playlist_tracks = backup_playlists_and_collect_tracks(
        yt_api, BACKUP_DIR, remove_disliked=True, include_library_tracks=True)
    track_db = pd.read_csv(os.path.join(
        BACKUP_DIR, TRACKS_TSV), sep='\t', index_col=0)
    new_tracks = playlist_tracks.loc[set(
        playlist_tracks.index) - set(track_db.index)]
    print('Track database has %d tracks, found %d unique new tracks' %
          (len(track_db), len(new_tracks)))
    track_db = pd.concat([track_db, get_tracks_info(yt_api, new_tracks)])
    track_db.to_csv(os.path.join(
        BACKUP_DIR, TRACKS_TSV), sep='\t', header=True)
    print('Track database now has %d tracks' % len(track_db))
