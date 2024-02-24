# GeMTeX

Dieses Repositorium umfasst  Arbeiten (Code u.a.) zum Projekt [GeMTeX](https://www.smith.care/de/gemtex_mii/ueber-gemtex/), 
die nicht gut im Projekt [Confluence](https://confluence.imi.med.fau.de) abgelegt werden können.

### `inception-projects`
Beinhaltet exportierte Basis-Projekte (also im Grunde Konfigurationen der Layer etc.) für
[INCEpTION](https://inception-project.github.io/), die von den einzelnen Standorten in ihre jeweilige
[INCEpTION](https://inception-project.github.io/)-Instanz importiert werden können.
Wenn nicht anders vermerkt, sind darin keine Dokumente vorhanden.

### `uima-cas-mapper`
Ein `Python`-Programm um `xmi` im
[UIMA-CAS](https://uima.apache.org/)-Format von einem Typensystem in ein anderes umzuschreiben (z.B. die Exporte der
Analysen der
[Averbis Health Discovery](https://averbis.com/health-discovery/) in eine Layer-Modellierung in
[INCEpTION](https://inception-project.github.io/)).
Dabei werden die entsprechenden Mapping-Anweisungen im `json`-Format angegeben. Eine genauere Beschreibung ist
Unterverzeichnis zu finden.

### `cda-transform`
Eine Demo/Machbarkeitsnachweis wie CDA Dokumente Level One über XSLT Sytlesheets in HTML oder Plain-Text gewandelt werden können.
