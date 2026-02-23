# SNOMED Postprocessing

### Docker
```
docker run
 --volume ./data:/app/data
 --rm
 ghcr.io/medizininformatik-initiative/gemtex/snomed-postprocessing:0.9.1
 log-critical-documents /app/data/inception-json-dump.zip
```

- log file befindet sich dann im Verzeichnis `./data` (Ort wird vom Skript auch angezeigt).
- `inception-json-dump.zip` muss in `./data` vorhanden sein.
- [gemtex_snomedct_codes_2024-04-01.hdf5](https://confluence.imi.med.fau.de/spaces/GEM/pages/317216732/SNOMED+CT+Semantic+Tag+Dashboard?preview=/317216732/359075603/gemtex_snomedct_codes_2024-04-01.hdf5) muss in `./data` vorhanden sein.