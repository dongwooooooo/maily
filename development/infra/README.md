# Maily Infra

인프라 영역이다. 현재는 로컬 개발용 PostgreSQL/Redis compose 기준만 둔다.

## 로컬 데이터 서비스

```bash
docker compose -f development/infra/docker/docker-compose.yml up -d
```

## 스택

- Docker Engine 29.x 기준
- PostgreSQL 18.4
- Redis 8.8

## 이후 다룰 책임

- 환경 변수와 시크릿
- OAuth redirect 환경
- worker/scheduler 실행 환경
- 데이터베이스와 migration
- 배포 파이프라인
- 로그와 모니터링
