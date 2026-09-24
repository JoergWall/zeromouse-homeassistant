# ZeroMOUSE Cloud-API (reverse engineered)

Quelle: `ZeroMouseRn.app` (iOS/React-Native, Bundle-ID `de.zeromouse.app`), Hermes-Bytecode v98
(`main.jsbundle`), disassembliert/dekompiliert mit [hermes-dec](https://github.com/P1sec/hermes-dec).
Stand der App: Build vom 2025-08-31.

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
| Firebase (nur Push) | Projekt `zeromouse`, Sender-ID `52558640423` |

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
| `updateMbrPtfEventData(input)` | `isSeen`, `isFavorite`, `isFlagged`, `catClusterId_byUser`, … |
| `deleteMbrPtfEventData(input)` | Ereignis löschen |
| `queryMbrPtfMessageDataByOwner(ownerID)` | In-App-Nachrichten |
| `getLabelData(deviceID)` | Hardware-/Label-Infos, Beta-Flag |
| `subscription onCreateMbrPtfEventData` | Echtzeit: neues Ereignis (ohne Variablen, serverseitig nach Owner gefiltert) |

`classification_byNet` eines Ereignisses:

| Wert | Bedeutung |
|---|---|
| `prey` | Beute erkannt |
| `clean` | keine Beute |
| `undecidable` | nicht entscheidbar |
| `out` | Katze geht raus |
| `early` / `late` | Auslösung zu früh/zu spät (keine Klassifikation) |
| `free`, `test`, `unknown` | Sonderfälle |

## 4. Bilder

S3-Key (Amplify Storage, `accessLevel: 'private'`):

```
private/{cognitoIdentityId}/devices/{deviceID}/events/{eventID}/images/{imageIndex}.jpg
```

`titleImageIndex` eines Events gibt das Vorschaubild an.
