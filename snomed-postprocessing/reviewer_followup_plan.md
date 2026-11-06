# Nachbereitung des App-Reviews: Anforderungen und Umsetzungsvorschlag

## 1. Ziel und Status

Dieses Dokument strukturiert sämtliche Punkte aus `todo.md`, beantwortet die dort gestellten Fragen anhand des aktuellen Codes und ergänzt Umsetzungshinweise sowie Abnahmekriterien.

**Status:** Arbeitsplan mit dokumentiertem Umsetzungsstand. Gewünschte Änderungen, verifizierter Ist-Zustand und neue Vorschläge sind jeweils getrennt gekennzeichnet. Numerische Schwellenwerte für automatische Entscheidungen müssen mit Reviewer-Beispielen validiert werden.

### Umsetzungsstand

Umgesetzt und mit fokussierten Tests geprüft:

- GUI startet ohne vorausgewählten Overlap-Ignore-Layer `webanno.custom.No_Human`; manuelle Eingabe bleibt möglich (Abschnitt 3).
- Die drei Fallback-Optionen sind standardmäßig aktiviert (Abschnitt 5.1).
- Historische Beziehungstypen: alle außer `MOVED_FROM` und `REFERS_TO` vorausgewählt; Overlap-Minimum `0.0`; separate Erklärung entfernt (Abschnitt 5.2).
- Explizite Einstellungen bleiben über Reruns erhalten. Eine leere Auswahl historischer Beziehungstypen wird nicht mehr stillschweigend durch Standardwerte ersetzt.
- Die nach außen sichtbare Terminologie verwendet „inclusion list“ / „exclusion list“ in GUI, CLI-Hilfetexten, Konsolenmeldungen, generierten Markdown-Reports und README (Abschnitt 4). Technische Bezeichner und Artefaktformate bleiben unverändert.
- Konzeptregeln für Number und Date mit einklappbarer Regelform, gemeinsamem **Apply rules to review**-Button, Override-Option, Review/Clear und `literal`-erhaltendem Write-back sind offline umgesetzt (Abschnitt 6).

Zusätzlich wurde die MIE-Ergebnisdarstellung aus `../../snomed-annotation-audit/` übernommen (Abschnitt 2): gruppierte Datentabellen, Kennzahlen, Filter mit Reset und sitzungsinterne Speicherung des letzten erfolgreichen Checks. Report-Downloads und Übergabe an die Sanitization bleiben erhalten. Filter ändern weder Exporte noch die gespeicherten Findings.

Die funktionalen Änderungen betreffen die GUI; die Terminologieumstellung umfasst zusätzlich Reports und CLI-Hilfetexte. CLI-/API-Standardwerte bleiben unverändert. Die übrigen Arbeitspakete und die Upload-Fehlerbehebung sind noch offen.

## 2. Policy-Check-Ergebnisse als interaktive Tabelle

**Anforderung:** Die Verbesserungen der MIE-Version zurückführen: Policy-Check-Ergebnisse sollen als interaktive Datentabelle statt ausschließlich als Markdown angezeigt werden.

**Umgesetzt:** Dokument-Expander mit Tabellen pro Annotator. Spalten: SCTID, FSN, Covered Text, Status, Check-Typ und Annotation-Layer. Kennzahlen sowie Filter für Status, Check-Typ, SCTID und Text inklusive Reset sind verfügbar. Dokument/Annotator stehen in der Gruppierung, Offsets bestimmen die anfängliche Reihenfolge; detaillierte Gründe und Offsets bleiben in den strukturierten Findings/Reports. Markdown-Downloads bleiben erhalten, die bisherige Inline-Markdown-Vorschau wird durch die Tabelle ersetzt. Ergebnisse bleiben über Reruns innerhalb der Sitzung sichtbar; ein Hinweis kennzeichnet den letzten erfolgreichen Check.

- Die konkrete MIE-Implementierung vor der Übernahme identifizieren und mit dem aktuellen Workflow vergleichen.
- Tabellenansicht mit den relevanten Finding-Feldern, insbesondere Dokument, Annotator, Layer, Textspanne, SCTID und Prüfgrund, anbieten.
- Sortierung und Filterung ermöglichen; vorhandene Downloads und strukturierte Findings nicht unbeabsichtigt entfernen.
- Die Anzeige aus denselben strukturierten Findings erzeugen wie die Exportartefakte, damit Ergebnisse konsistent bleiben.

**Abnahme:** Tabelle und Exporte enthalten dieselben Findings; Sortierung oder Filterung verändern die zugrunde liegenden Ergebnisse nicht.

## 3. Standardauswahl der Layer

**Anforderung:** Der Layer `no_human` ist standardmäßig **nicht ausgewählt**. Eine bewusste manuelle Auswahl bleibt möglich.

Vor der Umsetzung den tatsächlich verwendeten vollständigen CAS-Typnamen feststellen. Neue Sitzungen und neu geladene Projekte dürfen den Layer nicht automatisch aktivieren; explizite Nutzerauswahlen sollen erhalten bleiben.

## 4. Einheitliche Terminologie

| Bisher | Neu |
|---|---|
| `whitelist` | `inclusion list` |
| `blacklist` | `exclusion list` |

**Anforderung:** Die neuen Begriffe überall konsistent verwenden, insbesondere in Labels, Hilfetexten, Statusmeldungen, Reports, Dokumentation und Beispielen.

**Technische Einordnung:** Die alten Bezeichner sind derzeit auch Bestandteil von Python-Feldern, CLI-Optionen, JSON-Werten und HDF5-Pfaden. Ein bloßes globales Suchen/Ersetzen würde bestehende Artefakte und Aufrufe brechen.

**Aktueller Umfang (umgesetzt):** Nur die nach außen sichtbare Benennung ändern. GUI-Labels, Hilfetexte, Statusanzeigen, CLI-Hilfe, Konsolenmeldungen, Markdown-Reports und README verwenden die neuen Begriffe. Report-Überschriften und interne Markdown-Links sind aufeinander abgestimmt.

**Bewusst unverändert:** Python-Namen, CLI-Flags wie `--custom-blacklist`, HDF5-Pfade, JSON-Schlüssel sowie strukturierte `list_type`-/`reason`-/Statuswerte. In Metadatenansichten werden tatsächliche Speicherpfade ausdrücklich als HDF5-Pfade gekennzeichnet. Klinische Texte, FSNs, Dateinamen und vorhandene Reports werden nicht umgeschrieben. Keine Migration erforderlich; eine spätere technische Umbenennung wäre ein eigenständiger, gesondert zu beauftragender Schritt.

**Abnahme:** Neue Begriffe in den bearbeiteten Anzeige- und Reportflächen; bestehende CLI-Aufrufe und Artefakte bleiben verwendbar. Tests sichern Anzeige, Report-Links und unveränderte JSON-Identifikatoren ab.

## 5. Suggest policy sanitization: neue Standardwerte

### 5.1 Settings

Folgende Optionen sollen in einer neuen Sitzung standardmäßig aktiviert sein:

- **Historical ancestor fallback**
- **Semantic BM25 fallback**
- **Include exclusion-list findings in BM25 fallback**

Die letzte Option erweitert die Menge der zu bearbeitenden Findings. Sie erlaubt **nicht**, ausgeschlossene Konzepte als Ziel vorzuschlagen.

### 5.2 Advanced suggestion settings

- Unter **Allowed historical association types** alle unterstützten Typen außer `MOVED_FROM` und `REFERS_TO` vorauswählen.
- **Minimum lexical overlap ratio:** Standardwert von `0.15` auf **`0.0`** ändern.
- Die separate Sektion **Association type meanings** entfernen; Erläuterungen bleiben direkt an den Auswahloptionen verfügbar.
- Verweise wie „explanations are listed below“ ebenfalls entfernen/anpassen.

**Einordnung:** Ein Overlap-Minimum von null deaktiviert diese zusätzliche Mindestüberlappungsprüfung. Es erzeugt nicht automatisch Treffer ohne gemeinsame Such-Tokens; BM25-Suche, Mindestscore und Kandidatenvalidierung gelten weiterhin.

**Wichtig:** Eine breite Vorauswahl historischer Beziehungstypen dient der Vorschlagserzeugung, nicht automatisch der Freigabe. Beispielsweise bedeuten `POSSIBLY_EQUIVALENT_TO`, `PARTIALLY_EQUIVALENT_TO` oder `ALTERNATIVE` keine garantierte klinische Äquivalenz.

**Abnahme:** Die Werte gelten für neue Sitzungen; gespeicherte oder bewusst geänderte Einstellungen werden nicht bei jedem Rerun überschrieben.

## 6. Konfigurierbare Konzeptregeln: Number und Date

**Status:** Konzeptregeln inklusive GUI, gemeinsamem Apply-Schritt, Review/Clear und gemeinsamem CAS-Write-back implementiert und offline getestet. Live-Reimport nach INCEpTION steht noch aus. Die folgenden SCTIDs wurden vom Nutzer vorgegeben. Bezeichnungen und Zielverfügbarkeit bei der Ausführung anhand des ausgewählten SNOMED-Releases prüfen; die Regeln selbst über die SCTID identifizieren, nicht über FSN-Textvergleich.

### 6.1 Vorgefüllte Regeln

| Quellkonzept | Quell-SCTID | Aktion | Zielkonzept / Ziel-SCTID |
|---|---|---|---|
| Number (attribute) | `410680006` | **Remove ID only** (`clear_id`) | Kein Ziel: nur die Konzeptreferenz leeren |
| Date (attribute) | `410671006` | **Replace with concept** (`replace`) | Date property (qualifier value), `410672004` |

**Verbindliche Invarianten für beide Aktionen:**

- `literal` bleibt exakt erhalten: keine Löschung, Normalisierung, Neuberechnung oder Übernahme aus einem Zielkonzept. Auch leere Werte, Nullwerte und ein nicht vorhandenes Feature dürfen nicht künstlich verändert oder ergänzt werden.
- Die bestehende Annotation bleibt bestehen. Ihr Layer-Typ, ihre Offsets, ihr Textbezug und alle übrigen Features bleiben unverändert; verändert wird ausschließlich das konfigurierte Konzept-ID-Feature (standardmäßig `id`).
- Keine Annotation löschen, nicht durch eine neu erzeugte Annotation ersetzen und keinen Layer aus dem TypeSystem entfernen.
- URI-Präfixe und unpräfixierte SCTIDs gemäß den bestehenden ID-Einstellungen korrekt lesen und schreiben.
- Die Date-Regel ist eine deterministische Ersetzung, kein historischer oder BM25-Vorschlag. Bei aktivierter Regel darf sie nicht durch einen anders gerankten Kandidaten ersetzt werden.

### 6.2 Eigenständige Regelform

Die Streamlit-Form **Concept rules** liegt im Tab **Suggest policy sanitization** in einem standardmäßig eingeklappten Expander oberhalb der Fallback-Einstellungen; getrennt von den score-/assoziationsbasierten Auto-Apply-Bedingungen aus Abschnitt 7. Die beiden obigen Regeln sind vorausgefüllt; weitere Regeln können hinzugefügt, bearbeitet, deaktiviert und entfernt werden.

Vorgeschlagene Felder je Regel:

| Feld | Funktion |
|---|---|
| Aktiviert | Regel bewusst ein-/ausschalten |
| Override policy | Boolean pro Regel, standardmäßig aktiviert; erlaubt eine explizite Abweichung von inclusion-/exclusion-list-Anforderungen, ohne die Policy selbst zu verändern |
| Regel-ID / Name | Stabile technische Identität und verständliche Bezeichnung für Nachvollziehbarkeit |
| Quell-SCTID | Exakter Konzept-Match; FSN nur zur Anzeige/Validierung |
| Aktion | Auswahl zwischen **Remove ID only** und **Replace with concept** |
| Ziel-SCTID | Nur bei Ersetzung erforderlich; bei `clear_id` nicht zulässig |

Der Geltungsbereich wird nicht über zusätzliche Eingabeboxen konfiguriert: Die Regeln übernehmen die Ziel-Annotation-Layer aus der Sidebar und berücksichtigen alle Dokumente und Annotatoren. Frühere gespeicherte Regel-Scope-Filter werden bei neuen GUI-Regelanwendungen nicht angewandt.

`literal`-Erhalt ist eine feste Eigenschaft beider Aktionen und **keine abschaltbare Option**.

**Vereinfachte Bedienung (umgesetzt):** Die Regelform hat nur einen Aktionsbutton **Apply rules to review**: Einstellungen speichern/validieren, passende Annotationen scannen und Entscheidungen automatisch im Review auswählen. Eine Zusammenfassung zeigt ID-Entfernungen, Ersetzungen, tatsächliche Policy-Overrides und manuelle Konflikte. Separate Save-/Preview-/Übernahme-Buttons entfallen. JSON-Uploads laden nur die Konfiguration automatisch; der Download bleibt als eigener Button erhalten. Erneutes Anwenden erhält gespeicherte manuelle Apply-Checkbox-Änderungen. **Clear all pending rule decisions** entfernt ausdrücklich sämtliche ausstehenden Regelentscheidungen einschließlich dieser Checkbox-Auswahl, ändert weder Regeldefinitionen noch CAS-Dateien und steht gemeinsam mit der Regelkonfiguration/-anwendung im **Concept rules**-Expander in Tab 2. Ein separater Undo-Button und die zugehörigen Verlaufssnapshots entfallen; Tab 3 zeigt nur die resultierenden Entscheidungen mit Review-/Save-Funktion. Formulareingaben, Regelanwendung im Review und Streamlit-Reruns schreiben niemals direkt CAS-Dateien um. Die tatsächliche Änderung erfolgt erst über den expliziten Export-/Write-back-Schritt.

**Bestätigte Defaults:** Beide vorgefüllten Regeln aktiviert; `override policy` standardmäßig aktiviert, auch bei neu angelegten Regeln. Anwendung auf **alle passenden Annotationen im ausdrücklich gewählten Geltungsbereich**, nicht nur auf bereits gemeldete Policy-Findings. So gilt insbesondere die Date-Regel auch dann, wenn das Quellkonzept den Policy-Check bereits besteht. Das erfordert die Ermittlung passender Annotationen aus dem Projekt und darf nicht allein auf der Findings-Liste beruhen.

### 6.3 Validierung, Priorität und Sicherheit

- Quell-SCTID und Aktion validieren; bei `replace` zusätzlich Ziel-SCTID und Existenz/Aktivität prüfen. Bei deaktiviertem `override policy` muss das Ersetzungsziel auch die geltende Ziel-Policy erfüllen. Selbstersetzungen, widersprüchliche Regeln für dieselbe Quelle im selben Geltungsbereich und fehlende Zielcodes zurückweisen.
- Pro Annotation genau eine passende Konzeptregel auswerten, anhand ihrer ursprünglichen ID. Im ersten Umfang keine verkettete Anwendung mehrerer Regeln und keine implizite Reihenfolge als Konfliktlösung.
- Eine gültige, aktivierte Konzeptregel hat Vorrang vor generischen Historical-/Ancestor-/BM25-Vorschlägen. Vorhandene manuelle Entscheidungen nicht stillschweigend überschreiben; Konflikte sichtbar melden und eine explizite Entscheidung verlangen.
- **Policy-Override pro Regel:** Mit aktiviertem `override policy` hat die explizite Regel Vorrang vor inclusion-/exclusion-list-Anforderungen, auch wenn beispielsweise `410672004` nach der gewählten Policy ausgeschlossen ist. Die Prüfung, ob ein Ersetzungsziel existiert und aktiv ist, bleibt verbindlich. Bei deaktiviertem Override ein unzulässiges Ersetzungsziel mit klarer Meldung blockieren; nicht stillschweigend einen Fallback-Kandidaten wählen. `clear_id` hat kein Ersetzungsziel und benötigt daher keine Ziel-Mitgliedschaftsprüfung; die ID darf weiterhin geleert werden. Die Regeln gelten unabhängig davon, ob das Quellkonzept bereits ein Policy-Finding erzeugt hat.
- Override-Einstellung zusammen mit der Regel speichern und in Vorschau, Review und Decisions-Provenienz sichtbar machen. Zwischen „Override erlaubt“ und „tatsächlich Policy übergangen“ unterscheiden; die geltende Policy selbst bleibt unverändert.
- `clear_id` ist eine eigene gültige Aktion ohne Zielcode, kein Löschen und keine Ersetzung durch den Text `None`. Implementiert ist `None` als nicht gesetzte ID; JSONCAS-/XMI-Roundtrips bestätigen diese Repräsentation. Der Live-INCEpTION-Reimport bleibt zu prüfen.
- Regel-ID, Quelle, Aktion, gegebenenfalls Ziel und betroffene Annotation in Decisions/Reports nachvollziehbar speichern. Keine klinischen Literalwerte in Konsolenlogs ausgeben.
- Ausstehende Regelentscheidungen explizit über Clear zurücknehmen können; erneutes Anwenden erhält gespeicherte manuelle Checkbox-Auswahlen. Kein separater Undo-Verlauf für Konzeptregeln; die geplante Undo-Funktion in Abschnitt 7 bleibt davon unabhängig.

### 6.4 Technischer Implementierungsplan (offline umgesetzt)

1. **Regelmodell und Validierung:** Die zwei Aktionen, stabile Regel-IDs, Geltungsbereich, boolesches `override_policy` (Default `true`) und die vorgegebenen Defaults modellieren. Regeln separat von einzelnen Review-Entscheidungen serialisieren und wieder laden können; vorhandene Artefakte nicht migrieren oder überschreiben.
2. **Matching und Entscheidungen:** Passende Annotationen innerhalb der gewählten Layer/Dokumente/Annotatoren direkt aus dem Projekt ermitteln; deterministische Entscheidungen aus den Original-IDs erzeugen. Regeln vor generischen Fallbacks berücksichtigen und doppelte bzw. widersprüchliche Entscheidungen vermeiden.
3. **Decisions und Write-back:** `clear_id` durchgängig in Validierung, Review, Decisions-Export/-Import und gemeinsamem CAS-Write-back ergänzen; `replace` für Date wiederverwenden. Nur das ID-Feature setzen/leeren, `literal` und andere Features nicht anfassen. Lokalen ZIP-Export und INCEpTION-Upload-Artefakte mit derselben Semantik versorgen.
4. **GUI:** Einklappbare Regelform, Validierungsfehler, gemeinsamen Apply-Button mit Ergebniszusammenfassung und Rücknahme implementieren. Aktionen und Konflikte im Review klar anzeigen; Einstellungen über Reruns erhalten.
5. **Tests und Dokumentation:** Beide Regeln und generisch angelegte Regeln für JSONCAS und XMI prüfen; Literal-/Feature-Erhalt, ID-Präfixe, Scope, Policy-Konflikte, manuelle Konflikte, keine Regelverkettung, Wiederholbarkeit, Clear und JSON-Roundtrips absichern. INCEpTION-Reimport erst mit freigegebenem Testprojekt und gesonderter Netzwerkfreigabe prüfen.

### 6.5 Abnahmekriterien

**Offline geprüft:** Regel-/Decisions-JSON-Roundtrips, JSONCAS/XMI mit unverändertem `literal` (einschließlich leer/null/fehlendem Feature), weitere Features und Offsets, gemeinsamer ZIP-/Upload-Artefaktpfad mit und ohne Reparatur, Override an/aus, aktive Ziele, Scopes, keine Regelverkettung, Mehrdeutigkeiten, GUI-Reruns, manuelle Konflikte und Clear. Die GUI übernimmt für alle Regeln die Annotation-Layer aus der Sidebar und bearbeitet alle Dokumente/Annotatoren; separate Regel-Scope-Boxen entfallen. Die Engine-API unterstützt weiterhin explizite Filter. Angenommene Regeln reservieren ihre Annotationen im Review; generische Fallback-Zeilen für dieselben Annotationen werden dort ausgeblendet. Die generische Vorschlagserzeugung selbst bleibt unabhängig.

**Offen:** Live-INCEpTION-Reimport; weitere Auto-Apply-Bedingungen aus Abschnitt 7.

- Number `410680006`: ausschließlich die ID ist nach Anwendung leer.
- Date `410671006`: die ID verweist nach Anwendung auf `410672004`, nicht auf einen Fallback-Kandidaten.
- Für beide Regeln sind `literal`, andere Features, Annotation-Anzahl, Layer und Offsets vor/nach Serialisierung identisch.
- Deaktivierte Regeln und Annotationen außerhalb des gewählten Geltungsbereichs bleiben unverändert.
- Regel- und Decisions-Export/-Import erhalten Aktion, Quelle, Ziel und Provenienz; Reruns lösen keine zusätzlichen Änderungen aus.
- Konflikte werden sichtbar behandelt; Clear entfernt explizit alle ausstehenden Regelentscheidungen einschließlich gespeicherter manueller Checkbox-Auswahlen.
- JSONCAS-/XMI-Export und erzeugte Upload-Artefakte bewahren dieselbe Semantik; INCEpTION-Reimport bestätigt die Nutzbarkeit.

## 7. Review & apply: bedingungsbasierte automatische Auswahl

### 7.0 Verbindlicher Quell-Scope (bestätigt; noch umzusetzen)

**Apply Conditions darf ausschließlich Findings aus der inclusion-list-Prüfung automatisch auswählen** (`finding.list_type == "whitelist"`, z. B. `not_in_whitelist`). Das bezeichnet die Herkunft des Findings, nicht eine inclusion-list-Mitgliedschaft des Quellcodes.

- Findings aus der exclusion-list-Prüfung (`list_type == "blacklist"`) bleiben manuell, unabhängig von Historical Association, eindeutigem Ziel oder BM25-Score/-Abstand. Die Einschränkung gilt gleichermaßen für Bedingung A und B.
- Betrifft dieselbe Annotation auch ein exclusion-list-Finding, darf sie nicht über ein zusätzliches inclusion-list-Finding automatisch freigegeben werden.
- BM25-Vorschläge für exclusion-list-Findings dürfen weiterhin zur manuellen Prüfung erzeugt werden; Vorschlagserzeugung ist keine automatische Freigabe. Lexikalische Ähnlichkeit belegt keine klinische Eignung; eine vergleichende Zuverlässigkeit wurde hier nicht empirisch bestimmt.
- Gemischte Dokumente mit offenen exclusion-list-Findings nicht automatisch als reviewed markieren.
- Zielvalidität richtet sich weiterhin nach dem gewählten Policy-/Active-release-Modus; optionale Release-Ausschlüsse bleiben optional. Explizite Konzeptregeln aus Abschnitt 6 sind ein separater, bewusst konfigurierter Mechanismus und von diesem Quell-Scope nicht betroffen.

### 7.1 Bisherige Bulk-Aktionen ersetzen

Die vier globalen Aktionen entfernen:

- Apply all single/no-choice replacements
- Clear all single/no-choice replacements
- Apply first candidate(s) to all manual choices
- Clear all manual applications

Stattdessen eine Form mit zunächst zwei unabhängig konfigurierbaren Bedingungen und zwei Buttons anbieten:

- **Apply Conditions**
- **Undo Automatic Conditions**

Die Bedingungen werden vorgeschlagen als **ODER-Verknüpfung** ausgewertet: Eine passende historische Beziehung **oder** ein ausreichend klarer BM25-Erstplatzierter kann eine Auswahl auslösen. Diese Verknüpfung vor Umsetzung bestätigen.

### 7.2 Bedingung A: Historical Associations

Standardauswahl gemäß Review:

- `SAME_AS`
- `REPLACED_BY`
- `WAS_A`
- `ALTERNATIVE`
- `SIMILAR_TO`

**Vorgeschlagene Auswertungsregel:** Automatisch nur dann auswählen, wenn die zulässigen historischen Beziehungen genau einen gültigen Zielcode ergeben. Mehrere verschiedene gültige Ziele bleiben manuell zu entscheiden. Bei mehreren Beziehungstypen zum selben Ziel müssen die Typen strukturiert ausgewertet werden, nicht als ein einzelner kommaseparierter String.

**Fachlicher Hinweis:** Auch `WAS_A`, `ALTERNATIVE` und `SIMILAR_TO` sind keine Äquivalenzgarantie. Ihre automatische Freigabe ist eine explizite Review-Policy, keine aus SNOMED ableitbare Sicherheitsgarantie.

### 7.3 Bedingung B: klar führender BM25-Kandidat

Bei mehreren BM25-Kandidaten soll Kandidat 1 automatisch ausgewählt werden können, wenn sein Score ausreichend deutlich vor den Folgeplätzen liegt. Die vorgeschlagene Metrik und Einschränkungen stehen in Abschnitt 9.

### 7.4 Verhalten von Apply Conditions

- Passende Annotationen markieren und die konkrete Zielauswahl speichern.
- Automatisch entschiedene Zeilen im Review-Workflow als **resolved** behandeln.
- Nur tatsächlich vorhandene, aktuell gültige Ziele zulassen.
- Manuelle Entscheidungen, Löschungen und „Needs manual edit“-Markierungen nicht stillschweigend überschreiben.
- Regel, Parameter und Auslöser jeder automatischen Entscheidung nachvollziehbar speichern.
- Dokumente als **reviewed** markieren, wenn alle prüfpflichtigen Zeilen automatisch aufgelöst wurden und keine offenen oder manuell zu bearbeitenden Fälle verbleiben. Gemischte Dokumente nicht voreilig als geprüft markieren.
- Zusammenfassung anzeigen: Anzahl automatisch aufgelöster Zeilen, übersprungener Zeilen und neu als reviewed markierter Dokumente.

**Abgrenzung:** „Auto apply“ setzt zunächst Review-Entscheidungen. Die CAS-Dateien werden erst beim nachgelagerten, expliziten Apply-/Write-back-Schritt geändert.

### 7.5 Verhalten von Undo Automatic Conditions

Vor einer automatischen Aktion den Ausgangszustand der betroffenen Entscheidungen und Dokument-Review-Markierungen sichern.

- Automatische Änderungen zurücknehmen und den vorherigen Zustand wiederherstellen.
- Bereits vorher vorhandene manuelle Entscheidungen erhalten.
- Nachträgliche manuelle Änderungen nicht ungefragt rückgängig machen; solche Konflikte melden bzw. überspringen.
- Auch automatisch gesetzte `resolved`-/`reviewed`-Zustände berücksichtigen.
- Wiederholtes Anwenden darf keine zusätzlichen oder widersprüchlichen Entscheidungen erzeugen.

**Vorschlag für den ersten Umfang:** Undo bezieht sich auf den letzten Apply-Conditions-Durchlauf. Mehrstufiges Undo wäre eine separate Erweiterung.

## 8. Frage: Wird die exclusion list bei Sanitization beachtet?

### Verifizierter Ist-Zustand

Die Kandidatenprüfung wird zentral in `hdf5_handling/policy.py` durchgeführt und von Historical Associations, Ancestor-Fallback und BM25 einschließlich SNOGIT verwendet.

| Zielmodus | Aktuelle Kandidatenregel |
|---|---|
| **policy** | Aktiv, in der inclusion list und weder in der eingebetteten noch in einer übergebenen Runtime-exclusion-list. |
| **release** | Aktiv; die eingebettete exclusion list wird nur bei aktivierter entsprechender Einstellung berücksichtigt. Übergebene Runtime-Ausschlüsse werden berücksichtigt. |

Die GUI unterscheidet für den Release-Modus die Verwendung eingebetteter und/oder eigener Ausschlüsse. Eine eigene Liste wirkt nur, wenn sie in diesem Modus ausgewählt und aufgelöst wurde.

**Antwort:** Im Policy-Modus ja. Eine pauschale Zusicherung für jeden Sanitization-Modus wäre derzeit falsch: Im Release-Modus hängt die eingebettete Liste von der Konfiguration ab.

### Bestätigtes Verhalten (umgesetzt)

Für generische Historical-/Ancestor-/BM25-Vorschläge sind Ziele verboten, die durch die **wirksamen** Policy-Einstellungen ausgeschlossen werden. Im Modus **Active release** (Sidebar) bleibt die Durchsetzung eingebetteter/custom Ausschlüsse ausdrücklich optional und richtet sich nach der dortigen Auswahl; keine zusätzliche pauschale Sperre wurde eingeführt. **Explizite Ausnahme:** Konzeptregeln aus Abschnitt 6 dürfen mit aktiviertem `override policy` die wirksamen Policy-Anforderungen übersteuern; solche Entscheidungen werden sichtbar als Regel-Override ausgewiesen.

**Behobene Lücke:** Abgelehnte historische Ziele und Distanz-/Score-Diagnostik wurden bisher teilweise in `candidates` gespeichert und dadurch als auswählbare Review-Optionen angeboten. Sie liegen jetzt separat in `context_candidates`; `candidate_count` zählt nur auswählbare Ziele. JSON erhält diese Trennung; Review bietet nur `candidates` zur Auswahl an. Nach Änderung der Ziel-Einstellungen Vorschläge neu erzeugen.

**Bewusster Umfang:** Nur die fehlerhafte Vermischung von Auswahl und Diagnostik wird korrigiert. Keine Legacy-Normalisierung, keine zusätzliche Status-Allowlist und keine neue HDF5-Revalidierung bei Review/Export; bestehende Konzeptregel-Validierung und API-Verträge bleiben unverändert.

- Die geltende exclusion list sichtbar anzeigen.
- Die Kandidatenfilterung vor Ranking-/Review-Ausgabe anwenden.
- Historische Ziele, Ancestor-Ziele und BM25-/SNOGIT-Ziele identisch behandeln.
- Automatische Auswahl darf nur die generierten `candidates` berücksichtigen, niemals `context_candidates`. Keine zusätzliche Revalidierung älterer Dateien vorgesehen.
- Ausschlüsse haben Vorrang vor inclusion-list-Mitgliedschaft und hoher BM25-Bewertung.

**Abnahme:** Ein durch die wirksamen Einstellungen ausgeschlossener Zielcode erscheint in keinem auswählbaren generischen Vorschlag und kann nicht durch die automatischen Bedingungen aus Abschnitt 7 freigegeben werden. Eine Ausnahme ist ausschließlich eine explizite Konzeptregel mit aktiviertem `override policy` gemäß Abschnitt 6. Falls diagnostische Kandidaten gezeigt werden, klar als nicht auswählbar kennzeichnen.

## 9. Frage: Welche Metrik beschreibt den Abstand des ersten BM25-Kandidaten?

### 9.1 Vorschlag: Dominanz des ersten Score-Abstands

Für drei verschiedene, gültige Zielcodes mit sortierten Scores `s1 ≥ s2 ≥ s3 ≥ 0`:

```text
d12 = s1 - s2
d23 = s2 - s3
D   = d12 / (d12 + d23) = (s1 - s2) / (s1 - s3)
```

- `D = 0.5`: Abstand 1→2 ist genauso groß wie Abstand 2→3.
- `D ≥ 2/3`: Abstand 1→2 ist mindestens doppelt so groß wie Abstand 2→3.
- Hohe Werte sprechen für einen vergleichsweise klaren Erstplatzierten, nicht für klinische Richtigkeit.
- Bei `s1 = s3` ist die Metrik nicht definiert; Gleichstand führt nicht zur automatischen Auswahl.

Die beschränkte Kennzahl ist leichter darzustellen als `d12 / d23`, das bei `d23 = 0` unendlich wird. Ein kleines `d23` kann allerdings auch bei fast gleichen Scores einen hohen Wert ergeben.

### 9.2 Zusätzlicher relativer Mindestabstand

Deshalb zusätzlich:

```text
M = (s1 - s2) / s1       (nur für s1 > 0)
```

**Vorläufiger Startvorschlag für die Validierung:**

- `D ≥ 2/3` und
- `M ≥ 0.20` und
- bisherige Mindestscore-/Kandidatenvaliditätsprüfungen bestanden.

Beispiele:

| Scores | D | M | Ergebnis nach dem Startvorschlag |
|---|---:|---:|---|
| 12, 7, 6 | 0.83 | 0.42 | automatisch auswählbar |
| 10, 9.9, 9.89 | 0.91 | 0.01 | nicht automatisch: praktisch Gleichstand |
| 10, 8, 5 | 0.40 | 0.20 | nicht automatisch: kein klarer Abstandsknick |

**Diese Schwellen sind Heuristiken, keine empirisch bestätigten Defaults.** Sie anhand akzeptierter und abgelehnter Reviewer-Beispiele kalibrieren. Insbesondere den Anteil falscher automatischer Entscheidungen und die erreichte Abdeckung messen.

### 9.3 Einschränkungen und Sonderfälle

- Nur echte BM25-Scores verwenden, keine Reihenfolgen historischer oder hierarchischer Kandidaten als numerische Evidenz interpretieren.
- Nach Zielcode deduplizieren: mehrere Terme desselben Konzepts sind keine unabhängigen Folgeplätze.
- Bei weniger als drei Kandidaten im ersten Umfang keine automatische Entscheidung durch diese Regel. Ein Zweikandidaten-Fallback wäre gesondert festzulegen.
- Fehlende, nicht endliche oder ungültige Scores sowie Gleichstände führen zur manuellen Prüfung.
- Mindestens drei Kandidaten speichern/abrufen; die Entscheidung darf nicht nur auf den aktuell sichtbaren Tabellenzeilen beruhen.
- BM25 ist kein Wahrscheinlichkeitsmaß. FSN- und SNOGIT-Suchen können verschiedene Suchtexte und Indizes verwenden; ihre Rohscores sind nicht automatisch vergleichbar.
- Die aktuelle Implementierung kombiniert solche Treffer. Vor Freigabe dieser Automatik prüfen, ob alle drei Scores vergleichbar sind. Im ersten Umfang gemischte Suchkanäle ausschließen; später eine separat validierte Normalisierung oder Fusion erwägen.
- Ein geringer Lexical-Overlap-Schwellenwert bei der Vorschlagserzeugung rechtfertigt keine automatische Freigabe. Für automatische Entscheidungen kann ein eigener, strengerer Evidenzfilter sinnvoll sein; dessen Wert bleibt zu validieren.

## 10. Bug: Upload sanitizierter Daten nach INCEpTION scheitert beim Reviewer

**Beobachtung:** Der Upload sanitizierter Daten nach INCEpTION funktionierte beim Reviewer nicht, beim Entwickler jedoch schon. Als erster Debug-Hinweis wurde eine Meldung zu **fehlenden Layern** genannt; der genaue Wortlaut muss noch gesichert werden. Die Ursache ist noch nicht bestimmt; weder ein allgemeiner Defekt der Sanitization noch ein reines Berechtigungsproblem ist damit nachgewiesen.

### Diagnose und Reproduktion

- Den genauen fehlgeschlagenen Schritt bestimmen: Erstellen der Upload-Artefakte, Verbindung/Authentifizierung, Projekt-/Dokumentanlage oder CAS-Import. Fehlermeldung, Zeitpunkt und vorhandene Logs sichern.
- Prüfen, ob beide Personen dieselbe App-Version, dieselben Eingabeartefakte, denselben Workflow und dieselbe INCEpTION-Instanz verwenden. Vergleiche mit einem freigegebenen Testprojekt durchführen, nicht mit produktiven Projekten.
- Unterschiede erfassen: INCEpTION-Version, Zielprojekt, Benutzerrolle/Projektberechtigungen, Netzwerk/VPN/Proxy, URL und TLS-Konfiguration. Keine Passwörter, Tokens oder Authentifizierungsheader protokollieren.
- **Priorität aufgrund des ersten Debug-Hinweises:** Die konkret als fehlend gemeldeten Layer anhand ihrer vollständigen CAS-Typnamen identifizieren. Quellprojekt, sanitisiertes Exportartefakt und Zielprojekt hinsichtlich Layer-/Feature-Konfiguration und TypeSystem vergleichen. Prüfen, ob benötigte Layer im Zielprojekt fehlen oder anders benannt sind und ob gegebenenfalls erzeugte Zusatzlayer wie `webanno.custom.ManualReview` korrekt in die Projektkonfiguration übernommen werden. Dies sind zu prüfende Hypothesen, keine bestätigten Ursachen.
- Falls der CAS-Import scheitert: JSONCAS-/XMI-Format, TypeSystem, Annotation-Layer, Dokumentnamen und den konkreten abgewiesenen Payload-Typ untersuchen. Falls zulässig, einen manuellen Import desselben Artefakts in ein Testprojekt vergleichen.
- Auch einen partiell erfolgreichen Upload prüfen: Welche Projekte/Dokumente wurden bereits angelegt oder geändert? Wiederholungen dürfen nicht unbemerkt Duplikate erzeugen oder bestehende Inhalte überschreiben.

### Erforderliche Diagnoseausgaben

Fehlschläge sollen den betroffenen Verarbeitungsschritt und eine verständliche Fehlermeldung in der GUI sowie technische Details im Server-/Konsolenlog liefern. Bei HTTP-Fehlern Statuscode und eine bereinigte Servermeldung erfassen; bei lokalen Fehlern einen Traceback. Keine vollständigen CAS-Inhalte oder klinischen Texte in Logs ausgeben. Fehlende Angaben zur Reviewer-Sitzung zunächst nachfordern, bevor eine konkrete Fehlerbehebung festgelegt wird.

**Abnahme:** Der Fehler ist mit dokumentierten Bedingungen reproduzierbar bzw. eindeutig eingegrenzt. Nach der Korrektur kann der Reviewer mit den vorgesehenen Berechtigungen ein freigegebenes Testprojekt erfolgreich hochladen; dessen Annotationen und Änderungen sind in INCEpTION überprüfbar. Fehler und Teilfehler werden verständlich gemeldet, und das zuvor funktionierende Entwickler-Szenario bleibt funktionsfähig.

## 11. Empfohlene Umsetzungsreihenfolge

0. Reviewer-Uploadfehler frühzeitig reproduzieren und eingrenzen; eine notwendige Fehlerbehebung vor dem nächsten Reviewer-Durchlauf abschließen.
1. Exclusion-list-Verhalten über die Zielmodi hinweg festlegen und mit Regressionstests absichern.
2. Terminologie, Layer-Standardauswahl und Suggestion-Defaults umstellen; redundante Erklärung entfernen.
3. MIE-Tabellenansicht übernehmen.
4. Konzeptregeln gemäß Abschnitt 6 implementieren: eigene Regelform mit `override policy` (Default aktiviert), Number `410680006` → ID leeren, Date `410671006` → `410672004`; `literal` bei beiden unverändert erhalten. Beide Regeln aktiviert und auf alle passenden Annotationen im gewählten Scope anwenden.
5. Bedingungsform, historische Automatik, Zustandsverwaltung und Undo umsetzen.
6. BM25-Metriken zunächst zur Beobachtung anzeigen; mit Reviewer-Beispielen kalibrieren und anschließend die automatische Auswahl freigeben.

## 12. Übergreifende Tests und Abnahme

- [x] Gewünschte Layer-/Suggestion-Standardwerte aus Abschnitt 3 und 5 in einer neuen GUI-Sitzung korrekt.
- [x] Explizite Layer-/Suggestion-Einstellungen bleiben über Reruns erhalten.
- [x] Policy-Tabellen nutzen dieselben Findings wie Exporte und Sanitization; Filter verändern die Quelldaten nicht.
- [x] Durch wirksame Einstellungen ausgeschlossene Ziele werden als Diagnostik statt als generische Auswahloptionen erzeugt. Active-release-Enforcement bleibt optional, explizite Rule-Overrides bleiben möglich; keine Legacy-/Revalidierungsinfrastruktur.
- [x] Konzeptregelform erlaubt `clear_id` und `replace`, vorausgefüllt mit Number- und Date-Regel.
- [x] Number `410680006` entfernt ausschließlich die ID, nicht die Annotation.
- [x] Date `410671006` wird deterministisch durch `410672004` ersetzt.
- [x] Beide Aktionen erhalten `literal` exakt sowie alle übrigen Features, Layer, Offsets und Annotation-Anzahl (offline JSONCAS/XMI).
- [x] Regeln respektieren Scope und manuelle Entscheidungen; Ziel-Policy-Konflikte, Wiederholbarkeit und Clear sind geprüft.
- [x] `override policy` ist pro Regel standardmäßig aktiviert, editierbar und exportierbar; Tests prüfen beide Zustände und dokumentierte tatsächliche Policy-Overrides.
- [ ] Apply Conditions wählt ausschließlich inclusion-list-Quellfindings; exclusion-list-Findings bleiben auch bei eindeutigen historischen Zielen oder hohen BM25-Scores manuell.
- [ ] Mehrdeutige historische Ziele werden nicht versehentlich automatisch gewählt.
- [ ] BM25-Gleichstände, weniger als drei Ziele und nicht vergleichbare Scores bleiben manuell.
- [ ] Apply Conditions setzt Zielauswahl, resolved und reviewed konsistent.
- [ ] Undo stellt automatische Änderungen zurück, ohne manuelle Arbeit zu verlieren.
- [ ] JSONCAS-/XMI-Write-back, Decisions-Export/-Import und INCEpTION-Reimport funktionieren.
- [ ] Sanitized Upload funktioniert auch im Reviewer-Szenario; Fehler-/Teilfehlerdiagnose und sichere Wiederholung sind geprüft.

## 13. Verwendete Quellen

- Ursprüngliche Review-Notizen: `todo.md`.
- Ergänzende Nutzervorgabe: Number `410680006` → nur ID entfernen; Date `410671006` → Date property `410672004`; konfigurierbare Regelform und zwingender `literal`-Erhalt für beide Aktionen.
- OKF-Einstieg: `okf/snomed-post-processing/index.md`.
- Review-/Write-back-Semantik: `okf/snomed-post-processing/workflows/reviewed-decisions-and-writeback.md`.
- Direkte Codeprüfung: `gui/sanitization_check_tab.py`, `gui/sanitization_run_tab.py`, `hdf5_handling/policy.py`, `sanitization/resolver.py`, `sanitization/semantic_bm25.py` (jeweils unter `src/snomed_post_processing/`).
