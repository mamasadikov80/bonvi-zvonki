# ─────────────────────────────────────────────────────────────
#  BonviZvonki — Frontend (Vite + React + TypeScript)
#  node_modules konteyner ichida qoladi, host toza turadi.
# ─────────────────────────────────────────────────────────────
FROM node:22-alpine AS base
WORKDIR /app
ENV NODE_ENV=development

# ── Dev (hot reload) ─────────────────────────────────────────
FROM base AS dev
# ⚠️ `package-lock.json` ATAYLAB KO'CHIRILMAYDI.
#
# Lock fayl qaysi mashinada yaratilgan bo'lsa, o'sha platformaning
# ikkilik modullarini «tanlangan» deb belgilaydi. npm'da ma'lum
# nuqson bor (npm/cli#4828): boshqa platformada u kerakli
# `@rollup/rollup-linux-x64-musl` ni o'rnatmay ketadi va konteyner
# «Cannot find module» bilan yiqiladi. Mac'da yig'ilgan lock bilan
# Windows/x64 da aynan shunday bo'ldi.
#
# Faqat `package.json` ko'chiriladi — npm har platformada o'ziga
# keraklisini o'zi tanlaydi.
COPY package.json ./
RUN npm install --no-audit --no-fund
EXPOSE 5173
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0", "--port", "5173"]

# ── Build ────────────────────────────────────────────────────
FROM base AS build
# Sabab yuqorida — lock fayl platformaga bog'lab qo'yadi
COPY package.json ./
RUN npm install --no-audit --no-fund
COPY . .
RUN npm run build

# ── Prod (nginx) ─────────────────────────────────────────────
FROM nginx:alpine AS prod
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
