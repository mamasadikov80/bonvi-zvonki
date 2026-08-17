# Yordamchi skriptlar

Ikkalasi ham backend konteyneri ichida ishlaydi va MoyZvonki'ga
**faqat o'qish** so'rovi yuboradi (`calls.list`).

## `backfill_calls.py` — eski qo'ng'iroqlarni yuklash

```bash
docker compose cp tools/backfill_calls.py backend:/tmp/
docker compose exec -T backend python /tmp/backfill_calls.py 30
```

Oraliqni 2 kunlik bo'laklarga bo'lib tortadi.

⚠️ **Nega HTTP orqali emas.** Backend `--reload` rejimida ishlaydi va
har fayl tahririda qayta yuklanib, ketayotgan uzoq so'rovni
**o'ldiradi**. Bu skript mustaqil jarayon, shuning uchun unga ta'sir
qilmaydi. Ishlab chiqarish muhitida `POST /calls/sync` ham yetadi.

## `verify_activity.py` — mustaqil tekshiruv

```bash
TOK=$(curl -s -X POST localhost:8010/api/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"admin@zvonki.uz","password":"..."}' \
  | python3 -c 'import sys,json; print(json.load(sys.stdin)["access_token"])')

docker compose cp tools/verify_activity.py backend:/tmp/
docker compose exec -T -e ZV_TOKEN="$TOK" backend python /tmp/verify_activity.py 3
```

Uch manbani solishtiradi:

| | Manba |
|---|---|
| **A** | MoyZvonki'dan to'g'ridan-to'g'ri o'qish |
| **B** | shu ma'lumotdan **mustaqil** hisoblangan ko'rsatkichlar — tizim kodiga umuman tegmaydi, bu yerda o'z mantiqi yozilgan |
| **C** | tizimning `/analytics/activity` javobi |

Nima uchun kerak: **B va C farq qilsa, bittasi xato.** Shu usul bilan
sakkizta haqiqiy xato topildi, ular orasida kompaniya jamisining
mijozni ikki marta sanashi ham bor (+28%, xushomad qiladigan tomonga:
77.9% ko'rsatilardi, haqiqiysi 73.8%).

Bo'lim E — mantiqiy tenglikliklar (20 ta): yig'indilar mos keladimi,
foizlar to'g'ri bo'linuvchidan olinganmi, grafik ustunlari soni
davrga tengmi.

### Kutilgan farq

Bo'lim C dagi «bazada YO'Q» soni nolga teng bo'lmasligi **normal**:
MoyZvonki'dagi ba'zi hisoblar (HR va boshqa kompaniya) bizning
xodimlar ro'yxatiga bog'lanmagan va ular hisobotga kirmaydi.

Bo'lim D dagi hajm farqlari **aynan shu songa teng bo'lishi kerak**
(kiruvchi farqi + chiquvchi farqi = bazada yo'q soni). Teng bo'lmasa —
hisoblashda xato bor va uni izlash kerak.

### Oynalar mos bo'lishi shart

Skript oynani tizim bilan bir xil — mahalliy (Asia/Tashkent) butun
kunlarga tekislab oladi. Aks holda farqlar **oyna mos kelmaganidan**
chiqadi va ular ma'lumot xatosi deb o'qilardi.
