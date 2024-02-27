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
  "IDENTIFIER_CONSTANTS": {
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

#### IDENTIFIER CONSTANTS
Hier können mit einfachen `key`-`value` Paaren Konstanten für bestimmte Namensräume vergeben werden.
Im weiteren Verlauf der Konfigurationsdatei können diese dann mittels `#` referenziert werden.
```
{
  "IDENTIFIER_CONSTANTS": {
      "beispiel_constant": "ein.langer.Namensraum.der.nicht.ständig.ausgeschrieben.werden.soll"
  },
  "MAPPING": {
    "IDENTIFIER": {
      "target_default": "de.beispiel"
      "source_default": "#beispiel_constant"
    },
```
Wichtig ist dabei, darauf zu achten, dann der Referenz-Name (also hier 'beispiel_constant') keinen `.` enthält,
da bei der Auflösung Punkte als Trennzeichen interpretiert werden:
`#beispiel.constant` würde nur `#beispiel` versuchen in den `IDENTIFIER_CONSTANTS` zu finden.

#### MAPPING: IDENTIFIER
Hier sind derzeit nur die beiden Einträge für ``target_default`` und `source_default` vorgesehen.
Wie im obigen Beispiel ersichtlich, können Referenzen oder ausgeschriebene Werte verwendet werden.
Dabei bezeichnet ``target_default`` den Standard-Namensraum der Typen im Ziel-CAS und
`source_default` den Standard-Namensraum der Typen im Quell-CAS.
Diese Standardwerte die Kurz-Notation im weiteren Verlauf der Konfigurationsdatei und
werden verwendet wenn Typen mit einem ``.`` beginnen. (siehe Abschnitt `MAPPING: ENTRIES`)

#### MAPPING: ENTRIES
Die erste Ebene enthält die Typen die in der neuen CAS erstellt werden sollen.
```
"Age": {
  "layer": {}, (i)
  "features": { [...] } (ii)
}
```

##### (i) layer
Wenn der Wert des ``layer`` Eintrags leer gelassen wird (leeres `Object`), werden die unter *(b)* definierten Standard-Layer-Definitionen und der Name des `keys` verwendet.
Wenn also:
``"MAPPING" -> "IDENTIFIER" -> "target_default": "de.beispiel"`` und
``"MAPPING" -> "IDENTIFIER" -> "source_default": "com.example"``,
würde in der Quell-CAS jedes Layer `com.example.Age` in der Ziel CAS in ein `de.beispiel.Age` umgewandelt.  
Alternativ kann ein explizites Mapping angegeben werden:
``"layer": { "de.beispiel.Alter": "com.example.Age" }``; der `key` ist dann nur für die interne Referenz und wird nicht beachtet.
Wichtig ist außerdem, dass der Ziel-Layer auf der linken Seite steht.  
Falls der `layer` Eintrag hingegen ganz weggelassen würde oder einfach nur ein ``String`` ist, wird **nicht** nach einem entsprechenden Typ in der Quell-CAS gesucht, sondern das Mapping wird im `feature`-Eintrag genauer spezifiziert.

##### (ii) features
Definiert die `features`, die in der Ziel-CAS für das entsprechende Layer erstellt werden und was die Bedingungen in der Quell-CAS sind um entsprechendes `feature` mit einem/welchem Wert zu versehen.
Die einfachste Möglichkeit besteht aus zwei Varianten (wenn der Wert des `layer`-Eintrags entweder leer ist, oder ein explizites Mapping definiert wurde):
```
"Age": {
  "layer": {},
  "features": {
    "kind": "$DATE"
  }
},
```
Wenn also wieder gegeben:
``"MAPPING" -> "IDENTIFIER" -> "target_default": "de.beispiel"`` und
``"MAPPING" -> "IDENTIFIER" -> "source_default": "com.example"``,
würde durch die oben angegebene Definition in der Ziel-CAS ein `de.beispiel.Age` Layer erstellt für jedes `com.Example.Age` Layer in der Quell-CAS.
Des Weiteren würde jedem dieser `de.beispiel.Age` Layer ein `kind` Feature hinzugefügt, dass einen konstanten Wert besitzt (durch das '$' angegeben); in diesem Fall `DATE`.
```
"Contact": {
  "layer": {
    "de.beispiel.Kontakt": "com.example.Contact"
  },
  "features": {
    "kind": "kind"
  }
},
```
Zuallererst würden in diesem Beispiel etwaige Werte für `target_default` und `source_default` nicht beachtet und
für jedes Layer in der Quell-CAS mit dem Wert `com.example.Contact` würde ein `de.beispiel.Kontakt` Layer in der Ziel-CAS erstellt.
Außerdem würde jedes der neu erstellten Layer ein `kind` Feature bekommen, dass den Wert des `kind` Features aus dem Quell-CAS bekäme.  
``features`` kann ganz weggelassen oder der Wert (das ``Object``) leergelassen werden. *[Hier bestünde die Möglichkeit einer Implementation für 'übernehme alle features wenn `Object` ist leer', o.ä.]*
```
"PHI": {
  "features": {
    "kind": {
      "AGE": { (a)
        "layer": ".Age"
      },
      "CONTACT_FAX": { (b)
        "layer": ".Contact",
        "feature": "@kind==fax"
      },
      "CONTACT_OTHER": { (c)
        "layer": "org.example.Contact",
        "feature": "@kind==other|none"
      }
    }
  }
}
```
Dieses Beispiel beschreibt den Fall, dass die zugehörige `layer`-Definition ganz weggelassen würde (also nicht einfach nur leer) oder ein ``String`` ist.
Das erlaubt ein Mapping bei dem nach bestimmten Layern in der Quell-CAS gesucht wird um sie dem definierten Layer in der Ziel-CAS als Feature zuzuordnen.
Das Ziel-Layer würde im Beispiel den Wert aus `"MAPPING" -> "IDENTIFIER" -> "target_default"` annehmen (bis jetzt immer `de.beispiel`) zuzüglich des Layer-Namen aus der Definition (`PHI` hier):
``de.beispiel.PHI``. Ist ein `layer` Wert als ``String`` angegeben, wird dieser konkrete `String` als Ziel-Layer-Name erstellt.  
In obigen Beispiel wird ein Layer in der Ziel-CAS mit einem `kind` Feature angelegt, wenn:  
<ol type="a">
  <li>
    ein Layer in der Quell-CAS mit dem Wert 'com.example.Age' gefunden wird.
    Zuerst wird der Ausdruck '.Age' übersetzt in 'com.example.Age' (also wenn wir für `source_default` den Wert aus den bisherigen Beispielen annehmen).
    Der '.' am Anfang eines Wertes ist eine Möglichkeit der Shorthand-Notation.
    Der Wert des `kind` Features wäre dann 'AGE'.
  </li>
  <li>
    ein Layer in der Quell-CAS mit dem Wert 'com.example.Contact' gefunden wird,
    das zusäzlich ein 'kind' Feature besitzt mit dem Wert 'fax'. Das '@'-Zeichen startet eine simple Bool'sche Abfrage.
    Der Wert des `kind` Features der Ziel-CAS wäre dann 'CONTACT_FAX'.
  </li>
  <li>
    ein Layer in der Quell-CAS mit dem Wert 'org.example.Contact' gefunden wird (startet nicht mit einem Punkt, weshalb der String ohne zusätzliche Auflösung genommen wird).
    Wieder wird eine Bool'sche Abfrage gestartet: der 'kind' Wert ist entweder 'other' oder 'none'.
    Der Wert des `kind` Features wäre in diesem Fall 'CONTACT_OTHER'.
  </li>
</ol>