import os
import re
import zipfile
import shutil

# Default regex for the naming convention: 7 digits followed by .txt
PATTERN = re.compile(r"^(\d{7})\.txt")


def rename_zips_in_folder(folder_path, folder_name):
    """
    Checks if folder_name matches pattern and renames zips inside.
    Returns True if at least one file was renamed.
    """
    match = PATTERN.match(folder_name)
    if not match:
        return False

    digit_number = match.group(1)
    renamed_any = False

    try:
        for file in os.listdir(folder_path):
            if file.endswith(".zip"):
                old_path = os.path.join(folder_path, file)
                new_name = f"{digit_number}-{file}"
                new_path = os.path.join(folder_path, new_name)

                os.rename(old_path, new_path)
                print(f"[SUCCESS] Renamed: {file} -> {new_name}")
                renamed_any = True
    except OSError as e:
        print(f"[ERROR] Permission error in {folder_path}: {e}")

    return renamed_any


def should_extract_zip(zip_path):
    """
    Inspects every file and folder inside the zip.
    Returns True if it finds a target folder or another zip.
    """
    try:
        with zipfile.ZipFile(zip_path, "r") as z:
            for info in z.infolist():
                parts = info.filename.split("/")
                for part in parts:
                    if part and PATTERN.match(part):
                        return True
                if info.filename.endswith(".zip"):
                    return True
    except zipfile.BadZipFile:
        print(f"[ERROR] {zip_path} is a corrupt zip file.")
    return False


def repack_and_cleanup(original_zip_path, extract_dir):
    """
    Packs the extracted folder back into a zip (original zip folder is overwritten) and deletes the extracted folder.
    """
    try:
        base_name = original_zip_path.replace(".zip", "")

        shutil.make_archive(base_name, "zip", extract_dir)
        print(f"[REPACK] Repacked {original_zip_path}")

        shutil.rmtree(extract_dir)
        print(f"[CLEANUP] Removed temporary folder {extract_dir}")
    except Exception as e:
        print(f"[ERROR] Failed to repack {original_zip_path}: {e}")


def walk_recursive(current_path):
    """
    Walks the filesystem and handles ZIPs recursively.
    Returns True if any renaming happened in this branch.
    """
    current_path = os.path.abspath(current_path)
    folder_name = os.path.basename(current_path)

    # 1. Check if this folder itself is a target for renaming
    if rename_zips_in_folder(current_path, folder_name):
        return True

    # 2. Dive deeper into the current directory
    branch_changed = False
    try:
        items = os.listdir(current_path)
    except OSError:
        return False

    for item in items:
        item_path = os.path.join(current_path, item)

        if os.path.isdir(item_path):
            # Avoid recursing into the extracted folders
            if item.endswith("_extracted"):
                continue
            if walk_recursive(item_path):
                branch_changed = True

        elif item.endswith(".zip"):
            if should_extract_zip(item_path):
                extract_dir = item_path.replace(".zip", "_extracted")
                print(f"[EXTRACT] Diving into ZIP: {item} -> {extract_dir}")

                try:
                    with zipfile.ZipFile(item_path, "r") as z_ext:
                        z_ext.extractall(extract_dir)

                    if walk_recursive(extract_dir):
                        branch_changed = True
                    repack_and_cleanup(item_path, extract_dir)

                except Exception as e:
                    print(f"[ERROR] Failed to process ZIP {item}: {e}")

    if not branch_changed:
        print(f"[WARNING] No renaming occurred in branch: {current_path}")

    return branch_changed


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python zip-renaming.py <starting_path> [optional_pattern]")
        sys.exit(1)

    start_path = os.path.abspath(sys.argv[1])

    if len(sys.argv) == 3:
        PATTERN = re.compile(sys.argv[2])

    if not os.path.exists(start_path):
        print(f"Error: Path {start_path} does not exist.")
        sys.exit(1)

    print(f"Starting walk from: {start_path}\n" + "-" * 50)
    walk_recursive(start_path)
    print("-" * 50 + "\nProcess Complete.")
