# Procurement readiness

MailVault preserves the evidence required for procurement intelligence. It does not place domain-specific inference inside the archive core.

## Why complete messages are required

Supplier and commercial facts frequently appear only in message bodies:

- revised price;
- discount approval;
- delivery commitment;
- replacement proposal;
- technical acceptance or rejection;
- warranty statement;
- country of origin;
- payment terms;
- Incoterm clarification;
- explanation for price or lead-time change.

An attachment-only downloader cannot reliably support procurement memory.

## Procurement source manifest

`manifests/procurement_sources.jsonl` exposes body and MIME-part evidence with:

- canonical message archive ID;
- raw EML hash and path;
- provider message and thread identifiers;
- RFC thread headers;
- sender, recipients and domains;
- subject and dates;
- mailbox, labels and flags;
- MIME part path and role;
- filenames, MIME types, SHA-256 and object paths.

## Required downstream layers

A production RMS integration should add separate, versioned layers:

1. Native document extraction for text PDF, Word, Excel, HTML and structured formats.
2. Selective OCR for actual image documents and image-only PDF pages.
3. Document VLM fallback only for complex visual cases.
4. Counterparty and contact entity resolution.
5. Procurement case clustering.
6. Document classification.
7. Line-item, commercial-term and technical-attribute extraction.
8. Evidence-backed review and approval.
9. RMS ingestion through an idempotent adapter.

## Supplier intelligence

MailVault preserves the basis for deterministic metrics:

```text
RFQ count
response count
response latency
quotation completeness
technical compliance
replacement frequency
approved replacement rate
award rate
quoted lead time
actual delivery evidence
price competitiveness
certificate coverage
```

Metrics must account for canonical-message deduplication and mailbox occurrence semantics.

## Price intelligence

A price fact is incomplete without context. The downstream schema should retain:

```text
supplier
requested and offered item identity
manufacturer, brand, model and part number
quantity and unit of measure
unit and extended price
currency
quotation date and validity
Incoterm and named place
freight, insurance, tax and discount
payment terms
minimum order
lead time
source message, document, page/sheet/cell and exact evidence
```

Historical prices must not be represented as current market prices.

## Technical substitution memory

Requested identity and offered identity must remain distinct.

```text
requested manufacturer/brand/model/part/specification
offered manufacturer/brand/model/part/specification
technical differences
replacement type
proposal source
approval or rejection state
reason
approver evidence
awarded execution identity
```

The evidence graph should link inquiry line, offer line, datasheet, clarification email, approval/rejection and purchase-order line.

## Evidence contract

Every derived fact should include:

```text
source message archive ID
raw EML SHA-256
source MIME part path
blob SHA-256 when applicable
page, sheet, cell range, text span or bounding box
extractor name and version
confidence
review state
reviewer and review time when approved
```

No LLM output should become an approved procurement fact without evidence and policy checks.
