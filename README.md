# YTMusic Library

YouTube Music library management, metadata extraction, and playlist automation.

## Authentication Setup

This module requires browser-based authentication to manage playlists and library data.

1. **Capture Session**: Log into [music.youtube.com](https://music.youtube.com) in Chrome. Use Developer Tools (F12) -> Network tab to find a `browse` POST request.
2. **Copy as cURL**: Right-click the request and select **Copy as cURL (bash)**.
3. **Update `browser.json`**: Run `python browser_auth_update.py` and paste the cURL command, or manually update the `Cookie` and `Authorization` fields in `browser.json`.

For detailed instructions, troubleshooting, and template examples, see **[browser_auth_readme.md](file:///d:/Projects/_Projects_Synced/music-library/ytmusic/browser_auth_readme.md)**.

## Features

- **Automated Backups**: Exports library and playlists to TSV format with full metadata.
- **Metadata Enrichment**: Fetches release year, album type, and average ratings via `ytmusicapi`.
- **Playlist Automation**: Automated cleaning of "Radio" and "Album" playlists based on `LIKE`/`DISLIKE` status.
- **Cross-Platform Sync**: Synchronizes ratings and top tracks from MusicBee and Last.fm.
