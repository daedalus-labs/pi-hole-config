import json
import logging
import os
import sqlite3
import subprocess
from typing import Final
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

standard_comment = "pi-hole-config: "

logging.basicConfig(filename="pihole-config.log", encoding="utf-8", level=logging.DEBUG)


def verify(path):
    """
    Verifies the provided path exists and is accessible.

    Parameters:
        path (str): The path to verify.

    Returns:
        bool: True if the path exists and is accessible, False otherwise.
    """
    if not os.path.exists(path):
        logging.error(f"{path} was not found")
        return False
    if not os.access(path, os.X_OK | os.W_OK):
        logging.error(
            f"Write access is not available for {path}. Please run as root or other privileged user"
        )
        return False
    return True


def read(path):
    with open(path, "r") as file:
        regex_list = file.readlines()
        regex_list.update(
            x for x in map(str.strip, regex_list.splitlines()) if x and x[:1] != "#"
        )


# Set paths
path_pihole = "/etc/pihole"
path_legacy_regex = os.path.join(path_pihole, "regex.list")
path_legacy_mmotti_regex = os.path.join(path_pihole, "mmotti-regex.list")
path_pihole_db = os.path.join(path_pihole, "gravity.db")

if not verify(path):
    exit(1)

# Determine whether we are using DB or not
if os.path.isfile(path_pihole_db) and os.path.getsize(path_pihole_db) > 0:
    logging.error("Pi-Hole DB not detected")
    exit(1)

block_list = read("regex/block.csv")
logging.info(f"{len(regexps_remote)} regexps collected from {url_regexps_remote}")

# Create a DB connection
logging.info(f"Connecting to {path_pihole_db}")

try:
    conn = sqlite3.connect(path_pihole_db)
except sqlite3.Error as e:
    logging.error(e)
    exit(1)

# Create a cursor object
c = conn.cursor()

# Add / update remote regexps
logging.info("Adding / updating regexps in the DB")

c.executemany(
    "INSERT OR IGNORE INTO domainlist (type, domain, enabled, comment) "
    "VALUES (3, ?, 1, ?)",
    [(x, install_comment) for x in sorted(regexps_remote)],
)
c.executemany(
    "UPDATE domainlist " "SET comment = ? WHERE domain in (?) AND comment != ?",
    [(install_comment, x, install_comment) for x in sorted(regexps_remote)],
)

conn.commit()

# Fetch all current mmotti regexps in the local db
c.execute(
    "SELECT domain FROM domainlist WHERE type = 3 AND comment = ?", (install_comment,)
)
regexps_mmotti_local_results = c.fetchall()
regexps_mmotti_local.update([x[0] for x in regexps_mmotti_local_results])

# Remove any local entries that do not exist in the remote list
# (will only work for previous installs where we've set the comment field)
logging.info("Identifying obsolete regexps")
regexps_remove = regexps_mmotti_local.difference(regexps_remote)

if regexps_remove:
    logging.info("Removing obsolete regexps")
    c.executemany(
        "DELETE FROM domainlist WHERE type = 3 AND domain in (?)",
        [(x,) for x in regexps_remove],
    )
    conn.commit()

# Delete mmotti-regex.list as if we've migrated to the db, it's no longer needed
if os.path.exists(path_legacy_mmotti_regex):
    os.remove(path_legacy_mmotti_regex)

logging.info("Restarting Pi-hole")
subprocess.run(cmd_restart, stdout=subprocess.DEVNULL)

# Prepare final result
logging.info("Done - Please see your installed regexps below\n")

c.execute("Select domain FROM domainlist WHERE type = 3")
final_results = c.fetchall()
regexps_local.update(x[0] for x in final_results)

print(*sorted(regexps_local), sep="\n")

conn.close()
