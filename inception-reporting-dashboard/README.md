# Inception Reporting Dashboard
https://github.com/inception-project/inception-reporting-dashboard

## Installation

```commandline
docker build -t inception-project/inception-dashboard:VERSION .
```

###### Manager
```commandline
docker compose -f docker-compose-manager.yml up
```
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
``Docker``
```commandline
docker run -p 9012:8501 --name inception-dashboard-lead inception-project/inception-dashboard:VERSION --lead
```
Erstellt ein Container mit dem Namen ``inception-dashboard-lead``,
der das Lead Dashboard auf Port ``9012`` zur Verfügung stellt.

### Anderes

``Volumes`` müssten je nach Bedarf individuell eingestellt werden,
um die Projekt-Exporte dem lokalen Dateisystem zur Verfügung zu stellen.
