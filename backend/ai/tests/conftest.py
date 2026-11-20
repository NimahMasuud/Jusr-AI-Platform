from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from app.config import Settings
from app.main import create_app

ROOT = Path(__file__).resolve().parent.parent
SAMPLES = ROOT / "samples"

COORD = {"X-Staff-Id": "STAFF-021", "X-Role": "coordinator", "X-Facility": "Facility A"}
CLIN = {"X-Staff-Id": "STAFF-014", "X-Role": "referring_clinician", "X-Specialty": "haematology"}
RECV = {"X-Staff-Id": "STAFF-033", "X-Role": "receiving_clinician"}
PATIENT = {"X-Staff-Id": "PAT-1", "X-Role": "patient"}


@pytest.fixture
def client():
    return TestClient(create_app(Settings()))
