from flask import Flask, render_template, request, redirect, url_for
import matplotlib.pyplot as plt
import os

app = Flask(__name__)

ratings = {}
history = {}
tournaments = {}

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
