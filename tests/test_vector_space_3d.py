import pytest
from fastapi.testclient import TestClient
from src.main import app

client = TestClient(app)


def test_export_vector_space_3d_json():
    """Testa exportacao da nuvem de pontos 3D dos embeddings em JSON."""
    resp = client.get("/api/v1/memory/vector-space-3d?format=json")
    assert resp.status_code == 200
    data = resp.json()
    assert "points" in data
    assert "dimensions" in data
    assert data["dimensions"] == 3
    assert isinstance(data["points"], list)


def test_export_vector_space_3d_ply():
    """Testa exportacao em formato Polygon File Format (.PLY) sem labels para visualizadores 3D."""
    resp = client.get("/api/v1/memory/vector-space-3d?format=ply")
    assert resp.status_code == 200
    text = resp.text
    assert "ply" in text
    assert "property float x" in text
    assert "property float y" in text
    assert "property float z" in text
    assert "end_header" in text


def test_export_vector_space_3d_obj():
    """Testa exportacao em formato Wavefront OBJ (.OBJ)."""
    resp = client.get("/api/v1/memory/vector-space-3d?format=obj")
    assert resp.status_code == 200
    text = resp.text
    assert "# Wavefront OBJ" in text
