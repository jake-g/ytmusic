@REM CD /D D:\Projects\_Projects_Synced\music-library\ytmusic
@REM python ytmusic_library.py
@REM git add playlists/*.tsv
@REM git commit -m "update playlists"

CD /D D:\Projects\_Projects_Synced\music-library\music-sources-unified
@REM python lastfm_scrape_history.py
python match_ytmusic_tracks_with_musicbee.py
@REM git add *.tsv
@REM git commit -m "update tsvs"

@REM CD /D D:\Projects\_Projects_Synced\music-library\plex\music-rating-sync
@REM python sync_ratings.py

pause
