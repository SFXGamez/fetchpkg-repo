
#!/usr/bin/env python3

import sys
import json
import hashlib
import shutil
import tarfile
import re
import os
from pathlib import Path

REPO = Path(__file__).resolve().parent
PACKAGES = REPO / "packages"
DATABASE = REPO / "database.json"


def fail(message):
    print(f"FR: ERROR: {message}")
    sys.exit(1)


def get_metadata(package):
    try:
        with tarfile.open(package, "r:*") as archive:
            try:
                member = archive.getmember(".PKGINFO")
            except KeyError:
                fail("Package has no .PKGINFO metadata.")

            file = archive.extractfile(member)
            if file is None:
                fail("Could not read .PKGINFO.")

            content = file.read().decode("utf-8")

    except (tarfile.TarError, OSError, UnicodeDecodeError) as error:
        fail(f"Could not inspect package: {error}")

    metadata = {}

    for line in content.splitlines():
        if " = " not in line:
            continue

        key, value = line.split(" = ", 1)

        if key == "depend":
            metadata.setdefault("dependencies", []).append(value)
        elif key == "provides":
            metadata.setdefault("provides", []).append(value)
        else:
            metadata[key] = value

    required = ("pkgname", "pkgver")

    for key in required:
        if not metadata.get(key):
            fail(f"Missing {key} in .PKGINFO.")

    if not re.fullmatch(r"[A-Za-z0-9@._+-]+", metadata["pkgname"]):
        fail("Invalid package name.")

    return {
        "name": metadata["pkgname"],
        "version": metadata["pkgver"],
        "dependencies": metadata.get("dependencies", []),
        "provides": metadata.get("provides", [])
    }


def sha256_file(path):
    digest = hashlib.sha256()

    with open(path, "rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)

    return digest.hexdigest()


def main():
    if len(sys.argv) != 2:
        fail("Usage: python fr_add.py <package-file>")

    source = Path(sys.argv[1]).resolve()

    if not source.is_file():
        fail(f"Package not found: {source}")

    if not source.name.endswith(".tar.zst"):
        fail("Only .tar.zst packages are accepted.")

    PACKAGES.mkdir(exist_ok=True)

    try:
        with open(DATABASE, "r", encoding="utf-8") as file:
            database = json.load(file)
    except (OSError, json.JSONDecodeError) as error:
        fail(f"Could not read database.json: {error}")

    if not isinstance(database.get("packages"), dict):
        fail("Invalid database.json format.")

    print("FR: Inspecting package...")
    metadata = get_metadata(source)

    name = metadata["name"]

    if name in database["packages"]:
        fail(f"{name} already exists in the repository.")

    destination = PACKAGES / source.name

    if destination.exists():
        fail(f"File already exists: {destination.name}")

    print(f"FR: Package: {name}")
    print(f"FR: Version: {metadata['version']}")
    print("FR: Calculating SHA256...")

    digest = sha256_file(source)

    print("FR: Copying package...")
    shutil.copy2(source, destination)

    database["packages"][name] = {
        "version": metadata["version"],
        "file": f"packages/{source.name}",
        "dependencies": metadata["dependencies"],
        "provides": metadata["provides"],
        "sha256": digest
    }

    temporary = DATABASE.with_suffix(".json.tmp")

    try:
        with open(temporary, "w", encoding="utf-8") as file:
            json.dump(database, file, indent=4)
            file.write("\n")

        os.replace(temporary, DATABASE)

    except OSError as error:
        destination.unlink(missing_ok=True)
        temporary.unlink(missing_ok=True)
        fail(f"Could not update database: {error}")

    print(f"FR: Successfully added {name}!")
    print(f"FR: SHA256: {digest}")
    print("FR: Repository database updated.")


if __name__ == "__main__":
    main()
