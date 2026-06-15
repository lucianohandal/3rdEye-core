.PHONY: test db-test coverage coverage-html

PYTHON ?= .venv/bin/python
TEST_CMD = -m unittest discover -s tests -p '*.py' -t . -v

test:
	$(PYTHON) $(TEST_CMD)

db-test:
	@$(PYTHON) -c "from configs import get_config; raise SystemExit(0 if get_config(environment='test').database.url else 1)" || (echo "Set TEST_DATABASE_URL or database.url in configs.testing.yaml before running DB integration tests" && exit 1)
	$(PYTHON) $(TEST_CMD)

coverage:
	$(PYTHON) -m coverage run $(TEST_CMD)
	$(PYTHON) -m coverage report -m

coverage-html:
	$(PYTHON) -m coverage run $(TEST_CMD)
	$(PYTHON) -m coverage html
	$(PYTHON) -m coverage report -m
