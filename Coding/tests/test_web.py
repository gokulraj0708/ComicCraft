def test_web_form_generation(client):
    response = client.post(
        "/generate",
        data={
            "story_prompt": "A curious fox discovers a secret garden under the city library.",
            "character_name": "Fenn",
            "setting": "an underground garden",
            "tone": "Mysterious",
            "art_style": "Watercolor storybook",
            "panel_count": "3",
        },
    )
    assert response.status_code == 200, response.text
    assert "COMIC COMPLETE" in response.text
    assert response.text.count('class="comic-panel"') == 3
    assert "Download PDF" in response.text


def test_test_image_endpoint(client):
    response = client.get("/test-image", params={"prompt": "A robot reading a comic"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["provider"] == "placeholder"
    image = client.get(payload["image_url"])
    assert image.status_code == 200
    assert image.headers["content-type"] == "image/png"
