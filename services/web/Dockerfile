# ─────────────────────────────────────────────────────────────
#  ZvonkiDashboard — Frontend (Vite + React + TypeScript)
#  node_modules konteyner ichida qoladi, host toza turadi.
# ─────────────────────────────────────────────────────────────
FROM node:22-alpine AS base
WORKDIR /app
ENV NODE_ENV=development

# ── Dev (hot reload) ─────────────────────────────────────────
FROM base AS dev
COPY package.json package-lock.json* ./
RUN npm install
EXPOSE 5173
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0", "--port", "5173"]

# ── Build ────────────────────────────────────────────────────
FROM base AS build
COPY package.json package-lock.json* ./
RUN npm ci || npm install
COPY . .
RUN npm run build

# ── Prod (nginx) ─────────────────────────────────────────────
FROM nginx:alpine AS prod
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
