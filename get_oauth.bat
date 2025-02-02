
pip install -r requirements.txt --upgrade
python.exe -m pip install --upgrade pip 

@REM  2025 requires client it, i made youtube project:
@REM https://console.cloud.google.com/apis/credentials?project=graceful-alpha-154201
@REM Latest see: `client_auth.json`
@REM https://ytmusicapi.readthedocs.io/en/stable/setup/oauth.html
C:\Users\jake\AppData\Roaming\Python\Python312\Scripts\ytmusicapi.exe oauth