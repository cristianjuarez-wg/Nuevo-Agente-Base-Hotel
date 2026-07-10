"""
F3.3 — restaurant_name como campo del perfil del negocio.

Verifica que el endpoint público lo expone y que el PUT (admin) lo actualiza, para que un
cliente nuevo no tenga que tocar código para cambiar el nombre de su restaurante.
"""


def test_public_profile_incluye_restaurant_name(client):
    r = client.get("/api/public/business-profile")
    assert r.status_code == 200
    assert "restaurant_name" in r.json()


def test_put_actualiza_restaurant_name(client, admin_headers):
    nuevo = "La Cava del Sur"
    r = client.put("/api/business-profile", json={"restaurant_name": nuevo}, headers=admin_headers)
    assert r.status_code == 200, r.text
    assert r.json().get("restaurant_name") == nuevo
    # Y se refleja en el subset público (mismo origen).
    pub = client.get("/api/public/business-profile").json()
    assert pub["restaurant_name"] == nuevo
