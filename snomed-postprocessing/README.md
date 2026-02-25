# SNOMED Postprocessing

### Docker
```
docker run
 --volume ./data:/app/data
 --rm
 ghcr.io/medizininformatik-initiative/gemtex/snomed-postprocessing:0.9.2
 log-critical-documents /app/data/inception-json-dump.zip
```

- log file befindet sich dann im Verzeichnis `./data` (Ort wird vom Skript auch angezeigt).
- `inception-json-dump.zip` muss in `./data` vorhanden sein.
- [gemtex_snomedct_codes_2024-04-01.hdf5](https://confluence.imi.med.fau.de/spaces/GEM/pages/317216732/SNOMED+CT+Semantic+Tag+Dashboard?preview=/317216732/359075603/gemtex_snomedct_codes_2024-04-01.hdf5) muss in `./data` vorhanden sein.

##### Convenience Script
There is a convenience script with `./log-inception-docs.sh` that runs the above docker command with the given arguments:
* _arg1_ (mandatory): name of the inception dump zip (in the ``data`` folder)
* _arg2_ (optional): version of the docker image 

#### CLI Output:
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

#### LOG File:
## INITIAL_CAS
#### Albers.txt.xmi
| Snomed CT Code | Covered Text | Offset in Document | FSN |
| -------------: | -----------: | -----------------: | --: |
| 257915005 | Entnahmestellen | (3188, 3203) | Sampling - action (qualifier value) |
| 257915005 | Entnahmeareale | (8916, 8930) | Sampling - action (qualifier value) |

[...]

#### Fleischmann.txt.xmi
| Snomed CT Code | Covered Text | Offset in Document | FSN |
| -------------: | -----------: | -----------------: | --: |
| 160780003 | Beschäftigungstherapie | (4415, 4437) | Domiciliary occupational therapy (finding) |

[...]

#### Waldenstroem.txt.xmi
| Snomed CT Code | Covered Text | Offset in Document | FSN |
| -------------: | -----------: | -----------------: | --: |
| 162467007 | symptomfrei | (1064, 1075) | Free of symptoms (situation) |
| 251893009 | Symptomatik | (1088, 1099) | Symptom ratings (staging scale) |
| 42752001 | im Sinne einer | (2464, 2478) | Due to (attribute) |
| 367409002 | gefolgt | (3088, 3095) | Followed by (attribute) |
| 246106000 | Kontrolle | (3401, 3410) | Control (attribute) |
| 720378001 | allerdings sollte er dabei vorsichtig sein mit Autofahren, da diese Medikamente bekanntlich sedierend sind | (3498, 3604) | Patient advised medication may affect driving (situation) |
