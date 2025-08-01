# GeMTeX

Dieses Repositorium umfasst  Arbeiten (v.a. Code) zum Projekt [GeMTeX](https://www.smith.care/de/gemtex_mii/ueber-gemtex/), 
die nicht gut im Projekt-[Confluence](https://confluence.imi.med.fau.de) abgelegt werden können.

### [`averbis-custom-configs`](https://github.com/medizininformatik-initiative/GeMTeX/tree/main/averbis-custom-configs)
Verschiedene Konfigurationen (`json` Format), mit denen `AHD` Pipelines angepasst werden können.

### [`id_logik_recommender`](https://github.com/medizininformatik-initiative/GeMTeX/tree/main/id_logik_recommender)
__(Als Docker Image verfügbar: `docker pull ghcr.io/medizininformatik-initiative/gemtex/inception-idlogik-recommender:0.2.3`)__  
Ein in ``java`` implementierter Recommender für [INCEpTION](https://inception-project.github.io/) als Schnittstelle zum [IDLogik-Server](https://www.id-berlin.de/produkte/nlp-forschung/id-logik/).

### [`inception-projects`](https://github.com/medizininformatik-initiative/GeMTeX/tree/main/inception-projects)
Beinhaltet exportierte Basis-Projekte (also im Grunde Konfigurationen der Layer etc.) für
[INCEpTION](https://inception-project.github.io/), die von den einzelnen Standorten in ihre jeweilige
[INCEpTION](https://inception-project.github.io/)-Instanz importiert werden können.
Wenn nicht anders vermerkt, sind darin keine Dokumente vorhanden.

### [`inception-reporting-dashboard`](https://github.com/medizininformatik-initiative/GeMTeX/tree/main/inception-reporting-dashboard)
__(Als Docker Image verfügbar: `docker pull ghcr.io/medizininformatik-initiative/gemtex/inception-dashboard:0.9`)__  
Das Dashboard generiert verschiedene Diagramme für ein [INCEpTION](https://inception-project.github.io/)-Projekt. In seiner aktuellen Form kann es vom Projektmanager vor Ort verwendet werden, um verschiedene Metriken bezüglich des Fortschritts des Projekts und der Art der Annotationen zu visualisieren. Diese können dann exportiert und an die zentrale Projektleitung geschickt werden. Die Projektleitung kann dann anhand des Dashboards den Fortschritt der Projekte an den unterschiedlichen Standorten vergleichen und nachvollziehen.

### [`inception_ahd_recommender`](https://github.com/medizininformatik-initiative/GeMTeX/tree/main/inception_ahd_recommender)
__(Als Docker Image verfügbar: `docker pull ghcr.io/medizininformatik-initiative/gemtex/inception-ahd-recommender:1.4.2`)__  
Ein Recommender basierend auf dem [External INCEpTION Recommender](https://github.com/inception-project/inception-external-recommender), um in [INCEpTION](https://inception-project.github.io/) Annotationsvorschläge
der [Averbis Health Discovery](https://averbis.com/health-discovery/) zu generieren. 

### [`scripts`](https://github.com/medizininformatik-initiative/GeMTeX/tree/main/scripts)
Ordner für verschiedene Skripte/Demos.
* [`cda-transform`](https://github.com/medizininformatik-initiative/GeMTeX/tree/main/scripts/cda-transform)  
Eine Demo bzw. Machbarkeitsnachweis wie CDA Dokumente Level One über XSLT Stylesheets in HTML oder Plain-Text gewandelt werden können.
* [`health-discovery-scripts`](https://github.com/medizininformatik-initiative/GeMTeX/tree/main/scripts/health-discovery-scripts)  
Python-Skripte um die [Averbis Health Discovery](https://averbis.com/health-discovery/) per API anzusprechen.

### [`uima_cas_mapper`](https://github.com/medizininformatik-initiative/GeMTeX/tree/main/uima_cas_mapper)
Ein `Python`-Programm um `xmi` im
[UIMA-CAS](https://uima.apache.org/)-Format von einem Typensystem in ein anderes umzuschreiben (z.B. die Exporte der
Analysen der
[Averbis Health Discovery](https://averbis.com/health-discovery/) in eine Layer-Modellierung in
[INCEpTION](https://inception-project.github.io/)).
Dabei werden die entsprechenden Mapping-Anweisungen im `json`-Format angegeben. Eine genauere Beschreibung ist im
[Unterverzeichnis](https://github.com/medizininformatik-initiative/GeMTeX/blob/main/uima_cas_mapper/README.md) zu finden.


### Hinweis
Änderungen am ``main`` branch dieses Repositoriums sind nur durch einen entsprechenden ``pull request`` durchführbar.  
Fragen oder Anmerkungen zum Repositorium bitte an: franz.matthies@imise.uni-leipzig.de
