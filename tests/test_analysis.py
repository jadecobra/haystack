import pytest
from app.main import app
from fastapi.testclient import TestClient

client = TestClient(app)

def test_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}

def test_analyze_ticker_endpoint():
    response = client.get("/analyze/AAPL")
    assert response.status_code == 200
    assert "ticker" in response.json()
    assert "analysis" in response.json()

def test_analyze_ticker_invalid_ticker():
    response = client.get("/analyze/INVALID")
    assert response.status_code == 200
    assert "error" in response.json()
