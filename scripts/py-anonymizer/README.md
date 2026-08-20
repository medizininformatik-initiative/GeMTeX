# py-anonymizer-gemtex

**Processes Semann annotation .zip files and anonymizes user identifiers based on a CSV mapping.**

The tool extracts batch .zip files, finds document folders, processes annotation archives, updates document IDs in XMI files, and re-packages everything as `{batch_name}_processed.zip` files.

## Requirements

- Python 3.7+
- No external dependencies

## Quick Start

### 1. Prepare Your Files

Create a CSV mapping file with two columns:

```csv
ZipFileName,UserId
Annotation_001,user1
Annotation_002,user2
```

Column names can be: `ZipFileName`/`FileName`/`Name` and `UserId`/`User`

### 2. Run the Tool

**Windows**:
!!! Please have PYTHON in your PATH! (recommended to use the direct method with calling python3)

```bash
cd C:\gemtex\py-anonymizer-semann-gemtex
run.bat
```

**Linux/macOS**:
```bash
cd /path/to/py-anonymizer-semann-gemtex
./run.sh
```

Or directly:
```bash
python3 main.py
```

### 3. Provide Paths

```
Input folder (containing .zip files): /path/to/input
CSV mapping file (user mappings): /path/to/user_mappings.csv
Output folder (will be created if needed): /path/to/output
```

### 4. Confirm and Wait

```
Start processing? (y/n): y
```

Processing completes and files are cleaned up automatically.

## Input/Output Structure

**Input** folder contains batch .zip files:
```
input/
├── batch_001.zip
│   └── annotation/
│       ├── document_A/
│       │   ├── Annotation_001.zip
│       │   ├── Annotation_002.zip
│       │   └── INITIAL_CAS.zip
│       └── document_B/
│           └── Annotation_003.zip
└── batch_002.zip
```

**Output** folder contains processed archives:
```
output/
├── batch_001_processed.zip
│   ├── document_A/
│   │   ├── user1.zip
│   │   └── user2.zip
│   └── document_B/
│       └── user3.zip
└── batch_002_processed.zip
    └── ...
```

## Processing Flow

1. Extract each batch .zip file
2. Find `annotation/` folder and document folders inside
3. For each document folder:
   - Extract base name from document title in XMI
   - For each annotation .zip:
     - Look up annotation name in CSV mapping
     - **Error if not found** (shows available options)
     - Update document ID in XMI file
     - Rename XMI file to match mapped user ID
     - Create anonymized .zip
4. Re-package all processed documents as `{batch_name}_processed.zip`
5. Clean up all temporary files

## Error Handling

**Missing user in CSV**:
```
User mapping error: User 'Annotation_004' found in annotation but not in CSV mapping. 
Available mappings: ['Annotation_001', 'Annotation_002', 'Annotation_003']
```

Fix: Add the missing annotation to your CSV and run again.

**Missing input directory or CSV file**:
```
Input path does not exist or is not a directory: C:\path\to\input
```

Fix: Verify paths exist.

## Paths

Works with Windows, Linux, and macOS paths:

```
Windows:     C:\Users\data\input
Linux:       /home/user/data/input
macOS:       /Users/username/data/input
```

## Example

```bash
# Input
C:\data\input\
├── my_data.zip

# CSV: C:\data\mappings.csv
ZipFileName,UserId
Doctor_Smith,reviewer_A

# Command
python3 main.py

# Output
C:\data\output\
└── my_data_processed.zip
    └── document_name/
        └── reviewer_A.zip
```

## Exit Codes

- `0` - Success
- `1` - Error (check message for details)
- `130` - Interrupted by user

## API Usage

```python
from main import SemannAnonymizer

anonymizer = SemannAnonymizer(
    input_path="/path/to/input",
    csv_path="/path/to/mappings.csv",
    output_path="/path/to/output"
)

success = anonymizer.process()
```

## Notes

- Temporary files are automatically cleaned up after processing
- INITIAL_CAS.zip files are excluded from processing
- Input .zip file names can be anything - output uses the same name with `_processed` suffix
- All processes handle errors gracefully with cleanup
