# ID Logik Lookup Recommender

Dieses Projekt stellt einen Recommender für INCEpTION in Form einer Spring Boot Application bereit.  
Der Recommender bildet dann die Schnittstelle zwischen INCEpTION und dem ID Logik Server um Terme bzgl. SNOMED zu grounden.
Die fraglichen Terme müssen entweder selbst händisch oder durch eine andere Software (vgl. Averbis Health Discovery) automatisch annotiert werden.  

### Installation
Die Recommender-``jar`` kann selbständig mittels Maven (``mvn package``) erstellt werden.  
Es existiert aber auch ein [Docker-Image](https://github.com/medizininformatik-initiative/GeMTeX/pkgs/container/gemtex%2Finception-idlogik-recommender),
bzw. kann die vorhandene ``Dockerfile`` benutzt werden, um ein Image selbst zu bauen. 

### Konfiguration
Standard Konfiguration in `resources/application.yml`:
```
idlogik:
  protocol: http
  host: localhost
  port: 7777
  licence:
```
``protocol`` und ``port`` müssen im Standardfall nicht geändert werden. Falls sich der Recommender und der IDLogik Server in einer ``Docker``-Umgebung befinden, müsste `host` aber auch angepasst werden.
``licence`` muss zwangsläufig beim Start des Services als `property` übergeben werden (z.B. als ``command line option``):  
#### Java
```
java -jar IDLOGIK_RECOMMENDER.jar --idlogik.licence=LICENCE_KEY
```
So kann bei bedarf auch der ``Host``/``Port`` konfiguriert werden.
#### Docker Beispiel
````
docker run --network NETWORK_NAME ghcr.io/medizininformatik-initiative/gemtex/inception-idlogik-recommender:0.1.1 --idlogik.licence=LICENCE --idlogik.host=IDLOGIK_DOCKER_NETWORK_IP
````
**Bitte beachten**, dass die Angaben für ``--idlogik.licence``, ``--idlogik.host`` etc. nach dem Namen des Images stehen (das wird dem Container übergeben) und die Angaben ``--network`` oder ``--name`` (wenn man zur einfacheren Referenzierung einen statischen Namen für den Container vergeben will) vor den Namen des Images kommen!

###### NETWORK_NAME
Name des Docker-Netzwerks in dem sich der IDLogik Server und INCEpTION befinden.

###### LICENCE
Lizenz-Key für den IDLogik Server.
Unter Umständen muss dieser mit einfachen Anführungszeichen (`'`) umschlossen werden, da sich im Key Zeichen befinden können, die zu Problemen führen könne (z.B.: `|`).

###### IDLOGIK_DOCKER_NETWORK_IP
Die IP der IDLogik im Netzwerk (``NETWORK_NAME``).
