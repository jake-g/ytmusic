
import os
import pandas as pd
from ytmusicapi import YTMusic
import time

PLAYLIST_LIMIT=500
PLAYLIST_SONG_LIMIT=10000
USER='Jake G'
REMOVE_DISLIKE = True
BACKUP_DIR  = './playlists/'
METADATA_TSV = '_metadata.tsv'
TRACKS_TSV = '_tracks.tsv'

PLAYLIST_TSV_COLS = ['title', 'artist', 'album', 'likeStatus', 'duration', 'videoId', 'albumId', 'artistId']
METADATA_TSV_COLS = ['title','trackCount','duration','privacy','id']

def parse_playlist(yt, playlist_meta):
    playlist_meta.pop('thumbnails', None)
    tracks = playlist_meta.pop('tracks', None)
    tracks = pd.DataFrame(tracks)
    print(pd.DataFrame.from_dict(playlist_meta, orient='index'))
    tracks['artistId'] = tracks['artists'].dropna().apply(lambda x: x[0]['id']) # TODO handle > 1 artist
    tracks['artist'] = tracks['artists'].dropna().apply(lambda x: x[0]['name'])
    tracks['albumId'] = tracks['album'].dropna().apply(lambda x: x['id'])
    tracks['album'] = tracks['album'].dropna().apply(lambda x: x['name'])
    return tracks, playlist_meta

def merge_duplicates(group):
    _playlists = list(group['playlists'].values)
    row = group.iloc[0]
    row['playlists'] = _playlists
    return row

if __name__ == "__main__":
    start_time = time.time()
    yt = YTMusic('headers_auth.json')
    all_metadata = []
    all_tracks = []
    print('Backing up playlists to %s' % BACKUP_DIR)
    playlists = pd.DataFrame(yt.get_library_playlists(limit=PLAYLIST_LIMIT))
    for i, row in playlists.iterrows(): 
        print('\n\n(%d/%d)\t%s' % (i+1, len(playlists), row['title']))
        playlist = yt.get_playlist(row['playlistId'], limit=PLAYLIST_SONG_LIMIT)
        if playlist['trackCount'] == 0:
            print('Skipping: %s, due to zero tracks' % playlist['title'])
            continue

        tracks, metadata = parse_playlist(yt, playlist)
        all_metadata.append(metadata)
        tracks['playlists'] =  playlist['title']
        all_tracks.append(tracks)

        if REMOVE_DISLIKE:
            tracks_disliked = tracks.loc[tracks['likeStatus'] == 'DISLIKE']
            if len(tracks_disliked) and metadata['author']['name'] == USER:
                print('Removing %d tracks:\n%s' % (len(tracks_disliked), tracks_disliked['title']))
                yt.remove_playlist_items(metadata['id'], tracks_disliked.to_dict('records'))  
                tracks = tracks.loc[tracks['likeStatus'] != 'DISLIKE']
        tracks[PLAYLIST_TSV_COLS].to_csv(
            os.path.join(BACKUP_DIR, '%s.tsv' % playlist['title']), sep='\t', header=True)
        print(90*'-')

    elapsed_minutes = (time.time() - start_time) / 60.0
    all_tracks = pd.concat(all_tracks)
    unique_tracks = all_tracks.groupby('videoId').apply(merge_duplicates).set_index('videoId')
    unique_tracks.to_csv(os.path.join(BACKUP_DIR, TRACKS_TSV), sep='\t', header=True)
    print('Backed up joined playlist tracks to: %s' % BACKUP_DIR)

    all_metadata = pd.DataFrame(all_metadata)[METADATA_TSV_COLS]
    all_metadata.to_csv(os.path.join(BACKUP_DIR, METADATA_TSV), sep='\t', header=True)
    print('Backed up playlist metadata:\n%s' % all_metadata)
    print('Backed up %d playlists in %d minutes to: %s' % (len(all_metadata), elapsed_minutes, BACKUP_DIR))


