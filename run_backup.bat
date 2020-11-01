call conda activate py3
CD /D D:\Projects\_Projects_Synced\music-library\ytmusic

python backup_playlists.py

git add playlists/*.tsv
git commit -am "update playlists"

call conda deactivate
