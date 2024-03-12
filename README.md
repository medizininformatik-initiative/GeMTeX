# GeMTeX

Dieses Repositorium umfasst  Arbeiten (Code u.a.) zum Projekt [GeMTeX](https://www.smith.care/de/gemtex_mii/ueber-gemtex/), 
die nicht gut im Projekt-[Confluence](https://confluence.imi.med.fau.de) abgelegt werden können.

### `cda-transform`
Eine Demo/Machbarkeitsnachweis wie CDA Dokumente Level One über XSLT Sytlesheets in HTML oder Plain-Text gewandelt werden können.

### `inception-reporting-dashboard`
Der Dashboard generiert verschiedene Diagramme für ein INCEpTION-Projekt. In seiner aktuellen Form kann er vom Projektmanager vor Ort verwendet werden, um verschiedene Metriken bezüglich des Fortschritts des Projekts und der Art der Annotationen zu visualisieren. Diese können dann exportiert und an ein die zentrale Projectleitung geschickt werden. Die Projectleitung kann dann anhand des Dashboards den Fortschritt der Projekte an den unterschiedlichen Standorten vergelichen und nachvollziehen.

### `inception-projects`
Beinhaltet exportierte Basis-Projekte (also im Grunde Konfigurationen der Layer etc.) für
[INCEpTION](https://inception-project.github.io/), die von den einzelnen Standorten in ihre jeweilige
[INCEpTION](https://inception-project.github.io/)-Instanz importiert werden können.
Wenn nicht anders vermerkt, sind darin keine Dokumente vorhanden.

### `inception_ahd_recommender`
Ein Recommender basierend auf dem [External INCEpTION Recommender](https://github.com/inception-project/inception-external-recommender), um in [INCEpTION](https://inception-project.github.io/) Annotationsvorschläge
der [Averbis Health Discovery](https://averbis.com/health-discovery/) zu generieren. 

### `uima_cas_mapper`
Ein `Python`-Programm um `xmi` im
[UIMA-CAS](https://uima.apache.org/)-Format von einem Typensystem in ein anderes umzuschreiben (z.B. die Exporte der
Analysen der
[Averbis Health Discovery](https://averbis.com/health-discovery/) in eine Layer-Modellierung in
[INCEpTION](https://inception-project.github.io/)).
Dabei werden die entsprechenden Mapping-Anweisungen im `json`-Format angegeben. Eine genauere Beschreibung ist
[Unterverzeichnis](https://github.com/medizininformatik-initiative/GeMTeX/blob/main/uima_cas_mapper/README.md) zu finden.


### Hinweis
Änderungen am ``main`` branch dieses Repositoriums sind nur durch einen entsprechenden ``pull request`` durchführbar.
