from flask import Flask, render_template, request, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

app = Flask(__name__, instance_relative_config=True)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///instance/app.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

### MODELS ###
class Team(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    rating = db.Column(db.Float, default=1000.0)

class Tournament(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    date = db.Column(db.DateTime, default=datetime.utcnow)

class Match(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    team1_id = db.Column(db.Integer, db.ForeignKey('team.id'), nullable=False)
    team2_id = db.Column(db.Integer, db.ForeignKey('team.id'), nullable=False)
    winner_id = db.Column(db.Integer, db.ForeignKey('team.id'), nullable=False)
    tournament_id = db.Column(db.Integer, db.ForeignKey('tournament.id'), nullable=False)
    date_played = db.Column(db.DateTime, default=datetime.utcnow)

### ROUTES ###
@app.route('/')
def index():
    tournaments = Tournament.query.order_by(Tournament.date.desc()).all()
    return render_template('index.html', tournaments=tournaments)

@app.route('/tournament/<int:tournament_id>')
def view_tournament(tournament_id):
    tournament = Tournament.query.get_or_404(tournament_id)
    matches = Match.query.filter_by(tournament_id=tournament.id).all()
    teams = Team.query.all()
    return render_template('tournament.html', tournament=tournament, matches=matches, teams=teams)

@app.route('/add_tournament', methods=['POST'])
def add_tournament():
    name = request.form['name']
    new_tourney = Tournament(name=name)
    db.session.add(new_tourney)
    db.session.commit()
    return redirect(url_for('index'))

@app.route('/add_team', methods=['GET', 'POST'])
def add_team():
    if request.method == 'POST':
        name = request.form['name']
        new_team = Team(name=name)
        db.session.add(new_team)
        db.session.commit()
        return redirect(url_for('index'))
    return render_template('add_team.html')

@app.route('/delete_team/<int:team_id>')
def delete_team(team_id):
    team = Team.query.get_or_404(team_id)
    db.session.delete(team)
    db.session.commit()
    return redirect(url_for('index'))

@app.route('/match_result/<int:tournament_id>', methods=['GET', 'POST'])
def match_result(tournament_id):
    if request.method == 'POST':
        team1_id = int(request.form['team1'])
        team2_id = int(request.form['team2'])
        winner_id = int(request.form['winner'])
        
        if team1_id == team2_id:
            return "Teams must be different!"

        match = Match(team1_id=team1_id, team2_id=team2_id, winner_id=winner_id, tournament_id=tournament_id)
        db.session.add(match)

        # Rating Update (ELO style)
        team1 = Team.query.get(team1_id)
        team2 = Team.query.get(team2_id)
        k = 32
        expected1 = 1 / (1 + 10 ** ((team2.rating - team1.rating) / 400))
        expected2 = 1 - expected1
        score1 = 1.0 if winner_id == team1_id else 0.0
        score2 = 1.0 - score1

        team1.rating += k * (score1 - expected1)
        team2.rating += k * (score2 - expected2)

        db.session.commit()
        return redirect(url_for('view_tournament', tournament_id=tournament_id))

class Team(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
