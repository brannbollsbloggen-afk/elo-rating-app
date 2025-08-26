#!/usr/bin/env python3
"""
Elo Rating App (single-file Flask)

Features
--------
- Global Elo ratings across all tournaments (ratings persist between runs).
- Create tournaments, add/remove teams.
- Post/delete match results per tournament.
- View: global leaderboard, tournaments list, tournament standings & match history.
- Recompute global Elo on any write that affects matches/teams.
- SQLite persistence in ./instance/elo_app.db

Quickstart
----------
pip install Flask Flask-SQLAlchemy
python app.py
# visit http://127.0.0.1:8000

Production (Heroku/Render)
--------------------------
Add requirements.txt including Flask, Flask-SQLAlchemy, gunicorn
Add Procfile:  web: gunicorn app:app --log-file - --access-logfile -
"""

from __future__ import annotations

import os
import math
from datetime import datetime, date
from typing import Dict, List, Tuple, Optional, Iterable

from flask import (
    Flask, render_template_string, request, redirect, url_for, flash
)
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func, and_, or_

# -----------------------------
# Configuration
# -----------------------------

BASE_RATING = 1500.0
K_FACTOR = 32.0

app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev-secret-change-me")

# Ensure instance folder exists for SQLite DB
os.makedirs(app.instance_path, exist_ok=True)
db_path = os.path.join(app.instance_path, "elo_app.db")
app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{db_path}"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)


# -----------------------------
# Models
# -----------------------------

class Team(db.Model):
    __tablename__ = "teams"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(128), unique=True, nullable=False)
    active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def __repr__(self):
        return f"<Team {self.id} {self.name}>"


class Tournament(db.Model):
    __tablename__ = "tournaments"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(128), unique=True, nullable=False)
    start_date = db.Column(db.Date, nullable=True)
    end_date = db.Column(db.Date, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def __repr__(self):
        return f"<Tournament {self.id} {self.name}>"
class Match(db.Model):
    __tablename__ = "matches"
    id = db.Column(db.Integer, primary_key=True)
    tournament_id = db.Column(db.Integer, db.ForeignKey("tournaments.id", ondelete="CASCADE"), nullable=False)
    date_played = db.Column(db.Date, nullable=False, index=True)

    team1_id = db.Column(db.Integer, db.ForeignKey("teams.id", ondelete="CASCADE"), nullable=False)
    team2_id = db.Column(db.Integer, db.ForeignKey("teams.id", ondelete="CASCADE"), nullable=False)

    score1 = db.Column(db.Integer, nullable=False, default=0)
    score2 = db.Column(db.Integer, nullable=False, default=0)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    tournament = db.relationship("Tournament", lazy="joined")
    team1 = db.relationship("Team", foreign_keys=[team1_id], lazy="joined")
    team2 = db.relationship("Team", foreign_keys=[team2_id], lazy="joined")

    def __repr__(self):
        return f"<Match {self.id} T{self.tournament_id} {self.team1_id} vs {self.team2_id} {self.score1}-{self.score2}>"


class GlobalRating(db.Model):
    """
    Stores the latest global rating per team, updated after each recompute.
    This speeds up leaderboard display while still allowing full recomputation on edits.
    """
    __tablename__ = "global_ratings"
    team_id = db.Column(db.Integer, db.ForeignKey("teams.id", ondelete="CASCADE"), primary_key=True)
    rating = db.Column(db.Float, nullable=False, default=BASE_RATING)
    last_updated = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    team = db.relationship("Team", lazy="joined")

    def __repr__(self):
        return f"<GlobalRating team={self.team_id} rating={self.rating:.1f}>"


# -----------------------------
# Elo rating helpers
# -----------------------------

def expected_score(r_a: float, r_b: float) -> float:
    """Expected score for A vs B using Elo formula."""
    return 1.0 / (1.0 + 10.0 ** ((r_b - r_a) / 400.0))


def update_elo(r_a: float, r_b: float, score_a: float, k: float = K_FACTOR) -> Tuple[float, float]:
    """Return new ratings after a result for A (score_a in {0, 0.5, 1})."""
    ea = expected_score(r_a, r_b)
    eb = 1.0 - ea
    r_a_new = r_a + k * (score_a - ea)
    r_b_new = r_b + k * ((1.0 - score_a) - eb)
    return r_a_new, r_b_new


def match_outcome(score1: int, score2: int) -> float:
    """Convert scores to Elo score for team1: 1=win, 0.5=draw, 0=loss."""
    if score1 > score2:
        return 1.0
    elif score1 < score2:
        return 0.0
    else:
        return 0.5


# -----------------------------
# Rating recomputation
# -----------------------------

def iter_matches_chronological(matches_q: Iterable[Match]) -> Iterable[Match]:
    """Yield matches sorted by (date_played ASC, id ASC) to ensure deterministic order."""
    return sorted(matches_q, key=lambda m: (m.date_played, m.id))


def recompute_global_ratings() -> Dict[int, float]:
    """
    Recompute global ratings across ALL tournaments from scratch,
    in chronological order of matches. Persist to GlobalRating table.

    Returns a dict {team_id: rating}
    """
    teams = Team.query.all()
    ratings: Dict[int, float] = {t.id: BASE_RATING for t in teams}

    matches = iter_matches_chronological(Match.query.all())
    for m in matches:
        a = ratings.get(m.team1_id, BASE_RATING)
        b = ratings.get(m.team2_id, BASE_RATING)
        s_a = match_outcome(m.score1, m.score2)
        a_new, b_new = update_elo(a, b, s_a, K_FACTOR)
        ratings[m.team1_id] = a_new
        ratings[m.team2_id] = b_new

    # persist
    for team in teams:
        current = ratings.get(team.id, BASE_RATING)
        gr = GlobalRating.query.get(team.id)
        if not gr:
            gr = GlobalRating(team_id=team.id, rating=current, last_updated=datetime.utcnow())
            db.session.add(gr)
        else:
            gr.rating = current
            gr.last_updated = datetime.utcnow()

    db.session.commit()
    return ratings


def global_ratings_as_of(cutoff_date: date) -> Dict[int, float]:
    """
    Compute global ratings up to (and including) cutoff_date.
    Used to seed tournament standings from global state at tournament start.
    """
    teams = Team.query.all()
    ratings: Dict[int, float] = {t.id: BASE_RATING for t in teams}
    matches = iter_matches_chronological(
        Match.query.filter(Match.date_played <= cutoff_date).all()
    )
    for m in matches:
        a = ratings.get(m.team1_id, BASE_RATING)
        b = ratings.get(m.team2_id, BASE_RATING)
        s_a = match_outcome(m.score1, m.score2)
        a_new, b_new = update_elo(a, b, s_a, K_FACTOR)
        ratings[m.team1_id] = a_new
        ratings[m.team2_id] = b_new
    return ratings


def tournament_standings(tournament: Tournament) -> List[Tuple[Team, float]]:
    """
    Compute tournament
