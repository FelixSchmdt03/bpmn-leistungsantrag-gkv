"""
Testdaten-Generator für den Prozess „Leistungsantrag bearbeiten“ (Camunda 8).

Was das Skript macht:
  1. Startet zufällige Leistungsanträge (Nachricht „Antrag“)
  2. Erledigt alle Sendeaufgaben (Job-Typ „nachricht-versenden“) – ersetzt den fehlenden Job Worker
  3. Bearbeitet die Benutzeraufgaben mit realistischen, zufälligen Entscheidungen
  4. Schickt verzögert die Antworten von außen: Unterlagen (Versicherter), Gutachten (MD), selten eine Rücknahme

Zeitraffer: 1 Sekunde entspricht 1 Tag (MD 14–30 Tage, Nachreichung 10–30 Tage, Sachbearbeitung ~7–10 Tage).
Aufruf:   python testdaten_generator.py --anzahl 150 --minuten 15
Voraussetzung: Datei „.env“ mit den Zugangsdaten (Reiter „Env Vars“ in der Camunda Console) im selben Ordner.
"""
import argparse
import datetime as dt
import json
import os
import random
import sys
import time

try:
    import requests
except ImportError:
    sys.exit("Bitte zuerst installieren:  pip install requests")

JOB_TYP = "nachricht-versenden"
WORKER = "testdaten-generator"


# ---------------------------------------------------------------- Konfiguration
def lade_env(pfad=".env"):
    """Liest die .env-Datei (Format KEY=wert oder export KEY='wert')."""
    if not os.path.exists(pfad):
        sys.exit(f"Datei {pfad} nicht gefunden. Lege sie neben dieses Skript.")
    werte = {}
    for zeile in open(pfad, encoding="utf-8"):
        zeile = zeile.strip()
        if not zeile or zeile.startswith("#") or "=" not in zeile:
            continue
        if zeile.startswith("export "):
            zeile = zeile[len("export "):]
        key, val = zeile.split("=", 1)
        werte[key.strip()] = val.strip().strip("'").strip('"')
    return werte


def erstes(env, *namen):
    for n in namen:
        if env.get(n):
            return env[n]
    return None


class Camunda:
    def __init__(self, env):
        self.client_id = erstes(env, "ZEEBE_CLIENT_ID", "CAMUNDA_CLIENT_ID")
        self.secret = erstes(env, "ZEEBE_CLIENT_SECRET", "CAMUNDA_CLIENT_SECRET")
        self.token_url = erstes(env, "ZEEBE_AUTHORIZATION_SERVER_URL", "CAMUNDA_OAUTH_URL") \
            or "https://login.cloud.camunda.io/oauth/token"
        self.audience = erstes(env, "ZEEBE_TOKEN_AUDIENCE", "CAMUNDA_TOKEN_AUDIENCE") or "zeebe.camunda.io"
        self.base = erstes(env, "ZEEBE_REST_ADDRESS", "CAMUNDA_REST_ADDRESS")
        if not self.base:
            cid = erstes(env, "CAMUNDA_CLUSTER_ID")
            region = erstes(env, "CAMUNDA_CLUSTER_REGION")
            if cid and region:
                self.base = f"https://{region}.zeebe.camunda.io/{cid}"
        if not (self.client_id and self.secret and self.base):
            sys.exit("In der .env fehlen Client-ID, Secret oder REST-Adresse.")
        self.base = self.base.rstrip("/")
        self.token = None
        self.token_bis = 0

    def _token(self):
        if self.token and time.time() < self.token_bis - 60:
            return self.token
        r = requests.post(self.token_url, data={
            "grant_type": "client_credentials", "client_id": self.client_id,
            "client_secret": self.secret, "audience": self.audience}, timeout=30)
        r.raise_for_status()
        d = r.json()
        self.token, self.token_bis = d["access_token"], time.time() + d.get("expires_in", 3600)
        return self.token

    def post(self, pfad, body=None, ok_fehler=()):
        r = requests.post(f"{self.base}/v2{pfad}", json=body or {},
                          headers={"Authorization": f"Bearer {self._token()}"}, timeout=60)
        if r.status_code in ok_fehler:
            return None
        if r.status_code == 403:
            sys.exit(f"403 Forbidden bei {pfad}: Der Client braucht im Admin-Bereich des Clusters Rechte.\n{r.text}")
        if r.status_code >= 400:
            print(f"  ! {r.status_code} bei {pfad}: {r.text[:200]}")
            return None
        return r.json() if r.content else {}


# ---------------------------------------------------------------- Fachliche Zufallsdaten
LEISTUNGEN = [  # (leistungsart, Gewicht, Kosten von–bis, Beschreibungen)
    ("hilfsmittel", 55, (50, 2000), ["Rollator nach Hüft-OP", "Kompressionsstrümpfe", "Gehhilfe", "Badewannenlifter"]),
    ("haeusliche_krankenpflege", 25, (300, 4000), ["Wundversorgung nach OP", "Medikamentengabe", "Verbandswechsel"]),
    ("rehabilitation", 15, (1500, 6000), ["Ambulante Reha nach Knie-OP", "Orthopädische Reha", "Kardiologische Reha"]),
    ("vorsorge", 5, (800, 3000), ["Vorsorgekur", "Mutter-Kind-Kur"]),
]
NAMEN = ["Max Mustermann", "Erika Musterfrau", "Jonas Becker", "Lea Schulz", "Paul Wagner", "Mia Hoffmann",
         "Ben Fischer", "Emma Weber", "Noah Koch", "Hanna Richter"]


def neuer_antrag(nr, praefix):
    art, _, (lo, hi), texte = random.choices(LEISTUNGEN, weights=[l[1] for l in LEISTUNGEN])[0]
    return {
        "antragsId": f"{praefix}-{nr:03d}",
        "leistungsart": art,
        "versicherterName": random.choice(NAMEN),
        "versichertennummer": f"A{random.randint(100000000, 999999999)}",
        "eingangsdatum": dt.date.today().isoformat(),
        "leistungsbeschreibung": random.choice(texte),
        "verordnungLiegtVor": random.random() < 0.85,
        # Hilfsmittel sind meist günstig: 70 % liegen bis 500 €
        "kosten": (random.randint(5, 50) * 10 if art == "hilfsmittel" and random.random() < 0.7
                   else random.randint(lo // 10, hi // 10) * 10),
    }


# ---------------------------------------------------------------- Ablauf
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--anzahl", type=int, default=150, help="Anzahl Anträge")
    ap.add_argument("--minuten", type=float, default=15, help="Zeitraum, über den die Anträge verteilt werden")
    args = ap.parse_args()

    c = Camunda(lade_env(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")))
    print(f"Verbunden mit {c.base}")
    lauf = "L" + time.strftime("%d%H%M")   # eindeutige Antragsnummern je Lauf, z. B. L181430-001
    print(f"Antragsnummern dieses Laufs: {lauf}-001 ...")

    start_abstand = args.minuten * 60 / args.anzahl
    naechster_start, gestartet = time.time(), 0
    geplant = []           # verzögerte Nachrichten: (zeitpunkt, name, correlationKey, variablen)
    erledigt = set()       # bereits abgeschlossene User-Task-Keys
    pruef_runden = {}      # antragsId -> wie oft schon „Antrag prüfen“
    stat = {"gestartet": 0, "jobs": 0, "aufgaben": 0, "gutachten": 0, "nachforderungen": 0, "ruecknahmen": 0}
    ende_leerlauf = None
    letzter_status = 0

    while True:
        jetzt = time.time()

        # 1) Neue Anträge starten
        if gestartet < args.anzahl and jetzt >= naechster_start:
            gestartet += 1
            a = neuer_antrag(gestartet, lauf)
            if c.post("/messages/publication", {"name": "Antrag", "correlationKey": a["antragsId"],
                                                "timeToLive": 60000, "variables": a}) is not None:
                stat["gestartet"] += 1
                print(f"+ {a['antragsId']}: {a['leistungsart']}, {a['kosten']} €, Verordnung={a['verordnungLiegtVor']}")
                if random.random() < 0.03:  # seltene Rücknahme durch den Versicherten
                    geplant.append((jetzt + random.uniform(5, 30), "Rücknahme", a["antragsId"], {}))
            naechster_start = jetzt + random.expovariate(1 / start_abstand)

        # 2) Fällige Nachrichten von außen senden
        for eintrag in [g for g in geplant if g[0] <= jetzt]:
            geplant.remove(eintrag)
            _, name, key, var = eintrag
            c.post("/messages/publication", {"name": name, "correlationKey": key, "timeToLive": 3600000, "variables": var})
            if name == "Rücknahme":
                stat["ruecknahmen"] += 1
            print(f"  ✉ {name} für {key}")

        # 3) Sendeaufgaben erledigen
        res = c.post("/jobs/activation", {"type": JOB_TYP, "worker": WORKER, "timeout": 30000, "maxJobsToActivate": 50})
        for job in (res or {}).get("jobs", []):
            v, el = job.get("variables", {}), job.get("elementId")
            key = v.get("antragsId")
            if el == "TaskB_GutachtenBeauftragen":      # MD antwortet nach einer Weile
                geplant.append((jetzt + random.uniform(14, 30), "Gutachten", key,
                                {"gutachtenErgebnis": random.choices(["befuerwortet", "nicht befuerwortet"], [75, 25])[0]}))
                stat["gutachten"] += 1
            elif el == "TaskA_UnterlagenAnfordern":     # Versicherter reicht nach
                geplant.append((jetzt + random.uniform(10, 30), "Unterlagen", key, {"verordnungLiegtVor": True}))
                stat["nachforderungen"] += 1
            c.post(f"/jobs/{job['jobKey']}/completion", {"variables": {}}, ok_fehler=(404,))
            stat["jobs"] += 1

        # 4) Benutzeraufgaben bearbeiten (nicht alle sofort – so entstehen Liegezeiten)
        res = c.post("/user-tasks/search", {"filter": {"state": "CREATED"}, "page": {"limit": 100}})
        for t in (res or {}).get("items", []):
            tkey = t["userTaskKey"]
            if tkey in erledigt or random.random() > {"Task_AntragPruefen": 0.3, "Task_UeberAntragEntscheiden": 0.2}.get(t.get("elementId"), 0.5):
                continue
            vs = c.post(f"/user-tasks/{tkey}/variables/search", {"page": {"limit": 100}}) or {}
            v = {}
            for item in vs.get("items", []):
                try:
                    v[item["name"]] = json.loads(item["value"])
                except (ValueError, TypeError):
                    v[item["name"]] = item.get("value")
            ergebnis = entscheide(t.get("elementId"), v, pruef_runden)
            c.post(f"/user-tasks/{tkey}/assignment", {"assignee": "sachbearbeitung-demo", "allowOverride": True}, ok_fehler=(404, 409))
            if c.post(f"/user-tasks/{tkey}/completion", {"variables": ergebnis}, ok_fehler=(404, 409)) is not None:
                erledigt.add(tkey)
                stat["aufgaben"] += 1
                print(f"  ✔ {t.get('elementId')} {v.get('antragsId')}: {ergebnis}")

        # Statuszeile alle 30 Sekunden
        if jetzt - letzter_status > 30:
            offen_anz = len([x for x in (res or {}).get("items", []) if x["userTaskKey"] not in erledigt])
            print(f"  · Status {time.strftime('%H:%M:%S')}: gestartet {gestartet}, Jobs erledigt {stat['jobs']}, "
                  f"Aufgaben erledigt {stat['aufgaben']}, offene Aufgaben gefunden {offen_anz}, Nachrichten geplant {len(geplant)}")
            letzter_status = jetzt

        # Ende: alle gestartet, keine Nachrichten mehr offen, eine Weile nichts mehr zu tun
        if gestartet >= args.anzahl and not geplant:
            offen = (res or {}).get("items", [])
            if not [x for x in offen if x["userTaskKey"] not in erledigt]:
                ende_leerlauf = ende_leerlauf or jetzt
                if jetzt - ende_leerlauf > 30:
                    break
            else:
                ende_leerlauf = None
        time.sleep(2)

    print("\nFertig:", json.dumps(stat, ensure_ascii=False))


def entscheide(element, v, runden):
    """Realistische Zufallsentscheidungen für die Benutzeraufgaben."""
    aid = v.get("antragsId")
    if element == "Task_AntragPruefen":
        runden[aid] = runden.get(aid, 0) + 1
        if not v.get("verordnungLiegtVor") and runden[aid] == 1:
            return {"pruefergebnis": "UNTERLAGEN_FEHLEN"}
        if v.get("pflichtfall") or random.random() < 0.10:
            return {"pruefergebnis": "GUTACHTEN_ERFORDERLICH"}
        bewilligt = random.random() < 0.8
        return {"pruefergebnis": "ENTSCHEIDUNGSREIF",
                "entscheidung": "BEWILLIGT" if bewilligt else "ABGELEHNT",
                "begruendung": "Voraussetzungen erfüllt" if bewilligt else "Medizinische Notwendigkeit nicht ausreichend belegt"}
    if element == "Task_UeberAntragEntscheiden":
        quote = 0.85 if v.get("gutachtenErgebnis") == "befuerwortet" else 0.2
        bewilligt = random.random() < quote
        return {"entscheidung": "BEWILLIGT" if bewilligt else "ABGELEHNT",
                "begruendung": "Gutachten des MD befürwortet die Leistung" if bewilligt else "Gutachten des MD befürwortet die Leistung nicht"}
    return {"priorisiert": True}


if __name__ == "__main__":
    main()
