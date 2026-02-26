# SNOMED Postprocessing

This script logs all critical documents in the given inception dump (supported export formats: ``json`` ***[1]***).
Critical are documents when they contain SNOMED CT codes that are either on the blacklist or are not on the whitelist.
Whitelist and blacklist are both defined in a ``hdf5`` file, that must be provided.

## Usage
The script can be run either via the command line or via docker.
In both cases you need a hdf5 file ([gemtex_snomedct_codes_2024-04-01.hdf5](https://confluence.imi.med.fau.de/spaces/GEM/pages/317216732/SNOMED+CT+Semantic+Tag+Dashboard?preview=/317216732/359075603/gemtex_snomedct_codes_2024-04-01.hdf5); should be around 45MB) containing the whitelist/blacklist and a zip file containing the inception dump.  
The hdf5 file could also be created with this script itself if you ever need it for a different whitelist/blacklist. You would need a running SNOWSTORM instance though.
See ``uv run create-concepts-dump --help`` or 
``docker run ghcr.io/medizininformatik-initiative/gemtex/snomed-postprocessing:0.9.4 create-concepts-dump --help`` for further information. ***[2]***  
The simple usage for the use case in GeMTex is described in the following, however:

### CLI
You can run the logging script from within an [uv](https://docs.astral.sh/uv/getting-started/installation/) environment:
```
uv sync
uv run log-critical-documents --lists-path /path/to/hdf5-file /path/to/inception-json-dump.zip
```

### Docker
There is also a docker image available:
```
docker run
 --volume ./data:/app/data
 --rm
 ghcr.io/medizininformatik-initiative/gemtex/snomed-postprocessing:0.9.4
 log-critical-documents /app/data/inception-json-dump.zip
```
- log file will be in the `./data` folder (the script will show the final path as well).
- `inception-json-dump.zip` has to be in `./data`. ***[3]***
- [gemtex_snomedct_codes_2024-04-01.hdf5](https://confluence.imi.med.fau.de/spaces/GEM/pages/317216732/SNOMED+CT+Semantic+Tag+Dashboard?preview=/317216732/359075603/gemtex_snomedct_codes_2024-04-01.hdf5) has to be in `./data`, too.

#### Convenience Script
There is a convenience script with `./log-inception-docs.sh` that runs the above docker command with the given arguments:
* _arg1_ (mandatory): name of the inception dump zip (in the ``data`` folder)
* _arg2_ (optional): version of the docker image 


### CLI Output:
```
-- Whitelist --
INITIAL_CAS: Done.    0 critical document(s) found.
[...]
-- Blacklist --
INITIAL_CAS: Done.   13 critical document(s) found - with  19 concept(s) on 'blacklist'.
[...]
-- Result --
WARNING:root:  13 critical document(s) found. See '[...]/critical_documents_24-02-2026_08-46.md' for details.
```

## Additional Information / Footnotes
* Since the script needs to compare every document and its SNOMED CT codes (three digits in most documents) against the whitelist/blacklist, it might take a while to complete.
The script will show the progress in the console, and on the bright side, if it completed the whitelist (appr. 367 000 concepts), the comparison against the blacklist should be much faster, since it contains fewer concepts (only appr. 15 700). 

[1] Export > Export backup archive > Secondary format > UIMA CAS JSON 0.4.0  

[2] The available dump `gemtex_snomedct_codes_2024-04-01.hdf5` was created with the following two commands respectively:  
* `uv run create-concepts-dump --ip SNOWSTORM_IP --port SNOWSTORM_PORT --branch MAIN/2024-04-01 --dump-mode version` (whitelist)  
* `uv run create-concepts-dump --ip SNOWSTORM_IP --port SNOWSTORM_PORT --branch MAIN/2024-04-01 --filter-list ./config/blacklist_filter_tags.txt --dump-mode semantic` (blacklist)  

[3] the discrepancy between `/app/data/...` in the docker command and `./data/...` for the requirements is no error,
because the local `./data` will be mounted into the containers `/app/data` and the script that runs in the container will need the location relative to its filesystem.

## Resulting LOG File Example:
### Whitelist
[...]
### Blacklist
#### INITIAL_CAS
##### Albers.txt.xmi
| Snomed CT Code |    Covered Text | Offset in Document |                                 FSN |
|---------------:|----------------:|-------------------:|------------------------------------:|
|      257915005 | Entnahmestellen |       (3188, 3203) | Sampling - action (qualifier value) |
|      257915005 |  Entnahmeareale |       (8916, 8930) | Sampling - action (qualifier value) |

[...]

##### Fleischmann.txt.xmi
| Snomed CT Code |           Covered Text | Offset in Document |                                        FSN |
|---------------:|-----------------------:|-------------------:|-------------------------------------------:|
|      160780003 | Beschäftigungstherapie |       (4415, 4437) | Domiciliary occupational therapy (finding) |

[...]

##### Waldenstroem.txt.xmi
| Snomed CT Code |                                                                                               Covered Text | Offset in Document |                                                       FSN |
|---------------:|-----------------------------------------------------------------------------------------------------------:|-------------------:|----------------------------------------------------------:|
|      162467007 |                                                                                                symptomfrei |       (1064, 1075) |                              Free of symptoms (situation) |
|      251893009 |                                                                                                Symptomatik |       (1088, 1099) |                           Symptom ratings (staging scale) |
|       42752001 |                                                                                             im Sinne einer |       (2464, 2478) |                                        Due to (attribute) |
|      367409002 |                                                                                                    gefolgt |       (3088, 3095) |                                   Followed by (attribute) |
|      246106000 |                                                                                                  Kontrolle |       (3401, 3410) |                                       Control (attribute) |
|      720378001 | allerdings sollte er dabei vorsichtig sein mit Autofahren, da diese Medikamente bekanntlich sedierend sind |       (3498, 3604) | Patient advised medication may affect driving (situation) |

### Final Count
#### SNOMED CT Codes
| SNOMED CT Codes | Count |
|----------------:|------:|
|           33333 |     2 |
|         1234567 |    10 |
|           [...] | [...] |

#### Semantic Tags
| Semantic Tag | Count |
|-------------:|------:|
|    attribute |    65 |
|    situation |    12 |
|        [...] | [...] |
|  environment |     4 |