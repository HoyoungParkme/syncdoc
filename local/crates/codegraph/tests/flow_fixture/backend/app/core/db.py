from sqlalchemy import select
from sqlalchemy.orm import Session


def save(s: Session, payload):
    q = select(1)
    s.execute(q)
    s.commit()
    with Session() as other:
        other.flush()
