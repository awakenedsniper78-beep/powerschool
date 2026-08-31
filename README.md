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

## Privacy

- Binds to `127.0.0.1` only — reachable from this computer, nothing else.
- Talks to exactly one external host: your school's portal.
- No analytics, no CDN, no external fonts or scripts.
- `.env`, `cache.json`, and `saved_html/` are all gitignored.
- Read-only: nothing is ever submitted or changed on the portal.
