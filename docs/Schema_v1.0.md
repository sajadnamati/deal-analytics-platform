# Schema v1.0 — Freeze (2025-11-12)

### Overview
Schema v1.0 defines the **canonical data structure** for the Energy-Trade Analytics Platform.  
It serves as the single, stable backbone for all higher-level modules (API, AI, analytics).  
No structural changes are permitted after this freeze; future changes require a new schema version.

---

## 1. Core Table: `deal_event`
Each row represents a **commercial transaction** (deal).

| Column | Type | Description |
|--------|------|-------------|
| `id` | uuid (PK) | Unique deal identifier |
| `deal_timestamp` | timestamptz | Timestamp of deal creation or execution |
| `product_id` | uuid → `ref_product(id)` | Linked traded product |
| `unit_code` | text → `ref_unit(code)` | Measurement unit |
| `currency_code` | text → `ref_currency(code)` | Pricing currency |
| `counterparty_id` | uuid → `ref_counterparty(id)` | Trade counterparty |
| `quantity` | numeric | Volume transacted (≠ 0) |
| `fixed_price` | numeric | Deal price (≥ 0) |
| `direction` | text | Buy/Sell indicator |
| `effective_date`, `delivery_start`, `delivery_end` | date | Contract period fields |
| `price_type` | text | e.g. fixed / floating |
| `notes` | text | Free text remarks |
| `owner_id` | uuid | Auto-filled user ID (for RLS) |
| `created_at`, `updated_at` | timestamptz | Automatic audit timestamps |

---

## 2. Reference Tables

| Table | Key | Purpose |
|--------|-----|----------|
| `ref_product` | `id (uuid)` | Product catalog (HSFO, LSFO, Bitumen, etc.) |
| `ref_unit` | `code (text)` | Measurement units (MT, BBL …) |
| `ref_currency` | `code (text)` | Allowed currencies (USD, IRR …) |
| `ref_counterparty` | `id (uuid)` | Registered trading partners |

All reference tables enforce unique keys to guarantee data integrity.

---

## 3. Constraints & Integrity
- `quantity <> 0`
- `fixed_price ≥ 0` when provided  
- All FK references validated (`deal_event` → refs)  
- Deleting a referenced product/unit/currency is restricted.  
- Deleting a counterparty sets `counterparty_id = null` in existing deals.

---

## 4. Auditability
Automatic timestamps:
- `created_at` = insert time  
- `updated_at` = auto-updated on every change (via trigger)  

---

## 5. Security (RLS)
**Row-Level Security** is enabled on all tables.

| Table | Policy summary |
|--------|----------------|
| `deal_event` | Only row owner (`owner_id = auth.uid()`) may view or modify. |
| `ref_*` | Read-only to authenticated users; updates allowed only by service role. |
| `schema_version` | Read-only to authenticated users. |

This enforces full data segregation and prevents cross-user visibility.

---

## 6. Schema Registry
Table: `schema_version`

| Column | Type | Description |
|--------|------|-------------|
| `version` | text (PK) | Schema identifier |
| `release_date` | date | Freeze date |
| `notes` | text | Change summary |

Current entry:


---

## 7. Governance Rules
1. **Schema edits** require a migration script and version bump.  
2. **Branch protection**: `main` locked after tagging `v1.0`.  
3. **AI and API layers** must always read from a declared schema version.  
4. **Future versions** (`v1.1`, `v2.0`, …) will extend via controlled migrations only.

---

**Status:** ✅ Frozen  
**Tag:** `v1.0`  
**Date:** 2025-11-12  
**Owner:** Project Architect — S. Namati

