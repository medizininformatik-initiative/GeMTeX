# SNOMED Postprocessing

### Docker
```
docker run
 --volume ./data:/app/data
 --rm
 ghcr.io/medizininformatik-initiative/gemtex/snomed-postprocessing:0.9.1
 log-critical-documents /app/data/inception-json-dump.zip