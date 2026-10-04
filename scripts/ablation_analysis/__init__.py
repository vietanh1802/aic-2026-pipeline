# scripts/ablation_analysis/__init__.py
"""Offline analysis of an ablation run folder: statistics, tables, figures, error analysis, write-ups.

Lives outside the Docker image and the backend package on purpose. It reads ablation.db with sqlite3 and
needs numpy and matplotlib (scripts/requirements-analysis.txt), never imports app.*, and is not part of
the CI backend check.
"""
