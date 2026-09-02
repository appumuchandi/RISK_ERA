FROM node:22-alpine AS build

WORKDIR /app

# Copy package files
COPY package.json package-lock.json ./

# Install dependencies (production only for serving, all for build)
RUN npm ci

# Copy source code
COPY . .

# Build React/Vite application
RUN npm run build

# ---- Production stage ----
FROM nginx:alpine

# Copy built artifacts from build stage
COPY --from=build /app/dist /usr/share/nginx/html

# Copy nginx config if needed (default serves static files)
EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]