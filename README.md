# The goal
This is an application on GCP that consumes data from a Pub/Sub topic and stores it in BigQuery. It is designed to run within the free tier and without Dataflow.

# GCP Services used
- Pub/Sub: manages the data flow from the source to the destination
- BigQuery: stores the data in a structured format
- BigQuery Storage Write API: a newer API for writing data to BigQuery
- Cloud Functions (Gen 2): in this context, parses an incoming message into a valid record
- Cloud Run: provides the runtime for the function code
- Eventarc: triggers the function code based on events in Pub/Sub
- Cloud Build: builds the image needed to run the function
- Artifact Registry: stores the image used by Cloud Run
- Logging: makes logs from Google Cloud Functions available

# High level description of the pipeline
As the first design choice, I decided to create a "bronze" table, `products_raw`, as an untouched raw capture of every message, written by a Pub/Sub BigQuery subscription. The setup is simple and requires only Pub/Sub and BigQuery. That way, I mitigate risks such as faulty transformations or changed message formats, while retaining data for audit and replay. The table is not used further in the current streaming design.

The second significant choice is to use a Cloud Function (Gen 2) to parse the incoming message. It is triggered from the same Pub/Sub topic through Eventarc. The parser is fairly permissive and rejects messages only if they are not valid JSON or do not contain a product ID. Otherwise, missing or malformed fields are filled with `NULL`; if a timestamp cannot be parsed, its original value is retained in `last_update_raw`.

After the message is parsed, it is appended to the "silver" table, `products`, with a more rigid schema. For example, stringified values are cast to the appropriate types and `attributes` is mapped to a repeated key-value structure. My language of choice for the Cloud Function is Python, as I feel more comfortable with it. The drawback is that Python does not have a clean high-level interface for the BigQuery Storage Write API. I chose this API over legacy streaming inserts because it includes 2 TB of appends per month in the free tier. The cost I paid is low-level message encoding with `google.protobuf`.

Because Pub/Sub delivery is at least once, the current solution accepts duplicate records in the append-only "silver" table. Deduplication is handled by the `products_latest` view, which returns the newest record for each product ID. I picked that approach for simplicity and to privilege quick table updates over, for example, periodic batch processing. Dataflow is excluded by the assignment and is not part of this free-tier design. Depending on the actual volumes and velocities, it might be overkill anyway.

Overall, Google Cloud Functions are a low-maintenance, cost-aware option that can scale to zero and absorb bursts. If the requirements can be met with them, they are a serious contender not only for a demo, but also for a production environment.

Messages that repeatedly fail during processing are retried. After five failed deliveries, they are forwarded to a dead-letter queue (DLQ) topic, where they can be inspected and replayed.


# Design decisions and operation
## Assumptions
Messages are JSON objects with an `id`; other fields may be missing or malformed and are handled permissively. The pipeline is designed for a low-to-moderate, continuous stream. Because Pub/Sub is at-least-once, the typed table is append-only and duplicates are removed when reading through the deduplication view.

## Why these services
A Pub/Sub BigQuery subscription captures raw messages without application code, while the Gen 2 function provides lightweight, event-driven parsing. BigQuery is used for both raw and typed storage, and the Storage Write API supports streaming typed rows without relying on legacy streaming inserts.

## Running and deployment
Numbered PowerShell scripts enable the required APIs, create the BigQuery and Pub/Sub resources, deploy the function, configure the DLQ, and publish test messages. Unit tests can be run with Python's built-in `unittest`; BigQuery queries, function logs, and the DLQ subscription can then be used for end-to-end verification.

## Implementation challenges
The Storage Write API requires protobuf-encoded rows in Python, and source fields arrive as strings with potentially ambiguous formats, especially timestamps. Configuring dead-lettering also requires handling the Eventarc-managed subscription and preserving retry behavior for transient failures.

## Further improvements
The next steps would be Terraform and CI/CD, stronger schema contracts, monitoring and alerting, a dedicated least-privilege runtime identity, and an exactly-once or batch-merge strategy where volumes or business requirements justify it.


# Deployment
As of now the deployment is done through PowerShell scripts. Each script serves a specific, isolated purpose. The scripts are designed to be run in order.

- 00-config.ps1: contains common configuration for the deployment; called by other scripts
- 01-enable-apis.ps1: enables the required APIs
- 02-create-bigquery.ps1: creates the BigQuery dataset and tables
- 03-create-pubsub.ps1: creates the Pub/Sub topic and subscription
- 04-deploy-function.ps1: deploys the function to Cloud Run
- 05-configure-dlq.ps1: configures the DLQ subscription
- 06-test-publish.ps1: publishes test messages to the topic

New deployment does not require all scripts to be run. For example, if the python parser changes, only 04-deploy-function.ps1 needs to be run.

# Testing
Unit tests for the python parser can be run with Python's built-in `unittest`:
```python
python -m unittest discover tests
```

Script 06-test-publish.ps1 publishes test messages to the topic. The logs and manual bq queries serve as a manual verification.