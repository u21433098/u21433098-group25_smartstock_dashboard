"""Database backups for SmartStock: `flask backup` and `flask restore`.

One implementation for Windows and Linux (no PowerShell or shell scripts), so it works
the same on the café PC, on a Linux server, and in Task Scheduler or a systemd timer.

    flask backup                 save backups/smartstock_YYYY-MM-DD_HHMMSS.sql.gz,
                                 then delete backups older than 30 days
    flask restore FILE           replace ALL data with FILE (asks first; --yes skips the question)

How it works
- The database login comes from DATABASE_URL (the .env file), so nothing is typed or
  stored in a script. The password is handed to mysqldump/mysql in a temporary
  settings file that only this user can read and that is deleted straight after,
  so it never appears on the command line or in the list of running programs.
- It uses MySQL's own tools, mysqldump (backup) and mysql (restore). They come with
  MySQL Server, MariaDB and XAMPP and are found automatically; otherwise set MYSQL_BIN
  in .env to the folder that contains them.
- Backups are gzip-compressed (about 10 times smaller) and written to a ".part" file
  first, so a failed backup never leaves a broken file that looks complete.
"""
import glob
import gzip
import os
import shutil
import subprocess
import tempfile
import time
from datetime import datetime

from sqlalchemy.engine import make_url

KEEP_DAYS = 30
PREFIX = "smartstock_"
CHUNK = 64 * 1024
WINDOWS_FOLDERS = (r"C:\Program Files\MySQL\*\bin", r"C:\Program Files\MariaDB*\bin", r"C:\xampp\mysql\bin")


class BackupError(Exception):
    """Something the person running the command can fix; the message says what."""


def find_tool(name, mysql_bin=None):
    """Full path of mysqldump or mysql (name without .exe)."""
    exe = name + (".exe" if os.name == "nt" else "")
    if mysql_bin:
        path = os.path.join(mysql_bin, exe)
        if os.path.isfile(path):
            return path
        raise BackupError(f"{exe} is not in MYSQL_BIN ({mysql_bin}). Check that folder in .env.")
    found = shutil.which(name)
    if found:
        return found
    if os.name == "nt":
        for pattern in WINDOWS_FOLDERS:
            for folder in sorted(glob.glob(pattern), reverse=True):      # newest version first
                path = os.path.join(folder, exe)
                if os.path.isfile(path):
                    return path
    raise BackupError(f"{exe} was not found. Set MYSQL_BIN in .env to the folder that contains it, "
                      r"for example C:\Program Files\MySQL\MySQL Server 8.0\bin")


class _Login:
    """The MySQL login as a temporary option file (deleted when the `with` block ends)."""

    def __init__(self, database_url):
        url = make_url(database_url)
        if not url.drivername.startswith("mysql"):
            raise BackupError("Backups need a MySQL database: DATABASE_URL must start with mysql+pymysql://")
        self.database = url.database
        # In an option file, a quoted value treats \ and " specially, so escape them.
        password = (url.password or "").replace("\\", "\\\\").replace('"', '\\"')
        self._settings = ("[client]\n"
                          f"user={url.username}\n"
                          f'password="{password}"\n'
                          f"host={url.host or 'localhost'}\n"
                          f"port={url.port or 3306}\n"
                          "default-character-set=utf8mb4\n")

    def __enter__(self):
        handle, self.path = tempfile.mkstemp(prefix="smartstock_", suffix=".cnf")
        with os.fdopen(handle, "w", encoding="utf-8") as f:        # mkstemp: readable by this user only
            f.write(self._settings)
        return f"--defaults-extra-file={self.path}"                  # must be the first option

    def __exit__(self, *_):
        os.remove(self.path)


def _run(command, stdin=None, stdout=None):
    """Run a MySQL tool, streaming data in or out, and raise BackupError with its message if it fails."""
    with tempfile.TemporaryFile() as errors:
        process = subprocess.Popen(command, stdin=subprocess.PIPE if stdin else None,
                                   stdout=subprocess.PIPE if stdout else None, stderr=errors)
        if stdout:
            for chunk in iter(lambda: process.stdout.read(CHUNK), b""):
                stdout.write(chunk)
        if stdin:
            try:
                for chunk in iter(lambda: stdin.read(CHUNK), b""):
                    process.stdin.write(chunk)
            except BrokenPipeError:
                pass                                                 # the tool stopped early: its message explains why
            process.stdin.close()
        process.wait()
        if process.returncode != 0:
            errors.seek(0)
            message = errors.read().decode("utf-8", errors="replace").strip()
            raise BackupError(f"{os.path.basename(command[0])} failed: {message or 'exit code ' + str(process.returncode)}")


def prune(folder, keep_days=KEEP_DAYS, now=None):
    """Delete SmartStock backups older than keep_days. Returns how many were deleted."""
    cutoff = (now or time.time()) - keep_days * 86400
    removed = 0
    for path in glob.glob(os.path.join(folder, PREFIX + "*.sql*")):
        if not path.endswith(".part") and os.path.getmtime(path) < cutoff:
            os.remove(path)
            removed += 1
    return removed


def backup(database_url, folder, mysql_bin=None, keep_days=KEEP_DAYS):
    """Save a compressed backup. Returns (path of the new file, number of old backups deleted)."""
    dump = find_tool("mysqldump", mysql_bin)
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, f"{PREFIX}{datetime.now():%Y-%m-%d_%H%M%S}.sql.gz")
    partial = path + ".part"
    login = _Login(database_url)
    try:
        with login as option, gzip.open(partial, "wb") as out:
            # --single-transaction: a consistent copy without stopping the app.
            # --no-tablespaces: lets a normal (non-root) MySQL user make the backup.
            _run([dump, option, "--single-transaction", "--no-tablespaces", "--routines", login.database],
                 stdout=out)
        os.replace(partial, path)
    finally:
        if os.path.exists(partial):
            os.remove(partial)
    return path, prune(folder, keep_days)


def restore(database_url, backup_file, mysql_bin=None):
    """Replace all data in the database with a backup (.sql.gz or .sql)."""
    client = find_tool("mysql", mysql_bin)
    opener = gzip.open if backup_file.endswith(".gz") else open
    login = _Login(database_url)
    with login as option, opener(backup_file, "rb") as source:
        _run([client, option, login.database], stdin=source)
