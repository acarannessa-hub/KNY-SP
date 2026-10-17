"""
add_google_key.py -- put your Google service account key into .env SAFELY.

No copy-paste: this reads the downloaded JSON key file, checks it, encodes it,
and writes GOOGLE_SERVICE_ACCOUNT_B64 into your .env for you. If the line
already exists (even a broken one) it is REPLACED, never duplicated. Every
other line in .env is left untouched, and a backup is saved as .env.bak.

It prints only the robot email and a length. It never prints the key.

Usage (from the project folder):
  python add_google_key.py "C:\\Users\\you\\Downloads\\kny-sp-xxxx.json"
  python add_google_key.py "C:\\path\\key.json" --sheet-id <ID or full sheet URL>

Afterwards, run:  python check_sheets.py
"""

import argparse
import base64
import json
import os
import re
import shutil
import sys

KEY_NAME = "GOOGLE_SERVICE_ACCOUNT_B64"
SHEET_NAME = "GOOGLE_SHEET_ID"
ID_IN_URL = re.compile(r"/spreadsheets/d/([A-Za-z0-9_-]+)")


def die(message):
    sys.exit("ERROR: " + message)


def read_key_file(path):
    try:
        with open(path, encoding="utf-8-sig") as handle:
            info = json.load(handle)
    except FileNotFoundError:
        die(f"File not found: {path}\n"
            "Check the path. If you deleted the key file, create a new key: "
            "Google Cloud -> IAM & Admin -> Service Accounts -> your account "
            "-> Keys -> Add key -> Create new key -> JSON.")
    except (ValueError, UnicodeDecodeError):
        die("That file is not a valid JSON key file.")
    except OSError as error:
        die(f"Could not read the file: {error.strerror}")

    required = ("type", "client_email", "private_key", "token_uri")
    missing = [k for k in required if not isinstance(info, dict) or not info.get(k)]
    if missing or info.get("type") != "service_account":
        die("That JSON is not a SERVICE ACCOUNT key"
            + (f" (missing: {', '.join(missing)})" if missing else "")
            + ". Download one under Service Accounts -> Keys.")
    return info


def clean_sheet_id(value):
    match = ID_IN_URL.search(value)
    sheet_id = match.group(1) if match else value.strip()
    if not re.fullmatch(r"[A-Za-z0-9_-]{20,}", sheet_id):
        die("That does not look like a spreadsheet ID. Use the long code "
            "between /d/ and /edit in the sheet's web address.")
    return sheet_id


def load_env_text(env_path):
    if not os.path.exists(env_path):
        return "", "\n"
    raw = open(env_path, "rb").read()
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        die(f"{env_path} is saved as UTF-16 (often caused by PowerShell's >> "
            "operator). Open it in VS Code, click the encoding in the bottom "
            "bar, choose 'Save with Encoding' -> 'UTF-8', then run this again.")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        die(f"{env_path} is not UTF-8. Re-save it as UTF-8 and try again.")
    newline = "\r\n" if "\r\n" in text else "\n"
    return text.replace("\r\n", "\n"), newline


def set_env_value(text, name, value):
    """Remove every existing line for `name`, then append one correct line."""
    pattern = re.compile(rf"^\s*(export\s+)?{re.escape(name)}\s*=")
    kept = [line for line in text.split("\n") if not pattern.match(line)]
    while kept and kept[-1].strip() == "":
        kept.pop()
    kept.append(f"{name}={value}")
    return "\n".join(kept) + "\n"


def main():
    parser = argparse.ArgumentParser(
        description="Write the Google service account key into .env safely.")
    parser.add_argument("key_file", help="path to the downloaded .json key")
    parser.add_argument("--sheet-id", help="spreadsheet ID or full URL")
    parser.add_argument("--env-file", default=".env")
    args = parser.parse_args()

    info = read_key_file(args.key_file)

    compact = json.dumps(info, separators=(",", ":")).encode("utf-8")
    encoded = base64.b64encode(compact).decode("ascii")

    text, newline = load_env_text(args.env_file)
    if os.path.exists(args.env_file):
        shutil.copyfile(args.env_file, args.env_file + ".bak")

    text = set_env_value(text, KEY_NAME, encoded)
    if args.sheet_id:
        text = set_env_value(text, SHEET_NAME, clean_sheet_id(args.sheet_id))

    with open(args.env_file, "w", encoding="utf-8", newline="") as handle:
        handle.write(text.replace("\n", newline))

    # Prove what we wrote decodes back to the same key.
    assert json.loads(base64.b64decode(encoded)) == info

    print(f"Saved {KEY_NAME} to {args.env_file} ({len(encoded)} characters).")
    if args.sheet_id:
        print(f"Saved {SHEET_NAME}.")
    print(f"Service account email: {info['client_email']}")
    print("Share your Google Sheet (as Editor) with that email, then run:")
    print("    python check_sheets.py")
    print()
    print("You can now delete the downloaded .json file (keep it only in a "
          "password manager).")
    if os.path.exists(args.env_file + ".bak"):
        print(f"A backup of your old settings is in {args.env_file}.bak "
              "(also private; delete it once everything works).")


if __name__ == "__main__":
    main()
