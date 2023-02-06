import logging
import os
import sqlite3
import subprocess

STANDARD_COMMENT = "(pi-hole-config) {}"
REGEX_INDEX = 0
COMMENT_INDEX = 1
GROUPS_INDEX = 2

logging.basicConfig(filename="pihole-config.log", encoding="utf-8", level=logging.DEBUG)


def verify(path):
    """
    Verifies the provided path exists and is accessible.

    Args:
        path (str): The path to verify.

    Returns:
        bool: True if the path exists and is accessible, False otherwise.
    """
    if not os.path.exists(path):
        logging.error("{} was not found".format(path))
        return False
    if not os.access(path, os.X_OK | os.W_OK):
        logging.error("Write access is not available for {}. Please run as root or other privileged user".format(path))
        return False
    return True


def read(path):
    """
    Reads in the configuration data from a path.

    Args:
        path (str): The path to the `csv` to be read in.

    Returns:
        list: A list of all lines from the `csv`.
    """
    regex_list = list()
    with open(path, "r") as file:
        regex_list = file.readlines()
        regex_list.update(x for x in map(str.strip, regex_list.splitlines()) if x and x[:1] != "#")
    return regex_list


def parse(config_list):
    """
    Converts a list of regular expressions read in from a csv into a list of tuples
    of the form: [<regular expression>, <comment>, <associated groups>]

    Args:
        config_list (list): The list of regular expressions read in from the csv

    Returns:
        list: A list of tuples containing the parsed values from config_list
    """
    parsed_list = list()
    for config_item in config_list:
        config_items = config_item.split(",")
        if (len(config_items)) < 3:
            continue
        parsed_list.append(tuple(config_items[REGEX_INDEX], config_items[COMMENT_INDEX], config_items[GROUPS_INDEX]))
    return parsed_list


def add(cursor, parsed_object):
    logging.info("Adding / updating {} to DB".format(parsed_object))
    comment = STANDARD_COMMENT.format(parsed_object[COMMENT_INDEX])
    cursor.execute(
        "INSERT OR IGNORE INTO domainlist (type, domain, enabled, comment)",
        "VALUES (3, ?, 1, ?)",
        parsed_object[REGEX_INDEX],
        comment,
    )
    cursor.execute(
        "UPDATE domainlist " "SET comment = ? WHERE domain in (?) AND comment != ?",
        comment,
        parsed_object[REGEX_INDEX],
        comment,
    )


def connect():
    # Add / update remote regexps
    logging.info("Adding / updating regexps in the DB")

    c.executemany(
        "INSERT OR IGNORE INTO domainlist (type, domain, enabled, comment) " "VALUES (3, ?, 1, ?)",
        [(x, install_comment) for x in sorted(block_list)],
    )
    c.executemany(
        "UPDATE domainlist " "SET comment = ? WHERE domain in (?) AND comment != ?",
        [(install_comment, x, install_comment) for x in sorted(block_list)],
    )

    # Fetch all current mmotti regexps in the local db
    c.execute("SELECT domain FROM domainlist WHERE type = 3")
    regexps_mmotti_local_results = c.fetchall()
    regexps_mmotti_local.update([x[0] for x in regexps_mmotti_local_results])

    # Remove any local entries that do not exist in the remote list
    # (will only work for previous installs where we've set the comment field)
    logging.info("Identifying obsolete regexps")
    regexps_remove = regexps_mmotti_local.difference(block_list)

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


if __name__ == "__main__":
    # Set paths
    path_pihole = "/etc/pihole"
    path_pihole_db = os.path.join(path_pihole, "gravity.db")

    if not verify(path_pihole):
        exit(1)

    # Determine whether we are using DB or not
    if os.path.isfile(path_pihole_db) and os.path.getsize(path_pihole_db) > 0:
        logging.error("Pi-Hole DB not detected")
        exit(1)

    block_list = read("regex/block.csv")
    parsed_list = parse(block_list)

    print(parsed_list)

    # # Create a DB connection
    # logging.info("Connecting to {}".format(path_pihole_db))

    # try:
    #     conn = sqlite3.connect(path_pihole_db)
    # except sqlite3.Error as e:
    #     logging.error(e)
    #     exit(1)

    # # Create a cursor object
    # cursor = conn.cursor()

    # for parsed_object in parsed_list:
    #     add(cursor, parsed_object)

    # conn.commit()

    # conn.close()
