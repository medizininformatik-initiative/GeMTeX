# UIMA CAS Mapper

Diese Programm ermöglicht die Transformation von ``xmi`` im [UIMA-CAS](https://uima.apache.org/)-Format von einem Typensystem in ein anderes.  
```
main.py [-h] [-o OUTPUT_PATH] [-e FILE_ENDING] [-t TS_FILE_ENDING] xmi_path typesystem mapping_file

positional arguments:                                                                                     
  xmi_path              Ordner-Pfad der XMI die transformiert werden sollen.
  typesystem            Pfad zur Typensystem-Deklarations-Datei (XML).
  mapping_file          Pfad zur Datei, die definiert wie die Layer der Quell-XMI
                        in die Ziel-XMI transformiert werden.
  
options:
  -h, --help            Zeigt diese Hilfe an (englisch)
  -o OUTPUT_PATH, --output_path OUTPUT_PATH
                        Pfad unter dem die transformierten XMI/JSON Dateien
                        gespeichert werden sollen. (Standard: 'XMI_PATH/out')
  -e FILE_ENDING, --file_ending FILE_ENDING
                        Dateiendung der zu transformierenden CAS'. (Standard: 'xmi')
  -t TS_FILE_ENDING, --ts_file_ending TS_FILE_ENDING
                        Dateiendung der Typensystem-Datei. (Standard: 'xml')
  -x EXPORT_FORMAT, --export_format EXPORT_FORMAT
                        Welches Format die Ziel CAS haben sollen (json/xmi). (Standard: 'json')
```

## Mapping File

Eine Mapping Datei ist in JSON geschrieben und gibt an, wie die verschiedenen Layer einer `source` CAS in eine `target` CAS umgewandelt werden sollen.
Dabei gibt es folgende festgelegte Struktur:
```
{
  "IDENTIFIER_MACROS": {
      [...] (a)
  },
  "MAPPING": {
    "IDENTIFIER": { (b)
      "target_default": [...],
      "source_default": [...]
    },
    "ENTRIES": {
        [...] (c)
    }
  }
}
```
<ol type="a">
  <li>
    Hier können Platzhalter definiert werden die im weiteren Verlauf der Mapping Datei mit '#' referenziert werden können.
    Ein '.' darf dabei nicht verwendet werden, da dieser im Weiteren als Trennstelle interpretiert wird. 
  </li>
  <li>
    Hier sind z.Z. nur zwei Einträge vorgesehen:
    die Standard-Namensräume, die verwendet werden wenn im Folgenden Werte mit lediglich einem '.' beginnen.
  </li>
  <li>
    Dieser Abschnitt enthält den Großteil der Definitionen und ist `target`-orientiert.
    D.h. die Eltern-Layer-Einträge sind die der Ziel-CAS und darunter wird definiert, welche Quell-Layer darauf abgebildet werden soll.
  </li>
</ol>

#### IDENTIFIER MACROS


#### MAPPING: IDENTIFIER


#### MAPPING: ENTRIES
Die erste Ebene enthält die Typen die im neuen CAS erstellt werden sollen.
```
"Age": {
  "layer": {}, (i)
  "features": { [...] } (ii)
}
```

##### (i) layer
Wenn der ``layer`` Eintrag leer gelassen wird, werden die unter *(b)* definierten Standard-Layer-Definitionen und der Name des `keys` verwendet.
Wenn also:
``"MAPPING" -> "IDENTIFIER" -> "target_default": "de.beispiel"``
und ``"MAPPING" -> "IDENTIFIER" -> "source_default": "com.example"``,
würde in der Quell CAS jeder Type `com.example.Age` in der Ziel CAS in ein `de.beispiel.Age` umgewandelt.  
Alternativ kann ein explizites Mapping angegeben werden:
``"layer": { "de.beispiel.Alter": "com.example.Age" }``; der `key` ist dann nur für die interne Referenz und wird nicht beachtet.
Wichtig ist außerdem, dass der Ziel-Typ auf der linken Seite steht.

##### (ii) features