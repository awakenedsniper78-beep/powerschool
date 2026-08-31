"""
Encrypt your grade data and stage it for GitHub Pages.

Why encrypt at all? GitHub Pages serves static files -- there is no server there to
check a password. A login screen written in JavaScript alone would be theatre: the data
file would sit next to it, readable by anyone who typed the URL. So the password isn't
checked against anything, it *is* the key. What gets committed is ciphertext, and
without the password it is meaningless bytes.

Run this after every scrape:

    python publish.py

It reads cache.json, asks for the username and password you want to use (nothing to do
with your PowerSchool ones), and writes docs/data.enc.json. That file is safe to commit.
"""

import getpass
import json
import os
import secrets
import sys
from base64 import b64decode, b64encode

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE_FILE = os.path.join(HERE, "cache.json")
SAMPLE_FILE = os.path.join(HERE, "sample_data.json")
OUT_FILE = os.path.join(HERE, "docs", "data.enc.json")

# Deliberately slow. An attacker who grabs the public file can guess passwords offline as
# fast as their hardware allows, so the only defence is making each guess expensive.
# 310,000 is the OWASP floor for PBKDF2-SHA256; it costs your phone a fraction of a second.
ITERATIONS = 310_000


def derive_key(username, password, salt, iterations=ITERATIONS):
    """Both the username and password go into the key, so both must be right."""
    material = f"{username.strip().lower()}\n{password}".encode("utf-8")
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=iterations)
    return kdf.derive(material)


def encrypt(payload, username, password):
    salt = secrets.token_bytes(16)
    nonce = secrets.token_bytes(12)
    key = derive_key(username, password, salt)
    plaintext = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    ciphertext = AESGCM(key).encrypt(nonce, plaintext, None)
    return {
        "v": 1,
        "kdf": "PBKDF2-SHA256",
        "iterations": ITERATIONS,
        "cipher": "AES-GCM",
        "salt": b64encode(salt).decode(),
        "nonce": b64encode(nonce).decode(),
        "ciphertext": b64encode(ciphertext).decode(),
    }


def decrypt(blob, username, password):
    """Reverse of encrypt(). Returns None if the credentials don't open the file, which
    is also how a file written under a different password reads."""
    key = derive_key(username, password, b64decode(blob["salt"]), blob.get("iterations", ITERATIONS))
    try:
        plaintext = AESGCM(key).decrypt(b64decode(blob["nonce"]), b64decode(blob["ciphertext"]), None)
    except InvalidTag:
        return None
    return json.loads(plaintext.decode("utf-8"))


def load_payload():
    for path in (CACHE_FILE, SAMPLE_FILE):
        if os.path.exists(path):
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
            print(f"Encrypting {os.path.basename(path)}"
                  f"{'  (sample data -- run scrape.py for real grades)' if data.get('is_sample') else ''}")
            return data
    sys.exit("No cache.json or sample_data.json to publish. Run scrape.py first.")


def prompt_credentials():
    """Ask for the username and password that will unlock the file. Shared with
    build_offline.py so both entry points enforce the same rules."""
    print("\nPick the username and password you'll type on your phone.")
    print("These are yours alone -- NOT your PowerSchool login.\n")

    username = input("Username: ").strip()
    if not username:
        sys.exit("Username can't be blank.")

    password = getpass.getpass("Password: ")
    if len(password) < 8:
        # The encrypted file is public. A short password is a short walk for a cracker.
        sys.exit("Use at least 8 characters -- this file will be public, so length is the defence.")
    if getpass.getpass("Confirm password: ") != password:
        sys.exit("Passwords didn't match.")

    return username, password


def main():
    payload = load_payload()
    username, password = prompt_credentials()

    os.makedirs(os.path.dirname(OUT_FILE), exist_ok=True)
    with open(OUT_FILE, "w", encoding="utf-8") as fh:
        json.dump(encrypt(payload, username, password), fh, indent=2)

    print(f"\nWrote {os.path.relpath(OUT_FILE, HERE)}")
    print("Commit and push it, then open your Pages URL on your phone.\n")
    print("  git add docs/data.enc.json && git commit -m 'Update grades' && git push")


if __name__ == "__main__":
    main()
