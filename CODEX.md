# CODEX.md

## Scopo del progetto

**Spesa** è una pipeline locale e osservabile per trasformare fotografie di scontrini in dati strutturati, verificabili e utilizzabili per analisi della spesa personale.

Repository pubblico:

- <https://github.com/humanitiesNerd/spesa>

Il progetto non vuole delegare tutta la semantica a un modello linguistico. L'architettura separa intenzionalmente:

1. acquisizione delle immagini;
2. trascrizione OCR fedele;
3. parsing deterministico;
4. arricchimento semantico;
5. validazione;
6. esportazione;
7. analisi.

L'obiettivo è mantenere ogni trasformazione esplicita, ispezionabile, riproducibile e correggibile.

---

## Ambiente di sviluppo

Ambiente principale:

- Ubuntu 24.04 in WSL2;
- shell `zsh`;
- Python gestito con `uv`;
- repository versionato con Jujutsu (`jj`) e interoperabile con Git;
- directory abituale del progetto: `~/spesa/spesa`.

Installazione:

```bash
git clone https://github.com/humanitiesNerd/spesa
cd spesa
uv sync
```

Esecuzione dei test:

```bash
uv run pytest -v
```

I test pubblici devono funzionare senza:

- chiave API OpenAI;
- immagini reali di scontrini;
- dati privati;
- accesso di rete;
- OCR reale.

---

## Struttura concettuale della pipeline

### 1. Immagini originali

Le fotografie degli scontrini sono conservate localmente in:

```text
scontrini_originali/
```

Questi file contengono dati privati e non devono essere aggiunti al repository pubblico.

Le immagini possono arrivare dal telefono tramite Syncthing.

---

### 2. Trascrizione OCR

Lo script principale per l'OCR è:

```text
scripts/ocr_scontrino.py
```

Lo script:

- accetta immagini, comprese immagini HEIC;
- converte temporaneamente HEIC in JPEG quando necessario;
- invia l'immagine all'API OpenAI;
- richiede una trascrizione fedele delle righe;
- salva il risultato in JSON.

La responsabilità dell'LLM è limitata alla trascrizione. Non deve ricostruire autonomamente la semantica completa degli articoli.

Directory coinvolte:

```text
trascrizioni/
trascrizioni_raw/
```

La rappresentazione raw deve preservare:

- ordine delle righe;
- testo ambiguo;
- righe quantità/prezzo;
- righe sconto;
- intestazione;
- totale;
- riferimenti all'immagine sorgente.

Non “correggere” silenziosamente ciò che appare strano nello scontrino.

---

### 3. Parsing deterministico

Lo script principale è:

```text
scripts/parse_scontrino_raw.py
```

Il parser trasforma la trascrizione raw in una struttura semantica.

Principi:

- preferire funzioni piccole e leggibili;
- usare regex limitate a singoli formati;
- evitare regex monolitiche;
- separare parsing dell'intestazione e parsing del corpo;
- conservare le righe sorgente da cui deriva ogni elemento;
- produrre warning strutturati invece di fallire quando possibile.

Il parser deve gestire anche casi degradati, per esempio:

- intestazione del negozio assente o tagliata;
- OCR imperfetto;
- punto vendita non identificato;
- quantità come `2 x 1,990 EUR`;
- prezzi unitari con tre decimali;
- righe di sconto separate;
- descrizioni articolo spezzate;
- negozi che stampano voci generiche come `VARIE`.

Funzioni già introdotte o concetti equivalenti:

```text
is_items_header
is_probable_receipt_body_line
```

Warning noti:

```text
intestazione_negozio_mancante
punto_vendita_non_identificato
```

Un input incompleto non deve essere automaticamente considerato invalido.

---

### 4. Ricevute parsate

Le ricevute strutturate sono salvate localmente in:

```text
parsed_receipts/
```

Ogni ricevuta deve mantenere una relazione chiara con:

- identificativo della ricevuta;
- immagini sorgente;
- righe raw;
- negozio;
- data e ora;
- articoli;
- quantità;
- importi;
- sconti;
- totale;
- warning.

Il totale ricostruito deve poter essere confrontato con il totale stampato.

---

### 5. Esportazione degli articoli

Uno script di esportazione produce un CSV tabellare degli articoli estratti.

Nel workflow corrente, l'esportazione deve essere eseguita prima dell'arricchimento quando i dati parsati sono cambiati.

Esempio del passaggio concettuale:

```bash
uv run python -m scripts.export_items_csv
```

L'output principale è nella directory:

```text
exports/
```

---

### 6. Mapping semantico dei prodotti

File principale:

```text
data/product_mapping.csv
```

Il mapping usa esclusivamente corrispondenza esatta.

Non esiste più il campo `match_type` e non sono supportate regole generiche `contains`.

Il mapping collega una descrizione raw a metadati normalizzati, per esempio:

- `description_norm`;
- categoria;
- funzione alimentare;
- quantità di riferimento;
- unità di riferimento;
- altri attributi utili alle analisi.

Durante l'arricchimento, i prodotti sconosciuti devono essere aggiunti automaticamente a `product_mapping.csv` come righe incomplete.

Quando disponibili, vanno precompilati:

- `reference_quantity`;
- `reference_unit`.

Il completamento semantico resta manuale e deliberato.

Non introdurre fuzzy matching o classificazione automatica senza una richiesta esplicita e senza test: aumenterebbero l'opacità e il rischio di associazioni errate.

---

### 7. Override delle quantità

File:

```text
data/item_quantity_overrides.csv
```

Serve per correggere singoli acquisti quando la quantità non può essere dedotta in modo affidabile dalla descrizione o dal mapping generale.

La chiave deve usare nomi coerenti con l'export:

```text
receipt_id
line_index
```

Non rinominare `line_index` in modo diverso nei vari file.

Esempi tipici:

- multipack non esplicitato chiaramente;
- stesso prodotto venduto in confezioni diverse;
- quantità dedotta da etichetta o conoscenza esterna;
- voce generica dello scontrino chiarita tramite annotazione.

Gli override specifici hanno precedenza sul valore generale del mapping.

---

### 8. Arricchimento

Script:

```text
scripts/enrich_items.py
```

Input principale:

```text
exports/items.csv
data/product_mapping.csv
data/item_quantity_overrides.csv
```

Output principale:

```text
exports/items_enriched.csv
```

Responsabilità:

- applicare il mapping esatto;
- applicare gli override per singola riga;
- calcolare quantità e prezzi normalizzati;
- aggiungere prodotti sconosciuti al mapping;
- preservare identificativi e tracciabilità;
- segnalare dati incompleti.

Il file `items_enriched.csv` è la fonte diretta per le analisi successive. Non rifare inutilmente il merge con `product_mapping.csv` negli script di analisi.

---

## Analisi dei prezzi

Script:

```text
scripts/find_price_comparisons.py
```

Lo script legge direttamente:

```text
exports/items_enriched.csv
```

Obiettivo:

- confrontare lo stesso prodotto normalizzato tra supermercati;
- usare prezzi normalizzati, per esempio euro/kg o euro/litro;
- mostrare tutte le osservazioni rilevanti;
- evitare confronti semanticamente troppo generici.

Problemi già individuati:

1. la differenza di costo dei peperoni appare eccessiva e va verificata;
2. una categoria generica come `frutta` non è un prodotto confrontabile;
3. il report deve mostrare la lista completa di supermercati e prezzi, non soltanto migliore e peggiore.

Non “aggiustare” anomalie cancellandole. Prima verificare:

- quantità di riferimento;
- unità;
- peso netto;
- eventuali sconti;
- descrizione normalizzata;
- override;
- riga sorgente.

---

## Analisi temporale: priorità corrente

La priorità attuale è aggiungere analisi per intervallo temporale.

### Filtraggio dell'arricchimento

`enrich_items` dovrà accettare limiti inclusivi, per esempio:

```bash
uv run python -m scripts.enrich_items \
  --from-date 2026-06-15 \
  --to-date 2026-06-20
```

Requisiti:

- entrambe le date sono opzionali;
- senza date, elaborare tutti gli scontrini;
- con una sola data, applicare solo quel limite;
- i limiti sono inclusivi;
- validare il formato ISO `YYYY-MM-DD`;
- una esecuzione filtrata non deve sovrascrivere accidentalmente l'export completo;
- il nome o percorso dell'output filtrato deve rendere visibile l'intervallo usato;
- mantenere compatibilità con il workflow completo esistente.

### Livello di reporting separato

Le analisi non devono essere incorporate in modo confuso dentro `enrich_items`.

Creare uno script o modulo separato per produrre:

- andamento giornaliero della spesa;
- totale e media giornaliera;
- spesa per funzione;
- spesa per categoria;
- composizione di una funzione specifica;
- grafici salvati su file.

Caso d'uso prioritario:

- analizzare la spesa dal 15 giugno 2026;
- verificare il ritmo medio giornaliero;
- evitare che una finestra parziale venga confusa con l'intero archivio.

Grafici richiesti:

1. andamento giornaliero;
2. spesa per funzione o categoria;
3. grafico a torta di una funzione, per esempio `proteine_pronte`, suddivisa per `description_norm`.

I grafici devono derivare dai dati esportati, non da valori duplicati o inseriti manualmente nel codice.

---

## Privacy e repository pubblico

Considerare privati almeno:

```text
.env
.envrc
scontrini_originali/
trascrizioni/
trascrizioni_raw/
parsed_receipts/
exports/
logs/
```

Verificare sempre `.gitignore` prima di aggiungere file generati o fixture reali.

Non includere nei test pubblici:

- nomi e indirizzi personali;
- numeri di carta;
- dati completi di acquisti reali;
- immagini originali;
- ricevute non anonimizzate;
- chiavi API.

Per documentazione o fixture pubbliche usare dati:

- sintetici;
- minimali;
- anonimizzati;
- sufficienti a riprodurre il comportamento.

La storia pubblica del repository è stata già ripulita una volta da dati privati. Evitare qualunque regressione.

---

## Filosofia architetturale

Le modifiche devono privilegiare:

- esplicitazione delle trasformazioni;
- funzioni piccole;
- dati intermedi ispezionabili;
- warning strutturati;
- test di regressione basati su fixture;
- nomi coerenti tra CSV e codice;
- comportamento deterministico;
- possibilità di riprendere il lavoro dopo un'interruzione;
- separazione delle responsabilità;
- errori visibili invece di fallback silenziosi.

Da evitare:

- grandi refactor non richiesti;
- astrazioni premature;
- framework aggiunti senza necessità;
- typing complesso introdotto solo per “pulizia”;
- euristiche nascoste;
- deduzioni semantiche non verificabili;
- dipendenze dei test da servizi esterni;
- modifiche contemporanee a molti stadi della pipeline;
- rinominare colonne senza migrazione e test;
- sovrascrivere output completi con risultati filtrati.

Il progetto preferisce codice noioso, leggibile e diagnosticabile a codice ingegnoso ma opaco.

---

## Strategia di modifica consigliata

Prima di cambiare il codice:

1. leggere i file interessati;
2. individuare input e output reali;
3. controllare i test esistenti;
4. verificare i nomi delle colonne nei CSV;
5. proporre una modifica circoscritta;
6. aggiungere prima o insieme una fixture regressiva;
7. eseguire la suite completa.

Comando minimo di verifica:

```bash
uv run pytest -v
```

Per gli script modificati, eseguire anche un test manuale mirato con dati sintetici o locali.

Non modificare file di dati reali come effetto collaterale di un test.

Usare `tmp_path` e `monkeypatch` nei test che coinvolgono filesystem o percorsi configurabili.

---

## Jujutsu

Il repository usa Jujutsu.

Comandi utili:

```bash
jj status
jj diff
jj log -n 10
jj commit -m "descrizione"
```

Per pubblicare il lavoro, il bookmark `main` deve puntare al commit corretto:

```bash
jj bookmark set main -r @-
jj git push --bookmark main
```

Se `jj git push --bookmark main` risponde:

```text
Bookmark main@origin already matches main
Nothing changed.
```

significa che il bookmark locale non è stato spostato verso i nuovi commit oppure che tutto è già pubblicato.

Non eseguire operazioni distruttive sulla storia senza una richiesta esplicita.

---

## Criteri di completamento

Una modifica è completa quando:

- il comportamento richiesto è implementato;
- i test esistenti continuano a passare;
- sono presenti test per il nuovo comportamento;
- gli output restano ispezionabili;
- non vengono inclusi dati privati;
- non vengono alterati file reali durante i test;
- i comandi documentati funzionano;
- le assunzioni sono visibili nel codice o nella documentazione;
- i warning distinguono dati incompleti da errori effettivi.

---

## Come iniziare una sessione Codex

All'inizio di una sessione:

```bash
cd ~/spesa/spesa
jj status
jj log -n 5
uv run pytest -v
```

Poi leggere almeno:

```text
README.md
CODEX.md
pyproject.toml
scripts/enrich_items.py
scripts/find_price_comparisons.py
```

Se il lavoro riguarda parsing o OCR, leggere anche:

```text
scripts/ocr_scontrino.py
scripts/parse_scontrino_raw.py
tests/
```

Prima di scrivere codice, riassumere:

- stato attuale;
- file coinvolti;
- comportamento da preservare;
- piano minimo della modifica;
- test da aggiungere o aggiornare.

---

## Attività corrente suggerita

Implementare il supporto agli intervalli temporali senza confondere arricchimento e reporting.

Ordine consigliato:

1. aggiungere parsing e validazione di `--from-date` e `--to-date`;
2. filtrare le righe per `receipt_date`;
3. impedire la sovrascrittura dell'export completo;
4. aggiungere test per:
   - nessun filtro;
   - solo data iniziale;
   - solo data finale;
   - entrambe le date;
   - estremi inclusivi;
   - intervallo invalido;
   - formato data invalido;
   - output filtrato separato;
5. creare successivamente uno script di report che legga l'export arricchito;
6. aggiungere report tabellari prima dei grafici;
7. aggiungere i grafici solo dopo avere verificato i totali.

Non modificare contemporaneamente la semantica del mapping prodotti.
