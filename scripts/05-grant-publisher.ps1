# Grant service account permission to publish to the topic

$ErrorActionPreference = "Stop"
. "$PSScriptRoot\00-config.ps1"

gcloud pubsub topics add-iam-policy-binding $TopicName `
    --project=$ProjectId `
    --member="serviceAccount:$ServiceAccount" `
    --role="roles/pubsub.publisher"

Write-Host "Granted roles/pubsub.publisher on '$TopicName' to $ServiceAccount." -ForegroundColor Green
