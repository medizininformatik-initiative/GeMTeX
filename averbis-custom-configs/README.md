# Averbis Health Discovery Konfigurationen
Konfigurationen können per 
``PUT`` ``/rest/v1/textanalysis/projects/{projectName}/pipelines/{pipelineName}/configuration`` angepasst werden.
### ``gemtex_deid_custom_title``
* Hinzugefügt: ``WordListAnnotator`` + ``RutaEngine`` um einen neuen Typen zu erkennen `de.averbis.types.health.PHINameTitle`
  (entsprechendes Mapping muss in der Mappingfile definiert werden; bei `deid_mapping_singlelayer.json` schon als `NAME_TITLE` geschehen)

##### Achtung
Der Eintrag für den PHI-Annotator muss eventuell angepasst werden, wenn die AHD Version noch < 7.0.0 ist (oder die Pipeline nicht startet).
Bei den ``parameters`` muss dann der Eintrag `useTransformer` entfernt werden:
```
{
  "identifier": "PHI",
  "displayName": "PHI",
  "bundle": "de.averbis.textanalysis.health-discovery-textanalysis-plugin",
  "parameters": [
    {
      "key": "PHIAnnotator/useRules",
      "values": [
        "false"
      ]
    },
    {
      "key": "PHIAnnotator/useLSTM",
      "values": [
        "true"
      ]
    },
==> {
      "key": "PHIAnnotator/useTransformer",
      "values": [
        "false"
      ]
    }, <==
    {
      "key": "PHIAnnotator/detectPHISentences",
      "values": [
        "false"
      ]
    },
    {
      "key": "PHIDeidentifier/deidentificationMethod",
      "values": [
        "crossout"
      ]
    }
  ]
},
```