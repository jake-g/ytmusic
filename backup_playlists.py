
import os
import pandas as pd
import time
import datetime

from ytmusic_library import YTMusicPlaylists


def is_like_pl(name):
    name = os.path.splitext(name)[0].lower()
    contained_toks = [
        'thumbs_up', ' like', ' likes', ' top'
    ]
    exact_toks = [
        'ambient Indie synths', 'beats instrumental', 'Brass n chill',
        'blues', 'Chillwave', 'electronic chill', 'electronic new indie beats',
        'future bass', 'future beats', 'future garage', 'futurebeat_rap',
        'garage rock', 'hiphop', 'hiphop modern', 'indie',
        'jazz', 'jazz cool', 'jazz noir', 'my balls your chill', 'nudisco',
        'nudisco smooth', 'psych rock modern', 'psychedelic classic rock',
        'reggae classic', 'reggae modern', 'rnb dj',
        'rock 1960s classic', 'rock krautrock', 'rock modern chill',
        'Shoegaze', 'soul funk'
    ]
    if 'not like' in name:
        return False
    for t in contained_toks:
        if t.lower() in name:
            return True
    for t in exact_toks:
        if t.lower() == name:
            return True


def valid_date(date_str):
    try:
        datetime.datetime.strptime(date_str, '%Y-%m-%d')
        return True
    except ValueError:
        return False
        # raise ValueError("Incorrect data format, should be YYYY-MM-DD")


def decode(string, encode_key='latin-1', decode_key='windows-1252'):
    return str(string).encode(encode_key, errors='replace').decode(
        decode_key, errors='replace')


def get_yt_track_info(yt, row):
    copy_song_cols = ['keywords', 'averageRating', 'viewCount', 'release']
    copy_album_cols = ['type', 'trackCount', 'duration', 'year']
    if type(row['artistId']) != str:
        print(f'\nD ERROR: row["artistId"] not a str for row:\n{row}')
    elif 'privately_owned' in row['artistId']:
        print(f'\nSkipping privately owned track for row:\n{row}')
    else:
        song = yt.get_song(row.name)
        for col in copy_song_cols:
            if col not in song:
                continue
            if col == 'release' and not valid_date(song['release']):
                print('\tSkipping release field, not a valid date...')
                continue
            row[col] = song[col]
        if row['albumId'] and type(row['albumId']) == str:
            try:
                album = yt.get_album(row.albumId)
            except Exception as e:
                print(f'ERROR running: get_album(albumID)\n{e} for row\n{row}')
                return row
            if len(album['artists']):
                row['albumArtist'] = album['artists'][0]['name']
            elif len(album['tracks']) and len(album['tracks'][0]['artists']):
                row['albumArtist'] = album['tracks'][0]['artists'][0]['name']
            else:
                print(('\nD ERROR Failed: len(album["artists"]) ',
                       f'for album: {album}'))
            for col in copy_album_cols:
                if col not in album:
                    continue

                new_col = f'album{col[0].upper()}{col[1:]}'
                if album[col]:
                    row[new_col] = album[col]
                else:
                    print(
                        f'\nD ERROR column {col} not in albums\n{album}')
    return row


def update_track_db(yt, track_db, new_tracks):
    print('Track database has %d tracks, found %d unique new tracks' %
          (len(track_db), len(new_tracks)))

    i = 0
    tracks_w_info = []
    t0 = time.time()
    for vid, row in new_tracks.iterrows():
        i += 1
        tracks_w_info.append(get_yt_track_info(yt, row))
        track_str = decode('%s - %s - %s' % (
            row['artist'], row['album'], row['title']))
        print('(%d/%d): %s' % (i, len(new_tracks), track_str))

    tracks_w_info = pd.DataFrame(tracks_w_info)
    print('Scraped info for %d tracks' % len(tracks_w_info))

    track_db = pd.concat([track_db, tracks_w_info])
    track_db = track_db.sort_values(['artist', 'album'])
    elapsed_t = (time.time() - t0) / 60
    print('Finished in %d minutes' % elapsed_t)
    print('Track database now has %d tracks' % len(track_db))
    return track_db


def update_like_tsv(liked_tracks, like_tsv, header):
    # Load already existing like list tsv
    like_tracks = pd.read_csv(like_tsv, sep='\t', index_col=0)
    assert_msg = 'Expected %s to have header %s, not: %s' % (
        like_tsv, header, like_tracks.columns)
    assert list(like_tracks.columns) == header, assert_msg

    # Append new like tracks in db but not in like list, save tsv.
    new_like_tracks = liked_tracks.loc[set(
        liked_tracks.index) - set(like_tracks.index)]
    all_like_tracks = pd.concat([like_tracks, new_like_tracks])
    all_like_tracks.to_csv(like_tsv, sep='\t', header=True)
    print('Updated liked tracks with %d new entries (from %d to %d).' % (
        len(new_like_tracks), len(like_tracks), len(all_like_tracks)))
    return all_like_tracks


def backup_playlists_and_collect_tracks(yt_pl, backup_dir,
                                        remove_disliked=False,
                                        include_library_tracks=True,
                                        song_lim=200000, playlist_lim=500,
                                        yt_user='Jake G'):
    # Backs up library playlists and returns playlist info summary df,
    # also collects all unique tracks and returns track df.
    playlist_tsv_cols = ['title', 'artist', 'album', 'likeStatus',
                         'duration', 'videoId', 'albumId', 'artistId']
    db_remove_tsv_cols = ['setVideoId', 'feedbackTokens']
    metadata_tsv_cols = ['title', 'trackCount', 'duration', 'privacy', 'id']
    all_playlist_info = []
    all_tracks = []
    start_time = time.time()
    print('Fetching and backing up playlists to %s (~10 min)' % backup_dir)
    for i, row in yt_pl.playlists.iterrows():
        try:
            print('\n\n(%d/%d)\t%s' %
                  (i+1, len(yt_pl.playlists), decode(row['title'])))
            playlist = yt_pl.playlist_get_info(
                row['playlistId'], playlist_limit=song_lim, use_cache=True)
            if playlist['trackCount'] == 0:
                print('Skipping: %s, due to zero tracks' % decode(
                    playlist['title']))
                continue

            tracks, metadata = yt_pl.parse_playlist(playlist, verbose=True)
            all_playlist_info.append(metadata)
            tracks['playlists'] = playlist['title']
            all_tracks.append(tracks)

            if remove_disliked:
                tracks_disliked = tracks.loc[tracks['likeStatus'] == 'DISLIKE']
                if (len(tracks_disliked) and
                        metadata['author']['name'] == yt_user):
                    print('Removing %d tracks:\n%s' %
                          (len(tracks_disliked), tracks_disliked['title']))
                    yt_pl.yt.remove_playlist_items(
                        metadata['id'], tracks_disliked.to_dict('records'))
                    tracks = tracks.loc[tracks['likeStatus'] != 'DISLIKE']

            if len(tracks):
                tracks = tracks.sort_values(
                    ['likeStatus', 'artist'], ascending=False)
                fname = os.path.join(backup_dir, '%s.tsv' % playlist['title'])
                tracks[playlist_tsv_cols].to_csv(fname, sep='\t', header=True)
            print(90*'-')
        except Exception as e:
            print('Error in playlist %d: %s' % (i, e))
            print('Error in playlist title: %s' % decode(row['title']))

    playlist_info = pd.DataFrame(all_playlist_info)[metadata_tsv_cols]
    playlist_info.sort_values('title', ascending=False).to_csv(os.path.join(
        backup_dir, '_playlists.tsv'), sep='\t', header=True)
    playlist_elapsed = (time.time() - start_time) / 60
    print('Backed up playlist metadata:\n%s' % playlist_info)
    print('Fetched playlist and saved playlist .tsv files in %d minutes' %
          playlist_elapsed)

    if include_library_tracks:
        t1 = time.time()
        print('Fetching library tracks (approx 5 min)...')
        library_tracks = yt_pl.parse_tracks(
            yt_pl.yt.get_library_songs(limit=song_lim))
        all_tracks.append(library_tracks)
        library_elapsed = (time.time() - t1) / 60
        print('Fetched and saved %d tracks to _library.tsv in %d minutes\n' %
              (len(library_tracks), library_elapsed))
        library_tracks = library_tracks.sort_values('artist')
        fname = os.path.join(backup_dir, '%s.tsv' % '_library')
        library_tracks[playlist_tsv_cols].to_csv(fname, sep='\t', header=True)

    def _merge_duplicates(group):
        _playlists = list(group['playlists'].values)
        _row = group.iloc[0]
        row['playlists'] = _playlists
        return _row
    unique_tracks = pd.concat(all_tracks).groupby(
        'videoId').apply(_merge_duplicates).set_index('videoId')
    unique_tracks = unique_tracks.drop(db_remove_tsv_cols, axis=1)
    unique_tracks = unique_tracks.sort_values(
        ['likeStatus', 'artist'], ascending=False)
    elapsed_minutes = (time.time() - start_time) / 60.0
    print('Backed up %d playlists and %d tracks in %d minutes to: %s' %
          (len(playlist_info), len(unique_tracks),
           elapsed_minutes, backup_dir))
    return unique_tracks


if __name__ == "__main__":
    BACKUP_DIR = './playlists/'
    AUTH = 'headers_auth.json'
    SKIP_PLAYLIST_BACKUP = False
    TRACKS_NO_META_TSV = os.path.join(BACKUP_DIR, '_tracks_no_meta.tsv')
    TRACKS_DB_TSV = os.path.join(BACKUP_DIR, '_tracks_db.tsv')
    LIKE_TRACKS_TSV = os.path.join(BACKUP_DIR, '_liked_tracks.tsv')
    LIKE_TRACKS_HEADER = ['title', 'album', 'artist']  # more compact

    start_time = time.time()
    yt_api = YTMusicPlaylists(header=AUTH)

    # Backup playlists and fetch (or load from file) all playlist
    # and library tracks. The set of tracks are missing ytmusic
    # metadata like release year.
    if SKIP_PLAYLIST_BACKUP:  # load last backup from file (faster)
        tracks_no_meta = pd.read_csv(
            TRACKS_NO_META_TSV, sep='\t', index_col=0)
    else:  # default do full backup
        tracks_no_meta = backup_playlists_and_collect_tracks(
            yt_api, BACKUP_DIR, remove_disliked=True,
            include_library_tracks=True)
        tracks_no_meta.to_csv(TRACKS_NO_META_TSV, sep='\t', header=True)

    # Get ytmusic metadata for new tracks from tracks_no_meta
    # and update tracks_db
    track_db = pd.read_csv(TRACKS_DB_TSV, sep='\t', index_col=0)
    tracks_no_meta = pd.read_csv(TRACKS_NO_META_TSV, sep='\t', index_col=0)
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
    new_tracks_no_meta = tracks_no_meta.loc[new_track_ids]
    track_db = update_track_db(yt_api.yt, track_db, new_tracks_no_meta)
    track_db.to_csv(TRACKS_DB_TSV, sep='\t', header=True)

    # Update Likes list with playlist.tsv
    playlist_files = sorted(os.listdir(BACKUP_DIR))
    like_playlists = [pl for pl in playlist_files if is_like_pl(pl)]
    print('Found %d like playlists out ot the %d total' %
          (len(like_playlists), len(playlist_files)))
    playlist_liked_tracks = []
    for pl in like_playlists:
        track_df = pd.read_csv(os.path.join(
            BACKUP_DIR, pl), sep='\t', index_col=0)
        tracks_db_liked = track_df.loc[track_df['likeStatus'] == 'LIKE']
        tracks_db_liked = tracks_db_liked.set_index('videoId', drop=True)
        playlist_liked_tracks.append(tracks_db_liked)
        print('%s\t%0.1f%% currently liked (of %d total tracks) ' %
              (pl, 100*len(tracks_db_liked)/len(track_df), len(track_df)))
    playlist_liked_tracks = pd.concat(
        playlist_liked_tracks).sort_values('artist')
    playlist_liked_tracks = playlist_liked_tracks.loc[
        ~playlist_liked_tracks.index.duplicated(keep='first'),
        LIKE_TRACKS_HEADER]
    new_like_df = update_like_tsv(
        playlist_liked_tracks, like_tsv=LIKE_TRACKS_TSV,
        header=LIKE_TRACKS_HEADER)

    elapsed_time = (time.time() - start_time) / 60
    print('Completed in %d minutes' % elapsed_time)
