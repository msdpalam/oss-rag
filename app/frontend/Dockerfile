FROM node:20-alpine AS base
WORKDIR /app
COPY package.json ./
RUN npm install

# ── Development target ────────────────────────────────────────────────────────
FROM base AS development
ENV NODE_ENV=development
COPY . .
EXPOSE 3000
CMD ["npm", "run", "dev"]

# ── Production build ──────────────────────────────────────────────────────────
FROM base AS builder
ENV NODE_ENV=production
ARG VITE_API_URL=http://localhost:8000
ARG VITE_APP_TITLE="OSS RAG Chat"
ENV VITE_API_URL=$VITE_API_URL
ENV VITE_APP_TITLE=$VITE_APP_TITLE
COPY . .
RUN npm run build

# ── Production runtime (nginx) ────────────────────────────────────────────────
FROM nginx:alpine AS production
COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
