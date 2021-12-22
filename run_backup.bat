call conda activate py3
CD /D D:\Projects\_Projects_Synced\music-library\ytmusic
python backup_playlists.py
git add playlists/*.tsv
git commit -m "update playlists"

CD /D D:\Projects\_Projects_Synced\music-library\music-sources-unified
python match_ytmusic_tracks_with_musicbee.py
git add *.tsv
git commit -m "update tsvs"

call conda deactivate
pause
