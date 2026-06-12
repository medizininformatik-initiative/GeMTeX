# Recursive ZIP Renaming & Repacking Tool

This Python script is designed to traverse a directory tree and rename ZIP files to contain the documentID of the document it is based on.

## Overview

The script searches for folders matching a specific naming convention (by default, any folder starting with a **7-digit number followed by `.txt`**). When such a folder is found, the script prefixes any ZIP files inside that folder with the extracted 7-digit ID.

If the script encounters a ZIP file, it inspects the contents. If that ZIP contains either a target folder or another nested ZIP, the script extracts it, processes the interior recursively, repacks it, and deletes the temporary extraction folder.


## Requirements

- **Python 3.x**
- No external libraries are required. The script uses only standard Python modules: `os`, `re`, `zipfile`, and `shutil`.

## Usage

### Basic Command
Run the script by providing the path to the directory you wish to process:
```bash
python zip-renaming.py /path/to/your/folder
```

### Custom Pattern Command
If your folders do not follow the 7-digit `.txt` convention, you can provide a custom Regex pattern as the second argument:
```bash
python zip-renaming.py /path/to/your/folder "^ID_\d{5}"
```

## Important Warning: Data Backup

**This script modifies and overwrites your original ZIP files.** While it is designed to be safe and only changes names of files, not their content, it is highly recommended that you create a backup of your data before running the script on important archives.


## Example Scenario

**Before:**
```text
Root/
└── annotated_semantic/
    └── basic/
        └── curated-docs.zip/
            └── curation/
                └── 9999999.txt_deid-111111.txt.xmi
                    └── inception-document.zip
```

**After:**
```text
Root/
└── annotated_semantic/
    └── basic/
        └── curated-docs.zip/
            └── curation/
                └── 9999999.txt_deid-111111.txt.xmi
                    └── 9999999-inception-document.zip
```
