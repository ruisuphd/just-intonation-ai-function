# Create the Pub/Sub service agent so it exists before we assign IAM roles
resource "google_project_service_identity" "pubsub_agent" {
  provider = google-beta
  project  = var.project_id
  service  = "pubsub.googleapis.com"
}

# ---------------------------------------------------------------------------
# Topics
# ---------------------------------------------------------------------------

resource "google_pubsub_topic" "content_generate" {
  project = var.project_id
  name    = "content-generate"
}

resource "google_pubsub_topic" "batch_complete" {
  project = var.project_id
  name    = "batch-complete"
}

resource "google_pubsub_topic" "content_generate_dlq" {
  project = var.project_id
  name    = "content-generate-dlq"
}

resource "google_pubsub_topic" "batch_complete_dlq" {
  project = var.project_id
  name    = "batch-complete-dlq"
}

# ---------------------------------------------------------------------------
# Subscriptions (only created when push endpoints are available)
# ---------------------------------------------------------------------------

resource "google_pubsub_subscription" "content_generate_sub" {
  count                = var.fn_platform_generate_url != "" ? 1 : 0
  project              = var.project_id
  name                 = "content-generate-sub"
  topic                = google_pubsub_topic.content_generate.id
  ack_deadline_seconds = 300

  push_config {
    push_endpoint = var.fn_platform_generate_url

    oidc_token {
      service_account_email = var.service_account_email
    }
  }

  dead_letter_policy {
    dead_letter_topic     = google_pubsub_topic.content_generate_dlq.id
    max_delivery_attempts = 5
  }

  retry_policy {
    minimum_backoff = "10s"
    maximum_backoff = "600s"
  }
}

resource "google_pubsub_subscription" "batch_complete_sub" {
  count                = var.fn_package_builder_url != "" ? 1 : 0
  project              = var.project_id
  name                 = "batch-complete-sub"
  topic                = google_pubsub_topic.batch_complete.id
  ack_deadline_seconds = 300

  push_config {
    push_endpoint = var.fn_package_builder_url

    oidc_token {
      service_account_email = var.service_account_email
    }
  }

  dead_letter_policy {
    dead_letter_topic     = google_pubsub_topic.batch_complete_dlq.id
    max_delivery_attempts = 5
  }

  retry_policy {
    minimum_backoff = "10s"
    maximum_backoff = "600s"
  }
}

# ---------------------------------------------------------------------------
# IAM: allow Pub/Sub service agent to forward to DLQ and ack source subs
# Only created after the service agent exists and subscriptions are created
# ---------------------------------------------------------------------------

resource "google_pubsub_topic_iam_member" "content_generate_dlq_publisher" {
  count   = var.fn_platform_generate_url != "" ? 1 : 0
  project = var.project_id
  topic   = google_pubsub_topic.content_generate_dlq.name
  role    = "roles/pubsub.publisher"
  member  = "serviceAccount:${google_project_service_identity.pubsub_agent.email}"
}

resource "google_pubsub_subscription_iam_member" "content_generate_sub_subscriber" {
  count        = var.fn_platform_generate_url != "" ? 1 : 0
  project      = var.project_id
  subscription = google_pubsub_subscription.content_generate_sub[0].name
  role         = "roles/pubsub.subscriber"
  member       = "serviceAccount:${google_project_service_identity.pubsub_agent.email}"
}

resource "google_pubsub_topic_iam_member" "batch_complete_dlq_publisher" {
  count   = var.fn_package_builder_url != "" ? 1 : 0
  project = var.project_id
  topic   = google_pubsub_topic.batch_complete_dlq.name
  role    = "roles/pubsub.publisher"
  member  = "serviceAccount:${google_project_service_identity.pubsub_agent.email}"
}

resource "google_pubsub_subscription_iam_member" "batch_complete_sub_subscriber" {
  count        = var.fn_package_builder_url != "" ? 1 : 0
  project      = var.project_id
  subscription = google_pubsub_subscription.batch_complete_sub[0].name
  role         = "roles/pubsub.subscriber"
  member       = "serviceAccount:${google_project_service_identity.pubsub_agent.email}"
}
