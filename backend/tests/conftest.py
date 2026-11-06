"""Runs before any test module: tests must never touch the real database, real tokens or live posting."""
import os
import tempfile

os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mkdtemp()}/test.db"
os.environ["DRY_RUN"] = "true"
os.environ["OPENROUTER_API_KEY"] = ""
os.environ["LINKEDIN_ACCESS_TOKEN"] = ""
os.environ["INSTAGRAM_ACCESS_TOKEN"] = ""
