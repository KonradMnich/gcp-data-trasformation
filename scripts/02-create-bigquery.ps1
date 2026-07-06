# Create the BigQuery dataset, tables, and the dedup view.

$ErrorActionPreference = "Stop"
. "$PSScriptRoot\00-config.ps1"

# Dataset (EU multi-region)
bq --project_id=$ProjectId --location=$BqLocation mk --dataset `
    --description "Product data ingested from Pub/Sub (Kramp DE assignment)" `
    "${ProjectId}:${DatasetName}"

# Bronze: raw messages, partitioned on Pub/Sub publish time
bq --project_id=$ProjectId mk --table `
    --description "Raw Pub/Sub messages (bronze layer, written by BigQuery subscription)" `
    --time_partitioning_field publish_time `
    --time_partitioning_type DAY `
    "${ProjectId}:${DatasetName}.${RawTableName}" `
    "$PSScriptRoot\schemas\products_raw.json"

# Silver: typed products, partitioned on ingestion time
bq --project_id=$ProjectId mk --table `
    --description "Typed product records (silver layer, written by Cloud Run function)" `
    --time_partitioning_field ingested_at `
    --time_partitioning_type DAY `
    "${ProjectId}:${DatasetName}.${TypedTableName}" `
    "$PSScriptRoot\schemas\products.json"

# Dedup view (Pub/Sub is at-least-once, so duplicates are expected by design)
$viewSql = (Get-Content -Raw "$PSScriptRoot\schemas\products_latest_view.sql")
$viewSql = $viewSql -replace "__PROJECT__", $ProjectId -replace "__DATASET__", $DatasetName

$createView = @"
CREATE OR REPLACE VIEW ``$ProjectId.$DatasetName.$LatestViewName`` AS
$viewSql
"@
$createView | bq query --use_legacy_sql=false --project_id=$ProjectId

Write-Host "BigQuery dataset '$DatasetName' with tables '$RawTableName', '$TypedTableName' and view '$LatestViewName' created." -ForegroundColor Green
