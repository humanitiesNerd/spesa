# Spesa

[![Tests](https://github.com/humanitiesNerd/spesa/actions/workflows/tests.yml/badge.svg?branch=main)](https://github.com/humanitiesNerd/spesa/actions/workflows/tests.yml)

Spesa is a Python pipeline that turns grocery receipt photos into line-item data for personal budget analysis.

Most expense trackers record where a purchase was made and how much it cost. Spesa focuses on **what was bought**: products, quantities, unit prices, discounts and totals. This makes it possible to analyze spending by product, category, shop or practical use, and to compare prices over time.

Spesa is free and open-source software. Its OCR stage currently relies on OpenAI's proprietary hosted API, while parsing, validation, enrichment and analysis are performed locally by inspectable code. This keeps the resulting dataset under the user's control without relying on a proprietary expense-tracking application.

The project currently targets my own Italian grocery receipts. It is a personal tool under active development, not a universal receipt-scanning application.

## Quick start

### Requirements

* Python 3.12+
* [uv](https://docs.astral.sh/uv/)
* an OpenAI API key for OCR transcription
* Ubuntu or WSL recommended

Install the dependencies:

```bash
uv sync
```

Create a `.env` file:

```text
OPENAI_API_KEY=...
```

Process one receipt:

```bash
uv run python -m scripts.processa_scontrino scontrini_originali/RECEIPT.heic
```

The command produces:

```text
trascrizioni/RECEIPT.json
parsed_receipts/RECEIPT.parsed.json
```

Run the public test suite:

```bash
uv run pytest -v
```

The tests do not require an API key, real receipt images or an OCR request.

> Some directory names are still in Italian because the project began as a personal tool.

## What is it for?

Spesa was created to answer questions such as:


* How much do particular dietary choices cost?
* Can I adjust my dietary habits in order to spend a bit less ?
* Which products consume the largest share of my grocery budget?
* Could I buy the same item more cheaply at another shop?
* How often do I buy a product, and how does its price change?


Budget analysis is the primary goal. Nutrition-related classification is a smaller, secondary layer built on the same purchase data.

## How it works

```text
receipt photo
    ↓
OCR transcription
    ↓
ordered raw text lines
    ↓
deterministic Python parser
    ↓
products, quantities, prices and discounts
    ↓
check against the printed receipt total
    ↓
normalization and analysis
```

OpenAI is currently used only for visual transcription. The model returns ordered text lines; it does not decide which lines represent products, quantities or discounts.

Everything after transcription is handled by local deterministic code. The parser reconstructs the receipt and checks whether item amounts and discounts reconcile with the final printed total.

There is no alternative OCR backend yet. The raw-line JSON format provides a clear boundary where another OCR implementation could be added later.

This separation is intentional. An earlier version asked the model to both read and interpret each receipt. Its output was often plausible, but harder to reproduce, test and debug. Keeping OCR and parsing separate preserves inspectable intermediate files and makes parser behavior testable with fixtures.

## Real example

The following anonymized image is a real input. The raw text is in Italian because the project currently works with Italian supermarket receipts.

![Anonymized receipt example](docs/images/20260607_154438_prep.jpeg)

The OCR stage returns ordered text only:

```json
{
  "raw_lines": [
    "9 x 1,690 EUR",
    "*BEV.SZ SOIA 1 PIACER 22% 15,21",
    "TOTALE COMPLESSIVO 15,21",
    "di cui IVA 2,74",
    "Pagamento elettronico 15,21",
    "Importo pagato 15,21"
  ]
}
```

The local parser reconstructs the purchased item:

```json
{
  "description": "*BEV.SZ SOIA 1 PIACER",
  "quantity": 9,
  "unit_price": 1.69,
  "net_amount": 15.21
}
```

Here, quantity and unit price appear on one line, while the product description and total appear on the next. That relationship is reconstructed by explicit parsing rules rather than by the OCR model.

For supported layouts, the parser also performs an accounting check:

```text
sum(item amounts) + discounts == printed receipt total
```

A successful match does not prove that every OCR character is correct. It is a practical way to expose missing items, misread amounts or incorrectly associated discounts.

## Normalization and analysis

Receipt descriptions are progressively mapped to a consistent product taxonomy through an explicit CSV file. Unknown products can be added to the mapping for later manual classification.

![Product mapping](docs/images/product_mapping.png)

The enriched data can be analyzed with Python, pandas, jq, SQLite or other tools.

### Spending by product

![Spending by product](docs/images/spesa_per_prodotto.png)

### Spending by practical function

Products may also be grouped by use, for example `ready_to_eat_protein`, `breakfast_base` or `fresh_side_dish`.

![Spending by function](docs/images/spesa_per_funzione.png)

## Current scope and limitations

The parser currently supports receipt layouts encountered in my own data, including:

* Conad and Dok receipts;
* multiline quantity patterns such as `2 x 2,39 EUR`;
* product discounts;
* reconciliation with the final total.

Confidence is highest on layouts represented by test fixtures. Unsupported supermarkets, new promotional formats and OCR mistakes may require new rules or manual corrections.

When an edge case appears, it is added as a versioned fixture and protected by a regression test. The project does not yet claim broad compatibility with arbitrary receipts.

## Project structure

```text
fixtures/             versioned test fixtures
scripts/              Python scripts
scontrini_originali/  original receipt images
trascrizioni/         raw OCR JSON (gitignored)
parsed_receipts/      parsed output (gitignored)
tests/                pytest test suite
```

## Roadmap

* make the OCR backend replaceable;
* make the reports graphical;
* support more supermarket layouts;
* improve historical price comparisons;
* expand product categorization;
* export to SQLite and Beancount;
* develop further budget and nutrition reports.

## License

Spesa is licensed under the [Apache License 2.0](LICENSE.md).