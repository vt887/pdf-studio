FROM node:20-slim

WORKDIR /app

COPY apps/review-ui/package.json /app/package.json

RUN npm install --no-fund --no-audit

COPY apps/review-ui /app

EXPOSE 3000
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0", "--port", "3000"]
