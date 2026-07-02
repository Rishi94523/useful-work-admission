"""
Seed text samples (short reviews with known sentiment) for the distributed
LLM labeling pipeline. Ground-truth labels go into sample metadata for
accuracy measurement, exactly like the MNIST honeypot scheme.

Run from the server/ directory (uses the same DB as the server):
    venv/Scripts/python ../scripts/seed_text_samples.py
"""

import hashlib
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "server"))

from app.models.base import Base  # noqa: E402
from app.models.sample import Sample  # noqa: E402
from app.config import get_settings  # noqa: E402

settings = get_settings()

REVIEWS = [
    ("The movie was absolutely wonderful, I loved every minute of it!", "positive"),
    ("Terrible service, cold food, and rude staff. Never coming back.", "negative"),
    ("This is the best purchase I have ever made, highly recommend.", "positive"),
    ("What a complete waste of money, it broke after two days.", "negative"),
    ("An instant classic - beautiful, moving, and unforgettable.", "positive"),
    ("Utterly boring and predictable from start to finish.", "negative"),
    ("Fantastic quality and arrived earlier than expected. Very happy!", "positive"),
    ("The hotel room was filthy and the staff ignored our complaints.", "negative"),
    ("A delightful little cafe with amazing coffee and friendly owners.", "positive"),
    ("Disappointing sequel that ruins everything good about the original.", "negative"),
    ("Works perfectly, easy to set up, and great customer support.", "positive"),
    ("Overpriced, underwhelming, and the battery dies within an hour.", "negative"),
]


def main() -> None:
    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import sessionmaker

    sync_url = settings.database_url.replace("+aiosqlite", "").replace("+asyncpg", "")
    engine = create_engine(sync_url)
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)

    added = 0
    with session_factory() as session:
        for text, label in REVIEWS:
            blob = text.encode("utf-8")
            data_hash = hashlib.sha256(blob).hexdigest()
            exists = session.execute(
                select(Sample.id).where(Sample.data_hash == data_hash)
            ).first()
            if exists:
                continue
            session.add(
                Sample(
                    data_type="text",
                    model_type="sentiment",
                    data_hash=data_hash,
                    data_blob=blob,
                    metadata_={"true_label": label, "source": "seed-reviews"},
                )
            )
            added += 1
        session.commit()
    print(f"Seeded {added} text samples ({len(REVIEWS) - added} already present)")


if __name__ == "__main__":
    main()
