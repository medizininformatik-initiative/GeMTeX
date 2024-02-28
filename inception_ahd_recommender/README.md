# INCEpTION De-ID Recommender

[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

Dieses Repositorium ist eine abgespeckte Variante des
[External INCEpTION Recommender](https://github.com/inception-project/inception-external-recommender).
Für GeMTeX-Zwecke wurden alle überflüssigen Dateien/Abhängigkeiten entfernt,
um das resultierende `docker` Image nicht unnötig aufzublähen.

## Allgemein
Alle drei Services (`Averbis Health Discovery (AHD)`, `INCEpTION`, `Recommender`) müssen sich im gleichen `docker` Netzwerk befinden.
In der IMISE Referenzplattform arbeiten wir mit [Portainer](https://www.portainer.io/),
und darin lässt sich leicht ein neues `docker` Netzwerk erstellen und die verschiedenen Container diesem Netzwerk zuordnen, wie auch die IP-Adresse ablesen.
Das ganze lässt sich aber auch mit dem normalen `docker` Client bzw. über `docker compose` erledigen.  

Wenn die Services neu gestartet werden, ist es vorzuziehen, wenn die `Averbis HD` als erstes gestartet wird,
da der `Recommender` testet ob eine Verbindung zur angegebenen `<EXTERNAL_SERVER_ADRESS>` besteht.

## Konfiguration
Der `Recommender` benötigt ein paar Einstellungen, die über `environment variables` gesetzt werden;
ansonsten würden die Standard-Einstellungen verwendet, was größtenteils nicht zu einer sauberen Konfiguration führen würde.
Im Weiteren wird auf den folgenden Ausschnitt einer `docker compose` Datei Bezug genommen.
```
[...]
environment:
  - EXTERNAL_SERVER_ADDRESS=http://<ADRESSE_DER_AVERBIS_HD_IM_DOCKER_NETZWERK>:8080
  - EXTERNAL_SERVER_TOKEN=<API_TOKEN_DER_AVERBIS_HD>
  - PIPELINE_ENDPOINT=/health-discovery/rest/v1/textanalysis/projects/<PROEJKT_NAME_IN_AVERBIS_HD>/pipelines/<PIPELINE_NAME>/analyseText
  - CONSUMER=inception_ahd_recommender.ariadne.contrib.external_server_consumer.MappingConsumer::/mapping_files/<MAPPING_FILE>
  - SERVER_HANDLE=deid_recommender
  - RECOMMENDER_WORKERS=4
  - RECOMMENDER_ADDRESS=:5000
ports:
  - 5000:5000
networks:
  - recommender-network
volumes:
  - type: bind
    source: ../uima_cas_mapper/mapping-files
    target: /mapping_files
[...]
```

### ENVIRONMENT VARIABLES
###### EXTERNAL_SERVER_ADDRESS
Gibt die Adresse der `Averbis Health Discovery` im `docker` Netzwerk an. Sollten keine Änderungen an den Einstellungen der `AHD` vorgenommen worden sein,
ist der Port `8080`. Der Standard-Wert für `<EXTERNAL_SERVER_RECOMMENDER>` ist: `http://localhost:8080`.

###### EXTERNAL_SERVER_TOKEN
Die `AHD` benötigt ein Token für API-Zugriffe. Dieses muss entsprechend erst in der `AHD` aktiviert und dann hier hinterlegt werden:
[AHD-Help: API Token](https://help.averbis.com/health-discovery/user-manual/#HealthDiscoveryUserManualVersion6.20-ApplicationInterface:RESTAPI)
Es gibt für diese Variable keine Standard-Einstellung.

###### PIPELINE_ENDPOINT
Das ist der API-Endpunkt relativ zur `<EXTERNAL_SERVER_ADDRESS>`. Prinzipiell sollte sich da außer die Werte für
`<PROEJKT_NAME_IN_AVERBIS_HD>` und `<PIPELINE_NAME>` nichts ändern. Diese beiden Werte sind abhängig vom
[erstellten Projekt](https://help.averbis.com/health-discovery/user-manual/#HealthDiscoveryUserManualVersion6.20-LogintoHealthDiscoveryandcreateaproject)
in der `AHD` bzw. der zu verwendenden
[Pipeline](https://help.averbis.com/health-discovery/user-manual/#HealthDiscoveryUserManualVersion6.20-PipelineConfiguration).