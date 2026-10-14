"""Клиент API портала LingvoGameOs (ветка stas-sessions-game).

Протокол:
  POST {API}/game/session/resolve   {gameSessionId, token} -> {"valid", "gameId", "userId", "userName", "totalUserPoints"}
  POST {API}/score                   {gameSessionId, score, token} -> {"userId", "newTotalPoints"}

Адрес API берётся из переменной окружения LINGVO_API_URL
(иначе значение по умолчанию для локальной разработки).
"""

import os

import requests

API_URL = os.environ.get("LINGVO_API_URL", "http://game.рудзынг.рф/api")

# сколько секунд ждём ответа портала
TIMEOUT = 10


class ApiError(Exception):
    """Ошибка обращения к API портала (сеть/HTTP/формат ответа)."""


def get_game_session_id() -> int | None:
    """Читает ID новой сессии из query либо возвращает подтверждённый ID."""
    from flask import request, session

    raw = request.args.get("session") if request else None
    if raw is not None:
        if not raw.isdigit() or int(raw) <= 0:
            raise ApiError("Портал передал некорректный ID игровой сессии.")
        return int(raw)
    return session.get("game_session_id")


def get_game_session():
    """Проверяет подпись и сохраняет пользователя, выданного порталом."""
    from flask import request, session

    session_id = get_game_session_id()
    if not session_id:
        return None
    token = (
        request.args.get("token")
        if request.args.get("session") is not None
        else session.get("game_session_token")
    )

    try:
        response = requests.post(
            f"{API_URL}/game/session/resolve",
            json={
                "gameSessionId": session_id,
                "token": token,
            },
            timeout=TIMEOUT,
        )
    except requests.RequestException as e:
        raise ApiError(f"Портал недоступен: {e}") from e

    if response.status_code == 401:
        raise ApiError("Портал отклонил подпись игровой сессии.")
    if response.status_code == 404:
        raise ApiError("Игровая сессия не найдена.")
    if response.status_code != 200:
        raise ApiError(f"Ошибка API ({response.status_code}): {response.text}")

    data = response.json()
    if not isinstance(data, dict) or not data.get("valid") or not data.get("userId"):
        raise ApiError("Некорректный ответ API игровой сессии.")
    expected_game_id = os.environ.get("LINGVO_GAME_ID")
    if not expected_game_id or not expected_game_id.isdigit():
        raise ApiError("LINGVO_GAME_ID не настроен для этой игры.")
    if str(data.get("gameId")) != expected_game_id:
        raise ApiError("Игровая сессия выдана для другой игры.")

    session["game_session_id"] = session_id
    session["game_session_token"] = token
    session["portal_user_id"] = data["userId"]
    session["portal_user_name"] = data.get("userName") or "Игрок"
    session["portal_total_points"] = data.get("totalUserPoints", 0)
    return data


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
    session["portal_total_points"] = points
    return points
