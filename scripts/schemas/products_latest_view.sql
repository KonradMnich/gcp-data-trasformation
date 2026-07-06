-- Latest state per product id.
-- Pub/Sub delivers at-least-once, so the products table may contain duplicates
-- (same message delivered twice) or multiple updates of the same product.
-- This view keeps only the newest record per id.
SELECT * EXCEPT (row_num)
FROM (
  SELECT
    *,
    ROW_NUMBER() OVER (
      PARTITION BY id
      ORDER BY last_update DESC, ingested_at DESC
    ) AS row_num
  FROM `__PROJECT__.__DATASET__.products`
)
WHERE row_num = 1
