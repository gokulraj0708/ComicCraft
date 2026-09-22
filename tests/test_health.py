def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "app": "ComicCraft",
        "version": "1.0.0",
        "ai_mode": "demo",
        "image_provider": "placeholder",
    }


def test_home_page(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "Turn one bright idea" in response.text
    assert 'action="http://testserver/generate"' in response.text
