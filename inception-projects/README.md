# INCEpTION Projekte
Konfigurationen für [INCEpTION](https://inception-project.github.io/) in Form exportierter Projekte.

### `inception-gemtex-deid-base_project`
Eine Layer-Definition, die auf Grundlage der ersten Version der
[De-Identifikations-Annotationsleitlinien (v2)](https://confluence.imi.med.fau.de/display/GEM/De-Identifikation) erstellt wurde.
Enthält außerdem die durch die `deid`-Pipeline der
[Averbis Health Discovery](https://averbis.com/health-discovery/) vorannotierten Dokumente des [`GRASCCO`-Korpus'](https://zenodo.org/records/6539131).¹

### `inception-gemtex-deid-base_project-grascco_raw`
Konfiguriertes Projekt, dass auf Grundlage des 
[De-Identifikations-Guide (V3.3. 10.06.2024)](https://confluence.imi.med.fau.de/display/GEM/De-Identifikation) erstellt wurde. Enthält nicht annotierte _("leere")_ Dateien des [`GRASCCO`-Korpus'](https://zenodo.org/records/6539131)¹ (für Recommender-Ansatz).  
_(letztes Update: 12.07.2024)_

### Layers / Annotationsschemata

#### Hinweis
* Die Dateien der Layer bzw. die Definition der Annotation sind nicht in exportierten Projekten enthalten.
* Layer müssen separat aus vorhandenen Layer-Konfigurationen eingestellt oder importiert werden.
* Einstellungen in `Layers` &rarr; `Import` &rarr; `layer.json` &rarr; `Save` ([siehe Dokumentation INCEpTION](https://inception-project.github.io/releases/33.2/docs/user-guide.html#layers_and_features_in_getting_started))

#### Layer-Dateien

###### Layer für PHI-Annotation
* Version 1: [v1_PHI_layer.json](layers/v1_PHI_layer.json)
* **Version 1.1**: [v1.1_PHI_layer.json](layers/v1.1_PHI_layer.json) **(Aktualisierung 6.12.2024)**
  * Erweiterung mit `DATE_BIRTH` und `DATE_DEATH`
* **Version 1.2**: [v1.2_PHI_layer.json](layers/v1.1_PHI_layer.json) **(Aktualisierung 17.12.2024)**
  * Korrektur Beschreibung bzgl. `DATE`
  * Entfernung `NAME_OTHER`
* Hinweis für Integration neuer Layer-Einstellung in INCEpTION:
  * Einstellungen öffnen: `Layers` &rarr; (bestehendes) `PHI`-Layer auswählen &rarr; `Import` &rarr; `v1.1_PHI_layer.json` &rarr; `Save`
  * Alternative Einstellung in INCEpTION über `Tagsets` der jeweiligen Typen `DATE_BIRTH` und `DATE_DEATH`
    * `phiKind` --> `Tags` --> `Create` --> Name und Description eingeben --> `Save`

## Verweise
[1] Modersohn L, Schulz S, Lohr C, Hahn U.
GRASCCO - _The First Publicly Shareable, Multiply-Alienated German Clinical Text Corpus_.
Stud Health Technol Inform. 2022 Aug 17;296:66-72. doi: [10.3233/SHTI220805](https://ebooks.iospress.nl/doi/10.3233/SHTI220805). [PMID: 36073490](https://pubmed.ncbi.nlm.nih.gov/36073490/). [Data: https://zenodo.org/records/6539131](https://zenodo.org/records/6539131)
