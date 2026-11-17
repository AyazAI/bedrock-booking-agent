from __future__ import annotations

from booking_agent.rag.embeddings import cosine, embed


def test_hash_embeddings_prefer_shared_words() -> None:
    hours = embed("when are you open hours schedule")
    parking = embed("where do I park the car")
    query = embed("when are you open")
    assert cosine(query, hours) > cosine(query, parking)


def test_faq_answers_hours_and_abstains_on_parking(client) -> None:
    hours = client.post("/api/chat", json={"message": "When are you open?"}).json()
    assert hours["tool_calls"][0]["result"]["matched"] is True
    assert "Monday" in hours["reply"]
    parking = client.post("/api/chat", json={"message": "Where do I park?"}).json()
    assert parking["tool_calls"][0]["result"]["matched"] is False
    assert "confirm" in parking["reply"]
