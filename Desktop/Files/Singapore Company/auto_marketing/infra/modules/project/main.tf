locals {
  apis = [
    "cloudfunctions.googleapis.com",
    "run.googleapis.com",
    "firestore.googleapis.com",
    "storage.googleapis.com",
    "pubsub.googleapis.com",
    "cloudscheduler.googleapis.com",
    "secretmanager.googleapis.com",
    "aiplatform.googleapis.com",
    "cloudbuild.googleapis.com",
    "clouderrorreporting.googleapis.com",
    "cloudresourcemanager.googleapis.com",
    "artifactregistry.googleapis.com",
    "firebase.googleapis.com",
    "firebasehosting.googleapis.com",
  ]

  sa_roles = [
    "roles/aiplatform.user",
    "roles/datastore.user",
    "roles/storage.objectAdmin",
    "roles/pubsub.publisher",
    "roles/run.invoker",
    "roles/logging.logWriter",
    "roles/errorreporting.writer",
    "roles/secretmanager.secretAccessor",
  ]
}

resource "google_project_service" "apis" {
  for_each           = toset(local.apis)
  project            = var.project_id
  service            = each.value
  disable_on_destroy = false
}

resource "google_service_account" "cloud_functions" {
  project      = var.project_id
  account_id   = "sa-cloud-functions"
  display_name = "Cloud Functions Service Account"
  description  = "Shared identity for all Cloud Functions in the marketing toolkit"
}

resource "google_project_iam_member" "sa_roles" {
  for_each = toset(local.sa_roles)
  project  = var.project_id
  role     = each.value
  member   = "serviceAccount:${google_service_account.cloud_functions.email}"
}
