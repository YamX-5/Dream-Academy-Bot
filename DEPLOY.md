# Hosting Dream Academy Manager online (no laptop needed)

GitHub only stores the code — it cannot run a Python server. The free host that fits
this app is **PythonAnywhere**: Flask runs 24/7, the SQLite file persists, and the
URL never changes. Total setup is about 15 minutes, once.

## Part 1 — Push the code to GitHub (one time)

1. Go to https://github.com/new
   - Repository name: `dream-academy-manager`
   - Visibility: **Private**
   - Do NOT add a README or .gitignore (the project already has them)
2. On the laptop, in `D:\Dream Academy Bot`, run:

```
git remote add origin https://github.com/<YOUR_USERNAME>/dream-academy-manager.git
git push -u origin master
```

Git will open a browser window to sign in the first time.

## Part 2 — Deploy on PythonAnywhere (one time)

1. Create a free account at https://www.pythonanywhere.com (choose the **Beginner** plan).
2. Open a **Bash console** (Consoles tab) and run:

```
git clone https://github.com/<YOUR_USERNAME>/dream-academy-manager.git
cd dream-academy-manager
pip3 install --user -r requirements.txt
```

(For a private repo, GitHub will ask for your username and a Personal Access Token
as the password — create one at https://github.com/settings/tokens with `repo` scope.)

3. Go to the **Web** tab → **Add a new web app** → **Manual configuration** → **Python 3.10**.
4. In the web app settings:
   - **Source code**: `/home/<PA_USERNAME>/dream-academy-manager`
   - **Working directory**: `/home/<PA_USERNAME>/dream-academy-manager`
   - **WSGI configuration file**: click it and replace the whole content with:

```python
import sys
sys.path.insert(0, "/home/<PA_USERNAME>/dream-academy-manager")
from app import app as application
```

5. Click the green **Reload** button.
6. Your app is now live at `https://<PA_USERNAME>.pythonanywhere.com` — permanent URL,
   works from any phone, laptop can stay off.

## Part 3 — After deploying

- Open the site, log in with the **admin PIN** (`0000` by default) and change both PINs
  immediately in Settings.
- There is no "localhost admin" online — you always log in with the admin PIN.
- The QR page still works: open `/qr` while logged in as admin and send the QR
  to coaches once. The URL never changes, so this is one time only.
- Daily DB backups still run automatically into `backups/` on the server.
  Download a copy occasionally: Files tab → `dream-academy-manager/backups/`.
- **Free-tier note:** PythonAnywhere free apps must be renewed every 3 months —
  they email you a "Run until" button; one click keeps it alive.

## Updating the app later

On the laptop:
```
git add -A
git commit -m "describe the change"
git push
```

On PythonAnywhere (Bash console):
```
cd dream-academy-manager && git pull
```
Then hit **Reload** on the Web tab.

## Local mode still works

`start.bat` keeps working exactly as before (localhost admin without PIN +
Cloudflare tunnel). Use it as a fallback or for testing. Note that local and
online are **two separate databases** — pick one as the real one. If you move
to PythonAnywhere, do it before entering real data, or upload your local
`academy.db` once via the Files tab.
