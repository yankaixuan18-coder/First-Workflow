"""
Flask web application for Amazon product research and selection.
"""

import os
import uuid
import tempfile
from flask import Flask, request, jsonify, render_template, send_file, redirect, url_for
from dotenv import load_dotenv
import io

load_dotenv()

from claude_analyzer import analyze_product
from excel_handler import parse_excel, create_report

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024  # 16 MB max upload

# In-memory store for analysis results keyed by UUID
analysis_store = {}


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/analyze", methods=["POST"])
def analyze():
    """Accept JSON product data, run Claude analysis, return scorecard JSON."""
    data = request.get_json(force=True)
    if not data:
        return jsonify({"error": "No data provided"}), 400

    try:
        analysis = analyze_product(data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    # Store result for potential download
    result_id = str(uuid.uuid4())
    analysis_store[result_id] = {
        "data": data,
        "analysis": analysis,
        "original_path": None,
    }

    return jsonify({"id": result_id, "analysis": analysis})


@app.route("/upload", methods=["POST"])
def upload():
    """Accept Excel file upload, parse row 3, run analysis, return JSON."""
    if "file" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400

    file = request.files["file"]
    if not file.filename or not file.filename.lower().endswith(".xlsx"):
        return jsonify({"error": "Please upload a valid .xlsx file"}), 400

    # Save to temp file
    tmp = tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False)
    try:
        file.save(tmp.name)
        tmp.close()

        data = parse_excel(tmp.name)
    except Exception as e:
        return jsonify({"error": f"Failed to parse Excel file: {str(e)}"}), 400

    try:
        analysis = analyze_product(data)
    except Exception as e:
        return jsonify({"error": f"Analysis failed: {str(e)}"}), 500

    result_id = str(uuid.uuid4())
    analysis_store[result_id] = {
        "data": data,
        "analysis": analysis,
        "original_path": tmp.name,
    }

    return jsonify({"id": result_id, "analysis": analysis})


@app.route("/download/<result_id>")
def download(result_id):
    """Download Excel report for a given analysis ID."""
    entry = analysis_store.get(result_id)
    if not entry:
        return "Analysis not found", 404

    try:
        report_bytes = create_report(
            entry.get("original_path"),
            entry["data"],
            entry["analysis"],
        )
    except Exception as e:
        return f"Failed to generate report: {str(e)}", 500

    product_name = entry["data"].get("product_name", "product")
    safe_name = "".join(c for c in product_name if c.isalnum() or c in (" ", "-", "_")).strip()
    filename = f"AI分析_{safe_name or 'report'}.xlsx"

    return send_file(
        io.BytesIO(report_bytes),
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name=filename,
    )


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
