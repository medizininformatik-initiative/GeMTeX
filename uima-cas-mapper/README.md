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

