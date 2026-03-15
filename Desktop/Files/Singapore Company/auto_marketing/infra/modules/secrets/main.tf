locals {
  secret_names = ["stripe-api-key", "stripe-webhook-secret"]
}

resource "google_secret_manager_secret" "secrets" {
  for_each  = toset(local.secret_names)
  project   = var.project_id
  secret_id = each.value

  replication {
    auto {}
  }
}

resource "google_secret_manager_secret_version" "initial" {
  for_each    = google_secret_manager_secret.secrets
  secret      = each.value.id
  secret_data = "REPLACE_ME"

  lifecycle {
    ignore_changes = [secret_data]
  }
}
