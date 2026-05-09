# Authentication Setup (Browser Method)

To bypass YouTube Music OAuth limitations (HTTP 400 errors on playlist operations), this project uses **Browser Authentication** via a `browser.json` file.

## 1. Capture Your Session (cURL)

1. Open a Chromium browser (Chrome, Edge, Brave) and log into [music.youtube.com](https://music.youtube.com).
2. Press **F12** (or `Ctrl+Shift+I`) to open Developer Tools and go to the **Network** tab.
3. In the "Filter" box, type: `browse`.
4. **Refresh the page** (`F5`).
5. Look for a **POST** request named `browse?ctoken=...` (usually 100kB+ in size).
6. Right-click the request -> **Copy** -> **Copy as cURL (bash)**.

---

## 2. Generate `browser.json`

Choose **one** of the methods below to convert your copied cURL command into the required configuration file.

### Method A: Use the Auto-Updater Script (Recommended)

This is the fastest, least error-prone method.

1. Run the included script in your terminal: `python browser_auth_update.py`
2. Paste your copied cURL command.
3. Press **Enter**, type `DONE` on a new line, and press **Enter** again.
4. The script will automatically parse the data and generate/update your `browser.json` file.

### Method B: Use Gemini

1. Paste your cURL command into a chat with Gemini along with this prompt:
> "Convert this YouTube Music cURL command into a valid JSON object for `browser.json`. Extract and include `Cookie`, `Authorization`, `X-Goog-AuthUser`, and `x-origin`, along with standard headers like `User-Agent`."


2. Create a `browser.json` file in your project's root directory and paste the generated JSON block.

### Method C: Manual Setup

Create a `browser.json` file in your project root. Copy the template below and manually replace the `"Authorization"` and `"Cookie"` fields by finding the corresponding `-H` and `-b` flags in your cURL text.

```json
{
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36",
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Content-Type": "application/json",
    "Authorization": "PASTE_YOUR_AUTHORIZATION_HEADER_HERE",
    "X-Goog-AuthUser": "0",
    "x-origin": "https://music.youtube.com",
    "Cookie": "PASTE_YOUR_LONG_COOKIE_STRING_HERE"
}

```

---

## 3. Verify

Ensure `browser.json` is located in the same directory as your main Python script. The application will automatically detect it and use it to authenticate.
