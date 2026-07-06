# Shared configuration for all setup scripts.

$ProjectId = ""

$Region     = "europe-west1"
$BqLocation = "EU"

# Pub/Sub
$TopicName           = "synthetic-data-generator"
$DlqTopicName        = "synthetic-data-generator-dlq"
$RawSubscriptionName = "products-raw-bigquery"
$DlqSubscriptionName = "synthetic-data-generator-dlq-pull"

# BigQuery
$DatasetName    = "products"
$RawTableName   = "products_raw"
$TypedTableName = "products"
$LatestViewName = "products_latest"

# Cloud Run function (Gen 2)
$FunctionName = "product-consumer"
$MaxInstances = 3

# Service account
$ServiceAccount = ""