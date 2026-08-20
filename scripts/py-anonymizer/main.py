#!/usr/bin/env python3

import os
import sys
import shutil
import zipfile
import re
import tempfile
import csv
from pathlib import Path
from typing import Dict, Optional, Tuple


class AnonymizerError(Exception):
    """Base exception for anonymization errors."""
    pass


class UserMappingError(AnonymizerError):
    """Exception raised when a user is not found in the mapping."""
    pass


class SemannAnonymizer:
    def __init__(self, input_path: str, csv_path: str, output_path: str):
        """Initialize the anonymizer with paths."""
        self.input_path = Path(input_path)
        self.csv_path = Path(csv_path)
        self.output_path = Path(output_path)
        self.temp_dir = None
        self.user_mappings: Dict[str, str] = {}
        self.processed_files = []

        self._validate_paths()
        self._load_user_mappings()

    def _validate_paths(self):
        """Validate that input paths exist and output path is writable."""
        if not self.input_path.exists() or not self.input_path.is_dir():
            raise AnonymizerError(f"Input path does not exist or is not a directory: {self.input_path}")

        if not self.csv_path.exists() or not self.csv_path.is_file():
            raise AnonymizerError(f"CSV file does not exist: {self.csv_path}")

        try:
            self.output_path.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            raise AnonymizerError(f"Cannot create output directory: {self.output_path}. Error: {e}")

    def _load_user_mappings(self):
        """Load user mappings from CSV file."""
        try:
            with open(self.csv_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                if reader.fieldnames is None:
                    raise AnonymizerError("CSV file is empty")

                # Normalize header names
                headers = {h.lower() if h else None: h for h in reader.fieldnames}

                zip_name_col = None
                user_id_col = None

                for key, original in headers.items():
                    if key and ('zipfilename' in key or 'filename' in key or key == 'name'):
                        zip_name_col = original
                    if key and ('userid' in key or key == 'user'):
                        user_id_col = original

                if not zip_name_col or not user_id_col:
                    raise AnonymizerError(
                        f"CSV must have 'ZipFileName'/'FileName'/'Name' and 'UserId'/'User' columns. "
                        f"Found: {list(reader.fieldnames)}"
                    )

                # Reset file pointer to read data
                f.seek(0)
                reader = csv.DictReader(f)

                for row in reader:
                    if row[zip_name_col].strip() and row[user_id_col].strip():
                        self.user_mappings[row[zip_name_col].strip()] = row[user_id_col].strip()

                print(f"Loaded {len(self.user_mappings)} user mappings from CSV")

        except csv.Error as e:
            raise AnonymizerError(f"Error reading CSV file: {e}")
        except Exception as e:
            raise AnonymizerError(f"Failed to load user mappings: {e}")

    def _create_temp_dir(self):
        """Create a temporary directory for processing."""
        if self.temp_dir is None:
            self.temp_dir = tempfile.mkdtemp(prefix="semann-anonymizer-")
            print(f"Created temporary directory")

    def _cleanup_temp_dir(self):
        """Clean up temporary directory."""
        if self.temp_dir and os.path.exists(self.temp_dir):
            try:
                shutil.rmtree(self.temp_dir)
                print(f" Cleaned up temporary files")
            except Exception as e:
                print(f"Warning: Failed to cleanup temporary directory: {e}")

    def _find_xmi_file(self, folder: Path) -> Optional[Path]:
        """Find the first .xmi file in a folder recursively."""
        for root, dirs, files in os.walk(folder):
            for file in files:
                if file.lower().endswith('.xmi'):
                    return Path(root) / file
        return None

    def _update_document_id_in_xmi(self, xmi_file: Path, generic_name: str):
        """Update documentId attribute in XMI file."""
        content = xmi_file.read_text(encoding='utf-8')
        updated = re.sub(r'documentId="[^"]*"', f'documentId="{generic_name}"', content)
        xmi_file.write_text(updated, encoding='utf-8')

    def _rename_xmi_file(self, xmi_file: Path, generic_name: str) -> Path:
        """Rename XMI file to {generic_name}.xmi."""
        new_name = f"{generic_name}.xmi"
        new_path = xmi_file.parent / new_name
        xmi_file.rename(new_path)
        return new_path

    def _extract_zip(self, zip_path: Path, extract_to: Path) -> bool:
        """Extract a zip file to a directory."""
        try:
            with zipfile.ZipFile(zip_path, 'r') as zf:
                zf.extractall(extract_to)
            return True
        except Exception as e:
            print(f"Failed to extract {zip_path.name}: {e}")
            return False

    def _create_zip(self, folder: Path, output_path: Path) -> bool:
        """Create a zip file from a folder."""
        try:
            with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                for root, dirs, files in os.walk(folder):
                    for file in files:
                        file_path = Path(root) / file
                        arcname = file_path.relative_to(folder)
                        zf.write(file_path, arcname)
            return True
        except Exception as e:
            print(f"Failed to create zip {output_path.name}: {e}")
            return False

    def _process_batch_zip(self, batch_zip_path: Path) -> Tuple[int, int]:
        """Process a single batch .zip file and create prepared archive."""
        processed = 0
        skipped = 0

        batch_name = batch_zip_path.stem
        print(f"\nProcessing batch: {batch_zip_path.name}")

        batch_extract_dir = Path(self.temp_dir) / batch_name
        batch_extract_dir.mkdir(parents=True, exist_ok=True)

        # Temporary folder to collect this batch's output
        batch_output_temp = Path(self.temp_dir) / f"batch-output-{batch_name}"
        batch_output_temp.mkdir(parents=True, exist_ok=True)

        try:
            if not self._extract_zip(batch_zip_path, batch_extract_dir):
                raise AnonymizerError(f"Failed to extract batch zip")

            annotation_folder = batch_extract_dir / "annotation"
            if not annotation_folder.exists():
                print(f"No 'annotation' folder found in batch")
                return processed, skipped

            # Process each document folder
            document_folders = [d for d in annotation_folder.iterdir() if d.is_dir()]
            print(f"Found {len(document_folders)} document folders")

            for doc_folder in sorted(document_folders):
                try:
                    processed_doc, skipped_doc = self._process_document_folder(doc_folder, batch_output_temp)
                    processed += processed_doc
                    skipped += skipped_doc
                except UserMappingError as e:
                    raise  # Propagate user mapping errors
                except Exception as e:
                    print(f"Error processing {doc_folder.name}: {e}")
                    skipped += 1

            # Create processed archive from batch output
            if processed > 0:
                processed_zip = self.output_path / f"{batch_name}_processed.zip"
                if self._create_zip(batch_output_temp, processed_zip):
                    print(f"Created {processed_zip.name}")
                else:
                    print(f"Failed to create processed archive")

        finally:
            # Clean up temporary directories
            if batch_extract_dir.exists():
                shutil.rmtree(batch_extract_dir)
            if batch_output_temp.exists():
                shutil.rmtree(batch_output_temp)

        return processed, skipped

    def _process_document_folder(self, doc_folder: Path, output_base: Optional[Path] = None) -> Tuple[int, int]:
        """Process a single document folder."""
        if output_base is None:
            output_base = self.output_path

        processed = 0
        skipped = 0

        # Use original document folder name
        doc_folder_name = doc_folder.name
        print(f"  Processing: {doc_folder_name}")

        # Find all annotation zips (excluding INITIAL_CAS.zip)
        annotation_zips = [
            f for f in doc_folder.iterdir()
            if f.is_file() and f.suffix == '.zip' and f.name.lower() != 'initial_cas.zip'
        ]

        if not annotation_zips:
            print(f"No annotation zips found in {doc_folder.name}")
            return processed, skipped

        # Process each annotation zip
        output_folder = output_base / doc_folder_name
        output_folder.mkdir(parents=True, exist_ok=True)

        for annotation_zip in sorted(annotation_zips):
            temp_extract = Path(self.temp_dir) / f"temp-{os.urandom(8).hex()}"
            temp_extract.mkdir(parents=True, exist_ok=True)

            try:
                if not self._extract_zip(annotation_zip, temp_extract):
                    skipped += 1
                    continue

                xmi_file = self._find_xmi_file(temp_extract)
                if not xmi_file:
                    print(f"No XMI file in {annotation_zip.name}")
                    skipped += 1
                    continue

                # Get zip file name without extension
                zip_name_no_ext = annotation_zip.stem

                # Look up in user mappings
                if zip_name_no_ext not in self.user_mappings:
                    raise UserMappingError(
                        f"User '{zip_name_no_ext}' found in annotation but not in CSV mapping. "
                        f"Available mappings: {sorted(self.user_mappings.keys())}"
                    )

                generic_name = self.user_mappings[zip_name_no_ext]
                print(f"'{zip_name_no_ext}' → '{generic_name}'")

                # Update and rename XMI file
                xmi_content = xmi_file.read_text(encoding='utf-8')
                self._update_document_id_in_xmi(xmi_file, generic_name)
                xmi_file = self._rename_xmi_file(xmi_file, generic_name)

                # Create output zip
                output_zip = output_folder / f"{generic_name}.zip"
                if self._create_zip(temp_extract, output_zip):
                    print(f"Created {output_zip.name}")
                    self.processed_files.append(output_zip)
                    processed += 1
                else:
                    skipped += 1

            finally:
                if temp_extract.exists():
                    shutil.rmtree(temp_extract)

        return processed, skipped

    def process(self) -> bool:
        """Run the anonymization process."""
        self._create_temp_dir()

        try:
            # Find all .zip files in input directory
            batch_zips = sorted([f for f in self.input_path.iterdir() if f.is_file() and f.suffix == '.zip'])

            if not batch_zips:
                print("No .zip files found in input directory")
                return False

            print(f"\nFound {len(batch_zips)} batch .zip files")

            total_processed = 0
            total_skipped = 0

            for batch_zip in batch_zips:
                processed, skipped = self._process_batch_zip(batch_zip)
                total_processed += processed
                total_skipped += skipped

            print(f"\n")
            print(f" Processing complete!")
            print(f" Processed: {total_processed} files")
            print(f" Skipped: {total_skipped} files")
            print(f" Output: {self.output_path}")
            

            return total_processed > 0

        except UserMappingError as e:
            print(f"\nUser mapping error: {e}")
            return False

        except AnonymizerError as e:
            print(f"\nError during processing: {e}")
            return False

        except Exception as e:
            print(f"\nUnexpected error: {e}")
            return False

        finally:
            self._cleanup_temp_dir()


def get_path_input(prompt: str, must_exist: bool = True) -> Path:
    """Get and validate a path from user input."""
    while True:
        path_str = input(prompt).strip()
        if not path_str:
            print("Path cannot be empty")
            continue

        path = Path(path_str).expanduser()

        if must_exist and not path.exists():
            print(f"Path does not exist: {path}")
            continue

        if must_exist and path.is_file():
            print(f"Expected a directory, got a file: {path}")
            continue

        return path


def get_file_input(prompt: str) -> Path:
    """Get and validate a file path from user input."""
    while True:
        path_str = input(prompt).strip()
        if not path_str:
            print("Path cannot be empty")
            continue

        path = Path(path_str).expanduser()

        if not path.exists():
            print(f"File does not exist: {path}")
            continue

        if not path.is_file():
            print(f"Expected a file, got a directory: {path}")
            continue

        return path


def main():
    """Main entry point."""
    print("\n")
    print("py-anonymizer-semann-gemtex")
    print("Semann Document Anonymizer")

    try:
        print("\nProvide input paths:")
        input_path = get_path_input("Input folder (containing .zip files): ", must_exist=True)
        csv_path = get_file_input("CSV mapping file (user mappings): ")
        output_path = get_path_input("Output folder (will be created if needed): ", must_exist=False)

        print(f"\nConfiguration:")
        print(f"Input:  {input_path}")
        print(f"CSV:    {csv_path}")
        print(f"Output: {output_path}")

        confirm = input("\nStart processing? (y/n): ").strip().lower()
        if confirm != 'y':
            print("Cancelled.")
            sys.exit(0)

        anonymizer = SemannAnonymizer(str(input_path), str(csv_path), str(output_path))
        success = anonymizer.process()

        sys.exit(0 if success else 1)

    except KeyboardInterrupt:
        print("\n\nProcess interrupted by user")
        sys.exit(130)

    except Exception as e:
        print(f"\nFatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
