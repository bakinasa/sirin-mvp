.PHONY: up down logs build seed reset

up:
	docker compose up --build

down:
	docker compose down

logs:
	docker compose logs -f

build:
	docker compose build

reset:
	docker compose down -v
	docker compose up --build
