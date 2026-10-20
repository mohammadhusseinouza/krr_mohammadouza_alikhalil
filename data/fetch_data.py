"""Fetch the source data into data/halifax/ and data/linked-gtfs/.

Run from the repository root:  python data/fetch_data.py
(pipeline/run.py runs it first, so a clean checkout fetches its own data)

No account or API token needed. The source is public:

- Halifax Transit GTFS Schedule feed (Halifax Regional Municipality, Nova
  Scotia), Open Government Licence - Halifax. One zip holding nine related
  GTFS tables (agency, routes, trips, stops, stop_times, calendar,
  calendar_dates, shapes, feed_info). This script also extracts every table
  as its own .txt file (GTFS tables are CSV with a .txt extension), so every
  later lab can read plain CSV files.
- Linked GTFS (Pieter Colpaert and Andrew Byrd, Open Transport), CC BY 3.0.
  The RDF vocabulary for GTFS, http://vocab.gtfs.org/terms#, that the
  ontology reuses (ontology/ holds the corrected copy, Session 3). Pinned to the repository's last commit
  (fc12d51, 2016-01-19), so it never changes under a checksum.

A transit agency republishes its feed every few months and its own URL always
serves the newest one, so it has no fixed checksum. This script instead
downloads one dated snapshot from the Mobility Database archive (feed
mdb-734, captured 2026-08-24 01:20 UTC, feed_version
2026_08_August_20260806). That file never changes, so it is checked against
the SHA-256 recorded below, and a truncated or substituted file fails loudly
instead of silently. Files already present with the right checksum are not
downloaded again.
"""

import hashlib
import sys
import urllib.request
import zipfile
from pathlib import Path

# Some hosts refuse Python's default User-Agent; present a browser one instead.
_opener = urllib.request.build_opener()
_opener.addheaders = [("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0 Safari/537.36")]
urllib.request.install_opener(_opener)

DATA_DIR = Path(__file__).resolve().parent
HALIFAX_DIR = DATA_DIR / "halifax"
GTFS_DIR = HALIFAX_DIR / "gtfs"
LINKED_GTFS_DIR = DATA_DIR / "linked-gtfs"

SNAPSHOT = "mdb-734-202608240120"
LINKED_GTFS_COMMIT = "fc12d51feed4a29cb83384b360de5df8c5c5a7db"

FILES = [
    # (target path, url, algorithm, expected hash)
    (
        HALIFAX_DIR / f"{SNAPSHOT}.zip",
        f"https://files.mobilitydatabase.org/mdb-734/{SNAPSHOT}/{SNAPSHOT}.zip",
        "sha256",
        "f5d95091c8134716834734e2695b16689fd19c2302932e147c7075c6a9f6bb76",
    ),
    (
        LINKED_GTFS_DIR / "gtfs.ttl",
        f"https://raw.githubusercontent.com/OpenTransport/linked-gtfs/{LINKED_GTFS_COMMIT}/gtfs.ttl",
        "sha256",
        "f58ba3d35c9d380461ae59cdf83c5bf66c193980023c72496a5e3d30cbae4325",
    ),
]

# The nine tables this snapshot contains, per data/README.md.
EXPECTED_TABLES = [
    "agency.txt",
    "calendar.txt",
    "calendar_dates.txt",
    "feed_info.txt",
    "routes.txt",
    "shapes.txt",
    "stop_times.txt",
    "stops.txt",
    "trips.txt",
]


def file_hash(path: Path, algorithm: str) -> str:
    h = hashlib.new(algorithm)
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def fetch(path: Path, url: str, algorithm: str, expected: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and file_hash(path, algorithm) == expected:
        print(f"ok, already present: {path.name}")
        return
    print(f"downloading {path.name} ...")
    tmp = path.with_suffix(path.suffix + ".part")
    urllib.request.urlretrieve(url, tmp)
    got = file_hash(tmp, algorithm)
    if got != expected:
        tmp.unlink()
        sys.exit(f"checksum mismatch for {path.name}: expected {expected}, got {got}")
    tmp.replace(path)
    print(f"ok, {path.name} ({path.stat().st_size:,} bytes, {algorithm} verified)")


def extract_gtfs_tables() -> None:
    """Write each GTFS table in the zip to data/halifax/gtfs/."""
    GTFS_DIR.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(HALIFAX_DIR / f"{SNAPSHOT}.zip") as z:
        names = sorted(n for n in z.namelist() if n.endswith(".txt"))
        missing = set(EXPECTED_TABLES) - set(names)
        if missing:
            sys.exit(f"snapshot is missing tables: {sorted(missing)}")
        for name in names:
            out = GTFS_DIR / Path(name).name
            out.write_bytes(z.read(name))
            with out.open(encoding="utf-8-sig") as f:
                rows = sum(1 for line in f if line.strip()) - 1
            print(f"ok, {out.name}: {rows:,} rows")


if __name__ == "__main__":
    for spec in FILES:
        fetch(*spec)
    extract_gtfs_tables()
    print("\nDone. See data/README.md for what each file contains.")
