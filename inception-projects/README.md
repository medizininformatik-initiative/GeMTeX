# INCEpTION Projekte
Konfigurationen für [INCEpTION](https://inception-project.github.io/) in Form exportierter Projekte.

### `inception-gemtex-deid-base_project`
Eine Layer-Definition, die auf Grundlage des aktuellen
[De-Identifikations-Guide](https://confluence.imi.med.fau.de/display/GEM/De-Identifikation) (v2) erstellt wurde.
Enthält außerdem die durch die `deid`-Pipeline der
[Averbis Health Discovery](https://averbis.com/health-discovery/) vorannotierten Dokumente des [`GRASSCO`-Korpus'](https://zenodo.org/records/6539131).¹

### `inception-gemtex-deid-base_project-grascco_raw`
* Konfiguriertes Projekt mit auf Grundlage des aktuellen
[De-Identifikations-Guide (V3.3. 10.06.2024)](https://confluence.imi.med.fau.de/display/GEM/De-Identifikation) erstellt wurde.
* Enthält unannotierte ("leere") Dateien des [`GRASSCO`-Korpus'](https://zenodo.org/records/6539131)¹ (für Recommender-Ansatz).
* letztes Update: 12.07.2024

### Layers / Annotationsschemata

#### Hinweis
* Layer bzw. die Definition der Annotation sind nicht in exportierten Projekten enthalten.
* Layer müssen seprart aus vorhandenen Layer-Konfigurationen eingestellt oder importiert werden.
* Einstellungen in `Layers` &rarr; `import` &rarr; `layer.json`
* [Siehe Dokumentation INCEpTION](https://inception-project.github.io/releases/33.2/docs/user-guide.html#layers_and_features_in_getting_started)

#### Layer-Dateien
* [PHI_layer.json](layers/PHI_layer.json) (Layer für PHI-Annotation)


## Verweise
[1] Modersohn L, Schulz S, Lohr C, Hahn U.
GRASCCO - _The First Publicly Shareable, Multiply-Alienated German Clinical Text Corpus_.
Stud Health Technol Inform. 2022 Aug 17;296:66-72. doi: [10.3233/SHTI220805](https://ebooks.iospress.nl/doi/10.3233/SHTI220805). [PMID: 36073490](https://pubmed.ncbi.nlm.nih.gov/36073490/). [Data: https://zenodo.org/records/6539131](https://zenodo.org/records/6539131)
