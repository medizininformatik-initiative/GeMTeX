# INCEpTION De-ID Recommender

[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

Dieses Repositorium ist eine abgespeckte Variante des
[External INCEpTION Recommender](https://github.com/inception-project/inception-external-recommender).
Für GeMTeX-Zwecke wurden alle überflüssigen Dateien/Abhängigkeiten entfernt,
um das resultierende `docker` Image nicht unnötig aufzublähen.  

Derzeit wird in dieser `docker` Variante nur der Start eines Recommenders unterstützt (will man also mehrere haben, müssten mehrere `docker` Container gestartet werden).

## Allgemein
Alle drei Services (`Averbis Health Discovery (AHD)`, `INCEpTION`, `Recommender`) müssen sich im gleichen `docker` Netzwerk befinden.
In der IMISE Referenzplattform arbeiten wir mit [Portainer](https://www.portainer.io/),
und darin lässt sich leicht ein neues `docker` Netzwerk erstellen und die verschiedenen Container diesem Netzwerk zuordnen, wie auch die IP-Adresse ablesen.
Das ganze lässt sich aber auch mit dem normalen `docker` Client bzw. über `docker compose` erledigen.  

Wenn die Services neu gestartet werden, ist es vorzuziehen, wenn die `Averbis HD` als erstes gestartet wird,
da der `Recommender` testet ob eine Verbindung zur angegebenen `<EXTERNAL_SERVER_ADRESS>` besteht.  

Des Weiteren ist unter dem entsprechenden Projekt in der `AHD` ein entsprechend gestartete Pipeline notwendig (siehe `PIPELINE_ENDPOINT` weiter unten).  

Wenn `docker compose` verwendet werden soll, muss die `docker-compose.yml` noch geändert werden (siehe die folgenden Anweisungen), da u.a. ``EXTERNAL_SERVER_TOKEN`` gesetzt werden muss.

## Konfiguration
Der `Recommender` benötigt ein paar Einstellungen, die über `environment variables` gesetzt werden;
ansonsten würden die Standard-Einstellungen verwendet, was größtenteils nicht zu einer sauberen Konfiguration führen würde.
Im Weiteren wird auf den folgenden Ausschnitt einer `docker compose` Datei Bezug genommen.
```
[...]
    environment:
      - EXTERNAL_SERVER_ADDRESS=http://<ADRESSE_DER_AVERBIS_HD_IM_DOCKER_NETZWERK>:8080
      - EXTERNAL_SERVER_TOKEN=<API_TOKEN_DER_AVERBIS_HD>
      - PIPELINE_PROJECT=<PROEJKT_NAME_IN_AVERBIS_HD>
      - PIPELINE_NAME=<PIPELINE_NAME>
      - CONSUMER=ariadne.contrib.external_server_consumer.<CONSUMER_CLASS>[::<MAPPING_FILE>]
      [- CLASSIFIER=ariadne.contrib.external_uima_classifier.<CLASSIFIER_CLASS>]
      [- PROCESSOR={json | cas}]
      - SERVER_HANDLE=<NAME_OF_RECOMMENDER>
      - MODEL_DIR=<PATH_TO_MODELS>
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
networks:
  recommender-network:
    external: true
    name: recommender-network
[...]
```

### WSGI Server: Gunicorn
Der Service ist mit dem WSGI-Server ``gunicorn`` konfiguriert. Beim Start des Containers wird dieser durch den "Entrypoint" `"gunicorn"` aufgerufen.
Wenn keine anderen Argumente geliefert werden, wird dadurch die `gunicorn.conf.py` als Konfiguration benutzt und die Anzahl der ``worker`` und die ``address`` wie weiter unten beschrieben aus den Umgebungsvariablen bzw. der ``docker-compose.yml`` gelesen.
Hier muss also nichts weiter beachtet werden, es sei denn man möchte den ``gunicorn`` Server selbst noch weiter konfigurieren:
[Gunicorn Settings Documentation](https://docs.gunicorn.org/en/latest/settings.html).
Dazu müsste man sich aber den Container entsprechend selbst bauen, oder per ``docker volumes`` eine geänderte `gunicorn.conf.py` hosten.

### ENVIRONMENT VARIABLES
###### EXTERNAL_SERVER_ADDRESS
Gibt die Adresse der `Averbis Health Discovery` im `docker` Netzwerk an. Sollten keine Änderungen an den Einstellungen der `AHD` vorgenommen worden sein,
ist der Port `8080`. Der Standard-Wert für `<EXTERNAL_SERVER_RECOMMENDER>` ist: `http://localhost:8080`.

###### EXTERNAL_SERVER_TOKEN
Die `AHD` benötigt ein Token für API-Zugriffe. Dieses muss entsprechend erst in der `AHD` aktiviert und dann hier hinterlegt werden:
[AHD-Help: API Token](https://help.averbis.com/health-discovery/user-manual/#HealthDiscoveryUserManualVersion6.20-ApplicationInterface:RESTAPI)
Es gibt für diese Variable keine Standard-Einstellung.  
Zu beachten ist, dass die Benutzerin, zu der dieses Token gehört, auch entsprechend dem Projekt zugeordnet ist.

###### PIPELINE_PROJECT
Das
[erstellte Projekt](https://help.averbis.com/health-discovery/user-manual/#HealthDiscoveryUserManualVersion6.20-LogintoHealthDiscoveryandcreateaproject)
in der `AHD` (z.B.: 'GeMTeX')
  
###### PIPELINE_NAME
Die zu verwendende
[Pipeline](https://help.averbis.com/health-discovery/user-manual/#HealthDiscoveryUserManualVersion6.20-PipelineConfiguration)
im o.g. Projekt in der `AHD` (z.B.: 'deid')

###### (deprecated) PIPELINE_ENDPOINT
Mittlerweile wird standardmäßig die von Averbis zur Verfügung gestellte Python-API für die `AHD` benutzt, 
weshalb die explizite Angabe des Endpunkts nicht mehr benötigt wird.
Sollte dennoch im Hintergrund der `JsonProcessor` benutzt werden (siehe Abschnitt 'PROCESSOR' - 
und damit die `AHD` per `requests` angesprochen werden), werden die beiden Variablen `PIPELINE_PROJECT` und `PIPELINE_NAME`
aufgelöst nach:
```
/health-discovery/rest/v1/textanalysis/projects/<PIPELINE_PROJECT>/pipelines/<PIPELINE_NAME>/analyseText
```

###### CONSUMER_CLASS
Diese Variable bestimmt/konfiguriert den `Consumer`, der vorgibt wie die `CAS`/`JSON` Response der `AHD` verarbeitet wird.
Unter `ariadne.contrib.external_server_consumer` sind derzeit zwei `Consumer` implementiert und demzufolge kann `<CONSUMER_CLASS>` einen von zwei Werten annehmen: 
* `SimpleDeidConsumer`: dieser sucht in der Response einfach nach `de.averbis.types.health.`-{'Date', 'Name', 'Age', 'Contact', 'ID', 'Location', 'Profession', 'PHIOther'} Typen
    und schreibt diese Werte in ein in [INCEpTION](https://inception-project.github.io) entsprechend angegebenes [feature](https://inception-project.github.io/releases/31.1/docs/user-guide.html#recommenders_in_getting_started).
* `MappingConsumer`: dieser implementiert das Mapping vom [uima-cas-mapper](https://github.com/medizininformatik-initiative/GeMTeX/tree/main/uima-cas-mapper).
    Ein entsprechendes <MAPPING_FILE> muss hinter dem doppelten Doppelpunkt angegeben werden. Die Mapping files müssen über `docker volumes` zur Verfügung gestellt werden.

Der Standard-Wert für <CONSUMER_CLASS> ist der `SimpleDeidConsumer`, da dieser nicht weiter konfiguriert werden muss.

###### (optional/expert-mode) CLASSIFIER & PROCESSOR
Diese Variablen sollten nicht gesetzt werden und sind nur der Vollständigkeit halber konfigurierbar,
falls es Änderungen in der `AHD` oder der Python-API gibt, die einen kurzfristigen Einstellungspatch benötigen.  
* Mit `CLASSIFIER` kann eine bestimmte Implementation des `external_uima_classifier` erzwungen werden.
Es wird die dot-notierte Schreibweise erwartet (default: `ariadne.contrib.external_uima_classifier.AHDClassifier`).
* `PROCESSOR` kann i.M. zwei Werte annehmen und muss einem String-Wert vom Typ `ariadne.contrib.external_server_consumer.ProcessorType` entsprechen -
derzeit `cas` oder `json` (default: `cas`).

###### SERVER_HANDLE
Das bezeichnet nur den Endpoint unter dem [INCEpTION](https://inception-project.github.io) den Recommender zusammen mit IP und PORT ansprechen kann.
Der Standard-Wert ist `deid_recommender`.

###### MODEL_DIR
Konfiguriert den Ordner unter dem Modelle gespeichert oder von dem Modelle geladen werden.
Nutzt den Standard-Ordner, wenn nicht gesetzt. 

###### RECOMMENDER_WORKERS & RECOMMENDER_ADDRESS
Diese beiden Werte werden an den WSGI Server (`gunicorn`) übergeben und bestimmen mit `WORKERS` wieviele Benutzer*innen gleichzeitig den Recommender verwenden können
und mit `ADDRESS` unter welcher Adresse der Recommender von [INCEpTION](https://inception-project.github.io) erreicht werden kann.

###### DOCKER_MODE
_(default: True)_ Ob das Programm als Docker-Container läuft.  
Wird z.B. (im `AHDClassifier`) dazu genutzt, um zu bestimmen, ob eine `RequestException` bzgl. der Erreichbarkeit der `AHD` abgefangen
und das Programm geschlossen werden soll. Das ermöglicht dann das automatische Neustarten des Docker-Containers. 

### Andere Einstellungen in der docker-compose.yml
##### ports
```
    ports:
      - 5000:5000
```
Hier muss nur sichergestellt werden, dass der PORT mit dem der `<RECOMMENDER_ADDRESS>` übereinstimmt.
##### networks
```
    networks:
      - recommender-network
[...]
networks:
  recommender-network:
    external: true
    name: recommender-network
```
Wie auch immer das `docker` Netzwerk dann jeweils erstellt/behandelt wird; wichtig ist nur, dass alle drei Services im selben Netzwerk sind.
In diesem Beispiel wurde das `recommender-network` Netzwerk mittels des `docker` Clients erstellt und zudem in den entsprechenden `docker compose` Dateien der `AHD` und `INCEpTION` auch als `external: true` hinzugefügt.
Die entsprechenden IP-Adressen (für `<EXTERNAL_SERVER_ADDRESS>` und zur Referenz des `Recommenders` in `INCEpTION`) können mit `docker inspect recommender-network` abgelesen werden, wenn alle Services gestartet sind.
(Oder man weist den Services statische IPs zu, was im Zweifel in der `docker` Dokumentation nachgelesen werden kann.)
##### volumes
```
    volumes:
      - type: bind
        source: ../uima_cas_mapper/mapping-files
        target: /mapping_files
```
Wenn für `<CONSUMER_CLASS>` der ``MappingConsumer`` verwendet wird, braucht es eine Mapping Datei die mit `<MAPPING_FILE>` angegeben wird.
Dabei müssen dann die entsprechenden Dateien dem ``docker`` Container zur Verfügung gestellt werden (`source`) und `<MAPPING_FILE>` dann relativ zu `target` spezifiziert werden.
Anhand des Beispiels und einer Mapping Datei `../uima_cas_mapper/mapping-files/deid_mapping_singlelayer.json` wäre ``<MAPPING_FILE>`` dann als `/mapping-files/deid_mapping_singlelayer.json` anzugeben.  
Der Recommender `docker` Container (wenn das `RECOMMENDER_WORKDIR` in der `docker` Datei nicht geändert wird) beinhaltet aber auch zwei vorgefertigte Mapping Dateien unter `/inception_ahd_recommender/prefab-mapping-files`:
* `deid_mapping_singlelayer.json`
* `deid_mapping_multilayer.json`

Eine von denen kann dann auch mit ``<MAPPING_FILE>``=`/inception_ahd_recommender/prefab-mapping-files/<FILE>` referenziert werden.

## Entwicklung
### Versionsupdate
Wenn eine neue Version des Recommenders veröffentlicht werden soll, muss die Datei `VERSION` geändert werden
(dadurch wird der entsprechende workflow getriggert, sobald die Veränderung auf den `main` branch kommt → siehe `.github/workflows/ci_ahd_recommender.yaml`).
Bitte beachten, dass dann auch das version tag Suffix in der `docker-compose.yml` angepasst wird:
```
services:
  ahd-deid-recommender:
    image: ghcr.io/medizininformatik-initiative/gemtex/inception-ahd-recommender:1.2.3
  [...]
```