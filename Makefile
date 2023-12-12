build-prod:
	docker-compose -f docker-compose.prod.yaml build --no-cache

# don't forget to log in to quay.io
push-prod:
	docker-compose -f docker-compose.prod.yaml push
