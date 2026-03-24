terraform {
  required_version = ">= 1.5"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
    google-beta = {
      source  = "hashicorp/google-beta"
      version = "~> 5.0"
    }
    null = {
      source  = "hashicorp/null"
      version = "~> 3.0"
    }
  }

  backend "local" {}
}

provider "google" {
  project = var.project_id
  region  = var.region
}

provider "google-beta" {
  project = var.project_id
  region  = var.region
}

locals {
  function_urls = merge({
    "fn-daily-pipeline"      = ""
    "fn-tenant-pipelines"    = ""
    "fn-scheduled-publisher" = ""
    "fn-analytics-sync"      = ""
    "fn-platform-generate"   = ""
    "fn-package-builder"     = ""
  }, var.function_urls)
}

module "project" {
  source     = "./modules/project"
  project_id = var.project_id
}

module "firestore" {
  source     = "./modules/firestore"
  project_id = var.project_id
  region     = var.region
  depends_on = [module.project]
}

# Brand documents bucket — upload brand/ICP/case-study docs here for RAG indexing.
# Packages bucket (ZIP downloads) removed: outputs are now delivered via email.
module "storage" {
  source     = "./modules/storage"
  project_id = var.project_id
  region     = var.region
  depends_on = [module.project]
}

# Daily Cloud Scheduler → tenant pipeline function at 07:00 in scheduler_timezone
# (see module.scheduler). Dashboard "next run" copy uses per-tenant notification_time only.
module "scheduler" {
  source                     = "./modules/scheduler"
  project_id                 = var.project_id
  region                     = var.region
  service_account_email      = module.project.service_account_email
  fn_daily_pipeline_url      = local.function_urls["fn-daily-pipeline"]
  fn_tenant_pipelines_url    = local.function_urls["fn-tenant-pipelines"]
  fn_scheduled_publisher_url = local.function_urls["fn-scheduled-publisher"]
  fn_analytics_sync_url      = local.function_urls["fn-analytics-sync"]
  scheduler_timezone         = var.scheduler_timezone
  publisher_schedule         = var.publisher_schedule
  analytics_sync_schedule    = var.analytics_sync_schedule
  depends_on                 = [module.project]
}

module "pubsub" {
  source                   = "./modules/pubsub"
  project_id               = var.project_id
  service_account_email    = module.project.service_account_email
  fn_platform_generate_url = local.function_urls["fn-platform-generate"]
  fn_package_builder_url   = local.function_urls["fn-package-builder"]
  depends_on               = [module.project]
}

module "monitoring" {
  source             = "./modules/monitoring"
  project_id         = var.project_id
  notification_email = var.notification_email
  depends_on         = [module.project, module.pubsub]
}

module "secrets" {
  source     = "./modules/secrets"
  project_id = var.project_id
  depends_on = [module.project]
}
