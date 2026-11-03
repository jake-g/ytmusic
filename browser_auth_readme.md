# Authentication Setup (Browser Method)

To bypass YouTube Music OAuth limitations (HTTP 400 errors on playlist operations), this project uses **Browser Authentication** via a `browser.json` file.

## 1. Automatic Extraction (Default)

Run `make auth` (or `python browser_auth_update.py` in `ytmusic/`):

```bash
make auth
```

The script first attempts to automatically extract your `.youtube.com` cookies (`__Secure-3PAPISID`, etc.) directly from **Brave** or **Chrome** via `yt-dlp` and compute the `SAPISIDHASH` authorization header.

- **macOS**: Works automatically even while Brave/Chrome is open.
- **Windows**: Works automatically while Brave is open if Brave is launched with `--disable-features=LockProfileCookieDatabase` (configured on the PC shortcuts), or whenever the browser is closed.

---

## 2. Manual cURL Paste Fallback

If automatic extraction is unavailable (e.g., the browser cookie database is locked), `make auth` prompts you to paste a cURL command:

1. Open Brave or Chrome and log into [music.youtube.com/library](https://music.youtube.com/library).
2. Press **F12** (or `Ctrl+Shift+I`) to open Developer Tools and go to the **Network** tab.
3. In the "Filter" box, type: `browse` and refresh the page (**F5**).
4. Pick **any successful (status `200`, non-red) `POST` request** (`browse?prettyPrint=false` or `browse?ctoken=...`).
5. Right-click the request -> **Copy** -> **Copy as cURL (bash)**.
6. Paste the command into the terminal prompt and press **Enter twice**.
