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

## 6. Sonderregel für „Number (attribute)“

### 6.1 Gewünschtes Verhalten

Für eine Annotation mit dem entsprechenden SNOMED-Konzept soll eine konfigurierbare Sonderregel gelten:

- Nur das `id`-Feature der betroffenen Annotation leeren.
- Die Annotation selbst, ihr Layer-Typ, ihre Offsets, ihr Textbezug und alle anderen Features bleiben bestehen.
- Insbesondere **keine Annotation löschen** und keinen Layer aus dem TypeSystem entfernen.

### 6.2 Umsetzungsvorschlag

Eine eigene Einstellung bzw. Regelzeile anbieten, die mit diesem Sonderfall vorausgefüllt ist:

| Feld | Vorgeschlagener Inhalt |
|---|---|
| Konzept | „Number (attribute)“, auf eine verifizierte SCTID aufgelöst |
| Aktion | `clear_id` – nur Konzeptreferenz entfernen |
| Geltungsbereich | Explizit gewählte Annotation-Layer |
| Aktivierung | Sichtbare, veränderbare Option |

Die Regel intern über die **SCTID** identifizieren, nicht ausschließlich über den FSN-Text. Die richtige SCTID im verwendeten Release verifizieren; dieses Dokument legt keine unbestätigte ID fest.

Die aktuelle Write-back-Dokumentation beschreibt Ersetzen, Löschen und manuelle Bearbeitung, aber keine separate `clear_id`-Aktion. Diese muss durchgängig in Review, Decisions-JSON, Validierung und JSONCAS-/XMI-Write-back ergänzt werden.

**Noch zu entscheiden:** Soll die vorausgefüllte Regel standardmäßig aktiviert sein? Soll sie nur Findings oder jede passende Annotation im gewählten Geltungsbereich bearbeiten? Technisch ist außerdem das korrekte Leeren eines String-Features (`None` oder leerer String) anhand von CAS-Serialisierung und INCEpTION-Reimport zu testen.

**Abnahme:** Anzahl und Offsets der Annotationen bleiben identisch; nur die betroffenen IDs sind leer. Das Ergebnis kann wieder in INCEpTION importiert werden.

## 7. Review & apply: bedingungsbasierte automatische Auswahl

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

### Gewünschtes Soll-Verhalten

Wenn die Review-Anforderung lautet „ausgeschlossene Konzepte dürfen nie vorgeschlagen werden“, muss dies als verbindliche Regel für **alle** relevanten Zielmodi festgelegt werden:

- Die geltende exclusion list sichtbar anzeigen.
- Die Kandidatenfilterung vor Ranking-/Review-Ausgabe anwenden.
- Historische Ziele, Ancestor-Ziele und BM25-/SNOGIT-Ziele identisch behandeln.
- Die Regel beim automatischen Auswählen und vor Write-back erneut prüfen, insbesondere bei geladenen älteren Suggestions-/Decisions-Dateien.
- Ausschlüsse haben Vorrang vor inclusion-list-Mitgliedschaft und hoher BM25-Bewertung.

**Abnahme:** Ein absichtlich ausgeschlossener Zielcode erscheint in keinem auswählbaren Vorschlag und kann nicht durch automatische Bedingungen freigegeben werden. Falls diagnostische Kandidaten gezeigt werden, klar als nicht auswählbar kennzeichnen.

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
4. `clear_id` als eigenständige, verlustfreie Aktion implementieren und den Number-Sonderfall konfigurieren.
5. Bedingungsform, historische Automatik, Zustandsverwaltung und Undo umsetzen.
6. BM25-Metriken zunächst zur Beobachtung anzeigen; mit Reviewer-Beispielen kalibrieren und anschließend die automatische Auswahl freigeben.

## 12. Übergreifende Tests und Abnahme

- [x] Gewünschte Layer-/Suggestion-Standardwerte aus Abschnitt 3 und 5 in einer neuen GUI-Sitzung korrekt.
- [x] Explizite Layer-/Suggestion-Einstellungen bleiben über Reruns erhalten.
- [x] Policy-Tabellen nutzen dieselben Findings wie Exporte und Sanitization; Filter verändern die Quelldaten nicht.
- [ ] Exclusion-list-Ziele werden über alle Kandidatenquellen und unterstützten Zielmodi gesperrt.
- [ ] Number-Sonderregel entfernt ausschließlich die ID, nicht die Annotation.
- [ ] Mehrdeutige historische Ziele werden nicht versehentlich automatisch gewählt.
- [ ] BM25-Gleichstände, weniger als drei Ziele und nicht vergleichbare Scores bleiben manuell.
- [ ] Apply Conditions setzt Zielauswahl, resolved und reviewed konsistent.
- [ ] Undo stellt automatische Änderungen zurück, ohne manuelle Arbeit zu verlieren.
- [ ] JSONCAS-/XMI-Write-back, Decisions-Export/-Import und INCEpTION-Reimport funktionieren.
- [ ] Sanitized Upload funktioniert auch im Reviewer-Szenario; Fehler-/Teilfehlerdiagnose und sichere Wiederholung sind geprüft.

## 13. Verwendete Quellen

- Ursprüngliche Review-Notizen: `todo.md`.
- OKF-Einstieg: `okf/snomed-post-processing/index.md`.
- Review-/Write-back-Semantik: `okf/snomed-post-processing/workflows/reviewed-decisions-and-writeback.md`.
- Direkte Codeprüfung: `gui/sanitization_check_tab.py`, `gui/sanitization_run_tab.py`, `hdf5_handling/policy.py`, `sanitization/resolver.py`, `sanitization/semantic_bm25.py` (jeweils unter `src/snomed_post_processing/`).
