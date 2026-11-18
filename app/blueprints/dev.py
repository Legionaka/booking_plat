"""Local-only pages for reviewing the frontend foundation."""

from flask import Blueprint, abort, current_app, render_template

dev_bp = Blueprint("dev", __name__)


@dev_bp.get("/dev/components")
def component_sheet():
    if (
        current_app.config.get("APP_ENV") != "development"
        and not current_app.config.get("DEMO_MODE")
    ):
        abort(404)
    return render_template("dev/components.html")
