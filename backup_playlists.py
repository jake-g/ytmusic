from ytmusic_library import YTMusicPlaylists

SKIP_PLAYLIST_BACKUP = False
HEADER_FILE = 'headers_auth.json'
PLAYLIST_TSV_DIR = './playlists/'

if __name__ == "__main__":
    Y = YTMusicPlaylists(header=HEADER_FILE, playlist_tsv_dir=PLAYLIST_TSV_DIR)
    Y.run_backup(skip_playlist_tsv_backup=SKIP_PLAYLIST_BACKUP)
