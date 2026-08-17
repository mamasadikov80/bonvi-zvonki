"""MUSTAQIL TEKSHIRUV: MoyZvonki → o'z hisobim → tizim hisoboti.

Uch manba solishtiriladi:
  A. MoyZvonki `calls.list` (to'g'ridan-to'g'ri, faqat O'QISH)
  B. shu ma'lumotdan MUSTAQIL hisoblangan ko'rsatkichlar (bu skript)
  C. tizimning `/analytics/activity` javobi

A→B tizim kodiga UMUMAN tegmaydi: bu yerda o'z mantiqim yozilgan.
Agar B va C farq qilsa — bittasi xato va shuni topish kerak.
"""
import asyncio
import os
import sys
from collections import Counter, defaultdict
from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy import func, select

from src.core.database import SessionFactory
from src.modules.calls.infrastructure.models import CallModel
from src.modules.moizvonki.application.factory import moizvonki_client

DAYS = int(sys.argv[1]) if len(sys.argv) > 1 else 3
WINDOW_H = 24
API = "http://localhost:8000/api/v1"
TRANS = str.maketrans("", "", " ()-+")


def tail(num: str | None) -> str:
    d = (num or "").translate(TRANS)
    return d[-9:] if len(d) >= 9 else ""


def band(text: str) -> None:
    print("\n" + "═" * 62)
    print(" " + text)
    print("═" * 62)


async def moyzvonki_dan(since, until):
    rows = []
    async with SessionFactory() as session, moizvonki_client(session) as client:
        async for _n, page in client.iter_calls(since=since, until=until, supervised=True):
            rows.extend(page.calls)
    return rows


def mustaqil_hisob(calls, since, until):
    """MoyZvonki ma'lumotidan O'ZIM hisoblayman — tizim kodisiz."""
    ichida = [c for c in calls if since <= c.start_time <= until]
    kir = [c for c in ichida if not c.is_outbound]
    chiq = [c for c in ichida if c.is_outbound]
    missed = [c for c in kir if c.answered is False]

    # Mijoz darajasi: oxirgi javobsiz urinish
    oxirgi = {}
    for c in missed:
        t = tail(c.client_number)
        if not t:
            continue
        if t not in oxirgi or c.start_time > oxirgi[t]:
            oxirgi[t] = c.start_time

    aloqa = defaultdict(list)
    for c in ichida:
        t = tail(c.client_number)
        if t and (c.is_outbound or c.answered is True):
            aloqa[t].append(c.start_time)

    W = timedelta(hours=WINDOW_H)
    bogland = sum(
        1 for t, t0 in oxirgi.items()
        if any(t0 < a <= t0 + W for a in aloqa.get(t, []))
    )
    return {
        "jami": len(ichida),
        "kiruvchi": len(kir),
        "kiruvchi_javob": sum(1 for c in kir if c.answered is True),
        "chiquvchi": len(chiq),
        "chiquvchi_javob": sum(1 for c in chiq if c.answered is True),
        "chiquvchi_kotarilmagan": sum(1 for c in chiq if c.answered is False),
        "javobsiz": len(missed),
        "mijoz": len(oxirgi),
        "mijoz_boglangan": bogland,
        "mijoz_boglanmagan": len(oxirgi) - bogland,
    }


async def bazadan(since, until):
    async with SessionFactory() as s:
        rows = (await s.execute(
            select(CallModel.external_id, CallModel.direction, CallModel.answered,
                   CallModel.client_phone, CallModel.started_at, CallModel.duration_sec)
            .where(CallModel.started_at >= since, CallModel.started_at <= until)
        )).all()
    return rows


async def tizimdan(days, token):
    async with httpx.AsyncClient(timeout=60) as c:
        r = await c.get(f"{API}/analytics/activity", params={"days": days},
                        headers={"Authorization": f"Bearer {token}"})
        r.raise_for_status()
        return r.json()


async def main() -> None:
    # ⚠️ OYNA TIZIM BILAN BIR XIL bo'lishi shart. Tizim mahalliy butun
    # kunlarga tekislaydi; bu skript aylanuvchi UTC oynasini olsa,
    # farqlar OYNA MOS KELMAGANIDAN chiqadi va ular ma'lumot xatosi
    # deb o'qilardi.
    from zoneinfo import ZoneInfo

    until = datetime.now(UTC)
    mahalliy = until.astimezone(ZoneInfo("Asia/Tashkent"))
    kun_boshi = mahalliy.replace(hour=0, minute=0, second=0, microsecond=0)
    since = (kun_boshi - timedelta(days=DAYS - 1)).astimezone(UTC)
    print(f"Davr: {since:%d.%m %H:%M} → {until:%d.%m %H:%M}  ({DAYS} kun)")

    band("A. MoyZvonki'dan to'g'ridan-to'g'ri o'qish")
    mz = await moyzvonki_dan(since, until)
    print(f"  olingan qo'ng'iroq: {len(mz)}")

    band("B. MUSTAQIL hisob (tizim kodiga tegmasdan)")
    b = mustaqil_hisob(mz, since, until)
    for k, v in b.items():
        print(f"  {k:24} {v:6}")

    band("C. Ma'lumot BAZAGA to'g'ri yozilganmi")
    db = await bazadan(since, until)
    mz_ids = {c.db_call_id for c in mz if since <= c.start_time <= until}
    db_ids = {r.external_id for r in db}
    yoq = mz_ids - db_ids
    ortiq = db_ids - mz_ids
    print(f"  MoyZvonki'da: {len(mz_ids)}   bazada: {len(db_ids)}")
    print(f"  bazada YO'Q  : {len(yoq)}")
    print(f"  bazada ORTIQ : {len(ortiq)}")

    # Maydonlar bir xilmi
    mz_map = {c.db_call_id: c for c in mz}
    xato = Counter()
    for r in db:
        c = mz_map.get(r.external_id)
        if c is None:
            continue
        if (r.direction.value == "outbound") != c.is_outbound:
            xato["yo'nalish"] += 1
        if r.answered != c.answered:
            xato["answered"] += 1
        if tail(r.client_phone) != tail(c.client_number):
            xato["raqam"] += 1
        if r.duration_sec != c.duration_sec:
            xato["davomiylik"] += 1
    xulosa = dict(xato) if xato else "YO'Q - hammasi mos"
    print(f"  maydon farqlari: {xulosa}")

    band("D. TIZIM hisoboti vs MUSTAQIL hisob")
    token = os.environ.get("ZV_TOKEN", "")
    if not token:
        print("  (token berilmadi — o'tkazib yuborildi)")
        return
    sys_ = await tizimdan(DAYS, token)
    t = sys_["total"]
    juftlar = [
        ("kiruvchi", b["kiruvchi"], t["inbound_total"]),
        ("kiruvchi_javob", b["kiruvchi_javob"], t["inbound_answered"]),
        ("chiquvchi", b["chiquvchi"], t["outbound_total"]),
        ("chiquvchi_javob", b["chiquvchi_javob"], t["outbound_answered"]),
        ("chiquvchi_kotarilmagan", b["chiquvchi_kotarilmagan"], t["outbound_no_answer"]),
        ("javobsiz", b["javobsiz"], t["missed"]),
        ("mijoz", b["mijoz"], t["missed_clients"]),
        ("mijoz_boglangan", b["mijoz_boglangan"], t["clients_reached"]),
        ("mijoz_boglanmagan", b["mijoz_boglanmagan"], t["clients_unreached"]),
    ]
    hammasi_ok = True
    for nom, mustaqil, tizim in juftlar:
        farq = tizim - mustaqil
        belgi = "OK " if farq == 0 else "FARQ"
        if farq:
            hammasi_ok = False
        print(f"  {belgi} {nom:24} mustaqil={mustaqil:6}  tizim={tizim:6}  farq={farq:+d}")

    band("E. FOIZLAR mantiqan to'g'rimi")
    tekshir = [
        ("kiruvchi = javob + javobsiz + noma'lum",
         t["inbound_total"] == t["inbound_answered"] + t["missed"] + t["unknown_in"]),
        ("chiquvchi = javob + ko'tarilmagan + noma'lum",
         t["outbound_total"]
         == t["outbound_answered"] + t["outbound_no_answer"] + t["unknown_out"]),
        # ⚠️ `inbound_total`, `inbound_known` EMAS: soatlik razrez endi
        # kunlik bilan bir xil shaklda va NOMA'LUM qatorlarni ham hajmga
        # qo'shadi (foiz esa faqat bilinganlardan hisoblanadi)
        ("soatlik yig'indi = jami kiruvchi",
         sum(h["inbound"] for h in sys_["hours_series"]) == t["inbound_total"]),
        ("soatlik chiquvchi = jami chiquvchi",
         sum(h["outbound"] for h in sys_["hours_series"]) == t["outbound_total"]),
        ("soatlik ko'tarilmagan = jami",
         sum(h["outbound_no_answer"] for h in sys_["hours_series"])
         == t["outbound_no_answer"]),
        ("kunlik ko'tarilmagan = jami",
         sum(d["outbound_no_answer"] for d in sys_["days_series"])
         == t["outbound_no_answer"]),
        ("soatlik javobsiz = jami javobsiz",
         sum(h["missed"] for h in sys_["hours_series"]) == t["missed"]),
        ("grafik ustuni = so'ralgan kun",
         len(sys_["days_series"]) == sys_["days"]),
        ("ochiq javobsiz <= murojaat mumkin bo'lganlar",
         t["missed_open"] <= t["missed_addressable"]),
        ("chiquvchi >= javob + ko'tarilmagan",
         t["outbound_total"] >= t["outbound_answered"] + t["outbound_no_answer"]),
        ("javobsiz foizi = javobsiz / bilingan",
         t["missed_rate"] is None or
         abs(t["missed_rate"] - round(t["missed"] / max(t["inbound_known"], 1) * 100, 1)) < 0.15),
        ("qaytish foizi = bog'langan / mijoz",
         t["callback_rate"] is None or
         abs(t["callback_rate"] - round(t["clients_reached"] / max(t["missed_clients"], 1) * 100, 1)) < 0.15),
        ("bog'lanmagan = mijoz - bog'langan",
         t["clients_unreached"] == t["missed_clients"] - t["clients_reached"]),
        ("mijoz <= javobsiz (takroriy urinishlar)",
         t["missed_clients"] <= t["missed"]),
        ("bog'langan <= mijoz",
         t["clients_reached"] <= t["missed_clients"]),
        ("xodimlar yig'indisi = jami (kiruvchi)",
         sum(a["inbound_total"] for a in sys_["agents"]) == t["inbound_total"]),
        ("xodimlar yig'indisi = jami (javobsiz)",
         sum(a["missed"] for a in sys_["agents"]) == t["missed"]),
        # ⚠️ Bu tenglik ATAYLAB BUZILGAN: bitta mijoz ikki xodimga
        # qo'ng'iroq qilsa, xodim kesimida ikki qator (javobgarlik
        # alohida), kompaniya darajasida esa bitta odam. Shuning uchun
        # yig'indi jamidan KATTA yoki teng bo'lishi kerak.
        ("xodimlar yig'indisi >= jami (mijoz)",
         sum(a["missed_clients"] for a in sys_["agents"]) >= t["missed_clients"]),
        ("grafik yig'indisi = jami (kiruvchi)",
         sum(d["inbound"] for d in sys_["days_series"]) == t["inbound_total"]),
        ("grafik yig'indisi = jami (javobsiz)",
         sum(d["missed"] for d in sys_["days_series"]) == t["missed"]),
    ]
    for nom, natija in tekshir:
        if natija is None:
            print(f"  --   {nom}")
            continue
        if not natija:
            hammasi_ok = False
        print(f"  {'OK ' if natija else 'XATO'} {nom}")

    band("XULOSA: " + ("HAMMASI MOS" if hammasi_ok else "FARQ TOPILDI — tuzatish kerak"))

asyncio.run(main())
