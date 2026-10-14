"""Explicit retention operation; dry-run by default, no finance auto-deletion."""
import argparse
from datetime import timedelta
from sqlalchemy import delete, select, func, or_
from app.auth import now
from app.db import Session, settings
from app.models import AuthSession, LoginFlow, RateBucket, AuthEvent


def retain(db, apply=False, user_id=None):
    timestamp = now()
    policies = [
        (AuthSession, or_(AuthSession.expires_at <= timestamp, AuthSession.last_seen_at <= timestamp - timedelta(seconds=settings.session_idle_seconds))),
        (AuthEvent, AuthEvent.occurred_at < timestamp - timedelta(days=settings.audit_retention_days)),
    ]
    if user_id is None:
        import time
        policies += [(LoginFlow, LoginFlow.expires_at <= timestamp), (RateBucket, RateBucket.window < int(time.time()) // settings.rate_window_seconds - 2)]
    result = {}
    for model, condition in policies:
        if user_id is not None:
            condition = condition & (model.user_id == user_id)
        result[model.__tablename__] = db.scalar(select(func.count()).select_from(model).where(condition))
        if apply:
            db.execute(delete(model).where(condition))
    if apply:
        db.commit()
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--apply', action='store_true', help='Apply retention deletion; without this option only counts are reported')
    args = parser.parse_args()
    with Session() as db:
        print({'applied': args.apply, 'counts': retain(db, args.apply)})
