"""
Logs in to a PowerSchool guardian portal and fetches pages as you.

Why this file is short:
PowerSchool used to hash your password in the browser before sending it (MD5, then
HMAC-MD5 with a server-supplied "pskey"). Lots of old scraper libraries exist purely to
reimplement that. This district runs the newer "PCAS" build, which does NOT do that --
its signin-script.js just copies the password into a second field and posts it over
HTTPS, hashing it server-side:

    function doPCASLogin(form) {
        var originalpw = getFormValue(form, 'pw');
        setFormValue(form, 'dbpw', originalpw);   // plain copy, no hashing
    }

So logging in is an ordinary HTML form POST. That's all this file does.
"""

import os
import sys

import requests
from dotenv import load_dotenv

load_dotenv()

BASE_URL = os.getenv("PS_BASE_URL", "https://birmingham.powerschool.com").rstrip("/")
USERNAME = os.getenv("PS_USERNAME", "")
PASSWORD = os.getenv("PS_PASSWORD", "")
COOKIE = os.getenv("PS_COOKIE", "").strip()

# The portal sits behind Imperva (a bot-protection CDN). Sending a realistic browser
# User-Agent makes it far less likely to challenge us. We are not evading anything --
# we're one person reading their own grades at human speed.
BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)


class LoginError(RuntimeError):
    """Raised when we can't get an authenticated session."""


class PowerSchoolClient:
    def __init__(self, base_url=BASE_URL):
        self.base_url = base_url.rstrip("/")
        # A Session is the important bit: it remembers cookies across requests, so once
        # we log in, every later .get() is automatically authenticated.
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": BROWSER_UA})

    def login(self):
        """Get an authenticated session, either by posting the form or reusing a cookie."""
        if COOKIE:
            # Fallback path: user pasted a JSESSIONID from their browser into .env.
            self.session.cookies.set("JSESSIONID", COOKIE, domain=_host(self.base_url))
            if not self._is_logged_in():
                raise LoginError(
                    "PS_COOKIE was set but the session isn't valid. It has probably "
                    "expired -- grab a fresh JSESSIONID from your browser."
                )
            return self

        if not USERNAME or not PASSWORD:
            raise LoginError(
                "PS_USERNAME / PS_PASSWORD are empty. Copy .env.example to .env and "
                "fill them in."
            )

        # Step 1: load the login page first. This gets us the initial JSESSIONID and the
        # Imperva cookies. Posting credentials without these looks like a bot.
        self.session.get(f"{self.base_url}/public/home.html", timeout=30)

        # Step 2: post the form. These field names were read off the real login page.
        # `pw` and `dbpw` both carry the password (that's what doPCASLogin does), and
        # `ldappassword` is set too in case the district uses LDAP auth.
        payload = {
            "account": USERNAME,
            "pw": PASSWORD,
            "dbpw": PASSWORD,
            "ldappassword": PASSWORD,
            "translator_username": "",
            "translator_password": "",
            "translator_ldappassword": "",
            "returnUrl": "",
            "serviceName": "PS Parent Portal",
            "serviceTicket": "",
            "pcasServerUrl": "/",
            "credentialType": "User Id and Password Credential",
        }
        resp = self.session.post(
            f"{self.base_url}/guardian/home.html",
            data=payload,
            headers={"Referer": f"{self.base_url}/public/home.html"},
            timeout=30,
        )

        # PowerSchool returns HTTP 200 whether or not login worked -- on failure it just
        # re-renders the login page. So we check the *content*, not the status code.
        if not _looks_authenticated(resp.text):
            if "incapsula" in resp.text.lower() or "_Incapsula_" in resp.text:
                raise LoginError(
                    "Blocked by Imperva bot protection.\n"
                    "Use the fallback: log in with your browser, then copy the "
                    "JSESSIONID cookie value into PS_COOKIE in your .env file."
                )
            raise LoginError(
                "Login failed -- the portal sent us back to the sign-in page.\n"
                "Check PS_USERNAME / PS_PASSWORD in .env."
            )
        return self

    def get(self, path):
        """Fetch an authenticated page, e.g. client.get('/guardian/home.html')."""
        url = path if path.startswith("http") else f"{self.base_url}/{path.lstrip('/')}"
        resp = self.session.get(url, timeout=30)
        resp.raise_for_status()
        if not _looks_authenticated(resp.text):
            raise LoginError(f"Session expired while fetching {path}")
        return resp.text

    def _is_logged_in(self):
        resp = self.session.get(f"{self.base_url}/guardian/home.html", timeout=30)
        return _looks_authenticated(resp.text)


def _host(url):
    return url.split("://", 1)[-1].split("/", 1)[0]


def _looks_authenticated(html):
    """A logged-out response contains the login form; a logged-in one doesn't."""
    return 'name="LoginForm"' not in html and "/public/home.html" not in html[:2000]


if __name__ == "__main__":
    # Verification step 1 from the plan: prove auth works before writing any parser.
    try:
        client = PowerSchoolClient().login()
        html = client.get("/guardian/home.html")
    except LoginError as err:
        print(f"Login FAILED\n\n{err}", file=sys.stderr)
        sys.exit(1)

    print(f"Login OK  ({len(html):,} bytes fetched from /guardian/home.html)")
    # Save the page so we can write parsers against your real HTML without you having
    # to copy-paste it by hand. This folder is gitignored.
    os.makedirs("saved_html", exist_ok=True)
    with open("saved_html/home.html", "w", encoding="utf-8") as fh:
        fh.write(html)
    print("Saved to saved_html/home.html")
