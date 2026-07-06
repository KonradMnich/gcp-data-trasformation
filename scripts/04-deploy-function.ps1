
# Deploy the Cloud Run function (Gen 2) and wire the dead-letter queue.

$ErrorActionPreference = "Stop"
. "$PSScriptRoot\00-config.ps1"

# Deploy the function
gcloud functions deploy $FunctionName `
    --project=$ProjectId `
    --region=$Region `
    --gen2 `
    --runtime=python312 `
    --source="$PSScriptRoot\..\src" `
    --entry-point=handle_message `
    --trigger-topic=$TopicName `
    --memory=256Mi `
    --max-instances=$MaxInstances `
    --retry `
    --set-env-vars="BQ_PROJECT=$ProjectId,BQ_DATASET=$DatasetName,BQ_TABLE=$TypedTableName"

# Wire the DLQ onto the Eventarc-managed subscription
$TriggerResource = gcloud functions describe $FunctionName `
    --project=$ProjectId --region=$Region --gen2 `
    --format="value(eventTrigger.trigger)"
Write-Host "Eventarc trigger: $TriggerResource"

$SubscriptionResource = gcloud eventarc triggers describe $TriggerResource `
    --format="value(transport.pubsub.subscription)"
Write-Host "Trigger subscription: $SubscriptionResource"

gcloud pubsub subscriptions update $SubscriptionResource `
    --project=$ProjectId `
    --dead-letter-topic=$DlqTopicName `
    --dead-letter-topic-project=$ProjectId `
    --max-delivery-attempts=5 `
    --min-retry-delay=10s `
    --max-retry-delay=300s

$ProjectNumber = gcloud projects describe $ProjectId --format="value(projectNumber)"
$PubsubServiceAgent = "service-$ProjectNumber@gcp-sa-pubsub.iam.gserviceaccount.com"

gcloud pubsub subscriptions add-iam-policy-binding $SubscriptionResource `
    --project=$ProjectId `
    --member="serviceAccount:$PubsubServiceAgent" `
    --role="roles/pubsub.subscriber"

Write-Host "Function '$FunctionName' deployed; DLQ policy attached to its subscription." -ForegroundColor Green
