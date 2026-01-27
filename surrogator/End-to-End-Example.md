Minimal End-to-End-Example of Surrogator 🐊
===========================================

We prefer to use a Linux system.
You need around 8 GB disk space.

Installation
------------

-   Install [Python 3.11](https://www.python.org);
-   It is preferred, to use a [virtual
    environment](https://docs.python.org/3/library/venv.html)
    - if not installed, install `apt install python3.11-venv`

    - use a terminal:

        - create virtual environment: `python3.11 -m venv venv`
        - start virtual environment: `source venv/bin/activate`

-   Install following packages via
    [Pip](https://pypi.org/project/pip/), see
    [pyproject.toml](pyproject.toml) or run `pip install .`

```
        pandas~=2.2.2
        dkpro-cassis
        pycaprio~=0.3.0
        streamlit
        toml~=0.10.2
        mdutils~=1.6.0
        tabulate~=0.9.0
        streamlit_ext
        python-dateutil~=2.9.0
        requests~=2.32.3
        schwifty
        gender-guesser
        spacy
        joblib
        sentence-transformers
        Levenshtein
        scikit-learn
        openpyxl
        overpy
        anytree
```

* **Note**:
    * If you use the following data and instructions, there is an API call with the OpenStreetMap database by the Overpass API!
    * If you do not want to use a local dump, follow the instructions from [Readme.md](Readme.md) section 


Test Data
---------

* Test data is an exported annotation project of the [INCEpTION annotation plattform](https://inception-project.github.io/) with UIMA CAS JSON as additional export format.
* Original 15 text files of the minimal example: [test_data/deid-test-doc](test_data/deid-test-doc) 
* is provided under [test_data/projects](test_data/projects)
    * [test_data/projects/project-deid-test-data-1-2025-09-18-160813.zip](test_data/projects/project-deid-test-data-1-2025-09-18-160813.zip)
* There are 5 files with an OTHER or NONE (wrong) annotation. These files are not processed.


Notes about Output of Following Runs
------------------------------------

Every run of `surrogator.py` creates output into the directories 

-   `private` : for every run a private directory is created:
    -   the new created UIMA cas files in cas-project\_name-timestamp\_key
    -   a directory with aggregated statistics of quality control output

-   `public` : for further usage
    -   only new generated text files from the projects


Run via Terminal
----------------

## (1) Assurance Step / Quality Control Step

- It is preferred an assurance step before replacement by surrogates and look into the data.
- It is not necessary. Every following surrogation routine run this assurance step as initial step.
- Run: `python surrogator.py -qc -p test_data/projects`
- Example output: [test_data/test_output](test_data/test_output)
  - every run fills the directories
    - public : for further usage (research, LLM training, semantic annotation, ...)
    - private : archive @ Data Integration Center for every run a
    private directory is created, containing
    - with separated directories with a name convention of project\_name-timestamp
  - See following description in detail with examples


## (2) Run Surrogation

-   Run with mode *x*
    `python surrogator.py -x -p test_data/projects`

    * example output : [test_data/test_output/mode_x/](test_data/test_output/mode_x/)
        * private files : [test_data/test_output/mode_x/private-20250918-160856](test_data/test_output/mode_x/private-20250918-160856) 
            * [test_data/test_output/mode_x/private-20250918-160856/project-deid-test-data-1-2025-09-18-082608.zip/cas_project-deid-test-data-1-2025-09-18-082608.zip_20250918-160856/](test_data/test_output/mode_x/private-20250918-160856/project-deid-test-data-1-2025-09-18-082608.zip/cas_project-deid-test-data-1-2025-09-18-082608.zip_20250918-160856/)
                * new UIMA cas json files of process text documents
            * [test_data/test_output/mode_x/private-20250918-160856/project-deid-test-data-1-2025-09-18-082608.zip/quality_control_project-deid-test-data-1-2025-09-18-082608.zip_20250918-160856/](test_data/test_output/mode_x/private-20250918-160856/project-deid-test-data-1-2025-09-18-082608.zip/quality_control_project-deid-test-data-1-2025-09-18-082608.zip_20250918-160856/):
                * project-deid-test-data-1-2025-09-18-082608.zip_corpus_details.csv : Mentions of annotated PII items per document
                * project-deid-test-data-1-2025-09-18-082608.zip_corpus_documents.csv : Corpus list, files that are processed are tagged with 1, excluded files tagged with 1
                * project-deid-test-data-1-2025-09-18-082608.zip_statistics.csv : Statistics of annotated PII items per document 
                * quality_control.json : Summary of 3 mentioned csv files in json file 
                * Report_Quality_Control_project-deid-test-data-1-2025-09-18-082608.zip_20250918-160856.md : Summary of 3 mentioned csv files in md file 
        * public files : [test_data/test_output/mode_x/public-20250918-160856/](test_data/test_output/mode_x/public-20250918-160856/):
            * 10 text files with new processed text files with replaced 'X' tags for further usage

-   Run with mode *entity*
    `python surrogator.py -e -p test_data/projects`

    * example output:
        * private files : [test_data/test_output/mode_entity/private-20250918-160959](test_data/test_output/mode_entity/private-20250918-160959) 
            * [test_data/test_output/mode_entity/private-20250918-160959/project-deid-test-data-1-2025-09-18-082608.zip/cas_project-deid-test-data-1-2025-09-18-082608.zip_20250918-160959/](test_data/test_output/mode_entity/private-20250918-160959/project-deid-test-data-1-2025-09-18-082608.zip/cas_project-deid-test-data-1-2025-09-18-082608.zip_20250918-160959/)
                * new UIMA cas json files of process text documents
            * [test_data/test_output/mode_entity/private-20250918-160959/project-deid-test-data-1-2025-09-18-082608.zip/quality_control_project-deid-test-data-1-2025-09-18-082608.zip_20250918-160959/](test_data/test_output/mode_entity/private-20250918-160959/project-deid-test-data-1-2025-09-18-082608.zip/quality_control_project-deid-test-data-1-2025-09-18-082608.zip_20250918-160959/):
                * project-deid-test-data-1-2025-09-18-082608.zip_corpus_details.csv : Mentions of annotated PII items per document
                * project-deid-test-data-1-2025-09-18-082608.zip_corpus_documents.csv : Corpus list, files that are processed are tagged with 1, excluded files tagged with 1
                * project-deid-test-data-1-2025-09-18-082608.zip_statistics.csv : Statistics of annotated PII items per document 
                * quality_control.json : Summary of 3 mentioned csv files in json file 
                * Report_Quality_Control_project-deid-test-data-1-2025-09-18-082608.zip_20250918-160959.md : Summary of 3 mentioned csv files in md file 
        * public files : [test_data/test_output/mode_entity/public-20250918-160959/](test_data/test_output/mode_entity/public-20250918-160959/):
            * 10 text files with new processed text files with replaced entity tags for further usage


-   Run with mode *gemtex*
    `python surrogator.py -s -p test_data/projects`

    * example output:
        * private files : [test_data/test_output/mode_entity/private-20250918-161024](test_data/test_output/mode_entity/private-20250918-161024) 
            * [test_data/test_output/mode_entity/private-20250918-161024/project-deid-test-data-1-2025-09-18-082608.zip/cas_project-deid-test-data-1-2025-09-18-082608.zip_20250918-161024/](test_data/test_output/mode_entity/private-20250918-161024/project-deid-test-data-1-2025-09-18-082608.zip/cas_project-deid-test-data-1-2025-09-18-082608.zip_20250918-161024/)
                * new UIMA cas json files of process text documents
            * [test_data/test_output/mode_entity/private-20250918-161024/project-deid-test-data-1-2025-09-18-082608.zip/quality_control_project-deid-test-data-1-2025-09-18-082608.zip_20250918-161024/](test_data/test_output/mode_entity/private-20250918-161024/project-deid-test-data-1-2025-09-18-082608.zip/quality_control_project-deid-test-data-1-2025-09-18-082608.zip_20250918-161024/):
                * project-deid-test-data-1-2025-09-18-082608.zip_corpus_details.csv : Mentions of annotated PII items per document
                * project-deid-test-data-1-2025-09-18-082608.zip_corpus_documents.csv : Corpus list, files that are processed are tagged with 1, excluded files tagged with 1
                * project-deid-test-data-1-2025-09-18-082608.zip_statistics.csv : Statistics of annotated PII items per document 
                * quality_control.json : Summary of 3 mentioned csv files in json file 
                * Report_Quality_Control_project-deid-test-data-1-2025-09-18-082608.zip_20250918-161024.md : Summary of 3 mentioned csv files in md file 
            * 2 json files with key assignment for further usage in Pseudonym Management Systems
                * [test_data/test_output/mode_gemtex/private-20250918-161024/project-deid-test-data-1-2025-09-18-082608.zip/project-deid-test-data-1-2025-09-18-082608.zip_20250918-161024_key_assignment_gemtex.json](test_data/test_output/mode_gemtex/private-20250918-161024/project-deid-test-data-1-2025-09-18-082608.zip_20250918-161024_key_assignment_gemtex.json)
                  (normal nested json)     
                * [test_data/test_output/mode_gemtex/private-20250918-161024/project-deid-test-data-1-2025-09-18-082608.zip/project-deid-test-data-1-2025-09-18-082608.zip_20250918-161024_key_assignment_gemtex_flat.json](test_data/test_output/mode_gemtex/private-20250918-161024/project-deid-test-data-1-2025-09-18-082608.zip/project-deid-test-data-1-2025-09-18-082608.zip_20250918-161024_key_assignment_gemtex_flat.json)
                (flatted json, better for input in Pseudonym Management Systems)
        * public files : [test_data/test_output/mode_entity/public-20250918-161024/](test_data/test_output/mode_entity/public-20250918-161024/):
            * 10 text files with new processed text files with replaced gemtex surrogated tags for further usage

-   Run with mode *fictive*
    `python surrogator.py -f -p test_data/projects`

    -   NOTE: if you want, that all `DATE` annotations (incl.
        `DATE_BIRTH` and `DATE_DEATH`) are shifted, use the
        extension `-d` and an integer value,
    -   example: `python surrogator.py -f -p test_data/projects -d 7` as a shift of seven days.
    -   If there is no shift defined, there is no shift processed
        and `DATE_BIRTH` and `DATE_DEATH` the first day of the
        quarter.
    -   If a date is not processable, the surrogate replacement is `DATE`.

    * example output (created with `python surrogator.py -f -p test_data/projects -d 7`):
        * private files : [test_data/test_output/mode_entity/private-20250918-161119](test_data/test_output/mode_entity/private-20250918-161119) 
            * [test_data/test_output/mode_entity/private-20250918-161119/project-deid-test-data-1-2025-09-18-082608.zip/cas_project-deid-test-data-1-2025-09-18-082608.zip_20250918-161119/](test_data/test_output/mode_entity/private-20250918-161119/project-deid-test-data-1-2025-09-18-082608.zip/cas_project-deid-test-data-1-2025-09-18-082608.zip_20250918-161119/)
                * new UIMA cas json files of process text documents
            * [test_data/test_output/mode_entity/private-20250918-161119/project-deid-test-data-1-2025-09-18-082608.zip/quality_control_project-deid-test-data-1-2025-09-18-082608.zip_20250918-161119/](test_data/test_output/mode_entity/private-20250918-161119/project-deid-test-data-1-2025-09-18-082608.zip/quality_control_project-deid-test-data-1-2025-09-18-082608.zip_20250918-161119/):
                * project-deid-test-data-1-2025-09-18-082608.zip_corpus_details.csv : Mentions of annotated PII items per document
                * project-deid-test-data-1-2025-09-18-082608.zip_corpus_documents.csv : Corpus list, files that are processed are tagged with 1, excluded files tagged with 1
                * project-deid-test-data-1-2025-09-18-082608.zip_statistics.csv : Statistics of annotated PII items per document 
                * quality_control.json : Summary of 3 mentioned csv files in json file 
                * Report_Quality_Control_project-deid-test-data-1-2025-09-18-082608.zip_20250918-161119.md : Summary of 3 mentioned csv files in md file 
            * 2 json files with key assignment for further usage in Pseudonym Management Systems
                * [test_data/test_output/mode_gemtex/private-20250918-161119/project-deid-test-data-1-2025-09-18-082608.zip/project-deid-test-data-1-2025-09-18-082608.zip_20250918-161119_key_assignment_fictive.json](test_data/test_output/mode_gemtex/project-deid-test-data-1-2025-09-18-082608.zip_20250918-161119_key_assignment_fictive.json)
                  (normal nested json)     
                * [test_data/test_output/mode_gemtex/private-20250918-161119/project-deid-test-data-1-2025-09-18-082608.zip/project-deid-test-data-1-2025-09-18-082608.zip_20250918-161119_key_assignment_fictive_flat.json](test_data/test_output/mode_gemtex/private-20250918-161119/project-deid-test-data-1-2025-09-18-082608.zip/project-deid-test-data-1-2025-09-18-082608.zip_20250918-161119_key_assignment_fictive_flat.json)
                (flatted json, better for input in Pseudonym Management Systems)
        * public files : [test_data/test_output/mode_entity/public-20250918-161119/](test_data/test_output/mode_entity/public-20250918-161119/):
            * 10 text files with new processed text files with replaced fictitious tags for further usage

