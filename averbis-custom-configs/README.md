# Averbis Health Discovery Konfigurationen
Konfigurationen können per 
``PUT`` ``/rest/v1/textanalysis/projects/{projectName}/pipelines/{pipelineName}/configuration`` angepasst werden.
(siehe auch
[Hilfe zu REST API](https://help.averbis.com/health-discovery/user-manual/#HealthDiscoveryUserManualVersion6.20-ApplicationInterface:RESTAPI)
der ``AHD``)  
Alternativ (und vielleicht einfacher) kann eine REST-Anfrage auch über das AHD-User-Interface gestellt werden:  
![ahd](https://github.com/medizininformatik-initiative/GeMTeX/assets/4722688/81b4da1d-2821-4b03-ac56-f6af21d60ba0)

```
REST API v1 → Text Analysis → Change pipeline configuration
```

### ``gemtex_deid_custom_title_and_date``
* Hinzugefügt: ``WordListAnnotator`` + ``RutaEngine`` um neue Typen zu erkennen:
  * `de.averbis.types.health.PHINameTitle`
  * `de.averbis.types.health.PHIBirthDate`
  * `de.averbis.types.health.PHIDeathDate`

(entsprechendes Mapping muss in der Mappingfile definiert werden; bei `deid_mapping_singlelayer.json` schon als je `NAME_TITLE`, `DATE_BIRTH`, `DATE_DEATH` geschehen)

###### Alternative
Das ganze kann auch ohne API, aber trotzdem über die AHD geschehen:
``AHD → PROJEKT → Pipelines → Pipeline bearbeiten``

``→ WordlistAnnotator (entweder hinzufügen oder bearbeiten) → wordlist → das untenstehende ins Textfeld einfügen``
```
de.averbis.textanalysis.components.health.phiannotator.Dictionary.PHITitleInd
Priv.
Doz.
Drs.
Drs
OA
OÄ
Biol.
Bischof
Dipl.
Dr
Dr.
Dres.
(FH)
h.c.
hc
hc.
Inf.
Ing.
med.
med
dent
dent.
nat.
Päd.
phil.
Phil.
Prof.
Prof
rer.
soc.
Soz.
Univ.-
PD
PD.
Baron
Baronesse
Baronin
Bischof
Bruder
Dame
Edler
Freifrau
Freiherr
Freiin
Fürst
Fürstin
Graf
Gräfin
Hofrat
Konsul
Lord
Prinz
Prinzessin
Schwester
hc.
h.c.
PhD
MD
M.D.
MD.
MBA
Dipl.-Med.
Dipl.- Med.
```
``→ AdvancedRutaEngine (entweder hinzufügen oder bearbeiten) → rules → das untenstehende ins Textfeld einfügen``
```ecma script level 4
PACKAGE de.averbis.types.health;
// TYPESYSTEM de.averbis.types.health.SimplifiedHealthTypeSystem;
// TYPESYSTEM de.averbis.textanalysis.typesystems.health.CompleteInternalHealthTypeSystem;

// merge titles
((t:PHITitleInd{-> UNMARK(t)})[2,100]){-> PHITitleInd};
// med. alone is rather an adjective, TODO extract to list?
t:PHITitleInd{REGEXP("med\\.?|inf\\.?|hc\\.?|dent\\.?", true) -> UNMARK(t)};

DECLARE PHINameTitle;

PHITitleInd{-PARTOF(PHINameTitle)-> PHINameTitle} SW?{-PARTOF(PHITitleInd)} @PHIName;
@PHIName COMMA? PHITitleInd{-PARTOF(PHINameTitle)-> PHINameTitle};

DECLARE PHIBirthDate, PHIDeathDate;
bd:BirthDate.date{-> PHIBirthDate};
dd:DeathDate.date{-> PHIDeathDate};
```

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
