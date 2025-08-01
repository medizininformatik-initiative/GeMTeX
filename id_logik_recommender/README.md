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
annotation:
  filterFile:
```
* ``protocol`` und ``port`` müssen im Standardfall nicht geändert werden. Falls sich der Recommender und der IDLogik Server in einer ``Docker``-Umgebung befinden, müsste `host` aber auch angepasst werden.
* ``licence`` muss zwangsläufig beim Start des Services als `property` übergeben werden (z.B. als ``command line option`` siehe Beispiele - Java weiter unten).  
* ``filterFile`` Zeigt auf eine Textdatei, die reguläre Ausdrücke enthält, die nicht annotiert werden sollen:  
  * ``\b[0-9]{1,2}[.][0-9]{1,2}[.][0-9]{2,4}``, ``\b[0-9]{1,2}[:][0-9]{1,2}[:]{0,1}[0-9]{1,2}`` ignoriert alle Kombinationen für Uhrzeiten und Datumsangaben.
  * ``\b[A-Z][0-9]{2}[.]{0,1}[0-9,-]{0,2}`` matcht ICD-10 Codes. Hinweis: OPS Codes werden 
  durch den vorherigen regulären Ausdruck abgebildet.

#### Beispiele
##### Java
```
java -jar IDLOGIK_RECOMMENDER.jar --idlogik.licence=LICENCE_KEY
```
So kann bei bedarf auch der ``Host``/``Port`` konfiguriert werden.
##### Docker
````
docker run --network NETWORK_NAME ghcr.io/medizininformatik-initiative/gemtex/inception-idlogik-recommender:0.2.3 --idlogik.licence=LICENCE --idlogik.host=IDLOGIK_DOCKER_NETWORK_IP
````
**Bitte beachten**, dass die Angaben für ``--idlogik.licence``, ``--idlogik.host`` etc. nach dem Namen des Images stehen (das wird dem Container übergeben) und die Angaben ``--network`` oder ``--name`` (wenn man zur einfacheren Referenzierung einen statischen Namen für den Container vergeben will) vor den Namen des Images kommen!

###### NETWORK_NAME
Name des Docker-Netzwerks in dem sich der IDLogik Server und INCEpTION befinden.

###### LICENCE
Lizenz-Key für den IDLogik Server.
Unter Umständen muss dieser mit einfachen Anführungszeichen (`'`) umschlossen werden, da sich im Key Zeichen befinden können, die zu Problemen führen könne (z.B.: `|`).

###### IDLOGIK_DOCKER_NETWORK_IP
Die IP der IDLogik im Netzwerk (``NETWORK_NAME``).

### Anderes
Es wird ein Standard "FilterFile" mitgeliefert, dass sowohl in der ``application.yml``
wie auch im ``docker`` build Prozess referenziert wird und Anwendung findet.
Soll im ``docker`` Kontext eine anderes "FilterFile" verwendet werden,
muss das über ein entsprechendes ``volume`` nebst eigener Konfiguration zur Verfügung gestellt werden.
