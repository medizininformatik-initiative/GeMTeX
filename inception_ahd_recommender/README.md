# INCEpTION De-ID Recommender

[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

Dieses Repositorium ist eine abgespeckte Variante des
[External INCEpTION Recommender](https://github.com/inception-project/inception-external-recommender).
Für GeMTeX-Zwecke wurden alle überflüssigen Dateien/Abhängigkeiten entfernt,
um das resultierende Docker Image nicht unnötig aufzublähen.  

### Konfiguration
```
[...]
environment:
  - EXTERNAL_SERVER_ADDRESS=http://ADRESSE_DER_AVERBIS_HD_IM_DOCKER_NETZWERK:8080
  - EXTERNAL_SERVER_TOKEN=<API_TOKEN_DER_AVERBIS_HD>
  - PIPELINE_ENDPOINT=/health-discovery/rest/v1/textanalysis/projects/<PROEJKT_NAME_IN_AVERBIS_HD>/pipelines/<PIPELINE_NAME>/analyseText
  - CONSUMER=inception_ahd_recommender.ariadne.contrib.external_server_consumer.MappingConsumer::/mapping_files/deid_mapping_singlelayer.json
  - SERVER_HANDLE=deid_recommender
  - RECOMMENDER_WORKERS=4
  - RECOMMENDER_ADDRESS=:5000
ports:
  - 5000:5000
networks:
  - recommender-network
volumes:
  - type: bind
    source: ../mapping_files
    target: /mapping_files
[...]
```