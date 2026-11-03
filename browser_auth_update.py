"""Updates YouTube Music browser authentication credentials (browser.json).

Tries automatic cookie extraction from local browsers (Brave/Chrome) via yt-dlp,
and falls back to pasting a cURL command from DevTools.
"""

import io
import json
import os
import shlex
import sys
from typing import Dict, List, Optional

from ytmusicapi.helpers import get_authorization
from ytmusicapi.helpers import sapisid_from_cookie

os.chdir(os.path.dirname(os.path.abspath(__file__)))

ORIGIN = 'https://music.youtube.com'
DEFAULT_UA = (
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
    'Chrome/156.0.0.0 Safari/537.36'
)
OPTIONAL_HEADER_KEYS = (
    'referer',
    'x-goog-visitor-id',
    'x-youtube-bootstrap-logged-in',
    'x-youtube-client-name',
    'x-youtube-client-version',
)


def _build_auth_dict(
    cookies: str, headers: Optional[Dict[str, str]] = None
) -> Optional[Dict[str, str]]:
  """Constructs a browser.json dict from cookies and optional headers."""
  headers = headers or {}
  if '__Secure-3PAPISID' not in cookies:
    return None
  sapisid = sapisid_from_cookie(cookies)
  origin = headers.get('origin') or headers.get('x-origin') or ORIGIN
  auth_header = headers.get('authorization') or get_authorization(
      f'{sapisid} {origin}'
  )

  new_auth = {
      'User-Agent': headers.get('user-agent', DEFAULT_UA),
      'Accept': headers.get('accept', '*/*'),
      'Accept-Language': headers.get('accept-language', 'en-US,en;q=0.9'),
      'Content-Type': headers.get('content-type', 'application/json'),
      'Authorization': auth_header,
      'X-Goog-AuthUser': headers.get('x-goog-authuser', '0'),
      'x-origin': headers.get('x-origin', origin),
      'origin': origin,
      'Cookie': cookies,
  }
  for key in OPTIONAL_HEADER_KEYS:
    if key in headers:
      new_auth[key] = headers[key]
  return new_auth


def extract_browser_cookies() -> Optional[Dict[str, str]]:
  """Attempts automatic cookie extraction from Brave or Chrome via yt-dlp."""
  try:
    from yt_dlp.cookies import \
        extract_cookies_from_browser  # pylint: disable=import-outside-toplevel
  except ImportError:
    return None

  for browser in ('brave', 'chrome'):
    old_stderr = sys.stderr
    sys.stderr = io.StringIO()
    try:
      jar = extract_cookies_from_browser(browser)
    except Exception:  # pylint: disable=broad-exception-caught
      continue
    finally:
      sys.stderr = old_stderr

    yt_cookies = [
        f'{c.name}={c.value}' for c in jar if 'youtube.com' in (c.domain or '')
    ]
    auth = _build_auth_dict('; '.join(yt_cookies))
    if auth:
      print(f'Auto-extracted YouTube Music cookies from {browser}.')
      return auth
  return None


def parse_curl_input(lines: List[str]) -> Dict[str, str]:
  """Parses a pasted cURL command into a browser.json dictionary."""
  curl_input = '\n'.join(lines).split('--data')[0]
  if not curl_input.strip():
    print('No input provided. Exiting.')
    sys.exit(1)

  tokens = shlex.split(curl_input)
  headers: Dict[str, str] = {}
  cookies = ''

  for i, token in enumerate(tokens):
    if token in ('-H', '--header') and i + 1 < len(tokens):
      header_str = tokens[i + 1]
      if ':' in header_str:
        key, val = header_str.split(':', 1)
        headers[key.strip().lower()] = val.strip()
    elif token in ('-b', '--cookie') and i + 1 < len(tokens):
      cookies = tokens[i + 1]

  cookie_val = cookies if cookies else headers.get('cookie', '')
  auth = _build_auth_dict(cookie_val, headers)
  if not auth:
    raise KeyError('Missing required authorization or __Secure-3PAPISID cookie')
  return auth


def main() -> None:
  """Updates browser.json automatically or via pasted cURL fallback."""
  new_auth = extract_browser_cookies()

  if not new_auth:
    print(
        'Paste your full cURL command below. Press Enter twice when finished:\n'
    )
    lines: List[str] = []
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
    new_auth = parse_curl_input(lines)

  filepath = 'browser.json'
  with open(filepath, 'w', encoding='utf-8') as f:
    json.dump(new_auth, f, indent=4)

  print(f'\nSuccessfully updated: {os.path.abspath(filepath)}')
  print('Testing new authentication with ytmusic_library...')

  from ytmusic_library import \
      YTMusicPlaylists  # pylint: disable=import-outside-toplevel

  yt_pl = YTMusicPlaylists(header=filepath, playlist_tsv_dir='./playlists')
  yt_pl.test_ytmusic_api()

  print(
      f"Auth verified. Loaded {len(yt_pl.playlists['title'].unique())} "
      'playlists.'
  )


if __name__ == '__main__':
  main()
