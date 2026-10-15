# Digitaler Leistungsantrag in der GKV (BPMN 2.0 / Camunda 8)

<a href="https://www.credly.com/badges/6c178145-c9fc-41f1-8b55-721d4f2d8ac2/public_url">
  <img src="docs/badge-bpmn.png" alt="Camunda Knowledge – BPMN" width="140">
</a>
<a href="https://www.credly.com/badges/65984af8-7e16-459c-8b23-ddd1b5019758/public_url">
  <img src="docs/badge-business-analyst.png" alt="Camunda 8 – Business Analyst" width="140">
</a>

In diesem Projekt habe ich mir angeschaut, wie ein Leistungsantrag bei einer Krankenkasse bearbeitet wird, und den Ablauf mit BPMN neu gedacht. Ausgangspunkt war die Frage, wie man so einen Prozess digitalisieren kann, ohne dass die Fachlichkeit auf der Strecke bleibt.

Spannend fand ich vor allem die gesetzlichen Fristen. Nach § 13 Abs. 3a SGB V muss die Kasse innerhalb von drei Wochen entscheiden, mit Gutachten des Medizinischen Dienstes innerhalb von fünf. Wird die Frist ohne Begründung überschritten, gilt die Leistung als genehmigt. Ein Prozess, der Fristen nicht im Blick hat, ist hier also ein echtes Risiko.

## Projektstand

- [x] Ist-Prozess modelliert und Schwachstellen analysiert
- [x] Soll-Prozess entworfen (strategisch und operativ)
- [ ] Prozess in Camunda 8 ausführbar machen (Formulare, DMN, Nachrichten)
- [ ] Kennzahlen im Ist/Soll-Vergleich auswerten

## Ist-Prozess

![Ist-Prozess](docs/ist-leistungsantrag.png)

So läuft die Bearbeitung typischerweise ab, wenn noch viel auf Papier passiert: Der Antrag kommt per Post, wird gescannt, geprüft, bei Bedarf geht er zum Medizinischen Dienst, dann wird entschieden.

Beim Modellieren sind mir vor allem diese Punkte aufgefallen:

- Niemand überwacht die Entscheidungsfrist.
- Wird der Medizinische Dienst eingeschaltet, erfährt der Versicherte davon nichts. Dadurch gilt eigentlich weiter die kürzere Frist.
- Auf fehlende Unterlagen oder das Gutachten wird gewartet, ohne nachzuhaken.
- Jede Nachreichung läuft wieder über Post und Scanner.
- Ob ein Gutachten nötig ist, entscheidet jeder Sachbearbeiter für sich.
- Bescheide werden von Hand erstellt.

## Soll-Prozess

### Überblick

![Strategischer Prozess](docs/strategisch-leistungsantrag.png)

Die grobe Sicht für alle, die nur wissen wollen, was passiert, nicht wie.

### Detaillierter Ablauf

![Operativer Soll-Prozess](docs/soll-leistungsantrag.png)

Hier sieht man, wer was macht. Alles in der Lane „System“ übernimmt die Process Engine, Menschen kommen nur noch dort ins Spiel, wo wirklich eine fachliche Einschätzung gebraucht wird. Die beiden Kommunikationsschleifen (Unterlagen nachfordern, Gutachten einholen) habe ich in Unterprozesse ausgelagert, damit das Hauptmodell lesbar bleibt:

![Unterlagen nachfordern](docs/soll-unterlagen-nachfordern.png)

![MD-Gutachten einholen](docs/soll-gutachten-einholen.png)

### Was sich gegenüber dem Ist-Prozess ändert

| Problem im Ist-Prozess | Lösung im Soll-Prozess |
|---|---|
| Frist wird nicht überwacht | Ein Timer meldet sich vor Fristablauf, die Teamleitung priorisiert den Vorgang |
| Versicherter wird bei MD-Gutachten nicht informiert | Direkt nach dem Gutachtenauftrag geht automatisch eine Information raus |
| Warten ohne Nachhaken | Nach 14 bzw. 21 Tagen wird automatisch erinnert |
| Post und Scannen | Der Antrag kommt digital rein |
| Gutachtenbedarf uneinheitlich | Gesetzliche Pflichtfälle erkennt eine Entscheidungstabelle (DMN), alle anderen Fälle prüft weiterhin ein Sachbearbeiter |
| Bescheide von Hand | Der Bescheid wird automatisch aus einer Vorlage erzeugt |

Eine Sache war mir beim Gutachten wichtig: Das System kann nur sicher sagen, wann ein Gutachten **gesetzlich vorgeschrieben** ist. Ob es darüber hinaus nötig ist (§ 275 Abs. 1 SGB V), ist eine Ermessensfrage. Deshalb entscheidet das System hier nie „kein Gutachten“, sondern legt diese Fälle dem Sachbearbeiter vor.

Bewusst nicht modelliert habe ich das Widerspruchsverfahren und Hilfsmittel zum Behinderungsausgleich, für die eigene Fristen gelten.

## Dateien

| Datei | Inhalt |
|---|---|
| [`models/ist-leistungsantrag.bpmn`](models/ist-leistungsantrag.bpmn) | Ist-Prozess |
| [`models/strategisch-leistungsantrag.bpmn`](models/strategisch-leistungsantrag.bpmn) | Strategischer Überblick |
| [`models/soll-leistungsantrag.bpmn`](models/soll-leistungsantrag.bpmn) | Operativer Soll-Prozess (Camunda 8) |

Die Modelle lassen sich mit dem Camunda Desktop Modeler öffnen.

*Fiktives Lernprojekt ohne echte Daten.*
