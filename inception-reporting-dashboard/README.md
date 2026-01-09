# Inception Reporting Dashboard
https://github.com/inception-project/inception-reporting-dashboard  
VERSION [aktuell]: `0.9.7`

## Installation

```commandline
docker build --build-arg VERSION=0.9.7 -t inception-project/inception-dashboard:0.9.7 .
```

###### Manager
``Docker Compose``
```commandline
[REPOSITORY_NAME=REPO_NAME VERSION=VERSION] docker compose -f docker-compose-manager.yml up
```
* `[Optional]`: REPO_NAME (s. "Anderes"); default: ``ghcr.io/medizininformatik-initiative/gemtex``
* `[Optional]`: VERSION (s. "Anderes"); default: ``0.9.7``

``Docker``
```commandline
docker run -p 9011:8501 --name inception-dashboard-manager REPO_NAME/inception-dashboard:0.9.7 --manager
```
* `Zwingend`: REPO_NAME (s. "Anderes")

Erstellt ein Container mit dem Namen ``inception-dashboard-manager``,
der das Manager Dashboard auf Port ``9011`` zur Verfügung stellt.

###### Lead
``Docker Compose``
```commandline
[REPOSITORY_NAME=REPO_NAME VERSION=VERSION] docker compose -f docker-compose-lead.yml up
```
* `[Optional]`: REPO_NAME (s. "Anderes"); default: ``ghcr.io/medizininformatik-initiative/gemtex``
* `[Optional]`: VERSION (s. "Anderes"); default: ``0.9.5``

``Docker``
```commandline
docker run -p 9012:8501 --name inception-dashboard-lead REPO_NAME/inception-dashboard:0.9.7 --lead
```
* `Zwingend`: REPO_NAME (s. "Anderes")  

Erstellt ein Container mit dem Namen ``inception-dashboard-lead``,
der das Lead Dashboard auf Port ``9012`` zur Verfügung stellt.

### Anderes

#### Environment Variables

###### REPO_NAME
Je nachdem, ob das Image manuell mit den hier angegebenen Parametern erstellt wurde oder ob das gehostete Image verwendet wird,
muss/kann der Name des Repositoriums `REPO_NAME` angegeben werden:
* `manuell`: `inception-project`
* `gehostet`: `ghcr.io/medizininformatik-initiative/gemtex`

###### VERSION
Die Version ist standardmäßig immer die, die am Anfang der README angegeben ist.  
Bei Bedarf kann diese aber - wie das Repositorium - angepasst werden.

##### Volumes
``Volumes`` müssten je nach Bedarf individuell eingestellt werden,
um die Projekt-Exporte dem lokalen Dateisystem zur Verfügung zu stellen.
