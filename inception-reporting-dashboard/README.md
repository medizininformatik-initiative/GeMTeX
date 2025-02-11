# Inception Reporting Dashboard
https://github.com/inception-project/inception-reporting-dashboard

## Installation

```commandline
docker build --build-arg VERSION=VERSION_NR -t inception-project/inception-dashboard:VERSION_NR .
```
* `VERSION_NR` entsprechend der aktuellen Release Version des Dashboards angeben

###### Manager
``Docker Compose``
```commandline
docker compose -f docker-compose-manager.yml up
```
* `VERSION` & `REPOSITORY_NAME` müsste noch in `docker-compose-manager.yml` angepasst werden.

``Docker``
```commandline
docker run -p 9011:8501 --name inception-dashboard-manager REPOSITORY_NAME/inception-dashboard:VERSION --manager
```
Erstellt ein Container mit dem Namen ``inception-dashboard-manager``,
der das Manager Dashboard auf Port ``9011`` zur Verfügung stellt.

###### Lead
``Docker Compose``
```commandline
docker compose -f docker-compose-lead.yml up
```
* `VERSION` & `REPOSITORY_NAME` müsste noch in `docker-compose-lead.yml` angepasst werden.  

``Docker``
```commandline
docker run -p 9012:8501 --name inception-dashboard-lead REPOSITORY_NAME/inception-dashboard:VERSION --lead
```
Erstellt ein Container mit dem Namen ``inception-dashboard-lead``,
der das Lead Dashboard auf Port ``9012`` zur Verfügung stellt.

### Anderes

Je nachdem, ob das Image manuell mit den hier angegebenen Parametern erstellt wurde oder ob das gehostete Image verwendet wird,
muss in den zur Verfügung gestellten `compose` Dateien der `REPOSITORY_NAME` geändert werden:
* `manuell`: `inception-project`
* `gehostet`: `ghcr.io/medizininformatik-initiative/gemtex`

``Volumes`` müssten je nach Bedarf individuell eingestellt werden,
um die Projekt-Exporte dem lokalen Dateisystem zur Verfügung zu stellen.
