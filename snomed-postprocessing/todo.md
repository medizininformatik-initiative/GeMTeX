## Änderungen
- verbesserungen aus der MIE version (datatable für die policy checks anstatt markdown) nach hier zurückspielen
- das ``no_human`` layer soll nicht per default ausgewählt sein
- ersetze überall
  - ``whitelist`` -> ``inclusion list``
  - ``blacklist`` -> ``exclusion list``
- Tab ``Suggest policy sanitization`` - ``Settings``:
  - checked per default: ``Historical Ancestor fallback``, ``Semantic BM25 fallback``, ``Include blacklist findings in BM25 fallback``
  - ``Advanced suggestion settings``:
    - Alle ``Allowed historical association types`` außer ``MOVED_FROM`` und ``REFERS_TO`` sind default vorausgewählt
    - Default ``Minimum lexical overlap ratio`` auf 0 setzen
    - Sektion ``Association type meanings`` entfernen, da die Info in der Selektion vorhanden ist
- für FSN ``Number (attribute)`` soll eine automatische andere Regel gelten: die layer id wird gelöscht (also z.B. ``http://snomed.info/id/...``), aber das layer an sich bleibt bestehen!
  dafür müsste es aber eine zusätzlich Option geben, die mit dem speziellen Fall vorausgefüllt ist 
- Tab ``Review & apply``:
  - die vier Knöpfe ``Apply all single/no-choice replacements``, ``Clear all single/no-choice replacements``, ``Apply first candidates to all manual choices``, ``Clear all manual applications``
    werden gelöscht und ersetzt durch eine Form die (zu Beginn erst nur) 2 Bedingungen formulieren kann, die zu einem ``auto apply`` führen:
    - ``Historical Associations`` (default ``SAME_AS``, ``REPLACED_BY``, ``WAS_A``, ``ALTERNATIVE``, ``SIMILAR_TO``)
    - Bei multi-choice: relative Entfernung der BM25 Kandidaten #1 zu #2 im Vergleich von #2 zu #3
      - da muss ein default Wert bzw. eine Metrik noch gefunden werden (siehe ##Fragen)
  - Die erwähnten gelöschten Knöpfe werden durch zwei Knöpfe ersetzt:
    - ``Apply Conditions`` -- die oben genannten Bedingungen werden mit den entsprechenden Werten angewandt und alle Annotationen die dem entsprechen automatisch markiert und "resolved"
      - wenn ein Dokument nur solche automatisch angewandten Markierungen enthält, wird es als "reviewed" markiert
    - ``Undo Automatic Conditions`` -- "Decisions" werden wieder zurückgesetzt zu ihrem Ausgangszustand

## Fragen
- Im ``Sanitization`` modus: wird die ``exclusion list`` beachtet? Also es dürfen natürlich keine Vorschläge erscheinen, die exkludiert sind.
- Was für eine Metrik könnte man nehmen um eine relative Entfernung der BM25 Kandidaten darzustellen um ein Maß für die Güte des ersten Kandidaten zu bekommen?

## Bugs
- sanitized upload to ``INCEpTION`` didn't work for reviewer, but it worked for me... (something about missing layers)