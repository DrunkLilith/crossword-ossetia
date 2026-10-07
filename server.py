import os

from flask import Flask, render_template, redirect, request, session
from data import db_session
from data.categories import Category
from data.crosswords import Crosswords
from data.words import Words
from forms.user import LoginForm

from utils import api


def main():
    app = Flask(__name__)
    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "yandexlyceum_secret_key")

    db_session.global_init("db/crosswords.db")

    return app


PORTAL_REGISTER_URL = os.environ.get(
    "PORTAL_URL", "http://localhost:5086"
) + "/Account/Register"


def _load_portal_user():
    """Подтягивает имя пользователя портала из игровой сессии (клик по иконке профиля)."""
    if session.get("user_name"):
        return
    game_session_id = session.get("game_session_id")
    if not game_session_id:
        return
    try:
        data = api.get_game_session()
    except api.ApiError:
        return
    if data and data.get("valid"):
        session["user_id"] = data.get("userId")
        session["user_name"] = data.get("userName") or "Игрок"


app = main()


@app.route("/")
def index():
    session["cur_cross"] = 1
    session["guessed"] = list()
    # игровая сессия портала: iframe передаёт ?session=<id>
    session["game_session_id"] = None
    api.get_game_session_id()
    _load_portal_user()
    db_sess = db_session.create_session()
    cats = db_sess.query(Category)
    return render_template(
        "index.html", cats=cats, portal_register_url=PORTAL_REGISTER_URL
    )


@app.route("/start")
def start():
    # точка входа из iframe портала: /start?session=<id>
    return index()


@app.route("/crosswords", methods=["POST", "GET"])
def chose_cross():
    session["guessed"] = []
    cat_id = request.form.get("cat")
    db_sess = db_session.create_session()
    crossds = db_sess.query(Crosswords).filter(Crosswords.id_category == cat_id)
    return render_template("chose_cross.html", crossds=crossds)


@app.route("/crosswords/<int:id>")
def crossword(id):
    session["cur_cross"] = id
    matrix = [[""] * 10 for i in range(10)]
    db_sess = db_session.create_session()
    words = db_sess.query(Words).filter(Words.id_cross == id)
    descr = list(map(lambda x: x.description, words))
    ans = db_sess.query(Crosswords).filter(Crosswords.id == id).first()

    for ind, cross in enumerate(words):
        word = cross.word_iron.split()
        x, y = map(int, cross.coords.split())
        place = int(cross.place)
        f = False
        guessed = session.get("guessed") or []
        if word in guessed:
            f = True
        for i in range(len(word)):
            cell = word[i]
            if f:
                cell = cell.lower()
            if i == 0:
                matrix[y][x - 1] = (str(ind + 1), cross.id, "num")
            if i == place:
                matrix[y][x + i] = (cell, "bold_td")
            else:
                matrix[y][x + i] = (cell, "td")

    return render_template(
        "crossword.html", cross=matrix, descr=descr, ans=ans.word_ans_rus
    )


@app.route("/add_word<int:id>")
def ans(id):
    db_sess = db_session.create_session()
    print(session.get("cur_cross"))
    ans = (
        db_sess.query(Words)
        .filter(Words.id_cross == int(session.get("cur_cross")), Words.id == id)
        .first()
    )
    return render_template("check.html", ans=ans)


@app.route(f"/check/<int:id>", methods=["POST", "GET"])
def check(id):
    cur_cross = session.get("cur_cross")
    res = request.form.get(str(id)).upper().replace("АЕ", "Æ")
    word = request.form.get("word").split()
    if res == "".join(word):
        guessed = session.get("guessed")
        guessed.append(word)
        session["guessed"] = guessed
    return redirect(f"/crosswords/{cur_cross}")


@app.route(f"/final_check", methods=["POST"])
def final_check():
    cur_cross = session.get("cur_cross")
    quest = request.form.get("quest").upper()
    ans = request.form.get("ans")

    if quest == ans:
        # начисление баллов через игровую сессию портала
        try:
            api.add_points(5)
        except api.ApiError as e:
            print(f"Не удалось начислить баллы: {e}")

        return redirect("/victory")
    return redirect(f"/crosswords/{cur_cross}")


@app.route("/victory")
def victory():
    return render_template("victory.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        # вход через API портала (сессии, ветка stas-sessions-game)
        try:
            api.login(form.email.data, form.password.data)
            return redirect("/")
        except api.ApiError as e:
            return render_template("login.html", message=e, form=form)

    return render_template("login.html", title="Авторизация", form=form)


@app.route("/logout")
def logout():
    session.pop("user_id", None)
    session.pop("user_name", None)
    session.pop("game_session_id", None)
    return redirect("/")


@app.route("/register", methods=["GET", "POST"])
def register():
    # регистрация выполняется на портале
    return redirect(PORTAL_REGISTER_URL)


if __name__ == "__main__":
    app.run()
