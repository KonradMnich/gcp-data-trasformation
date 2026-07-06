
# Enable all GCP APIs the pipeline needs.

$ErrorActionPreference = "Stop"
. "$PSScriptRoot\00-config.ps1"

gcloud services enable `
    pubsub.googleapis.com `
    bigquery.googleapis.com `
    bigquerystorage.googleapis.com `
    cloudfunctions.googleapis.com `
    run.googleapis.com `
    eventarc.googleapis.com `
    cloudbuild.googleapis.com `
    artifactregistry.googleapis.com `
    logging.googleapis.com `
    --project=$ProjectId

Write-Host "APIs enabled for project $ProjectId." -ForegroundColor Green
