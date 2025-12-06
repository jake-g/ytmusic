Here is the updated `AUTH_README.md`. I added a specific section on using Gemini to handle the formatting, which is much less error-prone than manually copying parts of the cURL string.

***

# Authentication Setup (Browser Method)

Due to current limitations with the YouTube Music OAuth flow (HTTP 400 errors on playlist operations), this project uses **Browser Authentication**. This involves capturing a valid session from your web browser and saving it as `browser.json`.

## Generating `browser.json` via cURL

### 1. Capture the Request
1.  Open **Google Chrome** or a Chromium-based browser (Edge, Brave).
2.  Navigate to [music.youtube.com](https://music.youtube.com) and ensure you are logged into the correct account.
3.  Open Developer Tools by pressing **F12** (or `Ctrl+Shift+I`).
4.  Click on the **Network** tab.
5.  In the "Filter" box at the top left of the Network tab, type: `browse`.
6.  **Refresh the page** (`F5`). You should see several network requests appear.
7.  Look for a **POST** request named `browse?ctoken=...` (it usually has a distinct file size, e.g., 100kB+).
8.  Right-click the request name in the list.
9.  Select **Copy** -> **Copy as cURL (bash)**.

### 2a. Create the JSON File

1.  Create a file named `browser.json` in the root directory of your project.
2.  Paste the content below into the file.
3.  Replace the value of `"Cookie"` and `"Authorization"` with the data from your copied cURL command (see the mapping guide below).

**File Content (`browser.json`):**

```json
{
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36",
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Content-Type": "application/json",
    "Authorization": "PASTE_YOUR_AUTHORIZATION_HEADER_HERE",
    "X-Goog-AuthUser": "0",
    "x-origin": "https://music.youtube.com",
    "Cookie": "PASTE_YOUR_LONG_COOKIE_STRING_HERE"
}
```

#### Mapping cURL to JSON

When you paste your cURL command into a text editor, look for the `-H` (Header) flags to find the data needed for the JSON file.

  * **Authorization:**
      * *Look for:* `-H 'authorization: SAPISIDHASH 1765...'`
      * *Action:* Copy the entire string starting with `SAPISIDHASH...` and paste it into the `"Authorization"` field in the JSON.
  * **Cookie:**
      * *Look for:* `-H 'cookie: VISITOR_INFO1_LIVE=...; SID=...;'` or `-b 'VISITOR_INFO1_LIVE=...'`
      * *Action:* Copy the entire long string (everything inside the quotes) and paste it into the `"Cookie"` field in the JSON.


### 2b. Convert to JSON (The Easy Way)
The cURL command contains complex formatting that can be difficult to map manually. The value of the specific cookie string is often very long and sensitive to quotation marks.

**Use Gemini to format it for you:**
1.  Copy the cURL command from the step above and the `browser.json` example.
2.  Paste it into your chat with Gemini along with this prompt:
    > "Here is a cURL command from YouTube Music. Please convert the headers into a valid JSON object for `browser.json` usage. ensure `Cookie`, `Authorization`, `X-Goog-AuthUser`, and `x-origin` are included."
3.  Copy the JSON code block Gemini generates.

### 3. Save the File
1.  Create a file named `browser.json` in the root directory of your project (where `ytmusic_library.py` lives).
2.  Paste the JSON content into the file.
3.  Save the file.

### 4. Verify
Ensure the `browser.json` file is in the same directory as your Python script. The script is configured to detect this file and prioritize it over OAuth.

---

### (Reference) Manual Mapping
If you prefer to map the fields manually from the cURL command to the JSON file, ensure you extract these specific headers:

* **Authorization:** `-H 'authorization: SAPISIDHASH 1765...'`
* **Cookie:** `-H 'cookie: ...'` or `-b 'VISITOR_INFO1_LIVE=...'`
* **X-Goog-AuthUser:** `-H 'x-goog-authuser: 0'`
* **x-origin:** `-H 'x-origin: https://music.youtube.com'`
