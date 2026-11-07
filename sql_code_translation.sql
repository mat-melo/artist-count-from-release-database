-- =============================================================================
-- PART 1: Country-year table of new artist debuts
-- =============================================================================
CREATE OR REPLACE VIEW artist_debut_per_country_per_year AS
WITH filtered AS (
    -- Base table: MusicBrainz official releases
    -- Filtered to 1950–2025, valid ISO2 country codes, valid artist names
    SELECT
        artist_name,
        country_code,
        CAST(date_year AS INTEGER) AS year
    FROM official_releases
    WHERE date_year ~ '^\d{1,4}$'
      AND CAST(date_year AS INTEGER) BETWEEN 1950 AND 2025
      AND country_code NOT IN ('XW','XE','','XZ','XC','SU','CS','AN','YU','XG')
      AND country_code IS NOT NULL
      AND artist_name NOT IN ('Various Artists','','[unknown]','[dialogue]','[no artist]')
      AND artist_name IS NOT NULL
      AND artist_name !~ '^[0-9]+$'
),

debut_year AS (
    -- STEP 1: Earliest release year per artist = debut year
    SELECT artist_name, MIN(year) AS debut_year
    FROM filtered
    GROUP BY artist_name
),

debut_rows AS (
    -- STEP 2: Keep only rows where release year == debut year
    SELECT f.artist_name, f.country_code, f.year
    FROM filtered f
    JOIN debut_year d USING (artist_name)
    WHERE f.year = d.debut_year
),

total_per_country AS (
    -- STEP 3: Releases per (artist, country) in the debut year
    SELECT artist_name, country_code, COUNT(*) AS total_releases
    FROM debut_rows
    GROUP BY artist_name, country_code
),

country_choice AS (
    -- STEP 4: One debut country per artist:
    --   most releases in debut year, ties broken alphabetically by country_code
    SELECT artist_name, country_code AS debut_country
    FROM (
        SELECT
            artist_name,
            country_code,
            ROW_NUMBER() OVER (
                PARTITION BY artist_name
                ORDER BY total_releases DESC, country_code ASC
            ) AS rn
        FROM total_per_country
    ) t
    WHERE rn = 1
),

debut_count AS (
    -- STEP 5: Aggregate to country-year counts of new artists
    SELECT
        c.debut_country AS country_code,
        d.debut_year    AS year,
        COUNT(*)        AS debuting_artists
    FROM debut_year d
    JOIN country_choice c USING (artist_name)
    GROUP BY c.debut_country, d.debut_year
)

-- STEP 6: Attach human-readable country name
SELECT
    dc.country_code,
    dc.year,
    dc.debuting_artists,
    cl.country_name
FROM debut_count dc
LEFT JOIN country_lookup cl USING (country_code);
