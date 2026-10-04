"""Контракт analyze(), на который опираются сайт и бот: уровни, порядок признаков, первый совет."""
import pytest

from analyzer import MAX_LEN, analyze


def expected_level(score: int) -> str:
    if score >= 75:
        return "critical"
    if score >= 50:
        return "high"
    if score >= 20:
        return "medium"
    return "low"


@pytest.mark.parametrize(
    "text, level",
    [
        ("Привет, как дела?", "low"),
        ("Напишите мне в телеграм", "low"),
        ("Ваш аккаунт заблокирован", "medium"),
        ("Вы выиграли приз", "high"),
        ("Срочно переведи 5000 на карту", "high"),
        ("Срочно! Ваш аккаунт заблокирован, перейдите http://sberbank-secure.xyz/login", "critical"),
        (
            "Ваша карта заблокирована. Переведите деньги на безопасный счёт. "
            "Продиктуйте код из СМС. Это служба безопасности банка.",
            "critical",
        ),
    ],
)
def test_level_follows_score_thresholds(text, level):
    result = analyze(text)
    assert result["level"] == level
    assert result["level"] == expected_level(result["score"])


def test_score_exactly_50_is_high():
    result = analyze("Вы выиграли приз")
    assert result["score"] == 50
    assert result["level"] == "high"


def test_signs_sorted_by_score_descending():
    result = analyze(
        "Мама, это я, новый номер. Срочно переведи 5000 на карту, никому не говори. "
        "Продиктуй код из СМС"
    )
    scores = [s["score"] for s in result["signs"]]
    assert len(scores) >= 3
    assert scores == sorted(scores, reverse=True)


def test_first_recommendation_is_strongest_sign_advice():
    result = analyze("Уважаемый клиент, ваш аккаунт будет заблокирован")
    strongest = result["signs"][0]
    assert strongest["score"] >= 10
    assert result["recommendations"][0] == strongest["advice"]


def test_neutral_link_scores_5_and_gives_no_sign_advice():
    result = analyze("Посмотри https://example.com")
    assert result["level"] == "low"
    [link] = result["signs"]
    assert (link["id"], link["title"], link["score"]) == ("link", "В сообщении есть ссылка", 5)
    assert link["advice"] not in result["recommendations"]


def test_text_beyond_max_len_is_ignored():
    result = analyze("а" * MAX_LEN + " Срочно переведи 5000 на карту")
    assert result["length"] == MAX_LEN
    assert result["signs"] == []
    assert result["level"] == "low"


@pytest.mark.parametrize("text", ["", None])
def test_empty_input_is_low_risk(text):
    result = analyze(text)
    assert (result["score"], result["level"], result["signs"]) == (0, "low", [])
