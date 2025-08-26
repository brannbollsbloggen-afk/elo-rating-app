from flask import Flask, render_template, request, redirect, url_for
import matplotlib.pyplot as plt
import os

app = Flask(__name__, template_folder='templates_files')

ratings = {}
history = {}
tournaments = {}


# -------------------- MODELS --------------------

class Team(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    elo = db.Column(db.Float, default=1000)

class Match(db.Model):
    id = db_id = db.Column(db.Integer, db.ForeignKey('team.id'))
    date = db.Column(db.DateTime, default=datetime.utcnow)
    elo_change = db.Column(db.Float)

# -------------------- ELO CALCULATION --------------------

def calculate_elo(team1_elo, team2_elo, winner):
    k = 32
    expected1 = 1 / (1 + 10 ** ((team2_elo - team1_elo) / 400))
    expected2 = 1 - expected1

    if winner == 1:
        new_team1_elo = team1_elo + k * (1 - expected1)
        new_team2_elo = team2_elo + k * (0 - expected2)
    else:
        new_team1_elo = team1_elo + k * (0 - expected1)
        new_team2_elo = team2_elo + k * (1 - expected2)

    return new_team1_elo, new_team2_elo

# -------------------- ROUTES --------------------

@app.route('/')
def index():
    teams = Team.query.order_by(Team.elo.desc()).all()
    return render_template('index.html', teams=teams)

@app.route('/matches')
def matches():
    match_list = Match.query.order_by(Match.date.desc()).all()
    return render_template('matches.html', matches=match_list)

@app.route('/compare')
def compare():
    team1_name = request.args.get('team1')
    team2_name = request.args.get('team2')
    team1 = Team.query.filter_by(name=team1_name).first()
    team2 = Team.query.filter_by(name=team2_name).first()

    if not team1 or not team2:
        return "One or both teams not found."

    prob_team1 = 1 / (1 + 10 ** ((team2.elo - team1.elo) / 400))
    prob_team2 = 1 - prob_team1

    return render_template('compare.html', team1=team1, team2=team2,
                           prob_team1=round(prob_team1 * 100, 2),
                           prob_team2=round(prob_team2 * 100, 2))

# -------------------- ADMIN PANEL --------------------

@app.route('/admin', methods=['GET', 'POST'])
def admin():
    if request.method == 'POST':
        password = request.form['password']
        if password == 'admin123':  # Change this!
            session['admin'] = True
            return redirect(url_for('admin_panel'))
    return render_template('admin.html')

@app.route('/admin/panel')
def admin_panel():
    if not session.get('admin'):
        return redirect(url_for('admin'))
    return render_template('admin_panel.html')

@app.route('/admin/add-team', methods=['GET', 'POST'])
def add_team():
    if not session.get('admin'):
        return redirect(url_for('admin'))
    if request.method == 'POST':
        name = request.form['name']
        team = Team(name=name)
        db.session.add(team)
        db.session.commit()
        return redirect(url_for('admin_panel'))
    return render_template('add_team.html')

@app.route('/admin/add-match', methods=['GET', 'POST'])
def add_match():
    if not session.get('admin'):
        return redirect(url_for('admin'))
    teams = Team.query.all()
    if request.method == 'POST':
        team1_id = int(request.form['team1'])
        team2_id = int(request.form['team2'])
        winner_id = int(request.form['winner'])

        team1 = Team.query.get(team1_id)
        team2 = Team.query.get(team2_id)

        winner = 1 if winner_id == team1_id else 2
        new_elo1, new_elo2 = calculate_elo(team1.elo, team2.elo, winner)

        elo_change = abs(new_elo1 - team1.elo)

        team1.elo = new_elo1
        team2.elo = new_elo2

        match = Match(team1_id=team1_id, team2_id=team2_id,
                      winner_id=winner_id, elo_change=elo_change)
        db.session.add(match)
        db.session.commit()

        return redirect(url_for('admin_panel'))
    return render_template('add_match.html', teams=teams)



def expected_score(rating_a, rating_b):
    return 1 / (1 + 10 ** ((rating_b - rating_a) / 400))

def update_ratings(team_a, team_b, result, tournament):
    rating_a = ratings.get(team_a, 1000)
    rating_b = ratings.get(team_b, 1000)
    expected_a = expected_score(rating_a, rating_b)
    expected_b = expected_score(rating_b, rating_a)

    if result == "A":
        score_a, score_b = 1, 0
    elif result == "B":
        score_a, score_b = 0, 1
    else:
        score_a, score_b = 0.5, 0.5

    new_rating_a = rating_a + 32 * (score_a - expected_a)
    new_rating_b = rating_b + 32 * (score_b - expected_b)

    ratings[team_a] = new_rating_a
    ratings[team_b] = new_rating_b

    history.setdefault(team_a, []).append((team_b, result, round(new_rating_a, 2)))
    history.setdefault(team_b, []).append((team_a, result, round(new_rating_b, 2)))
    tournaments.setdefault(tournament, []).append((team_a, team_b, result))

@app.route("/")
def index():
    return render_template("index.html", ratings=ratings)

@app.route("/add_match", methods=["POST"])
def add_match():
    team_a = request.form["team_a"]
    team_b = request.form["team_b"]
    result = request.form["result"]
    tournament = request.form["tournament"]
    update_ratings(team_a, team_b, result, tournament)
    return redirect(url_for("index"))

@app.route("/history/<team>")
def team_history(team):
    return render_template("history.html", team=team, matches=history.get(team, []))

@app.route("/tournament/<name>")
def tournament_results(name):
    return render_template("tournaments.html", name=name, matches=tournaments.get(name, []))

@app.route("/plot")
def plot_ratings():
    plt.figure(figsize=(8, 4))
    teams = list(ratings.keys())
    values = [ratings[t] for t in teams]
    plt.bar(teams, values)
    plt.title("Elo Ratings")
    plt.ylabel("Rating")
    plt.xticks(rotation=45)
    plot_path = os.path.join("static", "ratings.png")
    plt.tight_layout()
    plt.savefig(plot_path)
    return render_template("plot.html", image="ratings.png")

if __name__ == "__main__":
    app.run(debug=True)
