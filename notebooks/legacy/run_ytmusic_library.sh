#!/usr/bin/env bash
ls
source ".venv/bin/activate"

cd "ytmusic/"
ls
echo "Starting ytmusic_library.py"
python ytmusic_library.py
git add playlists/*.tsv
# git commit -m "update playlists"