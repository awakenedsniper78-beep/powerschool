# PowerSchool Dashboard

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
publish.py     encrypts cache.json into docs/data.enc.json for the phone
docs/          the same dashboard, hosted on GitHub Pages behind a password
build_offline.py  bundles all of docs/ into one grades.html, no hosting needed
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

## Reading your grades on your iPhone

`docs/` is a copy of the dashboard built to run with no server at all, so GitHub Pages can
host it. You open a URL on your phone, type a username and password you picked yourself,
and your grades appear.

### Why the password is real

GitHub Pages serves files. There is no server there, so there is nothing to check a
password against — a login screen written in JavaScript alone would be a locked door
standing next to an open window, because the data file sits right beside it and anyone
could fetch it directly.

So the password isn't checked, it *is* the key. `publish.py` encrypts your grades with
AES-256-GCM using a key stretched from your username and password (PBKDF2-SHA256,
310,000 rounds). What gets committed is ciphertext. Your phone downloads it and decrypts
it locally — the password never leaves the device and is never stored in the repo.

### Getting it onto the phone — pick one

**GitHub Pages** is free only for *public* repositories. On a private repo it needs a paid
plan, so if this repo is private, pick one of the other two.

**1. GitHub Pages (free if the repo is public).** Make the repo public, then
**Settings → Pages → Source: Deploy from a branch → `main` → `/docs`** → Save. A minute
later you get `https://<you>.github.io/powerschool/`. Nothing secret lives in this repo —
`.env` and `cache.json` are gitignored and never were committed, and the only grade data
here is encrypted. Going public does reveal that *you* have a PowerSchool scraper for your
district, just never what your grades are.

**2. No hosting at all (free, repo stays private).**

```bash
python build_offline.py
```

That writes `grades.html`, one self-contained file with the stylesheet, the script, and
your encrypted grades inlined. Put it in iCloud Drive, then open it from the **Files** app
on your iPhone — it still asks for your password and still decrypts locally. Updating
means rebuilding the file and replacing it.

**3. A different free static host (free, repo stays private).** Netlify, Cloudflare Pages
and Vercel all have free tiers that deploy from a private repo — point them at `docs/`.
Or skip the repo link entirely and drag `grades.html` onto <https://app.netlify.com/drop>
for an instant URL.

### Every time you want fresh grades on your phone

```bash
python scrape.py                     # pull the latest from the portal
python publish.py                    # pick your username + password, encrypt
git add docs/data.enc.json
git commit -m "Update grades"
git push
```

(Using the offline file instead? Run `python build_offline.py` in place of `publish.py`
and copy the fresh `grades.html` over to iCloud Drive — nothing to commit.)

Both scripts ask for the username and password each run. Use the same ones every time,
or your phone won't be able to open the new file.

### On the phone

If you have a URL (options 1 and 3), open it in Safari, sign in, then tap
**Share → Add to Home Screen**. It gets its own icon and opens fullscreen, without
Safari's address bar. (A file opened from the Files app can't be added to the Home
Screen — that's the trade-off for needing no host.) Ticking "Stay signed in on this
iPhone" saves the password in that browser's local storage so you skip the login next
time — convenient, but it means anyone holding your unlocked phone can open it too.

### What this does and doesn't protect

- **Does:** the grade file is public, but it's unreadable ciphertext. A wrong password
  produces nothing at all — AES-GCM rejects it outright rather than returning garbage.
- **Doesn't:** anyone can *download* the encrypted file and guess passwords offline, as
  fast as their hardware allows. The 310,000 KDF rounds make each guess expensive, but
  the real defence is length. Use a passphrase of several words, not `grades123`.
- The repo is public, so the file's *existence* is public even though its contents aren't.
  Making the repo private hides it entirely — note that Pages on a private repo needs a
  paid GitHub plan.
- `cache.json` (plaintext grades) stays gitignored and never leaves your computer.
  Only `docs/data.enc.json` is ever committed.

## Privacy

- The local server binds to `127.0.0.1` only — reachable from this computer, nothing else.
- Talks to exactly one external host: your school's portal.
- No analytics, no CDN, no external fonts or scripts.
- `.env`, `cache.json`, and `saved_html/` are all gitignored. The only grade data that
  ever gets committed is `docs/data.enc.json`, which is encrypted.
- Read-only: nothing is ever submitted or changed on the portal.
