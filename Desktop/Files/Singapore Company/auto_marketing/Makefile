.PHONY: help dev deploy deploy-pipeline deploy-publisher deploy-analytics deploy-api deploy-rules deploy-frontend infra-plan infra-apply lint-py test-py run-pipeline sync-brand-context frontend-install frontend-build qa-backend qa-frontend qa dev-api dev-frontend qa-e2e qa-local-full

-include .env

PROJECT_ID ?= intonation-labs-marketing
REGION ?= asia-southeast1
GEMINI_REGION ?= global
FUNCTIONS_SRC := functions
PIPELINE_FUNCTION_NAME := fn-tenant-pipelines
PUBLISHER_FUNCTION_NAME := fn-scheduled-publisher
ANALYTICS_FUNCTION_NAME := fn-analytics-sync
API_SERVICE_NAME := automark-api
APPHOSTING_BACKEND_ID ?= automark-web
SERVICE_ACCOUNT ?= sa-cloud-functions@$(PROJECT_ID).iam.gserviceaccount.com
BRAND_DOCS_BUCKET ?= brand-documents-$(PROJECT_ID)
APP_URL ?= https://automark-web--intonation-labs-marketing.asia-east1.hosted.app
ALLOWED_ORIGINS ?= http://localhost:3000,https://automark-web--intonation-labs-marketing.asia-east1.hosted.app
STRIPE_STARTER_PRICE_ID ?=
STRIPE_PRO_PRICE_ID ?=
API_SECRET_FLAGS ?=
PIPELINE_SECRET_FLAGS ?=

SMTP_HOST ?=
SMTP_PORT ?= 587
SMTP_USER ?=
SMTP_FROM_EMAIL ?=
SMTP_TO_EMAIL ?=
SMTP_USE_TLS ?= true
SMTP_USE_SSL ?= false

COMMON_FUNCTION_VARS := GCP_PROJECT_ID=$(PROJECT_ID),GCP_REGION=$(REGION),GEMINI_REGION=$(GEMINI_REGION),BRAND_DOCS_BUCKET=$(BRAND_DOCS_BUCKET)
PIPELINE_VARS := $(COMMON_FUNCTION_VARS),SMTP_HOST=$(SMTP_HOST),SMTP_PORT=$(SMTP_PORT),SMTP_USER=$(SMTP_USER),SMTP_FROM_EMAIL=$(SMTP_FROM_EMAIL),SMTP_TO_EMAIL=$(SMTP_TO_EMAIL),SMTP_USE_TLS=$(SMTP_USE_TLS),SMTP_USE_SSL=$(SMTP_USE_SSL)
WORKER_VARS := $(COMMON_FUNCTION_VARS)
API_VARS := ^||^GCP_PROJECT_ID=$(PROJECT_ID)||GCP_REGION=$(REGION)||GEMINI_REGION=$(GEMINI_REGION)||BRAND_DOCS_BUCKET=$(BRAND_DOCS_BUCKET)||APP_URL=$(APP_URL)||ALLOWED_ORIGINS=$(ALLOWED_ORIGINS)||STRIPE_STARTER_PRICE_ID=$(STRIPE_STARTER_PRICE_ID)||STRIPE_PRO_PRICE_ID=$(STRIPE_PRO_PRICE_ID)

help:
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

dev: ## Run pipeline locally with functions-framework (port 8081)
	cd $(FUNCTIONS_SRC) && functions-framework --target=run_daily_pipeline --port=8081 --debug

run-pipeline: ## Trigger the pipeline manually (local dev server must be running)
	curl -s -X POST http://localhost:8081 -H "Content-Type: application/json" -d '{"tenant_id":"intonation-labs-internal"}' | python3 -m json.tool

sync-brand-context: ## Ingest local Markdown brand materials into Firestore
	GCP_PROJECT_ID=$(PROJECT_ID) GCP_REGION=$(REGION) python3 functions/brand_context_sync.py

deploy: deploy-pipeline deploy-publisher deploy-analytics deploy-api deploy-rules ## Deploy backend services and rules

deploy-pipeline: ## Deploy the tenant orchestrator Cloud Function
	@echo "Deploying $(PIPELINE_FUNCTION_NAME)..."
	gcloud functions deploy $(PIPELINE_FUNCTION_NAME) \
		--gen2 \
		--project=$(PROJECT_ID) \
		--runtime=python312 \
		--source=$(FUNCTIONS_SRC) \
		--entry-point=run_tenant_pipelines \
		--trigger-http \
		--region=$(REGION) \
		--memory=1024MB \
		--timeout=540s \
		--min-instances=0 \
		--service-account=$(SERVICE_ACCOUNT) \
		--no-allow-unauthenticated \
		--set-env-vars="$(PIPELINE_VARS)" \
		$(PIPELINE_SECRET_FLAGS)
	@echo "Done. Update infra/terraform.tfvars with the deployed function URL before running infra-apply."

deploy-publisher: ## Deploy the scheduled publisher Cloud Function
	@echo "Deploying $(PUBLISHER_FUNCTION_NAME)..."
	gcloud functions deploy $(PUBLISHER_FUNCTION_NAME) \
		--gen2 \
		--project=$(PROJECT_ID) \
		--runtime=python312 \
		--source=$(FUNCTIONS_SRC) \
		--entry-point=run_scheduled_publisher \
		--trigger-http \
		--region=$(REGION) \
		--memory=512MB \
		--timeout=300s \
		--min-instances=0 \
		--service-account=$(SERVICE_ACCOUNT) \
		--no-allow-unauthenticated \
		--set-env-vars="$(WORKER_VARS)"
	@echo "Done. Update infra/terraform.tfvars with the deployed function URL before running infra-apply."

deploy-analytics: ## Deploy the analytics sync Cloud Function
	@echo "Deploying $(ANALYTICS_FUNCTION_NAME)..."
	gcloud functions deploy $(ANALYTICS_FUNCTION_NAME) \
		--gen2 \
		--project=$(PROJECT_ID) \
		--runtime=python312 \
		--source=$(FUNCTIONS_SRC) \
		--entry-point=run_analytics_sync \
		--trigger-http \
		--region=$(REGION) \
		--memory=512MB \
		--timeout=300s \
		--min-instances=0 \
		--service-account=$(SERVICE_ACCOUNT) \
		--no-allow-unauthenticated \
		--set-env-vars="$(WORKER_VARS)"
	@echo "Done. Update infra/terraform.tfvars with the deployed function URL before running infra-apply."

deploy-api: ## Deploy the FastAPI backend to Cloud Run
	@echo "Deploying $(API_SERVICE_NAME)..."
	gcloud run deploy $(API_SERVICE_NAME) \
		--project=$(PROJECT_ID) \
		--region=$(REGION) \
		--source=$(FUNCTIONS_SRC) \
		--service-account=$(SERVICE_ACCOUNT) \
		--allow-unauthenticated \
		--set-env-vars="$(API_VARS)" \
		$(API_SECRET_FLAGS)

deploy-rules: ## Deploy Firestore security rules
	firebase deploy --only firestore:rules

deploy-frontend: ## Deploy the Next.js frontend to Firebase App Hosting
	firebase deploy --only apphosting:$(APPHOSTING_BACKEND_ID)

infra-plan: ## Terraform plan
	cd infra && terraform plan -var-file=terraform.tfvars

infra-apply: ## Terraform apply
	cd infra && terraform apply -var-file=terraform.tfvars

lint-py: ## Lint Python code
	cd $(FUNCTIONS_SRC) && python3 -m ruff check . && python3 -m ruff format --check .

test-py: ## Run Python tests
	cd $(FUNCTIONS_SRC) && python3 -m pytest tests/ -v

frontend-install: ## Install frontend dependencies
	cd frontend && npm install

frontend-build: ## Build the Next.js frontend
	cd frontend && npm run build

qa-backend: ## Run backend lint and tests
	cd $(FUNCTIONS_SRC) && python3 -m ruff check . && python3 -m ruff format --check . && python3 -m pytest tests/ -v

qa-frontend: ## Build the frontend for production
	cd frontend && npm run build

qa: qa-backend qa-frontend ## Run repo QA checks

dev-api: ## Run FastAPI backend locally (port 8080)
	cd $(FUNCTIONS_SRC) && uvicorn api.app:app --host=0.0.0.0 --port=8080 --reload

dev-frontend: ## Run Next.js frontend locally (port 3000)
	cd frontend && npm run dev

qa-e2e: ## Run Playwright E2E tests (starts API + frontend via webServer)
	cd frontend && npm run test:e2e

qa-local-full: qa-backend qa-frontend ## Full local QA: backend tests + frontend build
	@echo "QA passed. For browser E2E: start 'make dev-api' and 'make dev-frontend' in separate terminals, then 'make qa-e2e'."
