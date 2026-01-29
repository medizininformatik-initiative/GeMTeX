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
  annotation:
  filterFile: ./filter_phrases.txt
  domainFilterConcepts: 308916002;276339004;419891008;246061005;900000000000442005;900000000000454005;416698001;106237007;370136006;762947003;48176007;372148003;14679004;415229000;108334009;370115009;363743006;254291000;273249006;78621006;276825009;362981000;243796009
```
``protocol`` und ``port`` müssen im Standardfall nicht geändert werden. Falls sich der Recommender und der IDLogik Server in einer ``Docker``-Umgebung befinden, müsste `host` aber auch angepasst werden.
``licence`` muss zwangsläufig beim Start des Services als `property` übergeben werden (z.B. als ``command line option``):  
``filterFile`` Zeigt auf eine Textdatei, die reguläre Ausdrücke enthält, die nicht annotiert werden sollen:
Beispiele:
Der Ausdruck ``[0-9.:-/]*`` ignoriert alle Kombinationen aus Zahlen und den Zeichen ``.:-/``; damit werden einzelne Zahlen 
aber auch Uhrzeiten und Datumsangaben erfasst. Der Ausdruck ``[A-Z][0-9.-]*`` matcht ICD-10 Codes. Hinweis: OPS Codes werden 
durch den vorherigen regulären Ausdruck abgebildet.
``domainFilterConcepts`` Enthält eine Semikolon-getrennte Liste von SNOMED CT-Konzepten, die inkl. deren Subkonzepte als Filter verwendet werden sollen. D.h. diese Konzepte sind Concepte deren komplette Hierarchie als Filter verwendet werden soll.

| Name | Index | Bemerkung |
|------|-------|-------|
|environment / location|308916002||
|Environment|276339004||
|geographic location|-|in location enthalten|
|record artifact|419891008||
|Situation|-|nicht gefunden|
|Attribute|246061005||
|core metadata concept|900000000000442005||
|foundation metadata concept|900000000000454005||
|link assertion|416698001||
|linkage concept|106237007||
|namespace concept|370136006||
|OWL metadata concept|762947003||
|social concept|48176007|eigentlich social context|
|ethnic group|372148003||
|life style|-|nicht gefunden|
|Occupation|14679004||
|racial group|415229000||
|religion/philosophy|108334009|in social context enthalten|
|special concept|370115009||
|inactive concept|-|nicht gefunden|
|navigational concept|363743006||
|staging and scales|254291000||
|staging scale|-|in staging and scales enthalten|
|assessment scale|273249006||
|tumor staging|-|in staging and scales enthalten|
|physical Force|78621006||
|overlapping site|276825009||
|action|362981000|qualifier value|
|situation with explicit context|243796009||
#### Java
```
java -jar IDLOGIK_RECOMMENDER.jar --idlogik.licence=LICENCE_KEY
```
So kann bei bedarf auch der ``Host``/``Port`` konfiguriert werden.
#### Docker Beispiel
````
docker run --network NETWORK_NAME ghcr.io/medizininformatik-initiative/gemtex/inception-idlogik-recommender:0.1.2 --idlogik.licence=LICENCE --idlogik.host=IDLOGIK_DOCKER_NETWORK_IP
````
**Bitte beachten**, dass die Angaben für ``--idlogik.licence``, ``--idlogik.host`` etc. nach dem Namen des Images stehen (das wird dem Container übergeben) und die Angaben ``--network`` oder ``--name`` (wenn man zur einfacheren Referenzierung einen statischen Namen für den Container vergeben will) vor den Namen des Images kommen!

###### NETWORK_NAME
Name des Docker-Netzwerks in dem sich der IDLogik Server und INCEpTION befinden.

###### LICENCE
Lizenz-Key für den IDLogik Server.
Unter Umständen muss dieser mit einfachen Anführungszeichen (`'`) umschlossen werden, da sich im Key Zeichen befinden können, die zu Problemen führen könne (z.B.: `|`).

###### IDLOGIK_DOCKER_NETWORK_IP
Die IP der IDLogik im Netzwerk (``NETWORK_NAME``).
