# Create Pub/Sub topics and subscriptions.
$ErrorActionPreference = "Stop"
. "$PSScriptRoot\00-config.ps1"

# Topics
gcloud pubsub topics create $TopicName --project=$ProjectId
gcloud pubsub topics create $DlqTopicName --project=$ProjectId

# Pub/Sub service agent identity
$ProjectNumber = gcloud projects describe $ProjectId --format="value(projectNumber)"
$PubsubServiceAgent = "service-$ProjectNumber@gcp-sa-pubsub.iam.gserviceaccount.com"
Write-Host "Pub/Sub service agent: $PubsubServiceAgent"

# Allow the service agent to write into BigQuery (required by BigQuery subscriptions)
gcloud projects add-iam-policy-binding $ProjectId `
    --member="serviceAccount:$PubsubServiceAgent" `
    --role="roles/bigquery.dataEditor"
gcloud projects add-iam-policy-binding $ProjectId `
    --member="serviceAccount:$PubsubServiceAgent" `
    --role="roles/bigquery.metadataViewer"

# Allow the service agent to publish dead letters to the DLQ topic
gcloud pubsub topics add-iam-policy-binding $DlqTopicName `
    --project=$ProjectId `
    --member="serviceAccount:$PubsubServiceAgent" `
    --role="roles/pubsub.publisher"

# Bronze layer: BigQuery subscription (raw payload + message metadata)
gcloud pubsub subscriptions create $RawSubscriptionName `
    --project=$ProjectId `
    --topic=$TopicName `
    --bigquery-table="${ProjectId}:${DatasetName}.${RawTableName}" `
    --write-metadata

# DLQ retention: pull subscription so dead letters can be inspected/replayed
gcloud pubsub subscriptions create $DlqSubscriptionName `
    --project=$ProjectId `
    --topic=$DlqTopicName `
    --ack-deadline=60 `
    --message-retention-duration=7d

Write-Host "Pub/Sub topics and subscriptions created." -ForegroundColor Green
