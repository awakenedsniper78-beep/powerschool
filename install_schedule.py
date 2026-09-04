"""
Run the grade sync every six hours on this computer.

    python install_schedule.py            # set it up
    python install_schedule.py --remove   # undo it
    python install_schedule.py --dry-run  # show what would happen, change nothing

Why here rather than on GitHub: the school portal's bot protection blocks GitHub's
datacenter IPs, so the scheduled workflow gets a challenge page instead of a login. Your
home connection is an ordinary residential IP and isn't treated that way -- the same
sync that fails on a runner works from here.

The job only runs while the computer is awake. A laptop that's shut overnight simply
catches up at the next slot after you open it.
"""

import argparse
import os
import platform
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SYNC = os.path.join(HERE, "sync.py")
LOG = os.path.join(HERE, "sync.log")
TASK_NAME = "CurveGradeSync"
MARKER = "# curve-grade-sync"


def cron_line():
    """Every six hours, on the hour, logging to sync.log so failures aren't invisible."""
    return (f'0 */6 * * * cd "{HERE}" && "{sys.executable}" "{SYNC}" '
            f'>> "{LOG}" 2>&1  {MARKER}')


def _run_crontab(args, **kw):
    try:
        return subprocess.run(["crontab", *args], capture_output=True, text=True, **kw)
    except FileNotFoundError:
        sys.exit("This system has no `crontab` command, so there's nothing to schedule "
                 "with.\nRun `python sync.py` by hand, or schedule it with whatever "
                 "your system uses.")


def read_crontab():
    done = _run_crontab(["-l"])
    # An empty crontab exits non-zero with "no crontab for <user>"; that's not an error.
    return done.stdout if done.returncode == 0 else ""


def write_crontab(text):
    done = _run_crontab(["-"], input=text)
    if done.returncode:
        sys.exit(f"Couldn't write the crontab:\n{done.stderr.strip()}")


def install_cron(dry_run):
    existing = [l for l in read_crontab().splitlines() if MARKER not in l]
    updated = "\n".join(existing + [cron_line()]).strip() + "\n"
    print("Adding this crontab entry:\n\n  " + cron_line() + "\n")
    if dry_run:
        return print("(dry run -- nothing changed)")
    write_crontab(updated)
    print("Installed. It runs at 00:00, 06:00, 12:00 and 18:00 local time.")


def remove_cron(dry_run):
    lines = read_crontab().splitlines()
    kept = [l for l in lines if MARKER not in l]
    if len(kept) == len(lines):
        return print("No sync job was installed -- nothing to remove.")
    if dry_run:
        return print("(dry run -- would remove the sync entry)")
    write_crontab("\n".join(kept).strip() + "\n" if kept else "\n")
    print("Removed.")


def windows(dry_run, remove):
    if remove:
        cmd = ["schtasks", "/Delete", "/TN", TASK_NAME, "/F"]
    else:
        cmd = ["schtasks", "/Create", "/TN", TASK_NAME, "/SC", "HOURLY", "/MO", "6",
               "/TR", f'cmd /c cd /d "{HERE}" && "{sys.executable}" "{SYNC}" >> "{LOG}" 2>&1',
               "/F"]
    print("Running:\n\n  " + " ".join(cmd) + "\n")
    if dry_run:
        return print("(dry run -- nothing changed)")
    done = subprocess.run(cmd, capture_output=True, text=True)
    if done.returncode:
        sys.exit(f"schtasks failed:\n{done.stdout}{done.stderr}")
    print("Done." if remove else "Installed. It runs every six hours.")


def check_ready():
    """Fail early on the two things that would make every scheduled run useless."""
    if not os.path.exists(SYNC):
        sys.exit(f"Can't find {SYNC}.")
    env = os.path.join(HERE, ".env")
    if not os.path.exists(env):
        sys.exit("No .env file here. Copy .env.example to .env and fill it in first --\n"
                 "a scheduled run has no keyboard, so it can't ask you for anything.")
    text = open(env, encoding="utf-8").read()
    missing = [k for k in ("PS_USERNAME", "PS_PASSWORD", "DASH_USERNAME", "DASH_PASSWORD")
               if not any(l.startswith(f"{k}=") and l.split("=", 1)[1].strip()
                          for l in text.splitlines())]
    if missing:
        sys.exit(f"These are empty in .env: {', '.join(missing)}\n"
                 "Fill them in, or every scheduled run will fail.")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--remove", action="store_true", help="uninstall the scheduled job")
    ap.add_argument("--dry-run", action="store_true", help="show the change, don't make it")
    args = ap.parse_args()

    if not args.remove:
        check_ready()

    if platform.system() == "Windows":
        return windows(args.dry_run, args.remove)
    if args.remove:
        return remove_cron(args.dry_run)
    install_cron(args.dry_run)
    print(f"\nOutput goes to {os.path.relpath(LOG, HERE)}. Run it once now to check:\n"
          f"  python sync.py")


if __name__ == "__main__":
    main()
