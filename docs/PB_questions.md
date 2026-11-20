# SteamDB — Business Questions & Analytical Framework

## 1. Use Case & Core Objective
**Use Case:** A game studio or publisher planning a new release wants to understand which product characteristics and commercial levers maximize both **entry into** and **long-term permanence (longevity) inside** the Steam Global Top 100 Sellers chart.

**North-Star Question:**  
> Which product characteristics (monetization/price, play modes, genres/tags, perceived quality) and post-launch commercial levers (discounts, launch timing) best differentiate short-lived 1-week appearances from games that sustain long-term permanence in the Steam Top 100?

---

## 2. Analytical Scope, Definitions & Data Hygiene

### Core Metrics (Measuring "Permanence")
- **Total Weeks in Top 100 (`total_weeks`):** Distinct weeks a game appears in `weeksheet`.
- **Max Consecutive Streak (`max_consecutive_weeks`):** Longest uninterrupted run in the Top 100 (`consecutive_weeks`).
- **Next-Week Retention Rate (`retention_t1`):** Probability that a title present in week `t` remains in the Top 100 in week `t+1`.
- **Weekly Rank Delta (`rank_delta`):** `last_week_rank - rank` (positive values indicate rank improvement).

### Tenure Tiers (Game-Level Segmentation)
- **One-Week Spike:** `1 week` total
- **Short Run:** `2–4 weeks`
- **Medium Run:** `5–12 weeks`
- **Evergreen / High Longevity:** `13+ weeks` (with a `40+ weeks` sub-tier for perennial leaders)

### Cross-Cutting Segmentations & Hygiene Rules
1. **Exclude Non-Game Hardware:** Filter out hardware entries present in the chart (e.g., `Steam Deck` [`1675200`], `Steam Deck - Valve Certified Refurbished` [`2550670`], `Valve Index® Base Station` [`1059570`]) before computing game averages/retention.
2. **Free-to-Play vs. Paid Split:** Because Steam's Top 100 is **revenue-ranked**, free-to-play titles (`price = 0`) appear via in-game purchases/DLCs. Compare Free vs. Paid separately so live-service F2P giants do not mask patterns for paid titles.
3. **Play Modes Treated Separately:** Treat **Singleplayer**, **Multiplayer**, and **Co-op** as **distinct dimensions** (do not merge Multiplayer and Co-op into one bucket; account for both Store tags and Steam category labels such as `Singleplayer`/`Single-player`, `Multiplayer`/`Multi-player`/`Massively Multiplayer`, and `Co-op`/`Online Co-Op`/`Co-op Campaign`).
4. **Validated Tags & Minimum Sample Threshold:** Filter tags with `tags.whitelist = TRUE` and enforce a minimum number of distinct games and weekly appearances before ranking tag performance, avoiding outliers from rare tags.

---

## 3. Business Questions by Pillar

### Pillar 1 — Market Dynamics: Entry vs. Permanence
- **Q1.1 (Tenure Concentration):** What share of Top 100 games appear for only 1 week vs. 2–4, 5–12, or 13+ weeks? How much of the weekly chart space is occupied by evergreen titles?
- **Q1.2 (First-Time Debuts vs. Returning Games):** Do newly debuting titles (`consecutive_weeks = 1` and never seen before) retain better or worse in week `t+1` than returning titles (`last_week_rank IS NULL` with prior history)?
- **Q1.3 (Entry Rank Threshold):** How strongly does a title's debut/current rank tier (`Top 10`, `11–30`, `31–60`, `61–100`) predict its next-week retention rate and total longevity?

### Pillar 2 — Monetization & Pricing Strategy (Pre-Launch Product Decision)
- **Q2.1 (Free vs. Paid Longevity):** Do Free-to-Play games (`price = 0`) achieve higher median rank, consecutive streaks, and next-week retention than Paid games (`price > 0`)?
- **Q2.2 (Optimal Paid Price Band):** Among paid titles, which price bands (e.g., `<= $10`, `$10.01–$20`, `$20.01–$35`, `$35.01–$50`, `> $50`) maximize **total weeks**, **median weekly rank**, and **next-week retention** while keeping **discount dependency** low?
- **Q2.3 (Full Price vs. Discounted Rank Differential):** What is the rank and retention gap between weeks sold at full price (`discount = 0`) and weeks sold on sale (`discount > 0`) across each price band?

### Pillar 3 — Game DNA: Play Modes, Genres & Tags (Design & Positioning)
- **Q3.1 (Play-Mode Longevity: Singleplayer vs. Multiplayer vs. Co-op):** Treating **Multiplayer** and **Co-op** separately (alongside **Singleplayer**), how do their longevity distributions (`13+ weeks` share), median ranks, and retention rates compare — both overall and within Paid-only titles?
- **Q3.2 (Winning Individual Tags):** Which whitelisted tags (meeting the minimum sample threshold) exhibit the highest next-week retention, longest median tenure, and best average customer rating?
- **Q3.3 (Winning Tag Combinations):** Which **pairs of whitelisted tags** appear most frequently among `13+ week` evergreen titles vs. `1-week` spikes?
- **Q3.4 (Healthy Niches vs. Promo-Dependent Niches):** Which tags combine high longevity and solid ratings **without** relying heavily on deep discounting?

### Pillar 4 — Perceived Quality & Customer Ratings
- **Q4.1 (Value of High Ratings):** Are higher `rating_label` tiers (`Overwhelmingly Positive`, `Very Positive`, `Mostly Positive`, `Mixed` and below) associated with better median rank, higher next-week retention, and longer consecutive streaks?
- **Q4.2 (Quality Floor & Exceptions):** What is the typical minimum `rating` score among `13+ week` evergreen games? Which categories (e.g., competitive Multiplayer / live-service) sustain Top 100 presence even with `Mixed` ratings?

### Pillar 5 — Commercial Discount Strategy & Post-Discount Persistence
- **Q5.1 (Entry Trigger vs. Sustained Presence):** How often do discounts (`discount > 0`) act as the trigger for **entering or returning** to the Top 100 (`last_week_rank IS NULL`), compared to full-price entries?
- **Q5.2 (Optimal Discount Band):** Grouping discounts into clear bands (and checking the top most common discount percentages), which discount band delivers the highest **median weekly rank improvement (`last_week_rank - rank`)** without eroding subsequent retention?
- **Q5.3 (Multi-Week Sales & Post-Discount Hangover):** Because a discount in week `t` does **not always end in week `t+1`** (e.g., multi-week seasonal or publisher sales), evaluate discounted weeks across two distinct checks:
  1. **Immediate `t -> t+1` transitions:** share of discounted titles that remain in the Top 100 *still discounted* (`discount(t+1) > 0`), remain *after the discount ends* (`discount(t+1) = 0`), or *drop out* of the chart.
  2. **True post-discount persistence:** for the final week of a discount window (`discount(t) > 0` and `discount(t+1) = 0` or absent), what share of games hold a Top 100 spot organically once full price returns?

### Pillar 6 — Seasonality & Launch Timing
- **Q6.1 (Chart Turnover vs. Seasonal Sales):** Across the collected calendar (`week_date`), which months/periods show the highest rate of new entries (`last_week_rank IS NULL`) vs. heavy market-wide discounting (Steam Seasonal Sales)?
- **Q6.2 (Best Window for New Releases):** Do games entering during major sale weeks suffer lower next-week retention than games entering during non-sale weeks?

---

## 4. Assumptions & Limitations (Document for Stakeholders)
- **Revenue-Based Chart:** Rank reflects weekly Steam gross revenue, not unit sales or concurrent player counts.
- **Unobserved Variables:** Marketing spend, studio size, development budget, and external platform releases are outside the dataset; findings represent **empirical patterns and associations** within the Steam Top 100 rather than isolated causal proof.

---

## 5. Baseline Exploratory Checks (Initial Milestones)
- [x] Define rating score intervals for Steam labels (`Overwhelmingly Positive`, `Very Positive`, etc.).
- [x] Quantify most frequent whitelisted genres/tags among Top 10 vs. Top 100 titles.
- [x] Quantify baseline relationship between `price` and `rank` position.
