"""Liveness and dependency readiness endpoints."""

from flask import Blueprint, jsonify
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.extensions import db

health_bp = Blueprint("health", __name__)


@health_bp.get("/health")
def health() -> tuple[dict[str, object], int]:
    """Return liveness without depending on external services."""
    return jsonify({"status": "ok"}), 200


@health_bp.get("/ready")
def ready() -> tuple[dict[str, object], int]:
    """Check PostgreSQL readiness without coupling public health to Redis."""
    try:
        db.session.execute(text("SELECT 1"))
    except SQLAlchemyError:
        db.session.rollback()
        return jsonify({"status": "unhealthy"}), 503
    return jsonify({"status": "ok"}), 200
