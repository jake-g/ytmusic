CD /D D:\Projects\_Projects_Synced\music-library\ytmusic
python ytmusic_library.py
git add playlists/*.tsv
git commit -m "update playlists"

CD /D D:\Projects\_Projects_Synced\music-library\music-sources-unified
python lastfm_scrape_history.py
python match_ytmusic_tracks_with_musicbee.py
git add *.tsv
git commit -m "update tsvs"

CD /D D:\Projects\_Projects_Synced\music-library\plex\music-rating-sync
python sync_ratings.py

pause
