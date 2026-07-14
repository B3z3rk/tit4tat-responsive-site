from datetime import date, datetime, timedelta

from sqlalchemy.orm import Session as DbSession

from . import models
from .security import hash_password


def _mk_user(db, **kwargs):
    password = kwargs.pop("password")
    user = models.User(password_hash=hash_password(password), **kwargs)
    db.add(user)
    db.flush()
    return user


def seed_if_empty(db: DbSession) -> None:
    if db.query(models.User).count() > 0:
        return

    # --- core demo accounts (unchanged credentials from the old client-only build) ---
    admin = _mk_user(
        db, name="Admin User", email="admin@tit4tat.com", password="admin123",
        role="ADMIN", approval_status="approved",
        profile="Manages the platform, verifies users, reviews reports, and oversees community safety.",
    )
    _mk_user(
        db, name="Super Admin", email="superadmin@tit4tat.com", password="superadmin123",
        role="SUPER_ADMIN", approval_status="approved",
        profile="Platform owner. Full access, plus the only role that can create, demote, suspend, or "
                "reset the password of other Admin accounts.",
    )
    member = _mk_user(
        db, name="Maria Lopez", email="member@tit4tat.com", password="member123",
        role="MEMBER", approval_status="approved",
        profile="Verified community member. Can participate in activities, submit reports, and message neighbours.",
    )
    _mk_user(
        db, name="Jordan Smith", email="regular@tit4tat.com", password="regular123",
        role="REGULAR_MEMBER", approval_status="approved",
        profile="Everyday community user. Can view updates, join activities, report issues, and use emergency features.",
    )
    alex = _mk_user(
        db, name="Alex Johnson", email="alex.johnson@tit4tat.demo", password="welcome123",
        role="MEMBER", approval_status="approved",
        profile="Verified community member and active reporter.",
    )

    # --- named accounts ---
    _mk_user(
        db, name="Gabriella Paisley", email="gabriella.paisley@tit4tat.demo", password="welcome123",
        role="ADMIN", approval_status="approved",
        profile="Manages the platform, verifies users, reviews reports, and oversees community safety.",
    )
    _mk_user(
        db, name="Larry Howell", email="larry.howell@tit4tat.demo", password="welcome123",
        role="MEMBER", approval_status="approved",
        profile="Verified community member. Can participate in activities, submit reports, and message neighbours.",
    )
    _mk_user(
        db, name="Omar Ricketts", email="omar.ricketts@tit4tat.demo", password="welcome123",
        role="REGULAR_MEMBER", approval_status="approved",
        profile="Everyday community user. Can view updates, join activities, report issues, and use emergency features.",
    )
    _mk_user(
        db, name="Dontae Ellis", email="dontae.ellis@tit4tat.demo", password="welcome123",
        role="REGULAR_MEMBER", approval_status="approved",
        profile="Everyday community user. Can view updates, join activities, report issues, and use emergency features.",
    )

    # --- directory members (real accounts, unifying login + directory) ---
    member_specs = [
        dict(name="Sandra Miller", email="sandra.miller@tit4tat.demo", category="Local Business",
             specialty="Groceries and household supplies", location="Market Lane",
             availability="Mon - Sat, 8:00 AM - 7:00 PM", presence_status="Online", business=True,
             business_name="Miller’s Mini Mart",
             business_description="Groceries, household items, and quick supply requests for the community.",
             bio="Owner of Miller’s Mini Mart and an active Tit4Tat member who supports community drives and quick supply requests.",
             notes=["Reliable for basic household items.", "Supports community food donation activities."]),
        dict(name="Jason Brown", email="jason.brown@tit4tat.demo", category="General Member",
             specialty="Plumbing repairs", location="Pine Avenue", availability="Evenings and weekends",
             presence_status="Offline", business=False,
             bio="Community member with plumbing experience. Often helps neighbors identify leaks and water line issues.",
             notes=["Assisted with a leaking pipe report.", "Recommended for minor plumbing checks."]),
        dict(name="Marsha Allen", email="marsha.allen@tit4tat.demo", category="Community Leader",
             specialty="Community coordination", location="Oak Street", availability="Daily, 9:00 AM - 5:00 PM",
             presence_status="Online", business=False,
             bio="Community coordinator who helps organize activities, member approvals, and follow-ups on reports.",
             notes=["Coordinates clean-up activities.", "Helps verify new member references."]),
        dict(name="Kevin Thompson", email="kevin.thompson@tit4tat.demo", category="Local Business",
             specialty="Electrical repairs", location="Riverside Road", availability="Mon - Fri, 10:00 AM - 6:00 PM",
             presence_status="Online", business=True,
             business_name="Thompson Electrical Services",
             business_description="Certified electrician for household jobs, light repairs, and community safety checks.",
             bio="Certified electrician available for small household jobs, light repairs, and community safety checks.",
             notes=["Helped assess broken streetlights.", "Available for minor electrical checks."]),
        dict(name="Denise Clarke", email="denise.clarke@tit4tat.demo", category="Emergency Contact",
             specialty="First aid support", location="Central Park Area", availability="Emergency support only",
             presence_status="Online", business=False, is_essential_worker=True,
             bio="Trained in first aid and available to guide members during minor emergencies until formal help arrives.",
             notes=["Listed as a first aid contact.", "Can advise during community incidents."]),
        dict(name="Owen Grant", email="owen.grant@tit4tat.demo", category="General Member",
             specialty="Transportation assistance", location="School Road", availability="Weekends",
             presence_status="Offline", business=False,
             bio="Community member who sometimes assists elderly residents with transportation to nearby locations.",
             notes=["Assisted during food drive deliveries.", "Available mainly on weekends."]),
    ]

    # Directory category -> the matching specialized role (falls back to plain
    # MEMBER for general members with no specialization).
    CATEGORY_ROLE = {
        "Local Business": "LOCAL_BUSINESS",
        "Community Leader": "COMMUNITY_LEADER",
        "Emergency Contact": "EMERGENCY_CONTACT",
    }

    directory_users = {}
    for spec in member_specs:
        notes = spec.pop("notes")
        role = CATEGORY_ROLE.get(spec["category"], "MEMBER")
        u = _mk_user(
            db, password="welcome123", role=role, approval_status="approved", **spec,
        )
        for note_text in notes:
            db.add(models.MemberNote(user_id=u.id, note=note_text, created_by_id=admin.id))
        directory_users[spec["name"]] = u

    # --- activities ---
    activities = [
        dict(title="Clean Up Our Streets", category="Community Clean-Up", event_date=date(2026, 5, 24),
             time_label="8:00 AM - 11:00 AM", location="Central Park", organizer="Tit4Tat Community Team",
             description="Let's work together to keep our community clean, safe, and beautiful.",
             base_participants=32,
             image_url="https://images.unsplash.com/photo-1559027615-cd4628902d4a?auto=format&fit=crop&w=1200&q=80"),
        dict(title="Future Leaders Talk", category="Youth Mentorship", event_date=date(2026, 5, 25),
             time_label="2:00 PM - 4:00 PM", location="Community Center", organizer="Youth Development Group",
             description="A mentorship session for young people focused on leadership, confidence, and career growth.",
             base_participants=18,
             image_url="https://images.unsplash.com/photo-1521737604893-d14cc237f11d?auto=format&fit=crop&w=1200&q=80"),
        dict(title="Green Our Community", category="Tree Planting", event_date=date(2026, 5, 31),
             time_label="9:00 AM - 12:00 PM", location="Riverside Area", organizer="Tit4Tat Green Team",
             description="Join neighbors in planting trees and improving green spaces across the community.",
             base_participants=24,
             image_url="https://images.unsplash.com/photo-1622383563227-04401ab4e5ea?auto=format&fit=crop&w=1200&q=80"),
        dict(title="Feeding Families", category="Food Drive", event_date=date(2026, 6, 1),
             time_label="10:00 AM - 1:00 PM", location="Donation Point", organizer="Community Care Team",
             description="Support families in need by donating food items or volunteering at the distribution point.",
             base_participants=40,
             image_url="https://images.unsplash.com/photo-1593113598332-cd288d649433?auto=format&fit=crop&w=1200&q=80"),
    ]
    for spec in activities:
        db.add(models.Activity(created_by_id=admin.id, **spec))

    # --- reports (submitted by Alex Johnson) ---
    reports = [
        dict(id="T4T-RPT-001", title="Broken Streetlight", category="Streetlight", priority="High",
             status="Under Review", location="Pine Avenue, near Lot 12",
             description="Streetlight has been out for several nights and the area is very dark.",
             created_at=datetime(2026, 5, 21), timeline=[
                 "Report submitted by member", "Community admin assigned the issue",
                 "Awaiting update from maintenance contact",
             ]),
        dict(id="T4T-RPT-002", title="Garbage not collected", category="Garbage", priority="Medium",
             status="Submitted", location="Market Lane",
             description="Garbage has not been collected for three days and bags are piling up.",
             created_at=datetime(2026, 5, 22), timeline=[
                 "Report submitted by member", "Pending admin review",
             ]),
        dict(id="T4T-RPT-003", title="Leaking water line", category="Water Line", priority="Urgent",
             status="Urgent", location="Oak Street entrance",
             description="A water line appears to be leaking heavily near the community entrance.",
             created_at=datetime(2026, 5, 23), timeline=[
                 "Urgent report submitted", "Admin notified", "Emergency contact recommended",
             ]),
        dict(id="T4T-RPT-004", title="Pothole near school gate", category="Road Damage", priority="Low",
             status="Resolved", location="School Road",
             description="Pothole was affecting vehicles entering the school road.",
             created_at=datetime(2026, 5, 18), timeline=[
                 "Report submitted", "Issue reviewed", "Repair completed", "Report marked as resolved",
             ]),
    ]
    for spec in reports:
        timeline = spec.pop("timeline")
        created_at = spec["created_at"]
        report = models.Report(submitted_by_id=alex.id, updated_at=created_at, **spec)
        db.add(report)
        for i, note in enumerate(timeline):
            db.add(models.ReportTimelineEvent(
                report_id=report.id, note=note, created_by_id=admin.id,
                created_at=created_at + timedelta(hours=i),
            ))

    # --- messages (anchored on Maria Lopez / member@tit4tat.com as "me") ---
    def thread(other_name, exchanges):
        other = directory_users[other_name]
        base = datetime.utcnow() - timedelta(days=2)
        for i, (kind, text) in enumerate(exchanges):
            sender, recipient = (other, member) if kind == "received" else (member, other)
            db.add(models.Message(
                sender_id=sender.id, recipient_id=recipient.id, body=text,
                created_at=base + timedelta(minutes=i * 5),
                read_at=base + timedelta(minutes=i * 5) if kind == "sent" else None,
            ))

    thread("Marsha Allen", [
        ("received", "Good morning. I saw the streetlight report come in."),
        ("sent", "Morning. Yes, it has been out for a few nights now."),
        ("received", "I’ll check the report and update the group shortly."),
    ])
    thread("Sandra Miller", [
        ("received", "The supplies for the food drive are ready."),
        ("sent", "Perfect. I’ll let the volunteers know."),
    ])
    thread("Jason Brown", [
        ("sent", "Do you think you can check the leaking water line?"),
        ("received", "I can pass by and look at the water line."),
    ])
    thread("Denise Clarke", [
        ("received", "For anything urgent, use the emergency call button."),
    ])

    # --- announcements ---
    db.add(models.Announcement(
        title="Welcome to Tit4Tat",
        body="This community hub is now live. Join an activity, report an issue, or say hello in Messages.",
        created_by_id=admin.id,
    ))
    db.add(models.Announcement(
        title="Clean-up this Saturday",
        body="Don't forget the community clean-up at Central Park, 8:00 AM. Bring gloves if you have them!",
        created_by_id=admin.id,
    ))

    db.commit()
