# Inception Reporting Dashboard
https://github.com/inception-project/inception-reporting-dashboard

## Installation

```commandline
docker build --build-arg VERSION=VERSION_NR -t inception-project/inception-dashboard:VERSION_NR .
```
* `VERSION_NR` entsprechend der aktuellen Release Version des Dashboards angeben

###### Manager
```commandline
docker compose -f docker-compose-manager.yml up
```
* `VERSION` müsste noch in `docker-compose-manager.yml` angepasst werden.

``Docker``
```commandline
docker run -p 9011:8501 --name inception-dashboard-manager inception-project/inception-dashboard:VERSION --manager
```
Erstellt ein Container mit dem Namen ``inception-dashboard-manager``,
der das Manager Dashboard auf Port ``9011`` zur Verfügung stellt.

###### Lead
``Docker Compose``
```commandline
docker compose -f docker-compose-lead.yml up
```
* `VERSION` müsste noch in `docker-compose-lead.yml` angepasst werden.  

``Docker``
```commandline
docker run -p 9012:8501 --name inception-dashboard-lead inception-project/inception-dashboard:VERSION --lead
```
Erstellt ein Container mit dem Namen ``inception-dashboard-lead``,
der das Lead Dashboard auf Port ``9012`` zur Verfügung stellt.

### Anderes

``Volumes`` müssten je nach Bedarf individuell eingestellt werden,
um die Projekt-Exporte dem lokalen Dateisystem zur Verfügung zu stellen.
