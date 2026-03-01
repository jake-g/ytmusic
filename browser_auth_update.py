import json
import shlex
import os
import sys

# Change working directory to the script's directory (./ytmusic) immediately
os.chdir(os.path.dirname(os.path.abspath(__file__)))

def main():
    print("Paste your full cURL command below. Press Enter twice when finished:\n")
    
    lines = []
    empty_lines = 0
    while empty_lines < 2:
        try:
            line = input()
        except EOFError:
            break
        
        if not line.strip():
            empty_lines += 1
        else:
            empty_lines = 0
            lines.append(line)
            
    # Strip data payload so shlex doesn't break on escaped binary characters
    curl_input = '\n'.join(lines).split('--data')[0]
    
    if not curl_input.strip():
        print("No input provided. Exiting.")
        sys.exit(1)
        
    tokens = shlex.split(curl_input)
    headers = {}
    cookies = ""

    for i, token in enumerate(tokens):
        if token in ('-H', '--header') and i + 1 < len(tokens):
            header_str = tokens[i+1]
            if ':' in header_str:
                key, val = header_str.split(':', 1)
                headers[key.strip().lower()] = val.strip()
        elif token in ('-b', '--cookie') and i + 1 < len(tokens):
            cookies = tokens[i+1]

    # Map headers to the required format. Will throw a KeyError if 'authorization' isn't found.
    new_auth = {
        "User-Agent": headers.get('user-agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/145.0.0.0 Safari/537.36'),
        "Accept": headers.get('accept', '*/*'),
        "Accept-Language": headers.get('accept-language', 'en-US,en;q=0.9'),
        "Content-Type": headers.get('content-type', 'application/json'),
        "Authorization": headers['authorization'],
        "X-Goog-AuthUser": headers.get('x-goog-authuser', '0'),
        "x-origin": headers.get('x-origin', 'https://music.youtube.com'),
        "Cookie": cookies if cookies else headers.get('cookie', '')
    }

    # Since we changed directory at the top, we just write to 'browser.json'
    filepath = 'browser.json'

    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(new_auth, f, indent=4)

    print(f"\nSuccessfully updated: {os.path.abspath(filepath)}")

    # --- Validation Block ---
    print("Testing new authentication with ytmusic_library...")
    
    from ytmusic_library import YTMusicPlaylists

    # Path to playlists is relative to this script's location
    playlist_tsv_dir = './playlists'
    
    # Will throw an error if the TSV files or directories do not exist
    Y = YTMusicPlaylists(header=filepath, playlist_tsv_dir=playlist_tsv_dir)
    Y.test_ytmusic_api()
    
    print(f"Auth verified. Loaded {len(Y.playlists['title'].unique())} playlists.")

if __name__ == "__main__":
    main()