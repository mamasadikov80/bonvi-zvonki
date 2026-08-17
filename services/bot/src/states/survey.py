"""So'rovnoma bosqichlari (FSM).

Oqim:  guruhda tugma  →  shaxsiy chat  →  3 ta savol  →  rahmat
"""

from aiogram.fsm.state import State, StatesGroup


class SurveyFlow(StatesGroup):
    csat = State()  # 1-savol: 1–5 yulduz
    resolution = State()  # 2-savol: muammo hal bo'ldimi
    comment = State()  # 3-savol: izoh (ixtiyoriy)
