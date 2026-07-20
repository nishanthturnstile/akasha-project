# Crop-Akasha Reference Mapping

> Comprehensive mapping of the 76 Akasha crops against the existing `crops.json` reference data, including seeding types, varieties, maturity options, tillage types, and irrigation types.

---

## 1. Seeding Types

Defined in `app/bulk_creation.py` and seeded via Alembic revision `20260623_0003`.

| ID | Name | Description |
|----|------|-------------|
| 0 | `direct_seed` | Seeds sown directly in the field |
| 1 | `transplant` | Started in nursery, moved to field |
| 2 | `planting_cutting` | Vegetative propagation by cuttings or tubers |
| 3 | `vine` | Perennial vine crop |
| 4 | `perennial_tree` | Long-lived tree or shrub crop |

### Frontend label mapping

When a crop is selected in the vegetation cycle UI (`EditFieldDialog.tsx`), the start-date field label changes based on `seedingTypeId`:

| crops.json int | Backend name | DB id → `seedingTypeId` | Frontend label (`sowingDateLabel`) | Example crops |
|:---:|---|---|---|---|
| 0 | `direct_seed` | 1 | **Sowing date** | Wheat, Rice, Maize, Cotton, Chickpea |
| 1 | `transplant` | 2 | **Planting date** | Apple, Mango, Banana, Tomato, Citrus |
| 2 | `planting_cutting` | 3 | **Planting date** / **Cut-off (start) date** | Sugarcane, Potato |
| 3 | `vine` | 4 | **Bud swelling start date** | Grape |
| 4 | `perennial_tree` | 5 | **Bud sprouting start date** | Lemon, Orange |

---

## 2. Crop List (76 crops)

Numbered list as provided.

---

## 3. Varieties

All 76 crops currently have **not confirmed** variety lists. These need to be finalized in `varieties.json`.

---

## 4. Maturity Options

Available maturity options that can be assigned to any crop:

- `default-maturity`
- `early`
- `early-middle`
- `middle`
- `middle-late`
- `late`

All 76 crops currently have **all can choose** — any of the above maturity options may be assigned per variety.

---

## 5. Crop Mapping (Seeding, Varieties, Maturity)

### 5.1 Matched Crops — seeding_type confirmed from crops.json

| # | Crop | crops.json name_en (id) | seeding_type | Varieties exist? | Maturity options |
|---|------|------------------------|-------------|-----------------|-----------------|
| 1 | Almond | Almonds (28) | 0 — direct_seed | not confirmed | all can choose |
| 2 | Apple | Apple (30) | 1 — transplant | not confirmed | all can choose |
| 5 | Banana | Bananas (62) | 1 — transplant | not confirmed | all can choose |
| 6 | Barley | Spring barley (36) / Winter barley (38) | 0 — direct_seed | not confirmed | all can choose |
| 11 | Buckwheat | Buckwheat (45) | 0 — direct_seed | not confirmed | all can choose |
| 14 | Carrot | Carrot (99) | 0 — direct_seed | not confirmed | all can choose |
| 15 | Cashew | Cashew (53) | 0 — direct_seed | not confirmed | all can choose |
| 16 | Castor | Castor crop (100) | 0 — direct_seed | not confirmed | all can choose |
| 17 | Cauliflower | Cauliflower (130) | 0 — direct_seed | not confirmed | all can choose |
| 18 | Cherry | Cherry (51) | 1 — transplant | not confirmed | all can choose |
| 19 | Chickpea | Chickpea (89) | 0 — direct_seed | not confirmed | all can choose |
| 21 | Citrus | Citrus (20) | 1 — transplant | not confirmed | all can choose |
| 22 | Coconut | Coconut (125) | 0 — direct_seed | not confirmed | all can choose |
| 23 | Coffee | Coffee (16) | 0 — direct_seed | not confirmed | all can choose |
| 24 | Coriander | Coriander (147) | 0 — direct_seed | not confirmed | all can choose |
| 25 | Cotton | Cotton (12) | 0 — direct_seed | not confirmed | all can choose |
| 26 | Cowpea | Cowpea (90) | 0 — direct_seed | not confirmed | all can choose |
| 27 | Cucumber | Cucumber (79) | 0 — direct_seed | not confirmed | all can choose |
| 28 | Cumin | Cumin (83) | 0 — direct_seed | not confirmed | all can choose |
| 32 | Garlic | Garlic (68) | 0 — direct_seed | not confirmed | all can choose |
| 33 | Ginger | Ginger (64) | 0 — direct_seed | not confirmed | all can choose |
| 34 | Grape | Grapes (24) | 3 — vine | not confirmed | all can choose |
| 35 | Groundnut | Groundnut (93) | 0 — direct_seed | not confirmed | all can choose |
| 37 | Guava | Guava (201) | 0 — direct_seed | not confirmed | all can choose |
| 40 | Lentil | Lentils (96) | 0 — direct_seed | not confirmed | all can choose |
| 41 | Lucerne / Alfalfa | Alfalfa (23) | 0 — direct_seed | not confirmed | all can choose |
| 42 | Maize | Corn (Maize) (3) | 0 — direct_seed | not confirmed | all can choose |
| 43 | Mango | Mango (97) | 1 — transplant | not confirmed | all can choose |
| 44 | Mung Bean | Mungbean (88) | 0 — direct_seed | not confirmed | all can choose |
| 46 | Mustard | Mustard (103) | 0 — direct_seed | not confirmed | all can choose |
| 47 | Okra | Okra (128) | 0 — direct_seed | not confirmed | all can choose |
| 48 | Onion | Onions (69) | 0 — direct_seed | not confirmed | all can choose |
| 49 | Papaya | Papaya (134) | 0 — direct_seed | not confirmed | all can choose |
| 50 | Peas | Peas (7) | 0 — direct_seed | not confirmed | all can choose |
| 51 | Pigeon Pea | Pigeonpea (91) | 0 — direct_seed | not confirmed | all can choose |
| 52 | Pineapple | Pineapple (85) | 0 — direct_seed | not confirmed | all can choose |
| 53 | Pomegranate | Pomegranate (122) | 0 — direct_seed | not confirmed | all can choose |
| 54 | Potato | Potatoes (10) | 0 — direct_seed | not confirmed | all can choose |
| 57 | Rice | Rice (14) | 0 — direct_seed | not confirmed | all can choose |
| 58 | Rubber | Rubber (61) | 1 — transplant | not confirmed | all can choose |
| 59 | Safflower | Safflower (180) | 0 — direct_seed | not confirmed | all can choose |
| 61 | Sesame | Sesame (52) | 0 — direct_seed | not confirmed | all can choose |
| 62 | Soybean | Soybeans (6) | 0 — direct_seed | not confirmed | all can choose |
| 63 | Strawberry | Strawberry (115) | 1 — transplant | not confirmed | all can choose |
| 64 | Sugarcane | Sugarcane (21) | 2 — planting_cutting | not confirmed | all can choose |
| 65 | Sunflower | Sunflower (5) | 0 — direct_seed | not confirmed | all can choose |
| 66 | Sweet Potato | Sweet potato (92) | 0 — direct_seed | not confirmed | all can choose |
| 67 | Tapioca / Cassava | Cassava (54) | 0 — direct_seed | not confirmed | all can choose |
| 68 | Tea | Tea (219) | 1 — transplant | not confirmed | all can choose |
| 69 | Tobacco | Tobacco (18) | 0 — direct_seed | not confirmed | all can choose |
| 70 | Tomato | Tomatoes (84) | 1 — transplant | not confirmed | all can choose |
| 71 | Turmeric | Turmeric (65) | 0 — direct_seed | not confirmed | all can choose |
| 73 | Walnut | Walnuts (101) | 1 — transplant | not confirmed | all can choose |
| 74 | Watermelon | Watermelon (72) | 0 — direct_seed | not confirmed | all can choose |
| 75 | Wheat | Wheat (1) | 0 — direct_seed | not confirmed | all can choose |
| 76 | Linseed | Flax (13) | 0 — direct_seed | not confirmed | all can choose |

**56 matched crops**

---

### 5.2 Possible Match — name alias or ambiguous

| # | Crop | Possible crops.json match | Proposed seeding_type | Varieties | Maturity | Reason |
|---|------|--------------------------|---------------------|-----------|----------|--------|
| 3 | Areca | Areca nut (135) | 0 — direct_seed | not confirmed | all can choose | "Areca" = "Areca nut" |
| 4 | Bajra | Millet (58) | 0 — direct_seed | not confirmed | all can choose | Bajra = pearl millet |
| 9 | Black Pepper | Pepper (78) | 0 — direct_seed | not confirmed | all can choose | Pepper in crops.json may refer to *Piper nigrum* or capsicum |
| 10 | Brinjal | Eggplant (197) | 0 — direct_seed | not confirmed | all can choose | Brinjal = Eggplant / Aubergine |
| 20 | Chili | Chilli (75) | 0 — direct_seed | not confirmed | all can choose | Spelling difference (Chili vs Chilli) |
| 29 | Fennel | Fennel Bitter (152) / Fennel Sweet (153) | 0 — direct_seed | not confirmed | all can choose | Fennel exists as two sub-entries |
| 31 | Field Pea | Peas (7) | 0 — direct_seed | not confirmed | all can choose | Field pea is a specific type of pea |
| 38 | Jowar | Sorghum (41) | 0 — direct_seed | not confirmed | all can choose | Jowar = Indian name for sorghum |
| 45 | Muskmelon | Melon (57) | 0 — direct_seed | not confirmed | all can choose | Muskmelon is a specific melon type |
| 56 | Ragi | Millet (58) | 0 — direct_seed | not confirmed | all can choose | Ragi = finger millet |

**10 possible-match crops**

> **Seeding type** is taken from the matched `crops.json` entry (e.g. Areca → Areca nut `seeding_type: 0`). Since the name alias is not an exact match, the seeding type is marked as "proposed" rather than "confirmed".

---

### 5.3 Not Matched — not found in crops.json

| # | Crop | Proposed seeding_type | Varieties | Maturity | Notes (based on growth habit) |
|---|------|---------------------|-----------|----------|------------------------------|
| 7 | Berseem | 0 — direct_seed | not confirmed | all can choose | Annual forage legume — seed-sown like Alfalfa (0) |
| 8 | Bitter Gourd | 0 — direct_seed | not confirmed | all can choose | Annual vine — seed-sown like Cucumber (0) |
| 12 | Cabbage | 0 — direct_seed | not confirmed | all can choose | Annual/biennial leafy crop — seed-sown |
| 13 | Cardamom | 1 — transplant | not confirmed | all can choose | Perennial herb — nursery-propagated like Coffee (0) |
| 30 | Fenugreek | 0 — direct_seed | not confirmed | all can choose | Annual herb — seed-sown |
| 36 | Guar | 0 — direct_seed | not confirmed | all can choose | Annual legume — seed-sown like Cowpea (0) |
| 39 | Jute | 0 — direct_seed | not confirmed | all can choose | Annual fibre crop — seed-sown |
| 55 | Pumpkin | 0 — direct_seed | not confirmed | all can choose | Annual vine — seed-sown |
| 60 | Saffron | 1 — transplant | not confirmed | all can choose | Propagated from corms — perennial like transplant crops |
| 72 | Urad | 0 — direct_seed | not confirmed | all can choose | Annual legume — seed-sown like Mung Bean (0) |

**10 not-matched crops**

> **Seeding type** is proposed based on **growth habit** comparison with botanically similar crops already in `crops.json`. These are provisional and should be reviewed by a domain expert.

---

## 6. Tillage Types

Defined in `scripts/data/tillage-types.json`.

| # | Name |
|---|------|
| 1 | Conservation tillage |
| 2 | Conventional tillage |
| 3 | Intensive tillage |
| 4 | Mulch-till |
| 5 | No-till |
| 6 | Reduced tillage |
| 7 | Ridge-till |
| 8 | Rotational tillage |
| 9 | Strip-till |
| 10 | Zone tillage |

---

## 7. Irrigation Types

Defined in `scripts/data/irrigation-types.json`.

| # | Name |
|---|------|
| 1 | Center pivot irrigation |
| 2 | Drip irrigation |
| 3 | Hose-end sprinklers |
| 4 | Lateral move irrigation |
| 5 | Lawn sprinkler irrigation |
| 6 | Micro-irrigation |
| 7 | Rainfall irrigation |
| 8 | Sprinkler irrigation |
| 9 | Subirrigation |
| 10 | Surface irrigation |

---

## Summary

| Category | Count |
|----------|-------|
| Matched (seeding_type confirmed) | 56 |
| Possible match (alias/ambiguous) | 10 |
| Not matched (new crops) | 10 |
| **Total** | **76** |

---

## 8. Crop Selection Icons (hidden)

Crop badges (Sprout, Timer, Scissors) shown next to crop names in the vegetation cycle `Select` dropdown (`EditFieldDialog.tsx`) are currently hidden behind `const ENABLE = false;` in the `CycleCard` function.

To restore: flip both occurrences to `const ENABLE = true;` — one in the `SelectTrigger` block and one in the `SelectContent` `.map()` block.

| Icon | Component | Condition |
|------|-----------|-----------|
| `Sprout` | `hasVariety` | `crop.hasVariety` |
| `Timer` | `maturityOptions` | `crop.maturityOptions.length > 0` |
| `Scissors` | `seedingTypeId === 3` | `crop.seedingTypeId === 3` (planting/cutting crops)
