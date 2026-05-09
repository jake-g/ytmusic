# README

## Updated 2021

### Update authentication

1. got to [youtube music](https://music.youtube.com/library) in Chrome incogneto
2. Open developer tools to `Network` tab, it should start recording
3. Sign into account
4. Filter `Network` requests to `browse?`, click on one of them (should all be the same cookie)
5. Scroll to `Request Headers` section
6. Copy fields into `headers_auth.json`
7. Close window, dont log out

## Highlight Changelog

- **May 2026**: Modularized YTMusic directory with independent tests and CI workflows
- **Feb 2021**: Added detailed authentication instructions for browser session usage
- **Dec 2020**: Integrated "like mining" into the backup workflow and reorganized playlist subsets
- **Nov 2020**: Expanded track database to include all playlist and library tracks
- **Oct 2020**: Initial commit and first automated playlist backup
