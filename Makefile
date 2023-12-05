COMPOSE ?= $(shell command -v podman-compose 2> /dev/null || echo docker-compose)
CONTAINER_ENGINE ?= $(shell command -v podman 2> /dev/null || echo docker)
TEST_IMAGE_NAME=log-detective-website_test-backend
FEEDBACK_DIR=/persistent/results
PYTHONPATH=/opt/log-detective-website/backend


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
		-e ENV="devel" \
		-v .:/opt/log-detective-website:z \
		$(TEST_IMAGE_NAME) \
		bash -c "pytest -vvv /opt/log-detective-website/backend/tests/" \
