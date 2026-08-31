from frontend.models import Country, Vexillologist


def make_user(username="testuser", email="test@example.com", password="pass1234!"):
    return Vexillologist.objects.create_user(
        username=username,
        email=email,
        password=password,
    )


def make_country(**overrides):
    values = {
        "name": "Testland",
        "flag_emoji": "🏳",
        "flag_image_url": "https://example.com/flag.png",
        "capital": "Testville",
        "population": 1_000_000,
        "area_km2": 50_000,
        "official_language": "Testish",
        "region": "Europe",
        "entry_type": "Country",
        "fact": "A fun fact.",
    }
    values.update(overrides)
    return Country.objects.create(**values)
