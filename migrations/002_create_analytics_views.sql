-- Analytical read-only views for SteamDB Power BI, Excel, and SQL reporting.
-- Aligns directly with `txt files/PB_questions.md`:
--   - Excludes non-game hardware (Steam Deck, Steam Deck Refurbished, Valve Index Base Station)
--   - Treats Singleplayer, Multiplayer, and Co-op as distinct play-mode dimensions
--   - Respects collection calendar gaps and right-censoring when computing t+1 retention
--   - Tracks multi-week discounts vs. true post-discount persistence

-- 1. Calendar dimension with exact 7-day adjacency checks
CREATE OR REPLACE VIEW vw_analytics_calendar AS
WITH distinct_weeks AS (
    SELECT DISTINCT week_date
    FROM weeksheet
),
spaced AS (
    SELECT
        week_date,
        LAG(week_date) OVER (ORDER BY week_date) AS prev_calendar_week,
        LEAD(week_date) OVER (ORDER BY week_date) AS next_calendar_week
    FROM distinct_weeks
)
SELECT
    week_date,
    prev_calendar_week,
    next_calendar_week,
    (prev_calendar_week IS NOT NULL AND (week_date - prev_calendar_week) = 7) AS has_prev_week_collected,
    (next_calendar_week IS NOT NULL AND (next_calendar_week - week_date) = 7) AS has_next_week_collected,
    EXTRACT(YEAR FROM week_date)::INT AS calendar_year,
    EXTRACT(MONTH FROM week_date)::INT AS calendar_month,
    TO_CHAR(week_date, 'YYYY-MM') AS year_month,
    TO_CHAR(week_date, 'Mon YYYY') AS month_label
FROM spaced;


-- 2. Validated whitelisted game-to-tag bridge (excluding non-game hardware and catalog-only entries absent from weeksheet)
CREATE OR REPLACE VIEW vw_analytics_game_tags AS
SELECT DISTINCT
    g.id AS game_id,
    t.id AS tag_id,
    t.name AS tag_name
FROM games g
CROSS JOIN LATERAL UNNEST(COALESCE(g.tags, ARRAY[]::INT[])) AS u(tag_id)
JOIN tags t ON t.id = u.tag_id
WHERE g.id NOT IN (1675200, 2550670, 1059570)
  AND t.whitelist IS TRUE
  AND EXISTS (
      SELECT 1
      FROM weeksheet w
      WHERE w.game_id = g.id
  );


-- 3. Game-level profile & longevity dimension (1 row per valid game appearing in weeksheet)
CREATE OR REPLACE VIEW vw_analytics_game_profile AS
WITH play_modes AS (
    SELECT
        g.id AS game_id,
        BOOL_OR(t_id IN (2, 4182)) AS has_singleplayer,
        BOOL_OR(t_id IN (1, 3859, 128, 27, 7368, 17770)) AS has_multiplayer,
        BOOL_OR(t_id IN (1685, 3843, 4508, 3841, 48, 39)) AS has_coop
    FROM games g
    LEFT JOIN LATERAL UNNEST(COALESCE(g.tags, ARRAY[]::INT[])) AS t_id ON TRUE
    WHERE g.id NOT IN (1675200, 2550670, 1059570)
    GROUP BY g.id
),
latest_snapshot AS (
    SELECT DISTINCT ON (game_id)
        game_id,
        rating AS latest_rating,
        rating_label AS latest_rating_label,
        price AS latest_price
    FROM weeksheet
    WHERE game_id NOT IN (1675200, 2550670, 1059570)
    ORDER BY game_id, week_date DESC
),
agg AS (
    SELECT
        w.game_id,
        g.name AS game_name,
        COUNT(*)::INT AS total_weeks_in_top100,
        MAX(w.consecutive_weeks)::INT AS max_consecutive_weeks,
        MIN(w.week_date) AS first_seen_week,
        MAX(w.week_date) AS last_seen_week,
        MIN(w.rank)::INT AS best_rank,
        ROUND(AVG(w.rank), 2) AS avg_rank,
        ROUND((PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY w.rank))::NUMERIC, 2) AS median_rank,
        ROUND(AVG(w.rating), 4) AS avg_rating,
        ROUND(
            (COUNT(*) FILTER (WHERE w.discount > 0))::NUMERIC
            / NULLIF(COUNT(*) FILTER (WHERE w.discount IS NOT NULL), 0),
            4
        ) AS pct_weeks_discounted,
        MIN(w.price) AS min_price,
        MAX(w.price) AS max_price
    FROM weeksheet w
    JOIN games g ON g.id = w.game_id
    WHERE w.game_id NOT IN (1675200, 2550670, 1059570)
    GROUP BY w.game_id, g.name
)
SELECT
    a.game_id,
    a.game_name,
    a.total_weeks_in_top100,
    a.max_consecutive_weeks,
    a.first_seen_week,
    a.last_seen_week,
    a.best_rank,
    a.avg_rank,
    a.median_rank,
    a.avg_rating,
    ls.latest_rating,
    CASE
        WHEN ls.latest_rating_label IS NULL OR ls.latest_rating_label = 'no_label' THEN 'Unrated / <10 Reviews'
        ELSE ls.latest_rating_label
    END AS latest_rating_label,
    ls.latest_price,
    a.pct_weeks_discounted,
    CASE
        WHEN a.max_price IS NULL THEN 'Unknown'
        WHEN a.max_price = 0 THEN 'Free-to-Play'
        WHEN a.min_price > 0 THEN 'Paid'
        ELSE 'Mixed / Price Changed'
    END AS monetization_model,
    CASE
        WHEN a.total_weeks_in_top100 = 1 THEN '1 Week'
        WHEN a.total_weeks_in_top100 BETWEEN 2 AND 4 THEN '2-4 Weeks'
        WHEN a.total_weeks_in_top100 BETWEEN 5 AND 12 THEN '5-12 Weeks'
        ELSE '13+ Weeks (Evergreen)'
    END AS tenure_tier,
    (a.total_weeks_in_top100 >= 13) AS is_evergreen_13w,
    (a.total_weeks_in_top100 >= 40) AS is_perennial_40w,
    COALESCE(pm.has_singleplayer, FALSE) AS has_singleplayer,
    COALESCE(pm.has_multiplayer, FALSE) AS has_multiplayer,
    COALESCE(pm.has_coop, FALSE) AS has_coop,
    CASE
        WHEN NOT COALESCE(pm.has_singleplayer, FALSE)
         AND NOT COALESCE(pm.has_multiplayer, FALSE)
         AND NOT COALESCE(pm.has_coop, FALSE) THEN 'Unclassified'
        ELSE TRIM(BOTH ' + ' FROM
            CONCAT_WS(' + ',
                CASE WHEN COALESCE(pm.has_singleplayer, FALSE) THEN 'Singleplayer' END,
                CASE WHEN COALESCE(pm.has_multiplayer, FALSE) THEN 'Multiplayer' END,
                CASE WHEN COALESCE(pm.has_coop, FALSE) THEN 'Co-op' END
            )
        )
    END AS play_mode_combo
FROM agg a
LEFT JOIN play_modes pm ON pm.game_id = a.game_id
LEFT JOIN latest_snapshot ls ON ls.game_id = a.game_id;


-- 4. Weekly analytical fact view (1 row per valid game-week, with t+1 retention & discount transitions)
CREATE OR REPLACE VIEW vw_analytics_weekly_fact AS
WITH sequenced AS (
    SELECT
        w.id AS weeksheet_id,
        w.week_date,
        w.rank,
        w.game_id,
        w.price,
        w.discount,
        w.rating,
        w.rating_label,
        w.last_week_rank,
        w.consecutive_weeks,
        LEAD(w.week_date) OVER (PARTITION BY w.game_id ORDER BY w.week_date) AS lead_game_week_date,
        LEAD(w.rank) OVER (PARTITION BY w.game_id ORDER BY w.week_date) AS lead_game_rank,
        LEAD(w.discount) OVER (PARTITION BY w.game_id ORDER BY w.week_date) AS lead_game_discount
    FROM weeksheet w
    WHERE w.game_id NOT IN (1675200, 2550670, 1059570)
),
aligned AS (
    SELECT
        s.*,
        c.has_prev_week_collected,
        c.has_next_week_collected,
        c.year_month,
        gp.game_name,
        gp.total_weeks_in_top100,
        gp.max_consecutive_weeks,
        gp.first_seen_week,
        gp.monetization_model,
        gp.tenure_tier,
        gp.is_evergreen_13w,
        gp.has_singleplayer,
        gp.has_multiplayer,
        gp.has_coop,
        gp.play_mode_combo,
        CASE
            WHEN c.has_next_week_collected AND s.lead_game_week_date = (s.week_date + 7)
            THEN s.lead_game_rank
            ELSE NULL
        END AS next_week_rank,
        CASE
            WHEN c.has_next_week_collected AND s.lead_game_week_date = (s.week_date + 7)
            THEN s.lead_game_discount
            ELSE NULL
        END AS next_week_discount
    FROM sequenced s
    JOIN vw_analytics_calendar c ON c.week_date = s.week_date
    JOIN vw_analytics_game_profile gp ON gp.game_id = s.game_id
)
SELECT
    weeksheet_id,
    week_date,
    year_month,
    rank,
    CASE
        WHEN rank <= 10 THEN 'Top 10'
        WHEN rank <= 30 THEN '11-30'
        WHEN rank <= 60 THEN '31-60'
        ELSE '61-100'
    END AS rank_band,
    game_id,
    game_name,
    price,
    CASE
        WHEN price IS NULL THEN NULL
        ELSE (price = 0)
    END AS is_free,
    CASE
        WHEN price IS NULL THEN 'Unknown'
        WHEN price = 0 THEN 'Free ($0)'
        WHEN price <= 10 THEN '$0.01 - $10'
        WHEN price <= 20 THEN '$10.01 - $20'
        WHEN price <= 35 THEN '$20.01 - $35'
        WHEN price <= 50 THEN '$35.01 - $50'
        ELSE '$50+'
    END AS price_tier,
    discount,
    CASE
        WHEN discount IS NULL THEN NULL
        ELSE (discount > 0)
    END AS is_discounted,
    CASE
        WHEN discount IS NULL THEN 'Unknown'
        WHEN discount = 0 THEN 'No Discount (0%)'
        WHEN discount <= 20 THEN '1% - 20%'
        WHEN discount <= 40 THEN '21% - 40%'
        WHEN discount <= 60 THEN '41% - 60%'
        ELSE '61%+'
    END AS discount_tier,
    rating,
    CASE
        WHEN rating_label IS NULL OR rating_label = 'no_label' THEN 'Unrated / <10 Reviews'
        ELSE rating_label
    END AS rating_band,
    last_week_rank,
    CASE
        WHEN last_week_rank IS NOT NULL THEN (last_week_rank - rank)
        ELSE NULL
    END AS rank_delta,
    consecutive_weeks,
    CASE
        WHEN last_week_rank IS NOT NULL THEN 'Continuing'
        WHEN week_date = first_seen_week THEN 'First-Time Debut'
        ELSE 'Returning'
    END AS entry_type,
    monetization_model,
    total_weeks_in_top100,
    max_consecutive_weeks,
    tenure_tier,
    is_evergreen_13w,
    has_singleplayer,
    has_multiplayer,
    has_coop,
    play_mode_combo,
    has_next_week_collected,
    next_week_rank,
    next_week_discount,
    CASE
        WHEN NOT has_next_week_collected THEN NULL
        WHEN next_week_rank IS NOT NULL THEN TRUE
        ELSE FALSE
    END AS retained_t1,
    CASE
        WHEN NOT has_next_week_collected OR COALESCE(discount, 0) <= 0 THEN NULL
        WHEN next_week_rank IS NOT NULL AND COALESCE(next_week_discount, 0) > 0 THEN 'Retained (Still Discounted)'
        WHEN next_week_rank IS NOT NULL AND COALESCE(next_week_discount, 0) = 0 THEN 'Retained (Discount Ended)'
        ELSE 'Dropped Out'
    END AS post_discount_outcome_t1,
    CASE
        WHEN has_next_week_collected
         AND COALESCE(discount, 0) > 0
         AND (next_week_rank IS NULL OR COALESCE(next_week_discount, 0) = 0)
        THEN TRUE
        ELSE FALSE
    END AS is_discount_window_end,
    CASE
        WHEN has_next_week_collected
         AND COALESCE(discount, 0) > 0
         AND (next_week_rank IS NULL OR COALESCE(next_week_discount, 0) = 0)
        THEN (next_week_rank IS NOT NULL)
        ELSE NULL
    END AS retained_after_discount_end
FROM aligned;


-- 5. Pre-aggregated whitelisted tag performance summary (for Power BI & Excel)
CREATE OR REPLACE VIEW vw_analytics_tag_summary AS
SELECT
    gt.tag_id,
    gt.tag_name,
    COUNT(DISTINCT wf.game_id)::INT AS distinct_games,
    COUNT(DISTINCT wf.game_id) FILTER (WHERE wf.is_evergreen_13w)::INT AS evergreen_games_13w,
    COUNT(DISTINCT wf.game_id) FILTER (WHERE wf.total_weeks_in_top100 = 1)::INT AS one_week_games,
    COUNT(*)::INT AS weekly_appearances,
    ROUND((PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY wf.rank))::NUMERIC, 2) AS median_rank,
    ROUND(AVG(wf.rank), 2) AS avg_rank,
    ROUND(AVG(wf.rating), 4) AS avg_rating,
    ROUND(
        (COUNT(*) FILTER (WHERE wf.retained_t1 IS TRUE))::NUMERIC
        / NULLIF(COUNT(*) FILTER (WHERE wf.retained_t1 IS NOT NULL), 0),
        4
    ) AS retention_t1_rate,
    ROUND(
        (COUNT(*) FILTER (WHERE wf.is_discounted IS TRUE))::NUMERIC
        / NULLIF(COUNT(*) FILTER (WHERE wf.is_discounted IS NOT NULL), 0),
        4
    ) AS pct_discounted_weeks,
    ROUND(
        (COUNT(DISTINCT wf.game_id) FILTER (WHERE wf.is_evergreen_13w))::NUMERIC
        / NULLIF(COUNT(DISTINCT wf.game_id), 0),
        4
    ) AS pct_evergreen_games,
    CASE
        WHEN gt.tag_id IN (35, 37, 113, 493) THEN 'Monetization & Release'
        WHEN gt.tag_id IN (1, 2, 24, 27, 36, 39, 47, 48, 128, 1685, 1775, 3841, 3843, 3859, 4182, 4508, 6730, 7368, 17770) THEN 'Play Mode'
        WHEN (gt.tag_id < 100 AND gt.tag_id NOT IN (9, 19, 20, 21))
          OR gt.tag_id IN (1669, 7481, 21978) THEN 'Platform & Feature'
        ELSE 'Genre & Theme'
    END AS tag_group
FROM vw_analytics_game_tags gt
JOIN vw_analytics_weekly_fact wf ON wf.game_id = gt.game_id
GROUP BY gt.tag_id, gt.tag_name;


-- 6. Bridge table for non-mutually-exclusive play modes (Singleplayer, Multiplayer, Co-op)
CREATE OR REPLACE VIEW vw_analytics_game_play_modes AS
SELECT game_id, 'Singleplayer'::TEXT AS play_mode
FROM vw_analytics_game_profile
WHERE has_singleplayer IS TRUE
UNION ALL
SELECT game_id, 'Multiplayer'::TEXT AS play_mode
FROM vw_analytics_game_profile
WHERE has_multiplayer IS TRUE
UNION ALL
SELECT game_id, 'Co-op'::TEXT AS play_mode
FROM vw_analytics_game_profile
WHERE has_coop IS TRUE
UNION ALL
SELECT game_id, 'Unclassified'::TEXT AS play_mode
FROM vw_analytics_game_profile
WHERE NOT has_singleplayer AND NOT has_multiplayer AND NOT has_coop;
