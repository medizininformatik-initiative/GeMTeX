# INCEpTION Projekte
Konfigurationen für [INCEpTION](https://inception-project.github.io/) in Form exportierter Projekte.

## De-Identifikation

### 1. Version Annotation (01.03.2024) - `inception-gemtex-deid-base_project`

* [Annotationguide: De-Identifikations-Guide (V2)](https://confluence.imi.med.fau.de/display/GEM/De-Identifikation)
    (V1 wurde an die technische Umsetzung der Annotation angepasst, deswegen neue Version.)
* [Vorkonfiguriertes INCEpTION-Projekt](https://github.com/medizininformatik-initiative/GeMTeX/blob/main/inception-projects/inception-gemtex-deid-base_project-grascco_raw.zip)
  * Enthält die durch die `deid`-Pipeline der [Averbis Health Discovery](https://averbis.com/health-discovery/) vorannotierten Dokumente des [`GraSSCo`-Korpus'](https://zenodo.org/records/6539131).¹
  * Einzelne [Layer-Datei](TODO)
  * Kein Recommender

### 2. Version Annotation (27.03.2024) - `inception-gemtex-deid-base_project-grascco_raw`
Eine Layer-Definition, die auf Grundlage des aktuellen
[De-Identifikations-Guide](https://confluence.imi.med.fau.de/display/GEM/De-Identifikation) erstellt wurde.
Enthält außerdem unannotierte ("leere") Dateien des [`GRASSCO`-Korpus'](https://zenodo.org/records/6539131).¹
(Sinnvoll, wenn ein Recommender Ansatz benutzt werden soll.)

  * [Annotationsguide: De-Identifikations-Guide (V3)](https://confluence.imi.med.fau.de/display/GEM/De-Identifikation?preview=/246041156/278954276/GeMTeX_20240327_de-identifikation_guide.pdf)
    * Erweiterung des Annotations-Schema bzw. Definition der Layer: Alter, Beruf, Titel von Namen
    * Beispiele und Abgrenzung zwischen Definitionen
  * Enthält die durch die Dokumente des [`GraSSCo`-Korpus'](https://zenodo.org/records/6539131) nur als plain text. 
  * Einzelne [Layer-Datei](TODO)
  * Recommender sollte eingestellt sein.

## Verweise
[1] Modersohn L, Schulz S, Lohr C, Hahn U.
GraSSCo - _The First Publicly Shareable, Multiply-Alienated German Clinical Text Corpus_.
Stud Health Technol Inform. 2022 Aug 17;296:66-72. doi: [10.3233/SHTI220805](https://ebooks.iospress.nl/doi/10.3233/SHTI220805). [PMID: 36073490](https://pubmed.ncbi.nlm.nih.gov/36073490/). [Data: https://zenodo.org/records/6539131](https://zenodo.org/records/6539131)
