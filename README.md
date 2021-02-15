### Update authentication
1. got to (youtube music)[https://music.youtube.com/library] in Chrome incogneto
2. Open developer tools to `Network` tab, it should start recording
3. Sign into account
4. Filter `Network` requests to `browse?`, click on one of them (should all be the same cookie)
5. Scroll to `Request Headers` section
6. Copy fields into `headers_auth.json`
7. Close window, dont log out