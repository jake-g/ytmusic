
import os
import pandas as pd
import time
import datetime

from ytmusic_library import YTMusicPlaylists

SKIP_PLAYLIST_BACKUP = False
BACKUP_DIR = './playlists/'
AUTH = 'headers_auth.json'
TRACKS_NO_META_TSV = os.path.join(BACKUP_DIR, '_tracks_no_meta.tsv')
TRACKS_DB_TSV = os.path.join(BACKUP_DIR, '_tracks_db.tsv')
TRACK_RM_COLS = ['setVideoId', 'feedbackTokens']
PLAYLIST_COLS = ['title', 'artist', 'album', 'likeStatus',
                 'duration', 'videoId', 'albumId', 'artistId']
METADATA_COLS = ['title', 'trackCount', 'duration', 'privacy', 'id']
NOT_LIKE_TRACKS_TSV = os.path.join(BACKUP_DIR, '_not_liked_tracks.tsv')
NOT_LIKE_PREFIX = 'zz not like'
RADIO_TO_LIKE_PL_TSV = 'playlists/_ytmusic_radio_to_like_pl_map.tsv'
LIKE_TRACKS_TSV = os.path.join(BACKUP_DIR, '_liked_tracks.tsv')
LIKE_TRACKS_HEADER = ['title', 'album', 'artist']  # more compact
LIKE_TOKS = ['thumbs_up', ' like', ' likes', ' top']
LIKE_PLAYLISTS = [
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


def is_like_pl(name):
    name = os.path.splitext(name)[0].lower()
    if NOT_LIKE_PREFIX in name.lower():
        return False
    for t in LIKE_TOKS:
        if t.lower() in name:
            return True
    for t in LIKE_PLAYLISTS:
        if t.lower() == name:
            return True


def is_not_like_pl(name):
    if name.startswith(NOT_LIKE_PREFIX):
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
    track_str = f"{row['artist']} - {row['album']} - {row['title']}"
    if type(row['artistId']) != str:
        print(f'\nD ERROR: row["artistId"] not a str for row: {track_str}')
    elif 'privately_owned' in row['artistId']:
        print(f'\nSkipping privately owned track for row: {track_str}')
    else:
        song = yt.get_song(row.name)
        for col in copy_song_cols:
            if col not in song:
                continue
            if col == 'release' and not valid_date(song['release']):
                print(
                    f'\tSkipping release field, not a valid date: {track_str}')
                continue
            row[col] = song[col]
        if row['albumId'] and type(row['albumId']) == str:
            try:
                album = yt.get_album(row.albumId)
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
                    f'\nD ERROR Failed: len(album["artists"]) for album:  {track_str}')
            for col in copy_album_cols:
                if col not in album:
                    continue
                new_col = f'album{col[0].upper()}{col[1:]}'
                if album[col]:
                    row[new_col] = album[col]
                else:
                    print(f'\nD ERROR column {col} not in albums: {track_str}')
    return row


def get_new_or_newly_liked_tracks(track_db, tracks_no_meta):
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


def update_track_db(yt, track_db, new_tracks):
    print(f"Track database has {len(track_db)} tracks")
    print(f"Found {len(new_tracks)} unique new tracks")
    i = 0
    tracks_w_info = []
    t0 = time.time()
    for vid, row in new_tracks.iterrows():
        i += 1
        tracks_w_info.append(get_yt_track_info(yt, row))
        track_str = decode(
            f"{row['artist']} - {row['album']} - {row['title']}")
        if 'likeStatus' in row:
            track_str += decode(f" -> {row['likeStatus']}")
        # if 'averageRating' in row:
        #     track_str += decode(f" rating={round(row['averageRating'],2)}")
        # if 'release' in row:
        #     track_str += decode(f" ({row['release']})")
        if 'albumType' in row:
            track_str += decode(f" | {row['albumType']}")
        if 'albumYear' in row:
            track_str += decode(f" ({row['albumYear']})")
        print(f"({i}/{len(new_tracks)}): {track_str}")

    tracks_w_info = pd.DataFrame(tracks_w_info)
    print('Scraped info for %d tracks' % len(tracks_w_info))

    track_db = pd.concat([track_db, tracks_w_info])
    track_db = track_db.sort_values(['artist', 'album'])
    elapsed_t = (time.time() - t0) / 60
    print('Finished in %d minutes' % elapsed_t)
    print('Track database now has %d tracks' % len(track_db))
    return track_db


def collect_all_not_like_tracks():
    playlist_files = sorted(os.listdir(BACKUP_DIR))
    not_like_playlists = [pl for pl in playlist_files if is_not_like_pl(pl)]
    print('Found %d not like playlists out ot the %d total' %
          (len(not_like_playlists), len(playlist_files)))
    not_like_tracks = []
    for pl in not_like_playlists:
        tracks_db_not_liked = pd.read_csv(os.path.join(
            BACKUP_DIR, pl), sep='\t', index_col=0)
        tracks_db_not_liked = tracks_db_not_liked
        not_like_tracks.append(tracks_db_not_liked)
    not_like_tracks = pd.concat(
        not_like_tracks).sort_values('artist')
    not_like_tracks = not_like_tracks.loc[
        ~not_like_tracks.index.duplicated(keep='first'),
        LIKE_TRACKS_HEADER]
    print('Updated not liked tracks, contains %d entries.' %
          (len(not_like_tracks)))
    return not_like_tracks


def collect_all_like_tracks():
    playlist_files = sorted(os.listdir(BACKUP_DIR))
    like_playlists = [pl for pl in playlist_files if is_like_pl(pl)]
    print('Found %d like playlists out ot the %d total' %
          (len(like_playlists), len(playlist_files)))
    like_tracks = []
    for pl in like_playlists:
        track_df = pd.read_csv(os.path.join(
            BACKUP_DIR, pl), sep='\t', index_col=0)
        tracks_db_liked = track_df.loc[track_df['likeStatus'] == 'LIKE']
        tracks_db_liked = tracks_db_liked.set_index('videoId', drop=True)
        like_tracks.append(tracks_db_liked)
        print('%s\t%0.1f%% currently liked (of %d total tracks) ' %
              (pl, 100*len(tracks_db_liked)/len(track_df), len(track_df)))
    like_tracks = pd.concat(
        like_tracks).sort_values('artist')
    like_tracks = like_tracks.loc[
        ~like_tracks.index.duplicated(keep='first'),
        LIKE_TRACKS_HEADER]
    # Update Like tsv
    # Load already existing like list tsv
    like_tracks = pd.read_csv(LIKE_TRACKS_TSV, sep='\t', index_col=0)
    assert_msg = 'Expected %s to have header %s, not: %s' % (
        LIKE_TRACKS_TSV, LIKE_TRACKS_HEADER, like_tracks.columns)
    assert list(like_tracks.columns) == LIKE_TRACKS_HEADER, assert_msg
    # Append new like tracks in db but not in like list, save tsv.
    new_like_tracks = like_tracks.loc[frozenset(
        like_tracks.index) - frozenset(like_tracks.index)]
    all_like_tracks = pd.concat([like_tracks, new_like_tracks])
    print('Updated liked tracks with %d new entries (from %d to %d).' % (
        len(new_like_tracks), len(like_tracks), len(all_like_tracks)))
    return like_tracks


def dedupe_track_df(all_tracks):
    def _merge_duplicates(group):
        _playlists = list(group['playlists'].values)
        _row = group.iloc[0]
        _row['playlists'] = _playlists
        return _row
    unique_tracks = pd.concat(all_tracks).groupby(
        'videoId').apply(_merge_duplicates).set_index('videoId')
    unique_tracks = unique_tracks.drop(TRACK_RM_COLS, axis=1)
    unique_tracks = unique_tracks.sort_values(
        ['likeStatus', 'artist'], ascending=False)
    return unique_tracks


def backup_playlists_and_collect_tracks(yt_pl, backup_dir,
                                        remove_disliked=False,
                                        include_library_tracks=True,
                                        song_lim=200000,
                                        yt_user='Jake G'):
    # Backs up library playlists and returns playlist info summary df,
    # also collects all unique tracks and returns track df.
    all_playlist_info = []
    all_tracks = []
    start_time = time.time()
    print('Fetching and backing up playlists to %s (~10 min)' % backup_dir)
    for i, row in yt_pl.playlists.iterrows():
        try:
            pl_title = decode(row['title'])
            print('\n\n(%d/%d)\t%s' %
                  (i+1, len(yt_pl.playlists), pl_title))
            playlist = yt_pl.playlist_get_info(
                row['playlistId'], playlist_limit=song_lim, use_cache=True)
            if playlist['trackCount'] == 0:
                print('Skipping: %s, due to zero tracks' % pl_title)
                continue

            tracks, metadata = yt_pl.parse_playlist(playlist, verbose=True)
            all_playlist_info.append(metadata)
            tracks['playlists'] = playlist['title']
            all_tracks.append(tracks)
            # TODO add remove not like and move like
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
                tracks = tracks.sort_values(  # Sort tsv by like, then artist
                    ['likeStatus', 'artist'], ascending=False)
                fname = os.path.join(backup_dir, '%s.tsv' % playlist['title'])
                tracks[PLAYLIST_COLS].to_csv(fname, sep='\t', header=True)
            print(90*'-')
        except Exception as e:
            print('Error in playlist %d: %s' % (i, e))
            print('Error in playlist title: %s' % pl_title)

    # Save playlist info
    playlist_info = pd.DataFrame(all_playlist_info)[METADATA_COLS]
    playlist_info.sort_values('title', ascending=False).to_csv(os.path.join(
        backup_dir, '_playlists.tsv'), sep='\t', header=True)
    playlist_elapsed = (time.time() - start_time) / 60
    print('Backed up playlist metadata:\n%s' % playlist_info)
    print('Fetched playlist and saved playlist .tsv files in %d minutes' %
          playlist_elapsed)

    if include_library_tracks:
        t1 = time.time()
        print('Fetching library tracks (approx 7 min)...')
        library_tracks = yt_pl.parse_tracks(
            yt_pl.yt.get_library_songs(limit=song_lim))
        all_tracks.append(library_tracks)
        library_elapsed = (time.time() - t1) / 60
        print('Fetched and saved %d tracks to _library.tsv in %d minutes\n' %
              (len(library_tracks), library_elapsed))
        library_tracks = library_tracks.sort_values('artist')
        fname = os.path.join(backup_dir, '%s.tsv' % '_library')
        library_tracks[PLAYLIST_COLS].to_csv(fname, sep='\t', header=True)
    unique_tracks = dedupe_track_df(all_tracks)
    elapsed_minutes = (time.time() - start_time) / 60.0
    print('Backed up %d playlists and %d tracks in %d minutes to: %s' %
          (len(playlist_info), len(unique_tracks),
           elapsed_minutes, backup_dir))
    return unique_tracks


if __name__ == "__main__":

    start_time = time.time()
    yt_api = YTMusicPlaylists(header=AUTH)

    # Backup playlists and fetch (or load from file) all playlist
    # and library tracks. The set of tracks are missing ytmusic
    # metadata like release year.
    if not SKIP_PLAYLIST_BACKUP:  # load last backup from file (faster)
        tracks_no_meta = pd.read_csv(
            TRACKS_NO_META_TSV, sep='\t', index_col=0)
    else:  # default do full backup
        tracks_no_meta = backup_playlists_and_collect_tracks(
            yt_api, BACKUP_DIR, remove_disliked=True,
            include_library_tracks=True)
        tracks_no_meta.to_csv(TRACKS_NO_META_TSV, sep='\t', header=True)

    # Get ytmusic metadata for new tracks from tracks_no_meta, update tracks_db
    track_db = pd.read_csv(TRACKS_DB_TSV, sep='\t', index_col=0)
    new_tracks_no_meta = get_new_or_newly_liked_tracks(
        track_db, tracks_no_meta)
    track_db = update_track_db(yt_api.yt, track_db, new_tracks_no_meta)
    track_db.to_csv(TRACKS_DB_TSV, sep='\t', header=True)

    # Update combined like and not_like tsvs
    not_like_tracks = collect_all_not_like_tracks()
    not_like_tracks.to_csv(NOT_LIKE_TRACKS_TSV, sep='\t', header=True)
    like_tracks = collect_all_like_tracks()
    like_tracks.to_csv(LIKE_TRACKS_TSV, sep='\t', header=True)

    # Finish
    elapsed_time = (time.time() - start_time) / 60
    print('Completed in %d minutes' % elapsed_time)
