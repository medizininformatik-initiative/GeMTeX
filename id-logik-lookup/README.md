# ID Logik Lookup Recommender

Dieses Projekt stellt einen Recommender für INCEpTION in Form einer Spring Boot Application bereit.  
Der Recommender bildet dann die Schnittstelle zwischen INCEpTION und dem ID Logik Server um Terme bzgl. SNOMED zu grounden.

### Installation
_ToDo_

### Konfiguration
Standard Konfiguration:
```
idlogik:
  protocol: http
  host: localhost
  port: 7777
  licence:
```
``licence`` muss beim Start des Services als `property` übergeben werden (z.B. als ``command line option``):  
```
java -jar IDLOGIK_RECOMMENDER.jar --idlogik.licence=LICENCE_KEY
```
So kann bei bedarf auch der Host/Port konfiguriert werden. 

### Anderes
_ToDo_
