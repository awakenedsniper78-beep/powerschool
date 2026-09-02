# PowerSchool Dashboard
 
 https://awakenedsniper78-beep.github.io/powerschool/
 
A better-looking frontend for the PowerSchool guardian portal. Runs entirely on your
machine — your credentials and grades never leave it.

## Setup

```bash
pip install -r requirements.txt
```

Then copy `.env.example` to `.env` and fill in your username and password:

```
PS_BASE_URL=https://birmingham.powerschool.com
PS_USERNAME=your_username
PS_PASSWORD=your_password
```

`.env` is listed in `.gitignore`, so it can never be committed by accident. **Fill it in
yourself — don't paste your password into a chat window, including to me.**

## Running

Check that login works before anything else:

```bash
python ps_client.py
```

You should see `Login OK`. Then start the dashboard:

```bash
python server.py
```

Open <http://127.0.0.1:5000>.

## How it works

```
ps_client.py   logs in, holds the session cookie, fetches pages
parsers.py     turns portal HTML into plain Python dicts
scrape.py      runs the whole job, writes cache.json
server.py      serves the dashboard + hands it cache.json as JSON
static/        the dashboard itself (plain HTML/CSS/JS, no build step)
sync.py        scrape -> encrypt -> commit -> push, in one command
publish.py     just the encrypt step, if you want it on its own
docs/          the same dashboard, hosted on GitHub Pages behind a password
build_offline.py  bundles all of docs/ into one grades.html, no hosting needed
.github/workflows/update-grades.yml   runs sync.py twice a day, unattended
```

**Why Python does the login instead of JavaScript:** browsers refuse to let a page on
localhost post your credentials to `powerschool.com` — that's the CORS security rule, and
it exists for good reasons. So Python handles the portal, and the browser only ever talks
to your own local server.

**Why there's a cache:** `cache.json` holds the last successful scrape, so opening the
dashboard doesn't re-hit the school's servers every time. "Refresh from portal" forces a
fresh scrape.

## Notes on the login

PowerSchool historically hashed your password in the browser before sending it (MD5, then
HMAC-MD5 with a server-supplied key). Most scraper libraries on GitHub exist mainly to
reimplement that. **This district doesn't do it** — it runs the newer PCAS build, whose
`signin-script.js` copies the password straight through and hashes it server-side over
HTTPS. So the login here is an ordinary form POST, which is why `ps_client.py` is short.

### If login gets blocked

The portal sits behind Imperva bot protection. If `python ps_client.py` reports being
blocked, use the cookie fallback:

1. Log in to the portal normally in your browser.
2. Open DevTools → Application → Cookies → the portal's domain.
3. Copy the value of `JSESSIONID` into `PS_COOKIE` in `.env`.

Everything downstream works identically. The cookie expires after a while, so you'll need
to refresh it occasionally.

## The website

The dashboard also runs as a website you can open on your phone, at
`https://<you>.github.io/powerschool/`. It looks and works like the local one; it just
asks for a password first.

It keeps itself up to date. `.github/workflows/update-grades.yml` scrapes the portal
twice a day, encrypts the result, and commits it. Nothing has to run on your computer.

### Why there's a password

GitHub Pages serves files and nothing else. There is no server there to check a password
against, so a login screen written in JavaScript alone would be a locked door beside an
open window — the data file would sit next to it, readable by anyone who typed the URL.

So the password isn't checked, it *is* the key. `docs/data.enc.json` is AES-256-GCM
ciphertext under a key stretched from your username and password (PBKDF2-SHA256, 310,000
rounds). Your phone downloads it and decrypts it locally. A wrong password produces
nothing at all — the authentication tag simply fails.

### Turning it on

Add four secrets under **Settings → Secrets and variables → Actions**. You can do this
from Safari on your phone.

| Secret | What it is |
| --- | --- |
| `PS_USERNAME` | your PowerSchool username |
| `PS_PASSWORD` | your PowerSchool password |
| `DASH_USERNAME` | the username you'll type on the website |
| `DASH_PASSWORD` | the password you'll type on the website (8+ characters) |

Then **Actions → Update grades → Run workflow** for the first run. After that it's on its
own schedule. Open the site, sign in, and tap **Share → Add to Home Screen** to get an
icon that opens fullscreen.

GitHub encrypts these secrets and masks them in logs, including on a public repository.
Pull requests from forks don't get access to them.

### Doing it by hand instead

```bash
python sync.py
```

Scrapes, encrypts, commits, pushes — the same job the workflow does, run from your
computer. With `DASH_USERNAME` and `DASH_PASSWORD` in `.env` it asks nothing.

`python build_offline.py` is a third option: it bundles everything into a single
`grades.html` that needs no hosting at all, for putting in iCloud Drive or dragging onto
a free static host. Useful if you ever make this repo private, since Pages then costs
money.

### What this protects, and what it doesn't

- **Does:** the grade file is public, but it's unreadable ciphertext.
- **Doesn't:** anyone can download that file and guess passwords offline as fast as their
  hardware allows. The 310,000 KDF rounds make each guess expensive, but length is the
  real defence. Use a passphrase of several words, not `grades123`.
- The repo being public reveals that you scrape your district's portal — never your
  grades.
- `.env` and `cache.json` are gitignored and have never been committed. The only grade
  data in the repo is encrypted.

## Privacy

- The local server binds to `127.0.0.1` only — reachable from this computer, nothing else.
- Talks to exactly one external host: your school's portal.
- No analytics, no CDN, no external fonts or scripts.
- `.env`, `cache.json`, and `saved_html/` are all gitignored. The only grade data that
  ever gets committed is `docs/data.enc.json`, which is encrypted.
- Read-only: nothing is ever submitted or changed on the portal.
