# Averbis Health Discovery Konfigurationen
Konfigurationen können per 
``PUT`` ``/rest/v1/textanalysis/projects/{projectName}/pipelines/{pipelineName}/configuration`` angepasst werden.
### ``gemtex_deid_custom_title``
* Hinzugefügt: ``WordListAnnotator`` + ``RutaEngine`` um einen neuen Typen zu erkennen `de.averbis.types.health.PHINameTitle`
  (entsprechendes Mapping muss in der Mappingfile definiert werden; bei `deid_mapping_singlelayer.json` schon als `NAME_TITLE` geschehen)