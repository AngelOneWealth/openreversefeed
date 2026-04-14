"""Seed reference data (AMCs, schemes, accounts) into the library Postgres."""
import uuid

from django.core.management.base import BaseCommand
from sqlalchemy import func, select

from openreversefeed.db.models import Account, Amc, Scheme
from reference_app.ofr_bridge import get_session_factory

_FAKE_SCHEMES = [
    ("SYNLRGCAP001", "ALPHA01",   "Alpha Largecap Growth Fund - Direct"),
    ("SYNTOP100002", "BETA02",    "Beta Top 100 Growth Fund - Direct"),
    ("SYNSMLCAP003", "GAMMA03",   "Gamma Smallcap Growth Fund - Direct"),
    ("SYNMIDCAP004", "DELTA04",   "Delta Midcap Growth Fund - Direct"),
    ("SYNFLEXI005",  "EPSILON5",  "Epsilon Flexicap Growth Fund - Direct"),
]

_FAKE_ACCOUNTS = [
    ("Synthetic Investor 0", "AAAPL0001A", "individual"),
    ("Synthetic Investor 1", "AAAPL0002B", "joint"),
    ("Synthetic Investor 2", "AAAPL0003C", "individual"),
    ("Synthetic Investor 3", "AAAPL0003D", "joint"),
    ("Synthetic Investor 4", "AAAPL0004E", "individual"),
]


class Command(BaseCommand):
    help = "Seed reference data (AMCs, schemes, accounts). Idempotent."

    def handle(self, *args, **options):
        Session = get_session_factory()
        with Session() as session:
            existing = session.execute(select(func.count()).select_from(Account)).scalar()
            if existing:
                self.stdout.write(f"Already seeded ({existing} accounts). Skipping.")
                return

            amc_map = {}
            for _sc, code, _name in _FAKE_SCHEMES:
                amc = Amc(code=code, name=f"{code} AMC")
                session.add(amc)
                session.flush()
                amc_map[code] = amc

            for sc, code, name in _FAKE_SCHEMES:
                session.add(
                    Scheme(
                        scheme_code=sc,
                        amc_id=amc_map[code].id,
                        name=name,
                        plan_type="growth",
                        option="direct",
                    )
                )

            for name, pan, ot in _FAKE_ACCOUNTS:
                session.add(Account(id=uuid.uuid4(), name=name, pan=pan, ownership_type=ot))

            session.commit()
            self.stdout.write(
                self.style.SUCCESS(
                    f"Seeded {len(amc_map)} AMCs, {len(_FAKE_SCHEMES)} schemes, "
                    f"{len(_FAKE_ACCOUNTS)} accounts"
                )
            )
