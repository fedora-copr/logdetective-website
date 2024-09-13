COMPOSE ?= $(shell command -v podman-compose 2> /dev/null || echo docker-compose)
CONTAINER_ENGINE ?= $(shell command -v podman 2> /dev/null || echo docker)
TEST_IMAGE_NAME=logdetective-website_test-backend
FEEDBACK_DIR=/persistent/results
REVIEWS_DIR=/persistent/reviews
PYTHONPATH=/opt/logdetective-website/backend


build-prod:
	$(COMPOSE) -f docker-compose.prod.yaml build --no-cache

up-prod:
	$(COMPOSE) -f docker-compose.prod.yaml up

# don't forget to log in to quay.io
push-prod:
	$(COMPOSE) -f docker-compose.prod.yaml push


# take care of the pre-requisites by yourself
test-backend-local:
	PYTHONPATH=./backend pytest -vvv backend/tests/


test-backend-in-container:
	$(CONTAINER_ENGINE) build --rm --tag $(TEST_IMAGE_NAME) \
		-f docker/backend/Dockerfile \
		-f docker/backend/Dockerfile.tests
	$(CONTAINER_ENGINE) run -t -i \
		-e PYTHONPATH="$(PYTHONPATH)" \
		-e FEEDBACK_DIR="$(FEEDBACK_DIR)" \
		-e REVIEWS_DIR="$(REVIEWS_DIR)" \
		-e ENV="devel" \
		-v .:/opt/logdetective-website:z \
		$(TEST_IMAGE_NAME) \
		bash -c "pytest -vvv /opt/logdetective-website/backend/tests/" \
