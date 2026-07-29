# syntax=docker/dockerfile:1

FROM node:20-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

FROM node:20-alpine AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .

ARG NEXT_PUBLIC_API_URL=http://127.0.0.1:8001
ARG NEXT_PUBLIC_API_KEY=visionops-dev-key
ARG NEXT_PUBLIC_WS_URL=ws://127.0.0.1:8001/api/v1/ws/detections
ARG NEXT_PUBLIC_HLS_URL=http://127.0.0.1:8888/cam1/index.m3u8
ARG NEXT_PUBLIC_WHEP_URL=/api/mediamtx/whep?path=cam1

ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL
ENV NEXT_PUBLIC_API_KEY=$NEXT_PUBLIC_API_KEY
ENV NEXT_PUBLIC_WS_URL=$NEXT_PUBLIC_WS_URL
ENV NEXT_PUBLIC_HLS_URL=$NEXT_PUBLIC_HLS_URL
ENV NEXT_PUBLIC_WHEP_URL=$NEXT_PUBLIC_WHEP_URL
ENV NEXT_TELEMETRY_DISABLED=1

RUN npm run build

FROM node:20-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1
ENV PORT=3000
ENV HOSTNAME=0.0.0.0

# Server-side MediaMTX proxy target (browser still uses same-origin /api/mediamtx/whep)
ENV MEDIAMTX_WEBRTC_BASE=http://mediamtx:8889

RUN addgroup -S nodejs && adduser -S nextjs -G nodejs
COPY --from=builder /app/public ./public
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static

USER nextjs
EXPOSE 3000
CMD ["node", "server.js"]
