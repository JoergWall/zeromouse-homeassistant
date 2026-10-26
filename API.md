# ZeroMOUSE Cloud-API (reverse engineered)

> [!NOTE]
> Inoffizielle Dokumentation ohne Verbindung zu ZeroMOUSE, entstanden, um ZeroMOUSE mit
> Home Assistant nutzen zu können. Die API ist nicht öffentlich dokumentiert und kann sich
> jederzeit ändern. *Unofficial notes, not affiliated with ZeroMOUSE, written to make
> ZeroMOUSE work with Home Assistant. The API is undocumented and may change at any time.*

Quelle: Analyse der ZeroMOUSE-App (React Native), Stand 2025-08-31; Bewerten, Löschen und
Filter geprüft mit App 1.14.19 (Oktober 2026).

Das Backend ist ein klassischer **AWS Amplify**-Stack in `eu-central-1`:

| Baustein | Wert |
|---|---|
| Cognito User Pool | `eu-central-1_LS6CKN0t1` |
| User Pool App-Client | `7pdec0rbivg5hg8u3pke4veg0f` (kein Client-Secret) |
| Cognito Identity Pool | `eu-central-1:2b2f7d40-d6f9-474e-a06b-6441c4059601` |
| AppSync GraphQL | `https://f36gc6o7jnewxe37dhn3fochza.appsync-api.eu-central-1.amazonaws.com/graphql` (Auth: `AMAZON_COGNITO_USER_POOLS`) |
| AppSync Realtime | `wss://f36gc6o7jnewxe37dhn3fochza.appsync-realtime-api.eu-central-1.amazonaws.com/graphql` |
| REST (API Gateway) | `https://4oj9bcxedi.execute-api.eu-central-1.amazonaws.com/DEV` |
| S3 Bilder | Bucket `mbr-ptf-images-eu-central-1-dev` |

## 1. Authentifizierung

1. Login gegen den Cognito User Pool mit E-Mail + Passwort (Amplify-Standard: `USER_SRP_AUTH`).
   Ergebnis: `IdToken`, `AccessToken`, `RefreshToken` (Token-Lebensdauer 1 h).
2. `ownerID` in allen Queries = Claim `sub` aus dem ID-Token.
3. Refresh über `REFRESH_TOKEN_AUTH`.

| API | Header |
|---|---|
| GraphQL (AppSync) | `Authorization: <AccessToken>` |
| REST (API Gateway) | `auth-token: <IdToken>` |
| S3 | AWS SigV4 mit temporären Credentials aus dem Identity Pool |

Temporäre AWS-Credentials für S3:

```
POST https://cognito-identity.eu-central-1.amazonaws.com/
X-Amz-Target: AWSCognitoIdentityService.GetId            {"IdentityPoolId": "...", "Logins": {"cognito-idp.eu-central-1.amazonaws.com/eu-central-1_LS6CKN0t1": "<IdToken>"}}
X-Amz-Target: AWSCognitoIdentityService.GetCredentialsForIdentity   {"IdentityId": "...", "Logins": {...}}
```

## 2. REST-Endpunkte (`…/DEV`)

Alle mit Header `auth-token: <IdToken>`.

| Methode | Pfad | Body | Zweck |
|---|---|---|---|
| GET | `/device-shadow/?deviceID={id}` | – | AWS-IoT-Device-Shadow des Geräts |
| PATCH | `/device-shadow/?deviceID={id}` | Teilobjekt, z. B. `{"system":{"undecidableMode":1}}` | schreibt in `state.desired` |
| PATCH | `/block-modes/?deviceID={id}` | `{"blockModeIn": 0..3}` | Eingangsmodus |
| PATCH | `/block-modes/?deviceID={id}` | `{"blockModeOut": 0..2, "outOpenAt": min, "outCloseAt": min}` | Ausgangsmodus |
| GET | `/statistics/{id}` | – | `{"stats": {"prey_monthly": [{"period": "YYYY-MM", "value": n}]}}` |
| GET | `/user/` | – | Benutzerprofil |
| POST | `/user/rating-feedback` | `{"feedback": ...}` | App-Bewertung |
| PATCH | `/cat-clusters/` | `{"deviceID", "eventID", "catClusterId"}` | Katze eines Events korrigieren (lernt Embedding) |

### Device Shadow

```jsonc
{
  "state": {
    "reported": { … },           // Ist-Zustand des Geräts
    "desired":  { … }            // von der App gesetzt; App zeigt desired ?? reported
  }
}
```

| Pfad | Bedeutung | Werte |
|---|---|---|
| `system.kkzmBlockModeIn` | Eingangsmodus | `0` Freier Eintritt, `1` Beute blockieren, `2` Gesichtserkennung, `3` Gesperrt |
| `system.kkzmBlockModeOut` | Ausgangsmodus | `0` Offen, `1` Gesperrt, `2` Zeitbasiert |
| `system.kkzmOutOpenAt` / `kkzmOutCloseAt` | Zeitfenster Ausgang | Minuten seit Mitternacht (Default 540 / 1080) |
| `system.undecidableMode` | Verhalten bei „nicht entscheidbar“ | `0` Smart, `1` Immer öffnen, `2` Immer blockieren |
| `system.metricWifiRSSI` | WLAN-Signal | dBm |
| `proximity.irPreyEventTime` | Mindest-Sperrzeit nach Beute | Sekunden: 10, 15, 30, 60, 120, 300, 600, 900, 1800, 3600 |
| `rfid.blockEnabled` | „Beute blockieren“ (sonst nur aufzeichnen) | bool |

## 3. GraphQL (AppSync)

Wichtigste Operationen (vollständige Query-Strings stehen in `custom_components/zeromouse/api.py`):

| Operation | Zweck |
|---|---|
| `listFlapByOwnerID(ownerID)` | Geräte inkl. `catClusters {id name allowEntry embedding threshold}`, `blockUnknownCats`, Firmware, `ai_score`, `userFeedback_score`, `eventCount` |
| `getMbrPtfFlapData(deviceID)` | ein Gerät |
| `updateMbrPtfFlapData(input)` | Name, `blockUnknownCats`, `catClusters` (immer die komplette Liste senden) |
| `listEventbyDeviceChrono(deviceID, sortDirection, limit, nextToken, filter)` | Ereignisse (neueste zuerst mit `DESC`) inkl. `images {imageIndex …}` |
| `listEventbyFavoriteChrono(deviceID, …)` | nur Favoriten (eigener Index) |
| `listEventByOwner(ownerID, eventTime, …)` | Ereignisse aller Geräte eines Kontos |
| `updateMbrPtfEventData(input, condition)` | `isFlagged` (Bewertung), `isDeleted` (Löschen), `isFavorite`, `isSeen`, `catClusterId_byUser`, … – siehe 3.1 |
| `queryMbrPtfMessageDataByOwner(ownerID)` | In-App-Nachrichten |
| `getLabelData(deviceID)` | Hardware-/Label-Infos, Beta-Flag |
| `subscription onCreateMbrPtfEventData` | Echtzeit: neues Ereignis (ohne Variablen, serverseitig nach Owner gefiltert) |

`classification_byNet` eines Ereignisses und wie die App 1.14.19 es anzeigt (Titel und
Filter-Checkbox):

| Wert | Anzeige in der App | Bemerkung |
|---|---|---|
| `clean` | Keine Beute erkannt | |
| `early` | Keine Beute erkannt | vom Gerät als `isHidden: 1` markiert |
| `prey` | Beute erkannt | |
| `undecidable` | Nicht entscheidbar | `isHidden: 1`, wird trotzdem angezeigt |
| `late`, `unknown` | Nicht entscheidbar | `late` mit `isHidden: 1` |
| `test` | Hand erkannt | |
| `out` | Rausgehen erkannt | `isHidden: 1`; Checkbox nur bei aktivierten versteckten Ereignissen vorausgewählt |
| `free`, sonstige | Nicht entscheidbar | erscheinen in der ungefilterten Liste nicht |

### 3.1 Bewerten, Löschen, Filtern (App 1.14.19)

Es gibt **keine** `deleteMbrPtfEventData`-Mutation. Alles läuft über
`updateMbrPtfEventData`; `eventID` und `deviceID` sind Pflichtfelder des Inputs. Die
Integration schickt zusätzlich `condition: {eventTime: {attributeExists: true}}`, damit
eine falsche ID kein leeres Ereignis anlegt (Fehler `ConditionalCheckFailedException`).

| Aktion in der App | Input |
|---|---|
| *Richtig* | `isFlagged: 2`; erneutes Tippen auf das aktive *Richtig*: `isFlagged: 0` |
| *Falsch* | `isFlagged: 1`; erneutes Tippen: `isFlagged: 0` |
| *Löschen* | `isDeleted: 1` (das Ereignis bleibt in der Cloud, wird aber nicht mehr gelistet) |
| Favorit (Herz) | `isFavorite: 1, ttl: null` – das Ereignis läuft nicht mehr ab; höchstens `MAX_LIKED_EVENTS` = 50 Favoriten. Entfernen: `isFavorite: 0, ttl: <jetzt + Aufbewahrungsdauer>` (Epoch-Sekunden) |

Filterdialog (`DEFAULT_FILTER_STATE`: alle Checkboxen außer *Rausgehen erkannt* an;
diese folgt der Einstellung „versteckte Ereignisse anzeigen“). Die App setzt daraus
`classificationFilter` zusammen und filtert serverseitig mit
`or: [{classification_byNet: {eq: …}}, …]`, immer zusammen mit `ownerID eq` und
`isDeleted eq 0`:

| Checkbox | Klassifikationen |
|---|---|
| Keine Beute erkannt | `clean`, `early` |
| Beute erkannt | `prey` |
| Nicht entscheidbar | `undecidable`, `late`, `unknown` |
| Hand erkannt | `test` |
| Rausgehen erkannt | `out` |
| Nur Favoriten anzeigen | Abfrage über `listEventbyFavoriteChrono`, ignoriert die anderen Filter |

Ohne `classificationFilter` zeigt die App `early`, `late`, `undecidable` (auch wenn
versteckt) und alle nicht versteckten Ereignisse außer `free`.

## 4. Bilder

S3-Key (Amplify Storage, `accessLevel: 'private'`):

```
private/{cognitoIdentityId}/devices/{deviceID}/events/{eventID}/images/{imageIndex}.jpg
```

`titleImageIndex` eines Events gibt das Vorschaubild an.
