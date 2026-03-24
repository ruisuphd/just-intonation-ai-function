resource "google_firestore_database" "default" {
  project                     = var.project_id
  name                        = "(default)"
  location_id                 = var.region
  type                        = "FIRESTORE_NATIVE"
  concurrency_mode            = "PESSIMISTIC"
  app_engine_integration_mode = "DISABLED"
}

# ---------------------------------------------------------------------------
# intelligence_items indexes
# ---------------------------------------------------------------------------

resource "google_firestore_index" "intelligence_items_batch_relevance" {
  project    = var.project_id
  database   = google_firestore_database.default.name
  collection = "intelligence_items"

  fields {
    field_path = "batch_date"
    order      = "ASCENDING"
  }
  fields {
    field_path = "relevance_score"
    order      = "DESCENDING"
  }
}

resource "google_firestore_index" "intelligence_items_source_dedup" {
  project    = var.project_id
  database   = google_firestore_database.default.name
  collection = "intelligence_items"

  fields {
    field_path = "source_url"
    order      = "ASCENDING"
  }
  fields {
    field_path = "dedup_window_expires"
    order      = "DESCENDING"
  }
}

# ---------------------------------------------------------------------------
# brand_chunks indexes (non-vector)
# ---------------------------------------------------------------------------

resource "google_firestore_index" "brand_chunks_document_chunk" {
  project    = var.project_id
  database   = google_firestore_database.default.name
  collection = "brand_chunks"

  fields {
    field_path = "document_id"
    order      = "ASCENDING"
  }
  fields {
    field_path = "chunk_index"
    order      = "ASCENDING"
  }
}

# ---------------------------------------------------------------------------
# brand_documents indexes
# ---------------------------------------------------------------------------

resource "google_firestore_index" "brand_documents_status_uploaded" {
  project    = var.project_id
  database   = google_firestore_database.default.name
  collection = "brand_documents"

  fields {
    field_path = "status"
    order      = "ASCENDING"
  }
  fields {
    field_path = "uploaded_at"
    order      = "DESCENDING"
  }
}

# ---------------------------------------------------------------------------
# drafts indexes (tenant subcollection: tenants/{id}/drafts)
# ---------------------------------------------------------------------------

resource "google_firestore_index" "drafts_batch_status" {
  project    = var.project_id
  database   = google_firestore_database.default.name
  collection = "drafts"

  fields {
    field_path = "batch_date"
    order      = "ASCENDING"
  }
  fields {
    field_path = "status"
    order      = "ASCENDING"
  }
}

resource "google_firestore_index" "drafts_status_batch" {
  project    = var.project_id
  database   = google_firestore_database.default.name
  collection = "drafts"

  fields {
    field_path = "status"
    order      = "ASCENDING"
  }
  fields {
    field_path = "batch_date"
    order      = "DESCENDING"
  }
}

resource "google_firestore_index" "drafts_batch_status_platforms" {
  project    = var.project_id
  database   = google_firestore_database.default.name
  collection = "drafts"

  fields {
    field_path = "batch_date"
    order      = "ASCENDING"
  }
  fields {
    field_path = "status"
    order      = "ASCENDING"
  }
  fields {
    field_path   = "platforms_generated"
    array_config = "CONTAINS"
  }
}

resource "google_firestore_index" "drafts_status_created" {
  project    = var.project_id
  database   = google_firestore_database.default.name
  collection = "drafts"

  fields {
    field_path = "status"
    order      = "ASCENDING"
  }
  fields {
    field_path = "created_at"
    order      = "DESCENDING"
  }
}

resource "google_firestore_index" "drafts_batch_created" {
  project    = var.project_id
  database   = google_firestore_database.default.name
  collection = "drafts"

  fields {
    field_path = "batch_date"
    order      = "ASCENDING"
  }
  fields {
    field_path = "created_at"
    order      = "DESCENDING"
  }
}

resource "google_firestore_index" "drafts_batch_status_created" {
  project    = var.project_id
  database   = google_firestore_database.default.name
  collection = "drafts"

  fields {
    field_path = "batch_date"
    order      = "ASCENDING"
  }
  fields {
    field_path = "status"
    order      = "ASCENDING"
  }
  fields {
    field_path = "created_at"
    order      = "DESCENDING"
  }
}

resource "google_firestore_index" "drafts_status_platforms_created" {
  project    = var.project_id
  database   = google_firestore_database.default.name
  collection = "drafts"

  fields {
    field_path = "status"
    order      = "ASCENDING"
  }
  fields {
    field_path   = "platforms_generated"
    array_config = "CONTAINS"
  }
  fields {
    field_path = "created_at"
    order      = "DESCENDING"
  }
}

# ---------------------------------------------------------------------------
# intelligence_items newsletter query (gathered_at + relevance_score)
# ---------------------------------------------------------------------------

resource "google_firestore_index" "intelligence_items_gathered_relevance" {
  project    = var.project_id
  database   = google_firestore_database.default.name
  collection = "intelligence_items"

  fields {
    field_path = "gathered_at"
    order      = "ASCENDING"
  }
  fields {
    field_path = "relevance_score"
    order      = "DESCENDING"
  }
}

# ---------------------------------------------------------------------------
# publishing_records collection group (publisher scheduled query)
# ---------------------------------------------------------------------------

resource "google_firestore_index" "publishing_records_status_scheduled" {
  project     = var.project_id
  database    = google_firestore_database.default.name
  collection  = "publishing_records"
  query_scope = "COLLECTION_GROUP"

  fields {
    field_path = "status"
    order      = "ASCENDING"
  }
  fields {
    field_path = "scheduled_for"
    order      = "ASCENDING"
  }
}

# ---------------------------------------------------------------------------
# content_packages indexes
# ---------------------------------------------------------------------------

resource "google_firestore_index" "content_packages_type_batch" {
  project    = var.project_id
  database   = google_firestore_database.default.name
  collection = "content_packages"

  fields {
    field_path = "package_type"
    order      = "ASCENDING"
  }
  fields {
    field_path = "batch_date"
    order      = "DESCENDING"
  }
}

resource "google_firestore_index" "content_packages_status_expires" {
  project    = var.project_id
  database   = google_firestore_database.default.name
  collection = "content_packages"

  fields {
    field_path = "status"
    order      = "ASCENDING"
  }
  fields {
    field_path = "url_expires_at"
    order      = "ASCENDING"
  }
}

resource "google_firestore_index" "content_packages_status_created" {
  project    = var.project_id
  database   = google_firestore_database.default.name
  collection = "content_packages"

  fields {
    field_path = "status"
    order      = "ASCENDING"
  }
  fields {
    field_path = "created_at"
    order      = "ASCENDING"
  }
}

resource "google_firestore_index" "content_packages_warnings_batch" {
  project    = var.project_id
  database   = google_firestore_database.default.name
  collection = "content_packages"

  fields {
    field_path = "has_warnings"
    order      = "ASCENDING"
  }
  fields {
    field_path = "batch_date"
    order      = "DESCENDING"
  }
}

# ---------------------------------------------------------------------------
# prospect_signals indexes
# ---------------------------------------------------------------------------

resource "google_firestore_index" "prospect_signals_batch_strength" {
  project    = var.project_id
  database   = google_firestore_database.default.name
  collection = "prospect_signals"

  fields {
    field_path = "batch_date"
    order      = "ASCENDING"
  }
  fields {
    field_path = "strength_score"
    order      = "DESCENDING"
  }
}

resource "google_firestore_index" "prospect_signals_status_detected" {
  project    = var.project_id
  database   = google_firestore_database.default.name
  collection = "prospect_signals"

  fields {
    field_path = "status"
    order      = "ASCENDING"
  }
  fields {
    field_path = "detected_at"
    order      = "DESCENDING"
  }
}

resource "google_firestore_index" "prospect_signals_company_detected" {
  project    = var.project_id
  database   = google_firestore_database.default.name
  collection = "prospect_signals"

  fields {
    field_path = "company_name"
    order      = "ASCENDING"
  }
  fields {
    field_path = "detected_at"
    order      = "DESCENDING"
  }
}

# ---------------------------------------------------------------------------
# qualified_leads indexes
# ---------------------------------------------------------------------------

resource "google_firestore_index" "qualified_leads_status_icp" {
  project    = var.project_id
  database   = google_firestore_database.default.name
  collection = "qualified_leads"

  fields {
    field_path = "status"
    order      = "ASCENDING"
  }
  fields {
    field_path = "icp_fit_score"
    order      = "DESCENDING"
  }
}

resource "google_firestore_index" "qualified_leads_pinned_expires" {
  project    = var.project_id
  database   = google_firestore_database.default.name
  collection = "qualified_leads"

  fields {
    field_path = "is_pinned"
    order      = "ASCENDING"
  }
  fields {
    field_path = "expires_at"
    order      = "ASCENDING"
  }
}

# ---------------------------------------------------------------------------
# outreach_drafts indexes
# ---------------------------------------------------------------------------

resource "google_firestore_index" "outreach_drafts_lead_type" {
  project    = var.project_id
  database   = google_firestore_database.default.name
  collection = "outreach_drafts"

  fields {
    field_path = "lead_id"
    order      = "ASCENDING"
  }
  fields {
    field_path = "draft_type"
    order      = "ASCENDING"
  }
}

resource "google_firestore_index" "outreach_drafts_status_generated" {
  project    = var.project_id
  database   = google_firestore_database.default.name
  collection = "outreach_drafts"

  fields {
    field_path = "status"
    order      = "ASCENDING"
  }
  fields {
    field_path = "generated_at"
    order      = "DESCENDING"
  }
}

# ---------------------------------------------------------------------------
# suppress_list indexes
# ---------------------------------------------------------------------------

resource "google_firestore_index" "suppress_list_type_value" {
  project    = var.project_id
  database   = google_firestore_database.default.name
  collection = "suppress_list"

  fields {
    field_path = "type"
    order      = "ASCENDING"
  }
  fields {
    field_path = "value"
    order      = "ASCENDING"
  }
}

# ---------------------------------------------------------------------------
# brand_chunks vector indexes (not yet supported in Terraform — use gcloud)
# ---------------------------------------------------------------------------

resource "null_resource" "brand_chunks_vector_index" {
  provisioner "local-exec" {
    command = <<-EOT
      gcloud firestore indexes composite create \
        --project=${var.project_id} \
        --database="(default)" \
        --collection-group=brand_chunks \
        --query-scope=COLLECTION \
        --field-config=field-path=embedding,vector-config='{"dimension":"2048","flat":{}}' \
      || true
    EOT
  }

  triggers = {
    collection = "brand_chunks"
    dimension  = "2048"
  }

  depends_on = [google_firestore_database.default]
}

resource "null_resource" "brand_chunks_vector_language_index" {
  provisioner "local-exec" {
    command = <<-EOT
      gcloud firestore indexes composite create \
        --project=${var.project_id} \
        --database="(default)" \
        --collection-group=brand_chunks \
        --query-scope=COLLECTION \
        --field-config=field-path=embedding,vector-config='{"dimension":"2048","flat":{}}' \
        --field-config=field-path=language,order=ASCENDING \
      || true
    EOT
  }

  triggers = {
    collection = "brand_chunks"
    dimension  = "2048"
    extra      = "language"
  }

  depends_on = [google_firestore_database.default]
}
