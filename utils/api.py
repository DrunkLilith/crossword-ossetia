"""Клиент API портала LingvoGameOs (ветка stas-sessions-game).

Протокол:
  POST {API}/account/login           {email, password}  -> {"userId": "..."}
  GET  {API}/game/session/{id}                          -> {"valid", "gameId", "userId", "userName", "totalUserPoints"}
  POST {API}/score                   {gameSessionId, score} -> {"userId", "newTotalPoints"}
  GET  {API}/users/{userId}/points                      -> {"points": N}

Адрес API берётся из переменной окружения LINGVO_API_URL
(иначе значение по умолчанию для локальной разработки).
"""

import os

import requests

API_URL = os.environ.get("LINGVO_API_URL", "http://localhost:5147/api")

# сколько секунд ждём ответа портала
TIMEOUT = 10


class ApiError(Exception):
    """Ошибка обращения к API портала (сеть/HTTP/формат ответа)."""


def login(email: str, password: str) -> str:
    """Войти в аккаунт портала; возвращает userId. Кладёт его в flask-сессию."""
    from flask import session

    if not (email and password):
        raise ApiError("Неправильные данные!")

    try:
        response = requests.post(
            f"{API_URL}/account/login",
            json={"email": email, "password": password},
            timeout=TIMEOUT,
        )
    except requests.RequestException as e:
        raise ApiError(f"Портал недоступен: {e}") from e

    if response.status_code == 401:
        raise ApiError("Неправильный логин или пароль")
    if response.status_code != 200:
        raise ApiError(f"Ошибка API ({response.status_code}): {response.text}")

    data = response.json()
    user_id = data.get("userId") if isinstance(data, dict) else None
    if not user_id:
        raise ApiError("Не получен ID пользователя")

    session["user_id"] = user_id
    session["game_session_id"] = None  # сброс: сессия игры выдаётся заново
    return user_id


def get_game_session_id() -> int | None:
    """ID игровой сессии, выданной порталом (?session=...), или None.
    Вместе с ним портал передаёт HMAC-подпись (?token=...)."""
    from flask import request, session

    raw = request.args.get("session") if request else None
    if raw is not None and raw.isdigit():
        session["game_session_id"] = int(raw)
        session["game_session_token"] = request.args.get("token")
    return session.get("game_session_id")


def get_game_session():
    """Данные игровой сессии портала или None, если сессии нет."""
    session_id = get_game_session_id()
    if not session_id:
        return None

    try:
        response = requests.get(
            f"{API_URL}/game/session/{session_id}", timeout=TIMEOUT
        )
    except requests.RequestException as e:
        raise ApiError(f"Портал недоступен: {e}") from e

    if response.status_code == 404:
        return None
    if response.status_code != 200:
        raise ApiError(f"Ошибка API ({response.status_code}): {response.text}")

    return response.json()


def add_points(amount: int) -> int:
    """Начислить баллы через игровую сессию портала.

    Возвращает новый общий счёт пользователя.
    Работает только при валидной игровой сессии (iframe портала).
    """
    from flask import session

    session_id = session.get("game_session_id")
    if not session_id:
        raise ApiError("Игра запущена не с портала: сессия не выдана.")

    if amount <= 0:
        raise ApiError("Количество баллов должно быть положительным")

    try:
        response = requests.post(
            f"{API_URL}/score",
            json={
                "gameSessionId": session_id,
                "score": amount,
                "token": session.get("game_session_token"),
            },
            timeout=TIMEOUT,
        )
    except requests.RequestException as e:
        raise ApiError(f"Портал недоступен: {e}") from e

    if response.status_code != 200:
        raise ApiError(f"Ошибка API ({response.status_code}): {response.text}")

    points = response.json().get("newTotalPoints")
    if points is None:
        raise ApiError("Некорректный ответ API")
    return points


def get_points() -> int:
    """Текущий общий счёт пользователя портала."""
    from flask import session

    user_id = session.get("user_id")
    if not user_id:
        raise ApiError("Пользователь не авторизован.")

    try:
        response = requests.get(
            f"{API_URL}/users/{user_id}/points", timeout=TIMEOUT
        )
    except requests.RequestException as e:
        raise ApiError(f"Портал недоступен: {e}") from e

    if response.status_code != 200:
        raise ApiError(f"Ошибка API ({response.status_code}): {response.text}")

    data = response.json()
    if isinstance(data, dict):
        return data.get("points", 0)
    return data
