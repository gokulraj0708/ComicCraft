def sample_payload(panel_count=3):
    return {
        "story_prompt": "A young inventor helps a lost dragon return to its mountain home.",
        "character_name": "Mira",
        "setting": "a moonlit clockwork city",
        "tone": "Adventurous",
        "art_style": "Modern comic book",
        "panel_count": panel_count,
    }


def test_generate_get_and_download_comic(client, settings):
    response = client.post("/api/v1/comics", json=sample_payload())
    assert response.status_code == 201, response.text
    comic = response.json()
    assert len(comic["panels"]) == 3
    assert comic["provider_info"]["text_provider"] == "demo"
    assert comic["provider_info"]["image_providers_used"] == ["placeholder"]

    comic_id = comic["comic_id"]
    manifest = settings.storage_dir / "comics" / comic_id / "comic.json"
    assert manifest.is_file()
    assert (settings.storage_dir / "comics" / comic_id / "comic.pdf").is_file()
    assert all(
        (settings.storage_dir / "comics" / comic_id / "panels" / f"panel-{index}.png").is_file()
        for index in range(1, 4)
    )

    fetched = client.get(f"/api/v1/comics/{comic_id}")
    assert fetched.status_code == 200
    assert fetched.json()["comic_id"] == comic_id

    pdf = client.get(f"/download/{comic_id}")
    assert pdf.status_code == 200
    assert pdf.headers["content-type"] == "application/pdf"
    assert pdf.content.startswith(b"%PDF")


def test_legacy_json_aliases(client):
    payload = sample_payload()
    payload["prompt"] = payload.pop("story_prompt")
    payload["style"] = payload.pop("art_style")
    response = client.post("/generate-comic/json", json=payload)
    assert response.status_code == 200, response.text
    assert len(response.json()["panels"]) == 3


def test_api_validation(client):
    payload = sample_payload()
    payload["story_prompt"] = "too short"
    response = client.post("/api/v1/comics", json=payload)
    assert response.status_code == 422


def test_unknown_comic_is_404(client):
    response = client.get("/api/v1/comics/" + "0" * 32)
    assert response.status_code == 404
