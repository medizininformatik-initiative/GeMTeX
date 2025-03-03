import glob
import os
import time

from averbis import Client

# Configuration
HD_URL = "https://your-averbis-instance.com/health-discovery/"
API_TOKEN = "your-api-token"
PROJECT_NAME = "your-project"
PIPELINE_NAME = "your-pipeline"
INPUT_DIR = "input_data/"  # Directory containing subdirectories with text files. Each subdirectory will be treated as a batch. Text files (*.txt) in all subdirectories will be processed.
OUTPUT_DIR = "processed_data/"  # Directory to save processed CAS files


def get_subdirectories(directory):
    """Retrieve all subdirectories in the given directory."""
    return [d for d in glob.glob(os.path.join(directory, "**/"), recursive=False) if os.path.isdir(d)]


def get_text_files(directory):
    """Retrieve all text files from the given directory (recursively)."""
    return glob.glob(os.path.join(directory, "**/*.txt"), recursive=True)


def process_batch(batch_name, batch_files):
    """Upload a batch of text files to Averbis Health Discovery and process them."""
    # Connect to Averbis Health Discovery
    client = Client(HD_URL, api_token=API_TOKEN)
    project = client.get_project(PROJECT_NAME)
    pipeline = project.get_pipeline(PIPELINE_NAME)

    # Upload documents
    document_collection = project.create_document_collection(batch_name)
    for file in batch_files:
        with open(file, "r", encoding="utf-8") as f:
            document_collection.import_documents(f.read(), filename=os.path.relpath(file, INPUT_DIR).replace("/", "_"))

    # Process documents
    process = document_collection.create_and_run_process(process_name=f"{batch_name}-{pipeline.name}", pipeline=pipeline)
    print(f"Processing {len(batch_files)} documents with {pipeline.name} pipeline ... ", end="")
    wait_until_process_finished(process)
    print("done.")

    # Export results
    for file in batch_files:
        cas = process.export_text_analysis_to_cas(os.path.relpath(file, INPUT_DIR).replace("/", "_"))
        output_file = os.path.join(OUTPUT_DIR, os.path.relpath(file, INPUT_DIR))
        os.makedirs(os.path.dirname(output_file), exist_ok=True)
        cas.to_xmi(output_file.replace(".txt", ".xmi"), pretty_print=True)

    # Cleanup
    document_collection.delete()


def wait_until_process_finished(process):
    """Helper function to wait until the processing is finished."""
    state = process.get_process_state()
    while state.number_of_successful_documents + state.number_of_unsuccessful_documents < state.number_of_total_documents:
        time.sleep(1)
        state = process.get_process_state()


def main():
    subdirectories = get_subdirectories(INPUT_DIR)
    print(f"Found {len(subdirectories)} batches in {INPUT_DIR}.\n")

    for subdir in subdirectories:
        batch_name = os.path.relpath(subdir, INPUT_DIR)
        batch_files = get_text_files(subdir)
        print(f"Processing batch: {batch_name}.")
        process_batch(batch_name, batch_files)
        print(f"Batch {batch_name} processed and saved.\n")
    print(f"All files processed. Resulting UIMA CAS files are in {OUTPUT_DIR}.")


if __name__ == "__main__":
    main()
