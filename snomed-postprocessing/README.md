# SNOMED Postprocessing

This script logs all critical documents in the given inception dump (supported export formats: ``json``).
Critical are documents when they contain SNOMED CT codes that are either on the blacklist or are not on the whitelist.
Whitelist and blacklist are both defined in a ``hdf5`` file, that must be provided.

## Usage
The script can be run either via the command line or via docker.
In both cases you need a hdf5 file ([gemtex_snomedct_codes_2024-04-01.hdf5](https://confluence.imi.med.fau.de/spaces/GEM/pages/317216732/SNOMED+CT+Semantic+Tag+Dashboard?preview=/317216732/359075603/gemtex_snomedct_codes_2024-04-01.hdf5)) containing the whitelist/blacklist and a zip file containing the inception dump.  
The hdf5 file could also be created with this script itself if you ever need it for a different whitelist/blacklist. You would need a running SNOWSTORM instance though.
See ``uv run create-concepts-dump --help`` or 
``docker run ghcr.io/medizininformatik-initiative/gemtex/snomed-postprocessing:0.9.3 create-concepts-dump --help`` for further information.  
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
 ghcr.io/medizininformatik-initiative/gemtex/snomed-postprocessing:0.9.3
 log-critical-documents /app/data/inception-json-dump.zip
```
- log file will be in the `./data` folder (the script will show the final path as well).
- `inception-json-dump.zip` has to be in `./data`. [1]
- [gemtex_snomedct_codes_2024-04-01.hdf5](https://confluence.imi.med.fau.de/spaces/GEM/pages/317216732/SNOMED+CT+Semantic+Tag+Dashboard?preview=/317216732/359075603/gemtex_snomedct_codes_2024-04-01.hdf5) has to be in `./data`, too.

#### Convenience Script
There is a convenience script with `./log-inception-docs.sh` that runs the above docker command with the given arguments:
* _arg1_ (mandatory): name of the inception dump zip (in the ``data`` folder)
* _arg2_ (optional): version of the docker image 

_[1] the discrepancy between `/app/data/...` and `./data/...` is no error,
because the local `./data` will be mounted into the containers `/app/data` and the script that runs in the container will need the location relative to its filesystem._

### CLI Output:
```
-- Whitelist --
INITIAL_CAS: Done. Found   0 critical document(s).
[...]
-- Blacklist --
INITIAL_CAS: Done. Found  13 critical document(s). With  19 concept(s)  on 'blacklist'.
[...]
-- Result --
WARNING:root:  13 critical document(s) found. See '[...]/critical_documents_24-02-2026_08-46-07.md' for details.
```

## Resulting LOG File:
### Whitelist
[...]
### Blacklist
#### INITIAL_CAS
##### Albers.txt.xmi
| Snomed CT Code | Covered Text | Offset in Document | FSN |
| -------------: | -----------: | -----------------: | --: |
| 257915005 | Entnahmestellen | (3188, 3203) | Sampling - action (qualifier value) |
| 257915005 | Entnahmeareale | (8916, 8930) | Sampling - action (qualifier value) |

[...]

##### Fleischmann.txt.xmi
| Snomed CT Code | Covered Text | Offset in Document | FSN |
| -------------: | -----------: | -----------------: | --: |
| 160780003 | Beschäftigungstherapie | (4415, 4437) | Domiciliary occupational therapy (finding) |

[...]

##### Waldenstroem.txt.xmi
| Snomed CT Code | Covered Text | Offset in Document | FSN |
| -------------: | -----------: | -----------------: | --: |
| 162467007 | symptomfrei | (1064, 1075) | Free of symptoms (situation) |
| 251893009 | Symptomatik | (1088, 1099) | Symptom ratings (staging scale) |
| 42752001 | im Sinne einer | (2464, 2478) | Due to (attribute) |
| 367409002 | gefolgt | (3088, 3095) | Followed by (attribute) |
| 246106000 | Kontrolle | (3401, 3410) | Control (attribute) |
| 720378001 | allerdings sollte er dabei vorsichtig sein mit Autofahren, da diese Medikamente bekanntlich sedierend sind | (3498, 3604) | Patient advised medication may affect driving (situation) |
