"""Privileged service-layer code for the admin service.

Everything that needs admin-backend-sa's wider IAM lives here (Firebase Auth
admin calls, Cloud Build, BigQuery, Secret Manager). Shared, unprivileged
logic is imported from backend.services.* instead of being duplicated.
"""
