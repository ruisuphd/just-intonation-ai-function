resource "google_monitoring_notification_channel" "email" {
  project      = var.project_id
  display_name = "Founder Email"
  type         = "email"

  labels = {
    email_address = var.notification_email
  }
}

# ---------------------------------------------------------------------------
# Log-based metric: Cloud Function errors
# ---------------------------------------------------------------------------

resource "google_logging_metric" "function_errors" {
  project = var.project_id
  name    = "cloud-function-errors"
  filter  = "resource.type=\"cloud_run_revision\" severity>=ERROR"

  metric_descriptor {
    metric_kind = "DELTA"
    value_type  = "INT64"
    unit        = "1"
  }
}

resource "google_logging_metric" "stale_batch_recoveries" {
  project = var.project_id
  name    = "stale-batch-recoveries"
  filter  = "resource.type=\"cloud_run_revision\" AND (jsonPayload.message=\"retention.recovered_stale_batch\" OR textPayload:\"retention.recovered_stale_batch\")"

  metric_descriptor {
    metric_kind = "DELTA"
    value_type  = "INT64"
    unit        = "1"
  }
}

# ---------------------------------------------------------------------------
# Alert: Cloud Run 5xx error rate > 5% over 15 min
# ---------------------------------------------------------------------------

resource "google_monitoring_alert_policy" "function_error_rate" {
  project      = var.project_id
  display_name = "Cloud Run 5xx Error Rate > 5%"
  combiner     = "OR"
  enabled      = true

  conditions {
    display_name = "5xx error rate exceeds 5% over 15 minutes"

    condition_monitoring_query_language {
      query = <<-MQL
        fetch cloud_run_revision
        | metric 'run.googleapis.com/request_count'
        | group_by 15m,
            [value_request_count_aggregate: aggregate(value.request_count)]
        | {
            filter metric.response_code_class = '5xx'
          ;
            ident
          }
        | outer_join 0
        | div
        | condition val() > 0.05
      MQL

      duration = "0s"
    }
  }

  notification_channels = [google_monitoring_notification_channel.email.name]

  alert_strategy {
    auto_close = "604800s"
  }

  documentation {
    content   = "Server-side 5xx error rate on one or more Cloud Run revisions exceeded 5% over a 15-minute window. Expected 4xx responses are excluded. Check Cloud Logging for details."
    mime_type = "text/markdown"
  }
}

resource "google_monitoring_alert_policy" "function_latency_p95" {
  project      = var.project_id
  display_name = "Cloud Function p95 Latency > 2s"
  combiner     = "OR"
  enabled      = true

  conditions {
    display_name = "p95 request latency exceeds 2 seconds"

    condition_threshold {
      filter          = "resource.type = \"cloud_run_revision\" AND metric.type = \"run.googleapis.com/request_latencies\""
      comparison      = "COMPARISON_GT"
      threshold_value = 2000
      duration        = "300s"

      aggregations {
        alignment_period     = "60s"
        per_series_aligner   = "ALIGN_PERCENTILE_95"
        cross_series_reducer = "REDUCE_MAX"
      }
    }
  }

  notification_channels = [google_monitoring_notification_channel.email.name]

  alert_strategy {
    auto_close = "86400s"
  }

  documentation {
    content   = "One or more Cloud Run revisions crossed 2s p95 request latency for 5 minutes."
    mime_type = "text/markdown"
  }
}

# ---------------------------------------------------------------------------
# Alert: any message lands on content-generate-dlq
# ---------------------------------------------------------------------------

resource "google_monitoring_alert_policy" "content_generate_dlq" {
  project      = var.project_id
  display_name = "DLQ: content-generate-dlq has messages"
  combiner     = "OR"
  enabled      = true

  conditions {
    display_name = "Messages published to content-generate-dlq"

    condition_threshold {
      filter = <<-FILTER
        resource.type = "pubsub_topic"
        AND resource.labels.topic_id = "content-generate-dlq"
        AND metric.type = "pubsub.googleapis.com/topic/send_message_operation_count"
      FILTER

      comparison      = "COMPARISON_GT"
      threshold_value = 0
      duration        = "0s"

      aggregations {
        alignment_period   = "60s"
        per_series_aligner = "ALIGN_SUM"
      }
    }
  }

  notification_channels = [google_monitoring_notification_channel.email.name]

  alert_strategy {
    auto_close = "86400s"
  }

  documentation {
    content   = "A message was routed to the content-generate dead-letter topic after exhausting delivery attempts. Inspect the DLQ subscription and Cloud Logging for the root cause."
    mime_type = "text/markdown"
  }
}

# ---------------------------------------------------------------------------
# Alert: any message lands on batch-complete-dlq
# ---------------------------------------------------------------------------

resource "google_monitoring_alert_policy" "batch_complete_dlq" {
  project      = var.project_id
  display_name = "DLQ: batch-complete-dlq has messages"
  combiner     = "OR"
  enabled      = true

  conditions {
    display_name = "Messages published to batch-complete-dlq"

    condition_threshold {
      filter = <<-FILTER
        resource.type = "pubsub_topic"
        AND resource.labels.topic_id = "batch-complete-dlq"
        AND metric.type = "pubsub.googleapis.com/topic/send_message_operation_count"
      FILTER

      comparison      = "COMPARISON_GT"
      threshold_value = 0
      duration        = "0s"

      aggregations {
        alignment_period   = "60s"
        per_series_aligner = "ALIGN_SUM"
      }
    }
  }

  notification_channels = [google_monitoring_notification_channel.email.name]

  alert_strategy {
    auto_close = "86400s"
  }

  documentation {
    content   = "A message was routed to the batch-complete dead-letter topic after exhausting delivery attempts. Inspect the DLQ subscription and Cloud Logging for the root cause."
    mime_type = "text/markdown"
  }
}

resource "google_monitoring_alert_policy" "stale_batch_recovery_detected" {
  project      = var.project_id
  display_name = "Stale content batch recovered"
  combiner     = "OR"
  enabled      = true

  conditions {
    display_name = "stale-batch-recoveries > 0"

    condition_threshold {
      filter          = "metric.type = \"logging.googleapis.com/user/${google_logging_metric.stale_batch_recoveries.name}\""
      comparison      = "COMPARISON_GT"
      threshold_value = 0
      duration        = "0s"

      aggregations {
        alignment_period   = "60s"
        per_series_aligner = "ALIGN_SUM"
      }
    }
  }

  notification_channels = [google_monitoring_notification_channel.email.name]

  alert_strategy {
    auto_close = "3600s"
  }

  documentation {
    content   = "A content package entered stale-recovery flow. Investigate platform generation failures."
    mime_type = "text/markdown"
  }
}
